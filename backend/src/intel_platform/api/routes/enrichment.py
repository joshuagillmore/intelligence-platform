"""Cyber-observable enrichment API — the analyst "Investigate" action.

- POST /enrichment/entities/{id}          run all eligible providers (Investigate)
- GET  /enrichment/entities/{id}          cached enrichment view (no external calls)
- POST /enrichment/entities/{id}/refresh  force-refresh one provider (bypass cache)
- GET  /enrichment/providers              registered providers (drives admin/panel)

Providers pull related cyber data (WHOIS/DNS/GeoIP/certs/KEV/CVSS) through the
collection egress (VPN/Tor), never the LLM path.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore

router = APIRouter(dependencies=[Depends(verify_api_key)])


def _available_keys() -> frozenset[str]:
    """Names of keyed enrichment providers that have an active key.

    The free tier has none; keyed providers (Shodan/VT/…) plug in here later by
    checking the encrypted ApiKey store.
    """
    return frozenset()


def _service(store: GraphStore):
    import intel_platform.enrichment.providers  # noqa: F401  (register providers)
    from intel_platform.enrichment.cache import EnrichmentCache
    from intel_platform.enrichment.service import EnrichmentService

    return EnrichmentService(store, cache=EnrichmentCache(), available_keys=_available_keys())


@router.get("/enrichment/providers")
def list_providers():
    """List registered providers, their supported types, and key status."""
    import intel_platform.enrichment.providers  # noqa: F401  (register providers)
    from intel_platform.enrichment.base import PROVIDER_REGISTRY

    keys = _available_keys()
    return {
        "providers": [
            {
                "name": cls.name,
                "supported_types": sorted(cls.supported_types),
                "requires_key": cls.requires_key,
                "has_key": (cls.name in keys) if cls.requires_key else True,
                "auto": cls.auto,
            }
            for cls in sorted(PROVIDER_REGISTRY.values(), key=lambda c: c.name)
        ]
    }


@router.post("/enrichment/entities/{entity_id}")
async def investigate(entity_id: str, store: GraphStore = Depends(get_graph_store)):
    """Run every eligible provider for the entity and merge the results."""
    result = await _service(store).enrich_entity(entity_id)
    if result.get("error") == "not found":
        raise HTTPException(status_code=404, detail="Entity not found")
    return result


@router.post("/enrichment/entities/{entity_id}/refresh")
async def refresh(
    entity_id: str,
    provider: str = Query(..., description="Provider name to force-refresh"),
    store: GraphStore = Depends(get_graph_store),
):
    """Force a fresh lookup for one provider, bypassing the cache."""
    result = await _service(store).enrich_entity(
        entity_id, only={provider}, bypass_cache=True
    )
    if result.get("error") == "not found":
        raise HTTPException(status_code=404, detail="Entity not found")
    if not result.get("providers"):
        # `only` matched no eligible provider for this entity — a typo, a
        # wrong-type provider, or a keyed provider without a key.
        raise HTTPException(
            status_code=400,
            detail=f"Provider '{provider}' is not available for this entity",
        )
    return result


@router.get("/enrichment/entities/{entity_id}")
async def get_enrichment(entity_id: str, store: GraphStore = Depends(get_graph_store)):
    """Return the cached enrichment view without hitting any provider."""
    import intel_platform.enrichment.providers  # noqa: F401  (register providers)
    from intel_platform.enrichment.base import get_providers_for
    from intel_platform.enrichment.cache import EnrichmentCache
    from intel_platform.enrichment.observables import refang

    entity = store.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    observable = refang(entity.get("name", "")).strip()
    cache = EnrichmentCache()
    providers = get_providers_for(entity.get("entity_type", ""), _available_keys())
    cached: dict[str, dict | None] = {}
    for provider in providers:
        try:
            cached[provider.name] = await cache.get(provider.name, observable)
        except Exception:
            cached[provider.name] = None
    return {"entity_id": entity_id, "observable": observable, "cached": cached}
