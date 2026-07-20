"""Auto-enrich hook — the selective, first-seen enrichment pass.

``schedule_auto_enrich`` is called by ``graph_builder`` right after new cyber
nodes are created. It is fire-and-forget and gated by the
``enrichment_auto_enabled`` AppSetting (default OFF), so it stays completely
inert until an admin turns it on. Only providers flagged ``auto`` run, so a
first-seen IP/domain/CVE gets its cheap keyless lookups (DNS, GeoIP, KEV) and
nothing else.

Kept separate from the service so importing it (from the sync graph_builder)
pulls in no heavy dependencies — the service/providers/httpx are imported lazily
inside the background task.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

AUTO_ENABLED_KEY = "enrichment_auto_enabled"

# Cyber observable types worth an auto-enrich pass (the service filters further
# to providers actually flagged auto=True).
_CYBER_TYPES = {"IPAddress", "Domain", "Vulnerability", "URL", "EmailAddress", "Hash"}

# Strong refs to in-flight background tasks — the event loop keeps only a weak
# reference, so without this a task could be GC'd mid-flight.
_bg_tasks: set = set()


async def auto_enrich_enabled() -> bool:
    """Read the auto-enrich AppSetting. Fail-safe: any error → disabled."""
    try:
        from sqlalchemy import select

        from intel_platform.db.engine import get_session_factory
        from intel_platform.db.models import AppSetting

        factory = get_session_factory()
        async with factory() as session:
            value = (
                await session.execute(
                    select(AppSetting.value).where(AppSetting.key == AUTO_ENABLED_KEY)
                )
            ).scalar_one_or_none()
    except Exception:
        logger.debug("could not read %s; defaulting to disabled", AUTO_ENABLED_KEY, exc_info=True)
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def schedule_auto_enrich(store, entities: list[dict], loop=None) -> None:
    """Schedule a fire-and-forget auto-enrich pass for newly-created cyber nodes.

    Runs on the current loop when called from async code. When called from a
    worker thread (``build_graph_from_extractions`` via ``asyncio.to_thread`` in
    plan_executor), there is no running loop, so the caller passes its ``loop``
    and we hand the coroutine over thread-safely — otherwise auto-enrich would
    silently never fire for collection-plan ingestion. No cyber targets / no loop
    at all → clean no-op. The gate and heavy imports live inside the task.
    """
    targets = [e for e in entities if e.get("entity_type") in _CYBER_TYPES and e.get("id")]
    if not targets:
        return
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is not None:
        task = running.create_task(_run_auto_enrich(store, targets))
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)
    elif loop is not None:
        # No loop in this (worker) thread — schedule onto the caller's loop.
        asyncio.run_coroutine_threadsafe(_run_auto_enrich(store, targets), loop)
    # else: no loop available anywhere → nothing to run (sync context)


async def _run_auto_enrich(store, targets: list[dict]) -> None:
    # `store` outlives the request that scheduled us because GraphStore wraps the
    # process-global Neo4j driver (api.deps.get_neo4j_driver), not a per-request
    # resource. If driver management ever becomes per-request, revisit this.
    try:
        if not await auto_enrich_enabled():
            return
        import intel_platform.enrichment.providers  # noqa: F401  (register providers)
        from intel_platform.enrichment.cache import EnrichmentCache
        from intel_platform.enrichment.service import EnrichmentService

        service = EnrichmentService(store, cache=EnrichmentCache())
        for entity in targets:
            try:
                await service.auto_enrich(entity)
            except Exception:
                logger.debug("auto-enrich failed for %s", entity.get("id"), exc_info=True)
    except Exception:
        logger.debug("auto-enrich batch failed", exc_info=True)
