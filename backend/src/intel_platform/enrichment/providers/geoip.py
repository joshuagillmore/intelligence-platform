"""IP geolocation + ASN via ip-api.com (keyless, 45 req/min → rate-limited).

Populates ``IPAddress.asn`` and ``IPAddress.geolocation`` — the fields that
exist on the model today but nothing ever fills. No related edges.

The keyless endpoint is plain HTTP only. When collection egress is Tor, the
exit node would see which address is under investigation and could rewrite the
answer, so the lookup is skipped (and reported as skipped) in Tor mode.
"""
from __future__ import annotations

import json
from datetime import timedelta

from intel_platform.collection.proxy import ProxiedClient, get_active_proxy_config
from intel_platform.enrichment.base import (
    EnrichmentProvider,
    EnrichmentResult,
    ProviderError,
    fetch_json,
    register_provider,
)

# HTTP (not HTTPS) on the keyless endpoint; fields trimmed to what we store.
_URL = "http://ip-api.com/json/{ip}"
_FIELDS = "status,message,country,countryCode,region,regionName,city,lat,lon,isp,org,as,query"


async def _egress_mode() -> str:
    """The active collection egress mode (``direct`` | ``vpn`` | ``tor``)."""
    return (await get_active_proxy_config()).mode


@register_provider
class GeoIPProvider(EnrichmentProvider):
    name = "geoip"
    supported_types = {"IPAddress"}
    auto = True
    cache_ttl = timedelta(days=30)
    rate = 0.7          # ~42/min, under the 45/min free cap
    capacity = 10.0

    def __init__(self, client: ProxiedClient | None = None):
        self._client = client or ProxiedClient()

    async def lookup(self, value: str, entity_type: str) -> EnrichmentResult:
        if await _egress_mode() == "tor":
            return EnrichmentResult(skipped="plain-HTTP lookup not sent over Tor")
        url = _URL.format(ip=value)
        data = await fetch_json(self._client, self.name, url, params={"fields": _FIELDS}, timeout=10)
        if not isinstance(data, dict):
            raise ProviderError(self.name, "unexpected response shape")
        if data.get("status") != "success":
            # ip-api's "fail" (private/reserved range, invalid query) is a real
            # answer about this address: it has no public geolocation.
            return EnrichmentResult(raw=data, source_url=url)

        geo = {
            "city": data.get("city", ""),
            "region": data.get("regionName", ""),
            "country": data.get("country", ""),
            "country_code": data.get("countryCode", ""),
            "lat": data.get("lat"),
            "lon": data.get("lon"),
            "org": data.get("org") or data.get("isp", ""),
        }
        props = {
            "asn": data.get("as", ""),
            "geolocation": json.dumps(geo),
        }
        return EnrichmentResult(properties=props, raw=data, source_url=url)
