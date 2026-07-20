from __future__ import annotations

import json

from intel_platform.services.geo.coordinates import latlng_to_mgrs

# Simple geocoding lookup - hardcoded major cities/countries for offline use
# In production, would use a geocoding API
LOCATION_COORDS = {
    "moscow": (55.7558, 37.6173),
    "russia": (61.524, 105.3188),
    "ukraine": (48.3794, 31.1656),
    "kharkiv": (49.9935, 36.2304),
    "kyiv": (50.4501, 30.5234),
    "washington": (38.9072, -77.0369),
    "washington dc": (38.9072, -77.0369),
    "washington d.c.": (38.9072, -77.0369),
    "united states": (37.0902, -95.7129),
    "united kingdom": (55.3781, -3.4360),
    "london": (51.5074, -0.1278),
    "berlin": (52.5200, 13.4050),
    "germany": (51.1657, 10.4515),
    "france": (46.2276, 2.2137),
    "paris": (48.8566, 2.3522),
    "netherlands": (52.1326, 5.2913),
    "amsterdam": (52.3676, 4.9041),
    "romania": (45.9432, 24.9668),
    "bucharest": (44.4268, 26.1025),
    "beijing": (39.9042, 116.4074),
    "china": (35.8617, 104.1954),
    "tehran": (35.6892, 51.3890),
    "iran": (32.4279, 53.6880),
    "pyongyang": (39.0392, 125.7625),
    "north korea": (40.3399, 127.5101),
    "tokyo": (35.6762, 139.6503),
    "japan": (36.2048, 138.2529),
    "canada": (56.1304, -106.3468),
    "dubai": (25.2048, 55.2708),
    "voronezh": (51.6720, 39.1843),
    "brussels": (50.8503, 4.3517),
    "nato": (50.8503, 4.3517),  # NATO HQ Brussels
    "new york": (40.7128, -74.0060),
    "san francisco": (37.7749, -122.4194),
    "tel aviv": (32.0853, 34.7818),
    "israel": (31.0461, 34.8516),
    "syria": (34.8021, 38.9968),
    "iraq": (33.2232, 43.6793),
    "afghanistan": (33.9391, 67.7100),
    "pakistan": (30.3753, 69.3451),
    "india": (20.5937, 78.9629),
    "mumbai": (19.0760, 72.8777),
    "singapore": (1.3521, 103.8198),
    "australia": (-25.2744, 133.7751),
    "brazil": (-14.2350, -51.9253),
    # Africa
    "djibouti": (11.5721, 43.1456),
    "addis ababa": (9.0245, 38.7468),
    "ethiopia": (9.1450, 40.4897),
    "kenya": (-0.0236, 37.9062),
    "mombasa": (-4.0435, 39.6682),
    "nairobi": (-1.2921, 36.8219),
    "tanzania": (-6.3690, 34.8888),
    "dar es salaam": (-6.7924, 39.2083),
    "mozambique": (-18.6657, 35.5296),
    "nacala": (-14.5428, 40.6853),
    "sudan": (12.8628, 30.2176),
    "port sudan": (19.6158, 37.2164),
    "madagascar": (-18.7669, 46.8691),
    "nigeria": (9.0820, 8.6753),
    "south africa": (-30.5595, 22.9375),
    "senegal": (14.4974, -14.4524),
    "dakar": (14.7167, -17.4677),
    "somalia": (5.1521, 46.1996),
    "eritrea": (15.1794, 39.7823),
    # South China Sea / East Asia
    "south china sea": (12.0, 114.0),
    "spratly islands": (9.0, 113.0),
    "paracel islands": (16.5, 112.0),
    "fiery cross reef": (9.55, 112.89),
    "subi reef": (10.92, 114.08),
    "mischief reef": (9.90, 115.53),
    "woody island": (16.83, 112.34),
    "scarborough shoal": (15.15, 117.75),
    "taiwan": (23.6978, 120.9605),
    "taipei": (25.0330, 121.5654),
    "vietnam": (14.0583, 108.2772),
    "hanoi": (21.0278, 105.8342),
    "philippines": (12.8797, 121.7740),
    "manila": (14.5995, 120.9842),
    "malaysia": (4.2105, 101.9758),
    "okinawa": (26.3344, 127.8056),
    "naha": (26.2124, 127.6809),
    "zhanjiang": (21.2707, 110.3594),
    "guangdong": (23.3790, 113.7633),
    "darwin": (-12.4634, 130.8456),
    "reunion island": (-21.1151, 55.5364),
    "abu dhabi": (24.4539, 54.3773),
    "andaman and nicobar islands": (11.7401, 92.6586),
    # Southeast Asia
    "indonesia": (-0.7893, 113.9213),
    "jakarta": (-6.2088, 106.8456),
    "myanmar": (21.9162, 95.9560),
    "thailand": (15.8700, 100.9925),
    "bangkok": (13.7563, 100.5018),
    "cambodia": (12.5657, 104.9910),
    "laos": (19.8563, 102.4955),
    # Middle East
    "saudi arabia": (23.8859, 45.0792),
    "riyadh": (24.7136, 46.6753),
    "qatar": (25.3548, 51.1839),
    "doha": (25.2854, 51.5310),
    "yemen": (15.5527, 48.5164),
    "oman": (21.4735, 55.9754),
    "bahrain": (26.0667, 50.5577),
    "kuwait": (29.3117, 47.4818),
    # Europe additional
    "poland": (51.9194, 19.1451),
    "warsaw": (52.2297, 21.0122),
    "sweden": (60.1282, 18.6435),
    "stockholm": (59.3293, 18.0686),
    "norway": (60.4720, 8.4689),
    "finland": (61.9241, 25.7482),
    "spain": (40.4637, -3.7492),
    "madrid": (40.4168, -3.7038),
    "italy": (41.8719, 12.5674),
    "rome": (41.9028, 12.4964),
    "greece": (39.0742, 21.8243),
    "turkey": (38.9637, 35.2433),
    "ankara": (39.9334, 32.8597),
    "istanbul": (41.0082, 28.9784),
    # Americas
    "mexico": (23.6345, -102.5528),
    "mexico city": (19.4326, -99.1332),
    "colombia": (4.5709, -74.2973),
    "bogota": (4.7110, -74.0721),
    "argentina": (-38.4161, -63.6167),
    "buenos aires": (-34.6037, -58.3816),
    "chile": (-35.6751, -71.5430),
    # South/Central Asia
    "bangladesh": (23.6850, 90.3563),
    "dhaka": (23.8103, 90.4125),
    "sri lanka": (7.8731, 80.7718),
    "nepal": (28.3949, 84.1240),
    "uzbekistan": (41.3775, 64.5853),
    "kazakhstan": (48.0196, 66.9237),
    "south korea": (35.9078, 127.7669),
    "seoul": (37.5665, 126.9780),
}


