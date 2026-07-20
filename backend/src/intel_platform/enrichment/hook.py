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


def schedule_auto_enrich(store, entities: list[dict]) -> None:
    """Schedule a fire-and-forget auto-enrich pass for newly-created cyber nodes.

    No-ops when there are no cyber targets or no running event loop (e.g. a sync
    test / non-async caller). The gate and all heavy imports happen inside the
    scheduled task, so this stays cheap and side-effect-free when auto is off.
    """
    targets = [e for e in entities if e.get("entity_type") in _CYBER_TYPES and e.get("id")]
    if not targets:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # not in an async context — nothing to schedule onto
    loop.create_task(_run_auto_enrich(store, targets))


async def _run_auto_enrich(store, targets: list[dict]) -> None:
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
