"""IP geolocation + ASN via ip-api.com (keyless, 45 req/min → rate-limited).

Populates ``IPAddress.asn`` and ``IPAddress.geolocation`` — the fields that
exist on the model today but nothing ever fills. No related edges.
"""
from __future__ import annotations

import json
from datetime import timedelta

from intel_platform.collection.proxy import ProxiedClient
from intel_platform.enrichment.base import (
    EnrichmentProvider,
    EnrichmentResult,
    register_provider,
)

# HTTP (not HTTPS) on the keyless endpoint; fields trimmed to what we store.
_URL = "http://ip-api.com/json/{ip}"
_FIELDS = "status,message,country,countryCode,region,regionName,city,lat,lon,isp,org,as,query"


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
        url = _URL.format(ip=value)
        try:
            resp = await self._client.get(url, params={"fields": _FIELDS}, timeout=10)
            data = resp.json()
        except Exception:
            return EnrichmentResult(source_url=url)

        if not isinstance(data, dict):
            return EnrichmentResult(source_url=url)
        if data.get("status") != "success":
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
