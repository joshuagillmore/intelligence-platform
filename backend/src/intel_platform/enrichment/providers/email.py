"""Email-address enrichment (keyless).

For an ``EmailAddress`` observable this pulls cheap, keyless signals:
- the address's **domain** (and an explicit ``BELONGS_TO`` edge to it, so the
  analyst can pivot email → domain → infrastructure);
- whether that domain can receive mail (**MX** records, via DoH);
- whether it is a known **disposable / throwaway** provider;
- whether the address has a public **Gravatar** (a weak "this is a real, used
  address" signal).

All HTTPS GETs go through ProxiedClient (VPN/Tor egress). A paid breach-check
(e.g. HaveIBeenPwned) would slot in later as a keyed provider — not here.
"""
from __future__ import annotations

import hashlib
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
_GRAVATAR_URL = "https://www.gravatar.com/avatar/{hash}"

# A curated subset of common disposable / throwaway email domains. Not
# exhaustive — a full feed would be a keyed/downloaded list; this covers the
# frequently-seen ones for a fast, offline flag.
_DISPOSABLE_DOMAINS = frozenset({
    "mailinator.com", "guerrillamail.com", "guerrillamail.info", "10minutemail.com",
    "temp-mail.org", "tempmail.com", "throwawaymail.com", "yopmail.com", "getnada.com",
    "trashmail.com", "sharklasers.com", "maildrop.cc", "dispostable.com", "fakeinbox.com",
    "mailnesia.com", "mohmal.com", "spamgourmet.com", "mailcatch.com", "tempinbox.com",
    "emailondeck.com", "mytemp.email", "burnermail.io", "moakt.com", "tempr.email",
    "getairmail.com", "inboxkitten.com", "harakirimail.com", "33mail.com", "nada.email",
})


@register_provider
class EmailProvider(EnrichmentProvider):
    name = "email"
    supported_types = {"EmailAddress"}
    auto = False  # on-demand Investigate only, to bound volume
    cache_ttl = timedelta(days=7)
    rate = 3.0
    capacity = 5.0

    def __init__(self, client: ProxiedClient | None = None):
        self._client = client or ProxiedClient()

    async def lookup(self, value: str, entity_type: str) -> EnrichmentResult:
        local, _, domain = value.partition("@")
        domain = domain.strip().lower()
        if not domain:
            return EnrichmentResult()

        mx_hosts = await self._mx_records(domain)
        gravatar = await self._has_gravatar(value)

        props: dict = {
            "email_domain": domain,
            "has_mx": bool(mx_hosts),
            "disposable": domain in _DISPOSABLE_DOMAINS,
            "gravatar": gravatar,
        }
        if mx_hosts:
            props["mx_records"] = json.dumps(mx_hosts)

        related = [RelatedEntity(name=domain, entity_type="Domain", rel_type="BELONGS_TO")]
        return EnrichmentResult(
            properties=props,
            related=related,
            source_url=f"{_DOH_URL}?name={domain}&type=MX",
            raw={"domain": domain, "mx": mx_hosts, "gravatar": gravatar},
        )

    async def _mx_records(self, domain: str) -> list[str]:
        try:
            resp = await self._client.get(
                _DOH_URL,
                params={"name": domain, "type": "MX"},
                headers={"Accept": "application/dns-json"},
                timeout=10,
            )
            data = resp.json()
        except Exception:
            return []
        if not isinstance(data, dict):
            return []
        answers = data.get("Answer")
        if not isinstance(answers, list):
            return []
        return [
            str(a.get("data", "")).strip('"')
            for a in answers
            if isinstance(a, dict) and a.get("data")
        ]

    async def _has_gravatar(self, email: str) -> bool:
        digest = hashlib.md5(email.strip().lower().encode(), usedforsecurity=False).hexdigest()
        try:
            resp = await self._client.get(
                _GRAVATAR_URL.format(hash=digest), params={"d": "404"}, timeout=10
            )
            return getattr(resp, "status_code", None) == 200
        except Exception:
            return False
