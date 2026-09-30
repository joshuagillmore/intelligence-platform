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
    ProviderError,
    RelatedEntity,
    fetch_json,
    register_provider,
)

_DOH_URL = "https://cloudflare-dns.com/dns-query"
_RECORD_TYPES = ("A", "AAAA", "MX", "NS", "TXT")
_MAX_RELATED = 10
# DoH ``Status`` is the DNS RCODE. NOERROR (0) and NXDOMAIN (3) are answers;
# SERVFAIL, REFUSED and the rest mean the resolver could not answer.
_ANSWER_RCODES = (0, 3)


def doh_answers(data, provider: str) -> list[str]:
    """``Answer[].data`` values from a DoH JSON reply, or ``ProviderError``.

    Shared with the email provider's MX lookup. An absent ``Answer`` is a real
    "no records"; a non-dict reply, a failing RCODE, or an ``Answer`` that is
    not a list is not an answer at all.
    """
    if not isinstance(data, dict):
        raise ProviderError(provider, "unexpected response shape")
    status = data.get("Status", 0)
    if status not in _ANSWER_RCODES:
        raise ProviderError(provider, f"dns rcode {status}")
    answers = data.get("Answer")
    if answers is None:
        return []
    if not isinstance(answers, list):
        raise ProviderError(provider, "unexpected response shape")
    return [
        str(a.get("data", "")).strip('"')
        for a in answers
        if isinstance(a, dict) and a.get("data")
    ]


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
        # Any record type failing fails the lookup: a partial answer missing its
        # A records would be cached as "resolves to nothing".
        records: dict[str, list[str]] = {}
        for rtype in _RECORD_TYPES:
            data = await fetch_json(
                self._client, self.name, _DOH_URL,
                params={"name": value, "type": rtype},
                headers={"Accept": "application/dns-json"},
                timeout=10,
            )
            values = doh_answers(data, self.name)
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