def geocode_location(name: str) -> tuple[float, float] | None:
    """Look up coordinates for a location name. Returns (lat, lng) or None."""
    key = name.lower().strip()
    result = LOCATION_COORDS.get(key)
    if result:
        return result
    # Try stripping common prefixes
    for prefix in ("the ", "northern ", "southern ", "eastern ", "western ", "central "):
        if key.startswith(prefix):
            result = LOCATION_COORDS.get(key[len(prefix):])
            if result:
                return result
    # Try removing parenthetical/suffix info
    if "(" in key:
        result = LOCATION_COORDS.get(key.split("(")[0].strip())
        if result:
            return result
    return None


def geocode_all_locations(store, project_id: str) -> list[dict]:
    """Geocode all Location entities in a project and return results."""
    entities = store.search_entities(project_id=project_id, entity_type="Location", limit=1000)
    results = []
    for entity in entities:
        name = entity.get("name", "")
        coords = geocode_location(name)
        result = {
            "id": entity.get("id"),
            "name": name,
            "entity_type": "Location",
        }
        if coords:
            result["latitude"] = coords[0]
            result["longitude"] = coords[1]
            result["geocoded"] = True
        else:
            result["latitude"] = None
            result["longitude"] = None
            result["geocoded"] = False
        results.append(result)
    return results


def _valid_latlng(lat: float, lng: float) -> bool:
    return -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0


def _extract_coords(entity: dict) -> tuple[float | None, float | None, str]:
    """Resolve (lat, lng, source) for an entity, or (None, None, "") if unplaceable.

    Precedence: persisted latitude/longitude on the node > a GeoIP `geolocation`
    JSON blob (from the geoip enrichment provider) > the offline gazetteer by
    name. Out-of-range coordinates are rejected (fall through to the next source).
    """
    lat, lng = entity.get("latitude"), entity.get("longitude")
    if lat is not None and lng is not None:
        try:
            lat, lng = float(lat), float(lng)
            if _valid_latlng(lat, lng):
                return lat, lng, entity.get("geo_source") or "persisted"
        except (TypeError, ValueError):
            pass

    blob = entity.get("geolocation")
    if blob:
        try:
            geo = json.loads(blob) if isinstance(blob, str) else blob
            glat, glng = geo.get("lat"), geo.get("lon")
            if glat is not None and glng is not None:
                glat, glng = float(glat), float(glng)
                if _valid_latlng(glat, glng):
                    return glat, glng, "geoip"
        except (ValueError, TypeError, AttributeError):
            pass

    coords = geocode_location(entity.get("name", ""))
    if coords and _valid_latlng(coords[0], coords[1]):
        return coords[0], coords[1], "gazetteer"
    return None, None, ""


def geolocate_entities(store, project_id: str) -> list[dict]:
    """Every entity in the project that can be placed on the map.

    Unlike geocode_all_locations (Location names only), this includes IPAddress
    nodes whose GeoIP `geolocation` blob carries lat/lon, and any node already
    carrying coordinates. Coordinates are resolved on the fly (both the JSON
    parse and the dict lookup are cheap) — this is a pure read with NO write-back:
    persisting crude gazetteer coords here would shadow the real geocoder in G2.
    """
    entities = store.get_geolocatable_entities(project_id, limit=2000)
    results = []
    for entity in entities:
        lat, lng, source = _extract_coords(entity)
        mgrs = ""
        if lat is not None:
            try:
                mgrs = latlng_to_mgrs(lat, lng)
            except Exception:
                mgrs = ""
        results.append({
            "id": entity.get("id"),
            "name": entity.get("name", ""),
            "entity_type": entity.get("entity_type", "Location"),
            "latitude": lat,
            "longitude": lng,
            "geocoded": lat is not None and lng is not None,
            "geo_source": source,
            "mgrs": mgrs,
            "properties": dict(entity),
        })
    return results
