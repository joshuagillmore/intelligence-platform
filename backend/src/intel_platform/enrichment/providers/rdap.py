"""WHOIS via RDAP (keyless), for domains and IPs.

Uses the rdap.org bootstrap resolver, which redirects to the authoritative
registry (ProxiedClient follows redirects). Extracts registrar, registration/
expiry dates, and the registrant/netblock organization from the RDAP JSON.
"""
from __future__ import annotations

from datetime import timedelta

from intel_platform.collection.proxy import ProxiedClient
from intel_platform.enrichment.base import (
    EnrichmentProvider,
    EnrichmentResult,
    ProviderError,
    fetch_json,
    register_provider,
)

_DOMAIN_URL = "https://rdap.org/domain/{value}"
_IP_URL = "https://rdap.org/ip/{value}"


def _event_date(events: list, action: str) -> str:
    for ev in events or []:
        if ev.get("eventAction") == action:
            return ev.get("eventDate", "")
    return ""


def _entity_name(entities: list, role: str) -> str:
    """Pull a human/org name for the entity holding `role` from its vCard."""
    for ent in entities or []:
        roles = ent.get("roles", []) or []
        if role not in roles:
            continue
        vcard = ent.get("vcardArray", [])
        if len(vcard) >= 2:
            for field in vcard[1]:
                if field and field[0] == "fn" and len(field) >= 4:
                    return str(field[3])
        if ent.get("handle"):
            return str(ent["handle"])
    return ""


@register_provider
class RDAPProvider(EnrichmentProvider):
    name = "rdap"
    supported_types = {"Domain", "IPAddress"}
    auto = False
    cache_ttl = timedelta(days=7)
    rate = 2.0
    capacity = 5.0

    def __init__(self, client: ProxiedClient | None = None):
        self._client = client or ProxiedClient()

    async def lookup(self, value: str, entity_type: str) -> EnrichmentResult:
        url = (_IP_URL if entity_type == "IPAddress" else _DOMAIN_URL).format(value=value)
        data = await fetch_json(self._client, self.name, url, timeout=15)
        if not isinstance(data, dict):
            raise ProviderError(self.name, "unexpected response shape")
        entities = data.get("entities", []) or []
        events = data.get("events", []) or []

        if entity_type == "IPAddress":
            props = {
                # NOT `asn` — geoip owns that field on the IPAddress node; use a
                # distinct key so a full Investigate doesn't let the two clobber
                # each other via SET n += props.
                "net_name": data.get("name", "") or data.get("handle", ""),
                "registrant": _entity_name(entities, "registrant")
                or _entity_name(entities, "administrative"),
            }
        else:
            props = {
                "registrar": _entity_name(entities, "registrar"),
                "registrant": _entity_name(entities, "registrant"),
                "registration_date": _event_date(events, "registration"),
            }
        props = {k: v for k, v in props.items() if v}
        return EnrichmentResult(properties=props, raw=data, source_url=url)
