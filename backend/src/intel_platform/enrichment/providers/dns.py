"""DNS enrichment via DNS-over-HTTPS (Cloudflare).

Keyless. Resolves a domain's A/AAAA/MX/NS/TXT records over plain HTTPS GET (so
it flows through ProxiedClient / the VPN-Tor egress with no raw-socket
dependency), stores them on the node, and emits deterministic
``(:Domain)-[:RESOLVES_TO]->(:IPAddress)`` edges for its A/AAAA answers.
"""
from __future__ import annotations

import json
from datetime import timedelta

from intel_platform.collection.proxy import ProxiedClient
from intel_platform.enrichment.base import (
    EnrichmentProvider,
    EnrichmentResult,
    RelatedEntity,
    register_provider,
)

_DOH_URL = "https://cloudflare-dns.com/dns-query"
_RECORD_TYPES = ("A", "AAAA", "MX", "NS", "TXT")
_MAX_RELATED = 10


@register_provider
class DNSProvider(EnrichmentProvider):
    name = "dns"
    supported_types = {"Domain"}
    auto = True
    cache_ttl = timedelta(days=1)
    rate = 5.0
    capacity = 10.0

    def __init__(self, client: ProxiedClient | None = None):
        self._client = client or ProxiedClient()

    async def lookup(self, value: str, entity_type: str) -> EnrichmentResult:
        records: dict[str, list[str]] = {}
        for rtype in _RECORD_TYPES:
            try:
                resp = await self._client.get(
                    _DOH_URL,
                    params={"name": value, "type": rtype},
                    headers={"Accept": "application/dns-json"},
                    timeout=10,
                )
                data = resp.json()
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            values = [
                str(a.get("data", "")).strip('"')
                for a in (data.get("Answer") or [])
                if a.get("data")
            ]
            if values:
                records[rtype] = values

        related: list[RelatedEntity] = []
        for rtype in ("A", "AAAA"):
            for ip in records.get(rtype, []):
                related.append(RelatedEntity(name=ip, entity_type="IPAddress", rel_type="RESOLVES_TO"))
        related = related[:_MAX_RELATED]

        props = {"dns_records": json.dumps(records)} if records else {}
        return EnrichmentResult(
            properties=props,
            related=related,
            source_url=f"{_DOH_URL}?name={value}",
            raw=records,
        )
