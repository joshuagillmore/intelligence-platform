"""Overpass (OSM) local-feature lookup — the robust replacement for Wikimapia.

Given a coordinate, returns nearby GEOINT-relevant features (airfields, military
sites, ports, power/infrastructure, government, hospitals/police, and
neighbourhoods) with their positions — the "what's around this geotarget"
workflow. Egress runs through ProxiedClient (VPN/Tor); ``overpass_base_url`` is
config-driven so a self-hosted Overpass instance is a .env swap (the public
instance rate-limits hard and should not be used for bulk).
"""
from __future__ import annotations

from intel_platform.config import settings

# (category, Overpass tag selector) — the query unions all of these `around` the
# point; the category is re-derived from each result's tags in _categorize().
_SELECTORS = [
    "[aeroway=aerodrome]",
    "[military]",
    "[landuse=military]",
    "[harbour=yes]",
    '[landuse~"port|harbour"]',
    '[man_made~"tower|mast|works|pipeline|bunker_silo"]',
    '[power~"plant|substation"]',
    "[office=government]",
    '[amenity~"hospital|police|fire_station|fuel"]',
    '[place~"neighbourhood|suburb|quarter"]',
]

_TAG_KEEP = {
    "name", "military", "aeroway", "harbour", "power", "place",
    "man_made", "amenity", "office", "landuse", "operator",
}


def _build_query(lat: float, lon: float, radius: int) -> str:
    parts = "".join(f"nwr(around:{radius},{lat},{lon}){sel};" for sel in _SELECTORS)
    return f"[out:json][timeout:25];({parts});out center tags 80;"


def _categorize(tags: dict) -> str:
    if tags.get("aeroway") == "aerodrome":
        return "airfield"
    if "military" in tags or tags.get("landuse") == "military":
        return "military"
    if tags.get("harbour") or tags.get("landuse") in ("port", "harbour"):
        return "port"
    if tags.get("power") in ("plant", "substation"):
        return "power"
    if any(k in str(tags.get("man_made", "")) for k in ("tower", "mast", "works", "pipeline", "bunker")):
        return "infrastructure"
    if tags.get("office") == "government":
        return "government"
    if tags.get("amenity") in ("hospital", "police", "fire_station", "fuel"):
        return "emergency"
    if tags.get("place") in ("neighbourhood", "suburb", "quarter"):
        return "neighbourhood"
    return "feature"


async def nearby_features(client, base_url: str, lat: float, lon: float,
                          radius: int = 2000, limit: int = 80) -> list[dict]:
    """Return nearby OSM features as [{name, category, lat, lon, tags}].

    Best-effort: any error (rate limit, VPN block, bad shape) → empty list.
    """
    query = _build_query(lat, lon, radius)
    try:
        resp = await client.post(
            base_url, data={"data": query},
            headers={"User-Agent": settings.geo_user_agent}, timeout=30,
        )
        data = resp.json()
    except Exception:
        return []
    if not isinstance(data, dict):
        return []

    features: list[dict] = []
    for element in (data.get("elements") or [])[:limit]:
        if not isinstance(element, dict):
            continue
        tags = element.get("tags") or {}
        if not isinstance(tags, dict):
            continue
        center = element.get("center") or {}
        lat_e = element.get("lat", center.get("lat"))
        lon_e = element.get("lon", center.get("lon"))
        if lat_e is None or lon_e is None:
            continue
        category = _categorize(tags)
        features.append({
            "name": tags.get("name") or tags.get("official_name") or category,
            "category": category,
            "lat": lat_e,
            "lon": lon_e,
            "tags": {k: v for k, v in tags.items() if k in _TAG_KEEP},
        })
    return features
