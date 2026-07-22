"""Fetch + parse + load the pinned ATT&CK Enterprise bundle.

The bundle (~50 MB) is fetched on demand (a manual admin action) through the
collection :class:`ProxiedClient` for egress consistency, cached to a gitignored
path under ``data/attack/`` (never committed), parsed with the stdlib, and loaded
into Neo4j via :func:`graph_ops.ingest_model`. Re-ingest is idempotent.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from neo4j import Driver

from intel_platform.collection.proxy import ProxiedClient
from intel_platform.config import settings

from .graph_ops import ingest_model
from .stix_parser import ParsedAttack, parse_bundle

logger = logging.getLogger(__name__)

# repo-root/data/attack — ATTRIBUTION.md lives here and the fetched bundle is
# cached alongside it (gitignored). __file__ is
# backend/src/intel_platform/services/attack/ingest.py → parents[5] is the root.
_DATA_DIR = Path(__file__).resolve().parents[5] / "data" / "attack"


def _bundle_url(version: str) -> str:
    return f"{settings.attack_stix_base_url.rstrip('/')}/enterprise-attack-{version}.json"


def _cache_path(version: str) -> Path:
    return _DATA_DIR / f"enterprise-attack-{version}.json"


def _parse_cached(cache: Path) -> ParsedAttack:
    """Read + JSON-parse + STIX-parse a cached bundle (blocking; run off-loop)."""
    return parse_bundle(json.loads(cache.read_text(encoding="utf-8")))


def _cache_and_parse(cache: Path, raw: str) -> ParsedAttack:
    """Cache the fetched bundle then JSON+STIX-parse it (blocking; run off-loop)."""
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(raw, encoding="utf-8")
    except OSError:
        logger.warning("Could not cache ATT&CK bundle to %s", cache, exc_info=True)
    return parse_bundle(json.loads(raw))


async def _load_parsed(version: str) -> ParsedAttack:
    """Return the parsed ATT&CK model, from cache if present else fetched.

    The ~53 MB JSON parse, disk write, and two-pass STIX parse are CPU/IO-bound and
    are offloaded with ``asyncio.to_thread`` so they never block the event loop; only
    the network fetch itself (non-blocking async I/O) runs on the loop.
    """
    cache = _cache_path(version)
    if cache.exists():
        logger.info("Loading cached ATT&CK bundle %s", cache.name)
        return await asyncio.to_thread(_parse_cached, cache)

    url = _bundle_url(version)
    logger.info("Fetching ATT&CK bundle from %s", url)
    resp = await ProxiedClient().get(url, timeout=120)
    resp.raise_for_status()
    return await asyncio.to_thread(_cache_and_parse, cache, resp.text)


async def fetch_and_ingest(driver: Driver, version: str | None = None) -> dict:
    """Fetch (or load cached), parse, and load the pinned bundle. Returns counts.

    Re-ingest is idempotent for additions (MERGE on ``attack_id``); it does not prune
    nodes removed/revoked in a newer ATT&CK release (deferred — see the design spec).
    """
    version = version or settings.attack_stix_version
    parsed = await _load_parsed(version)
    counts = await asyncio.to_thread(ingest_model, driver, parsed, version)
    return {"version": version, "counts": counts}
