"""Certificate transparency via crt.sh (keyless).

Summarizes the certs issued for a domain — issuers seen and how many distinct
subject-alternative names — and optionally surfaces a capped set of
SAN-discovered sibling domains as ``ASSOCIATED_WITH`` related nodes.
"""
from __future__ import annotations

from datetime import timedelta

from intel_platform.collection.proxy import ProxiedClient
from intel_platform.enrichment.base import (
    EnrichmentProvider,
    EnrichmentResult,
    RelatedEntity,
    register_provider,
)

_URL = "https://crt.sh/"
_MAX_RELATED = 10


@register_provider
class CertsProvider(EnrichmentProvider):
    name = "certs"
    supported_types = {"Domain"}
    auto = False
    cache_ttl = timedelta(days=7)
    rate = 1.0
    capacity = 5.0

    def __init__(self, client: ProxiedClient | None = None):
        self._client = client or ProxiedClient()

    async def lookup(self, value: str, entity_type: str) -> EnrichmentResult:
        try:
            resp = await self._client.get(
                _URL, params={"q": value, "output": "json"}, timeout=20
            )
            rows = resp.json()
        except Exception:
            return EnrichmentResult(source_url=_URL)

        if not isinstance(rows, list):
            return EnrichmentResult(source_url=_URL)

        issuers: set[str] = set()
        sans: set[str] = set()
        for row in rows:
            if row.get("issuer_name"):
                issuers.add(str(row["issuer_name"]))
            for name in str(row.get("name_value", "")).splitlines():
                name = name.strip().lstrip("*.").lower()
                if name:
                    sans.add(name)

        # SAN-discovered sibling domains (exclude the queried domain itself).
        siblings = sorted(n for n in sans if n != value.lower())[:_MAX_RELATED]
        related = [
            RelatedEntity(name=d, entity_type="Domain", rel_type="ASSOCIATED_WITH")
            for d in siblings
        ]

        props = {
            "cert_issuers": sorted(issuers)[:_MAX_RELATED],
            "cert_san_count": len(sans),
        }
        return EnrichmentResult(
            properties=props,
            related=related,
            source_url=f"{_URL}?q={value}",
            raw={"issuers": sorted(issuers)[:_MAX_RELATED], "san_count": len(sans)},
        )
