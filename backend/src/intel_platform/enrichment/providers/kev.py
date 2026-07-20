"""CISA Known Exploited Vulnerabilities (KEV) membership.

Keyless. The KEV catalog is one JSON document; we fetch it once and cache the
parsed CVE set in-process (refreshed every few hours) so a per-CVE lookup is a
dict membership test, not a re-download. A hit marks the Vulnerability node
``known_exploited`` and sets severity to critical — real data replacing the
hollow ``/cyber`` severity stat.
"""
from __future__ import annotations

import time
from datetime import timedelta

from intel_platform.collection.proxy import ProxiedClient
from intel_platform.enrichment.base import (
    EnrichmentProvider,
    EnrichmentResult,
    register_provider,
)

_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
_CATALOG_TTL = 6 * 3600  # seconds

# Module-level catalog cache: {"cves": {CVEID: entry} | None, "fetched": monotonic}
_catalog: dict = {"cves": None, "fetched": 0.0}


def _reset_catalog() -> None:
    """Test hook: force the next lookup to re-fetch the catalog."""
    _catalog["cves"] = None
    _catalog["fetched"] = 0.0


async def _get_catalog(client: ProxiedClient) -> dict:
    now = time.monotonic()
    if _catalog["cves"] is not None and (now - _catalog["fetched"]) < _CATALOG_TTL:
        return _catalog["cves"]
    resp = await client.get(_KEV_URL, timeout=30)
    data = resp.json()
    cves = {
        str(v.get("cveID", "")).upper(): v
        for v in (data.get("vulnerabilities") or [])
        if v.get("cveID")
    }
    _catalog["cves"] = cves
    _catalog["fetched"] = now
    return cves


@register_provider
class KEVProvider(EnrichmentProvider):
    name = "kev"
    supported_types = {"Vulnerability"}
    auto = True
    cache_ttl = timedelta(days=1)
    rate = 5.0
    capacity = 10.0

    def __init__(self, client: ProxiedClient | None = None):
        self._client = client or ProxiedClient()

    async def lookup(self, value: str, entity_type: str) -> EnrichmentResult:
        try:
            catalog = await _get_catalog(self._client)
        except Exception:
            return EnrichmentResult(source_url=_KEV_URL)

        entry = catalog.get(value.upper())
        if not entry:
            return EnrichmentResult(properties={"known_exploited": False}, source_url=_KEV_URL)

        props = {
            "known_exploited": True,
            "kev_date_added": entry.get("dateAdded", ""),
            "severity": "critical",
        }
        return EnrichmentResult(properties=props, raw=entry, source_url=_KEV_URL)
