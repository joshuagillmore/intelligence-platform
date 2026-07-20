"""Enrichment orchestrator.

``EnrichmentService.enrich_entity`` is the analyst "Investigate" action: for one
observable node it runs every eligible provider (respecting the cache and rate
limiter), merges the returned properties onto the node, upserts any discovered
related nodes/edges, and records the raw payload. ``auto_enrich`` is the
selective, fire-and-forget pass run when a cyber node is first created — it runs
only providers flagged ``auto``.

Providers are isolated: neither a provider's lookup nor the graph write it
triggers can fail the rest of the investigation. External calls happen inside
the providers (through ``ProxiedClient``), so this orchestrator stays
transport-agnostic.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from datetime import datetime, timezone

from intel_platform.enrichment.base import (
    EnrichmentResult,
    RelatedEntity,
    get_providers_for,
)
from intel_platform.enrichment.cache import RateLimiter
from intel_platform.enrichment.observables import refang

logger = logging.getLogger(__name__)

# Node-identity keys a provider must never overwrite via SET n += $props — a
# rogue/buggy Phase-3 provider returning these could move a node between
# projects or change its type/name. Stripped before every merge.
_PROTECTED_KEYS = frozenset({
    "id", "name", "project_id", "entity_type", "entity_category",
    "created_at", "source_doc_id",
})


def _result_to_cache(result: EnrichmentResult) -> dict:
    """Serialize a full result so a cache hit can rebuild AND reapply it."""
    return {
        "properties": result.properties,
        "related": [asdict(r) for r in result.related],
        "source_url": result.source_url,
        "raw": result.raw,
    }


def _result_from_cache(cached: dict) -> EnrichmentResult:
    """Rebuild an EnrichmentResult from a cached payload (tolerant of shape)."""
    try:
        related = [RelatedEntity(**r) for r in (cached.get("related") or [])]
    except Exception:
        related = []
    return EnrichmentResult(
        properties=cached.get("properties") or {},
        related=related,
        source_url=cached.get("source_url", "") or "",
        raw=cached.get("raw") or {},
    )


class EnrichmentService:
    def __init__(self, store, *, write_related=None, cache=None, limiter=None,
                 available_keys: frozenset[str] | set[str] = frozenset()):
        self.store = store
        self.cache = cache
        self.limiter = limiter or RateLimiter()
        self.available_keys = available_keys
        # None -> use the built-in graph writer; injectable for tests.
        self._write_related_fn = write_related

    async def enrich_entity(self, entity_id: str, *, only: set[str] | None = None,
                            bypass_cache: bool = False) -> dict:
        """Run eligible providers for an entity (the Investigate action).

        ``only`` restricts to named providers (the per-source refresh button);
        ``bypass_cache`` forces a fresh lookup.
        """
        entity = self.store.get_entity(entity_id)
        if not entity:
            return {"entity_id": entity_id, "error": "not found", "providers": {}}
        providers = get_providers_for(entity.get("entity_type", ""), self.available_keys)
        if only is not None:
            providers = [p for p in providers if p.name in only]
        return await self._run(entity, providers, bypass_cache=bypass_cache)

    async def auto_enrich(self, entity: dict) -> dict:
        """Run only auto=True providers (the selective first-seen pass)."""
        providers = [
            p for p in get_providers_for(entity.get("entity_type", ""), self.available_keys)
            if p.auto
        ]
        return await self._run(entity, providers)

    # Overall wall-clock budget for one Investigate. Providers run concurrently
    # (their awaited HTTP yields the loop), so a request finishes in about the
    # slowest single provider, not the sum — and this bounds a hung provider.
    OVERALL_BUDGET_S = 40.0

    async def _run(self, entity: dict, providers, bypass_cache: bool = False) -> dict:
        entity_id = entity.get("id")
        entity_type = entity.get("entity_type", "")
        project_id = entity.get("project_id", "")
        observable = refang(entity.get("name", "")).strip()
        results: dict[str, dict] = {}

        if not entity_id:
            logger.warning("enrichment: entity has no id; skipping (name=%r)", entity.get("name"))
            return {"entity_id": None, "observable": observable, "providers": {}}

        if not providers:
            return {"entity_id": entity_id, "observable": observable, "providers": {}}

        # Each provider writes its own result into `results`, so partial progress
        # survives an overall-budget timeout.
        async def _one(provider):
            await self._run_provider(
                provider, entity, observable, entity_type, project_id, bypass_cache, results
            )

        try:
            await asyncio.wait_for(
                asyncio.gather(*[_one(p) for p in providers]),
                timeout=self.OVERALL_BUDGET_S,
            )
        except asyncio.TimeoutError:
            for provider in providers:
                results.setdefault(provider.name, {"status": "timeout"})

        return {"entity_id": entity_id, "observable": observable, "providers": results}

    async def _run_provider(self, provider, entity, observable, entity_type,
                            project_id, bypass_cache, results) -> None:
        # The cache spares the external CALL, not the per-node write: on a hit we
        # still apply the cached result to THIS node, since a second node with the
        # same observable must get the same properties/edges.
        cached = None
        if self.cache is not None and not bypass_cache:
            try:
                cached = await self.cache.get(provider.name, observable)
            except Exception:
                logger.debug("enrichment cache get failed for %s", provider.name, exc_info=True)
        if cached is not None:
            applied = self._safe_apply(entity, project_id, _result_from_cache(cached))
            results[provider.name] = {"status": "cached" if applied else "error"}
            return

        try:
            if self.limiter is not None:
                await self.limiter.acquire(
                    provider.name, rate=provider.rate, capacity=provider.capacity
                )
            result = await provider.lookup(observable, entity_type)
        except Exception as exc:  # per-provider isolation (lookup)
            logger.warning(
                "enrichment provider %s failed for %s: %s", provider.name, observable, exc
            )
            results[provider.name] = {"status": "error"}
            return

        # per-provider isolation (graph write) — a store failure here must not
        # abort the other providers.
        if not self._safe_apply(entity, project_id, result):
            results[provider.name] = {"status": "error"}
            return

        if self.cache is not None:
            try:
                await self.cache.set(
                    provider.name, observable, _result_to_cache(result),
                    entity_type=entity_type, source_url=result.source_url,
                    ttl=provider.cache_ttl,
                )
            except Exception:
                logger.debug("enrichment cache set failed for %s", provider.name, exc_info=True)

        results[provider.name] = {
            "status": "ok",
            "properties": result.properties,
            "related": len(result.related),
        }

    def _safe_apply(self, entity: dict, project_id: str, result) -> bool:
        """Apply a result to the node, isolating any store/graph write failure."""
        try:
            self._apply(entity, project_id, result)
            return True
        except Exception:
            logger.warning(
                "enrichment: applying result to %s failed", entity.get("id"), exc_info=True
            )
            return False

    def _apply(self, entity: dict, project_id: str, result) -> None:
        """Merge provider output onto the node + write discovered edges."""
        props = {k: v for k, v in result.properties.items() if k not in _PROTECTED_KEYS}
        props["enriched"] = True
        props["enriched_at"] = datetime.now(timezone.utc).isoformat()
        self.store.update_entity(entity.get("id"), props)

        if result.related:
            writer = self._write_related_fn or self._default_write_related
            writer(entity, result.related, project_id)

    def _default_write_related(self, entity: dict, related, project_id: str) -> None:
        """Upsert related nodes (exact-match dedup) and their typed edges."""
        from intel_platform.models.relationships import Relationship

        for rel in related:
            try:
                node_id = self._get_or_create_node(rel, project_id)
            except Exception:
                logger.debug("enrichment: could not upsert related node %s", rel.name, exc_info=True)
                continue
            if not node_id:
                continue
            src_id, tgt_id = (
                (entity.get("id"), node_id) if rel.direction == "out"
                else (node_id, entity.get("id"))
            )
            try:
                self.store.create_relationship(Relationship(
                    source_id=src_id, target_id=tgt_id, rel_type=rel.rel_type,
                    confidence=0.95, method="enrichment",
                    evidence=str(rel.properties.get("evidence", "")),
                ))
            except Exception:
                logger.debug("enrichment: could not create %s edge", rel.rel_type, exc_info=True)

    def _get_or_create_node(self, rel, project_id: str) -> str | None:
        from intel_platform.models.entities import Entity, EntityType
        from intel_platform.services.graph_builder import ENTITY_TYPE_MAP

        # Deterministic exact-name dedup first — the fulltext top-N can miss a
        # high-frequency name (e.g. a country), which would spawn duplicate
        # roll-up nodes; fall back to the fuzzy candidate scan.
        try:
            exact = self.store.find_entity_by_exact_name(project_id, rel.name, rel.entity_type)
        except Exception:
            exact = None
        if exact and exact.get("id"):
            return exact.get("id")

        try:
            candidates = self.store.search_entity_by_name(project_id, rel.name, limit=5) or []
        except Exception:
            candidates = []
        for cand in candidates:
            if (cand.get("name", "").lower() == rel.name.lower()
                    and cand.get("entity_type") == rel.entity_type):
                return cand.get("id")

        cls = ENTITY_TYPE_MAP.get(rel.entity_type)
        if cls is not None:
            model = cls(name=rel.name, project_id=project_id)
        else:
            model = Entity(name=rel.name, entity_type=EntityType(rel.entity_type), project_id=project_id)
        created = self.store.create_entity(model)
        return created.get("id") if created else None
