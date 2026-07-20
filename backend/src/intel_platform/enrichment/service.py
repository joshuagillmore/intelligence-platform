"""Enrichment orchestrator.

``EnrichmentService.enrich_entity`` is the analyst "Investigate" action: for one
observable node it runs every eligible provider (respecting the cache and rate
limiter), merges the returned properties onto the node, upserts any discovered
related nodes/edges, and records the raw payload. ``auto_enrich`` is the
selective, fire-and-forget pass run when a cyber node is first created — it runs
only providers flagged ``auto``.

Providers are isolated: one failing provider never fails the investigation.
External calls happen inside the providers (through ``ProxiedClient``), so this
orchestrator stays transport-agnostic.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from intel_platform.enrichment.base import get_providers_for
from intel_platform.enrichment.cache import RateLimiter
from intel_platform.enrichment.observables import refang

logger = logging.getLogger(__name__)


class EnrichmentService:
    def __init__(self, store, *, write_related=None, cache=None, limiter=None,
                 available_keys: frozenset[str] | set[str] = frozenset()):
        self.store = store
        self.cache = cache
        self.limiter = limiter or RateLimiter()
        self.available_keys = available_keys
        # None -> use the built-in graph writer; injectable for tests.
        self._write_related_fn = write_related

    async def enrich_entity(self, entity_id: str) -> dict:
        """Run all eligible providers for an entity (the Investigate action)."""
        entity = self.store.get_entity(entity_id)
        if not entity:
            return {"entity_id": entity_id, "error": "not found", "providers": {}}
        providers = get_providers_for(entity.get("entity_type", ""), self.available_keys)
        return await self._run(entity, providers)

    async def auto_enrich(self, entity: dict) -> dict:
        """Run only auto=True providers (the selective first-seen pass)."""
        providers = [
            p for p in get_providers_for(entity.get("entity_type", ""), self.available_keys)
            if p.auto
        ]
        return await self._run(entity, providers)

    async def _run(self, entity: dict, providers) -> dict:
        entity_id = entity.get("id")
        entity_type = entity.get("entity_type", "")
        project_id = entity.get("project_id", "")
        observable = refang(entity.get("name", "")).strip()
        results: dict[str, dict] = {}

        for provider in providers:
            # Cache first — a re-seen IOC across documents costs nothing.
            cached = None
            if self.cache is not None:
                try:
                    cached = await self.cache.get(provider.name, observable)
                except Exception:
                    logger.debug("enrichment cache get failed for %s", provider.name, exc_info=True)
            if cached is not None:
                results[provider.name] = {"status": "cached"}
                continue

            try:
                if self.limiter is not None:
                    await self.limiter.acquire(
                        provider.name, rate=provider.rate, capacity=provider.capacity
                    )
                result = await provider.lookup(observable, entity_type)
            except Exception as exc:  # per-provider isolation
                logger.warning(
                    "enrichment provider %s failed for %s: %s", provider.name, observable, exc
                )
                results[provider.name] = {"status": "error", "error": str(exc)}
                continue

            self._apply(entity, project_id, result)

            if self.cache is not None:
                try:
                    await self.cache.set(
                        provider.name, observable, result.raw or result.properties,
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

        return {"entity_id": entity_id, "observable": observable, "providers": results}

    def _apply(self, entity: dict, project_id: str, result) -> None:
        """Merge provider output onto the node + write discovered edges."""
        props = dict(result.properties)
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
