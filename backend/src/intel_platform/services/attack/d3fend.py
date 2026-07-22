"""D3FEND defensive countermeasures for an ATT&CK technique (Phase 3b).

D3FEND publishes, per offensive ATT&CK technique, the defensive techniques
(countermeasures) that address it. We fetch that mapping **lazily and keyless**
from ``d3fend.mitre.org`` (no vendored 10 MB dataset), parse the SPARQL-style
bindings to ``[{id, label}]``, and cache the result in Postgres
(:class:`~intel_platform.db.models.AttackD3fendCache`) with a TTL so a repeat
lookup is a single indexed read rather than a re-fetch.

Every fetch/parse path **degrades to an empty list** — a D3FEND outage, a 404
(no mapping for that technique), or a malformed body yields
``{"countermeasures": []}``, never a 500. Egress goes through the collection
:class:`ProxiedClient` (SSRF-guarded, proxy-aware) like the other keyless
lookups.

D3FEND™ is a knowledge graph developed by MITRE, NSA-funded; Approved for Public
Release — see ``data/attack/ATTRIBUTION.md``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from intel_platform.collection.proxy import ProxiedClient
from intel_platform.config import settings

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Parsing (pure; no network) --------------------------------------------

def parse_countermeasures(payload: object) -> list[dict]:
    """Extract distinct ``{id, label, name}`` countermeasures from a D3FEND response.

    The response is SPARQL-style: ``off_to_def.results.bindings`` is a list of
    binding rows, each row a dict of ``{var: {"value": ...}}``. We read
    ``def_tech_id.value`` / ``def_tech_label.value`` per row, skip any row missing
    either, and de-duplicate by id (a technique can map to a countermeasure via
    several paths). ``name`` is the d3f: local name parsed from the ``def_tech``
    URI (e.g. ``…#DataInventory``) — the canonical URL slug, since the short id
    (``D3-DI``) does not resolve as a slug; empty if the URI is absent. Any shape
    surprise degrades to ``[]``.
    """
    if not isinstance(payload, dict):
        return []
    off_to_def = payload.get("off_to_def")
    if not isinstance(off_to_def, dict):
        return []
    results = off_to_def.get("results")
    if not isinstance(results, dict):
        return []
    bindings = results.get("bindings")
    if not isinstance(bindings, list):
        return []

    out: list[dict] = []
    seen: set[str] = set()
    for row in bindings:
        if not isinstance(row, dict):
            continue
        id_node = row.get("def_tech_id")
        label_node = row.get("def_tech_label")
        if not isinstance(id_node, dict) or not isinstance(label_node, dict):
            continue
        cid = str(id_node.get("value") or "").strip()
        label = str(label_node.get("value") or "").strip()
        if not cid or not label or cid in seen:
            continue
        seen.add(cid)
        uri_node = row.get("def_tech")
        uri = str(uri_node.get("value") or "").strip() if isinstance(uri_node, dict) else ""
        name = uri.rsplit("#", 1)[-1].rsplit("/", 1)[-1] if uri else ""
        out.append({"id": cid, "label": label, "name": name})
    return out


# --- Fetch (on demand, keyless, degrading) ---------------------------------

async def _fetch_countermeasures(tid: str, client: ProxiedClient | None) -> list[dict] | None:
    """Fetch + parse a technique's D3FEND mapping.

    Returns the parsed list on a clean 200 (possibly empty) and ``[]`` on a 404
    (a stable "no mapping" answer, worth caching). Returns ``None`` to signal a
    *degraded* fetch (network error, non-2xx, malformed body) — the caller then
    returns ``[]`` without poisoning the cache, so a later call retries.
    """
    url = f"{settings.d3fend_api_base.rstrip('/')}/{tid}.json"
    client = client or ProxiedClient()
    try:
        resp = await client.get(url, timeout=30)
    except Exception:
        logger.warning("D3FEND fetch failed for %s", tid, exc_info=True)
        return None
    if resp.status_code == 404:
        return []  # technique has no D3FEND mapping — a cacheable empty result
    try:
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        logger.warning("D3FEND response unusable for %s", tid, exc_info=True)
        return None
    return parse_countermeasures(payload)


# --- Cache (Postgres; TTL from config) -------------------------------------

def _is_fresh(fetched_at: datetime | None, ttl_days: int, now: datetime) -> bool:
    if fetched_at is None:
        return False
    if fetched_at.tzinfo is None:  # tolerate a naive timestamp (treat as UTC)
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    return fetched_at + timedelta(days=ttl_days) > now


async def _get_cached(session, tid: str, ttl_days: int) -> list[dict] | None:
    from sqlalchemy import select

    from intel_platform.db.models import AttackD3fendCache

    result = await session.execute(
        select(AttackD3fendCache).where(AttackD3fendCache.technique_id == tid)
    )
    row = result.scalar_one_or_none()
    if row is None or not _is_fresh(row.fetched_at, ttl_days, _now()):
        return None
    return list(row.countermeasures or [])


async def _upsert_cache(session, tid: str, countermeasures: list[dict]) -> None:
    from sqlalchemy import select

    from intel_platform.db.models import AttackD3fendCache

    result = await session.execute(
        select(AttackD3fendCache).where(AttackD3fendCache.technique_id == tid)
    )
    row = result.scalar_one_or_none()
    now = _now()
    if row is not None:
        row.countermeasures = countermeasures
        row.fetched_at = now
    else:
        session.add(AttackD3fendCache(
            technique_id=tid, countermeasures=countermeasures, fetched_at=now,
        ))
    await session.commit()


# --- Public entrypoint -----------------------------------------------------

async def get_countermeasures(
    session, technique_id: str, *, client: ProxiedClient | None = None,
    ttl_days: int | None = None,
) -> dict:
    """Return ``{"countermeasures": [{id, label}]}`` for a technique.

    Serves a fresh cache hit without a network call; otherwise fetches, caches,
    and returns. Every failure path degrades to ``{"countermeasures": []}`` — this
    never raises, so the route never 500s on a D3FEND outage.
    """
    tid = (technique_id or "").strip().upper()
    if not tid:
        return {"countermeasures": []}
    if ttl_days is None:
        ttl_days = int(getattr(settings, "attack_d3fend_ttl_days", 30) or 30)

    try:
        cached = await _get_cached(session, tid, ttl_days)
        if cached is not None:
            return {"countermeasures": cached}

        countermeasures = await _fetch_countermeasures(tid, client)
        if countermeasures is None:  # degraded fetch — return [] without caching
            return {"countermeasures": []}

        try:
            await _upsert_cache(session, tid, countermeasures)
        except Exception:
            # A cache write failure must not fail the lookup — the value is valid.
            logger.warning("D3FEND cache upsert failed for %s", tid, exc_info=True)
        return {"countermeasures": countermeasures}
    except Exception:
        # Last-resort guard (e.g. a cache read blowing up) — never surface it.
        logger.warning("D3FEND countermeasure lookup failed for %s", tid, exc_info=True)
        return {"countermeasures": []}
