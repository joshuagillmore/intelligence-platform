from __future__ import annotations

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
}


def geocode_location(name: str) -> tuple[float, float] | None:
    """Look up coordinates for a location name. Returns (lat, lng) or None."""
    key = name.lower().strip()
    return LOCATION_COORDS.get(key)


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
