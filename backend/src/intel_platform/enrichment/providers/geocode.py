"""Forward geocoding + administrative hierarchy via Nominatim (OSM), keyless.

Turns a place name into coordinates plus the full admin hierarchy (country →
state/province/governorate → county → city → neighbourhood + postal) — so
discrete admin geography is *derived from the gazetteer* rather than regexed out
of text (that's the reliable way to get provinces/governorates/postal codes).
Also creates BELONGS_TO parent nodes for the country and first-level admin
division so entities can be rolled up by area.

Public Nominatim caps at 1 req/s and requires a User-Agent (ToS); egress runs
through ProxiedClient (VPN/Tor). `nominatim_base_url` is config-driven — point
it at a self-hosted instance for bulk/unlimited use.
"""
from __future__ import annotations

from datetime import timedelta

from intel_platform.collection.proxy import ProxiedClient
from intel_platform.config import settings
from intel_platform.enrichment.base import (
    EnrichmentProvider,
    EnrichmentResult,
    RelatedEntity,
    register_provider,
)
from intel_platform.services.geo.coordinates import latlng_to_mgrs

# Place-ish entity types this provider will geocode. Everything geographic is
# currently "Location" (subtypes land in G4); the subtypes are listed so the
# provider keeps working once they persist.
_GEO_TYPES = {
    "Location", "Country", "City", "Region", "Province", "Governorate",
    "District", "Facility", "Base", "Port", "Airbase", "Embassy",
}


def _admin_fields(address: dict) -> dict:
    """Map a Nominatim `address` object to our flat admin fields."""
    admin1 = (address.get("state") or address.get("region")
              or address.get("province") or "")
    admin2 = (address.get("county") or address.get("state_district")
              or address.get("district") or "")
    city = (address.get("city") or address.get("town") or address.get("village")
            or address.get("municipality") or "")
    neighbourhood = (address.get("neighbourhood") or address.get("suburb")
                     or address.get("quarter") or "")
    return {
        "country": address.get("country", ""),
        "country_code": (address.get("country_code") or "").upper(),
        "admin1": admin1,
        "admin2": admin2,
        "city": city,
        "neighbourhood": neighbourhood,
        "postal_code": address.get("postcode", ""),
    }


@register_provider
class GeocodeProvider(EnrichmentProvider):
    name = "geocode"
    supported_types = _GEO_TYPES
    auto = False
    cache_ttl = timedelta(days=30)
    rate = 1.0        # Nominatim public policy: 1 req/s
    capacity = 1.0

    def __init__(self, client: ProxiedClient | None = None):
        self._client = client or ProxiedClient()

    async def lookup(self, value: str, entity_type: str) -> EnrichmentResult:
        url = f"{settings.nominatim_base_url.rstrip('/')}/search"
        try:
            resp = await self._client.get(
                url,
                params={"q": value, "format": "jsonv2", "addressdetails": "1", "limit": "1"},
                headers={"User-Agent": settings.geo_user_agent},
                timeout=15,
            )
            data = resp.json()
        except Exception:
            return EnrichmentResult(source_url=url)

        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            return EnrichmentResult(source_url=url)
        hit = data[0]
        try:
            lat, lon = float(hit.get("lat")), float(hit.get("lon"))
        except (TypeError, ValueError):
            return EnrichmentResult(source_url=url, raw=hit)
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            return EnrichmentResult(source_url=url, raw=hit)

        address = hit.get("address")
        admin = _admin_fields(address if isinstance(address, dict) else {})
        props = {
            "latitude": lat,
            "longitude": lon,
            "geo_source": "nominatim",
            "display_name": hit.get("display_name", ""),
            "location_type": hit.get("addresstype") or hit.get("type", ""),
            **{k: v for k, v in admin.items() if v},
        }
        try:
            props["mgrs"] = latlng_to_mgrs(lat, lon)
        except Exception:
            pass

        # Roll-up parents (BELONGS_TO): first-level admin + country, guarded
        # against linking a node to itself (e.g. geocoding a country).
        related: list[RelatedEntity] = []
        this = value.strip().lower()
        for parent in (admin.get("admin1"), admin.get("country")):
            if parent and parent.strip().lower() != this:
                related.append(RelatedEntity(name=parent, entity_type="Location", rel_type="BELONGS_TO"))

        return EnrichmentResult(properties=props, related=related, source_url=url, raw=hit)
