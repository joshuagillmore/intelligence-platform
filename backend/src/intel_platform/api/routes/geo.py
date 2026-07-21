import asyncio
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException
from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.collection.proxy import ProxiedClient
from intel_platform.config import settings
from intel_platform.graph.store import GraphStore
from intel_platform.services.geocoding import _extract_coords, geolocate_entities
from intel_platform.services.text_utils import normalize_datetime

router = APIRouter(dependencies=[Depends(verify_api_key)])


def _compute_location_edges(locations: list[dict], store: GraphStore) -> list[dict]:
    """Compute edges between locations based on shared non-location entities.

    If entity X is connected to both Location A and Location B,
    that creates an edge A↔B with weight = number of shared entities.
    """
    location_ids = {loc["id"] for loc in locations if loc.get("id")}
    loc_id_to_name = {loc["id"]: loc["name"] for loc in locations if loc.get("id")}
    loc_id_to_coords = {}
    for loc in locations:
        # `is not None`, not truthiness — a real 0.0 (equator / prime meridian)
        # must not be treated as missing.
        if loc.get("latitude") is not None and loc.get("longitude") is not None:
            loc_id_to_coords[loc["id"]] = (loc["latitude"], loc["longitude"])

    # For each location, find connected non-location entities
    # entity_id → set of location_ids it connects to
    entity_to_locations: dict[str, set[str]] = defaultdict(set)
    # Also track entity names for tooltip info
    entity_names: dict[str, str] = {}

    for loc in locations:
        lid = loc.get("id")
        if not lid:
            continue
        rels = store.get_relationships(lid)
        for rel in rels:
            target_id = rel.get("target_id", "")
            target_name = rel.get("target_name", "")
            # Skip if target is also a location — we want shared NON-location entities
            if target_id in location_ids:
                continue
            entity_to_locations[target_id].add(lid)
            entity_names[target_id] = target_name

    # Build edges: for each entity connected to 2+ locations, create edges between those locations
    edge_map: dict[tuple[str, str], dict] = {}
    for entity_id, connected_locs in entity_to_locations.items():
        if len(connected_locs) < 2:
            continue
        loc_list = sorted(connected_locs)
        for i in range(len(loc_list)):
            for j in range(i + 1, len(loc_list)):
                key = (loc_list[i], loc_list[j])
                if key not in edge_map:
                    edge_map[key] = {
                        "source_id": key[0],
                        "target_id": key[1],
                        "source_name": loc_id_to_name.get(key[0], ""),
                        "target_name": loc_id_to_name.get(key[1], ""),
                        "weight": 0,
                        "shared_entities": [],
                    }
                    # Add coordinates if both locations are geocoded
                    if key[0] in loc_id_to_coords and key[1] in loc_id_to_coords:
                        edge_map[key]["source_coords"] = list(loc_id_to_coords[key[0]])
                        edge_map[key]["target_coords"] = list(loc_id_to_coords[key[1]])
                edge_map[key]["weight"] += 1
                ename = entity_names.get(entity_id, entity_id)
                if len(edge_map[key]["shared_entities"]) < 10:  # Cap the list
                    edge_map[key]["shared_entities"].append(ename)

    return sorted(edge_map.values(), key=lambda e: e["weight"], reverse=True)


@router.get("/geo/locations")
def get_geo_locations(project_id: str, store: GraphStore = Depends(get_graph_store)):
    """Get all geolocatable entities (places + IP/WHOIS geo) with relationships and edges."""
    locations = geolocate_entities(store, project_id)

    # Enrich with relationships
    for loc in locations:
        if loc.get("id"):
            rels = store.get_relationships(loc["id"])
            loc["relationships"] = [
                {"target_name": r.get("target_name"), "rel_type": r.get("rel_type"),
                 "target_id": r.get("target_id", ""),
                 "confidence": r.get("confidence", r.get("props", {}).get("confidence"))}
                for r in rels
            ]
            loc["connection_count"] = len(rels)

    # Compute location-to-location edges via shared entities. IPs are shown as
    # markers but excluded here — edges are geographic (place↔place), not the
    # co-occurrence noise IP↔place would add.
    place_locations = [loc for loc in locations if loc.get("entity_type") != "IPAddress"]
    geo_edges = _compute_location_edges(place_locations, store)

    return {
        "locations": locations,
        "edges": geo_edges,
        "total": len(locations),
        "geocoded": sum(1 for loc in locations if loc.get("geocoded")),
        "edge_count": len(geo_edges),
    }


@router.get("/geo/within")
def get_within(
    project_id: str, min_lat: float, min_lng: float, max_lat: float, max_lng: float,
    store: GraphStore = Depends(get_graph_store),
):
    """Entities whose coordinates fall inside a bounding box — the "what's in
    this area" (AOI) query. Reuses the same coordinate resolver as the map.

    Flat bbox: does not handle antimeridian crossing (a view straddling 180°
    longitude would miss the far side) — fine for typical AOIs.
    """
    inside = [
        loc for loc in geolocate_entities(store, project_id)
        if loc["latitude"] is not None and loc["longitude"] is not None
        and min_lat <= loc["latitude"] <= max_lat
        and min_lng <= loc["longitude"] <= max_lng
    ]
    return {
        "entities": inside,
        "count": len(inside),
        "bbox": {"min_lat": min_lat, "min_lng": min_lng, "max_lat": max_lat, "max_lng": max_lng},
    }


@router.get("/geo/nearby/{entity_id}")
async def get_nearby(entity_id: str, radius: int = 2000, store: GraphStore = Depends(get_graph_store)):
    """Nearby OSM features (airfields / military / ports / infrastructure /
    government / neighbourhoods) around a geolocated entity — local GEOINT
    context via Overpass. Best-effort: returns [] if the entity has no
    coordinates or Overpass is unreachable."""
    # Neo4j driver is synchronous; offload so it doesn't block the event loop.
    entity = await asyncio.to_thread(store.get_entity, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    lat, lng, _ = _extract_coords(entity)
    if lat is None:
        return {"features": [], "count": 0, "center": None, "error": "entity has no coordinates"}
    radius = max(100, min(radius, 20000))  # clamp 100m..20km

    from intel_platform.services.geo.overpass import nearby_features
    features = await nearby_features(ProxiedClient(), settings.overpass_base_url, lat, lng, radius)
    return {
        "features": features,
        "count": len(features),
        "center": {"lat": lat, "lng": lng},
        "radius": radius,
    }


@router.get("/geo/entity-timeline")
def get_entity_timeline(
    entity_id: str,
    project_id: str,
    store: GraphStore = Depends(get_graph_store),
):
    """Get temporal data for an entity — event dates, relationship dates, document ingestion dates.

    Returns bucketed counts for the traffic frequency chart and raw events for the temporal window.
    """
    entity = store.get_entity(entity_id)
    if not entity:
        return {"events": [], "buckets": [], "date_range": None}

    events = []

    # 1. Entity's own creation/event date
    created = normalize_datetime(entity.get("created_at"))
    if created:
        events.append({
            "date": created,
            "type": "entity_created",
            "label": f"{entity.get('name', '')} first observed",
        })

    # Check for event_datetime on Event entities
    event_dt = entity.get("event_datetime")
    if event_dt:
        parsed = normalize_datetime(event_dt)
        if parsed:
            events.append({"date": parsed, "type": "event", "label": entity.get("name", "")})

    # 2. Connected entities — their dates
    rels = store.get_relationships(entity_id)
    for rel in rels:
        # Relationship first_seen
        first_seen = rel.get("first_seen") or rel.get("props", {}).get("first_seen")
        if first_seen:
            parsed = normalize_datetime(first_seen)
            if parsed:
                target_name = rel.get("target_name", "")
                events.append({
                    "date": parsed,
                    "type": "relationship",
                    "label": f"{rel.get('rel_type', '')} → {target_name}",
                })

        # PERF: single fetch per relationship target instead of separate fetches
        # for Date and Document checks
        target = store.get_entity(rel.get("target_id", ""))
        rel_type = rel.get("rel_type", "")

        # Connected Date entities (OCCURRED_ON relationships)
        if rel_type == "OCCURRED_ON" and target and target.get("entity_type") == "Date":
            events.append({
                "date": target.get("name", ""),
                "type": "event_date",
                "label": f"Event on {target.get('name', '')}",
            })

        # Connected Document entities — ingestion date
        if target and target.get("entity_type") == "Document":
            doc_created = normalize_datetime(target.get("created_at"))
            if doc_created:
                events.append({
                    "date": doc_created,
                    "type": "document_ingested",
                    "label": f"Source: {target.get('name', '')}",
                })

    # Sort by date
    events.sort(key=lambda e: e.get("date", ""))

    # Compute date range
    dates = [e["date"] for e in events if e.get("date")]
    date_range = None
    if dates:
        date_range = {"start": min(dates), "end": max(dates)}

    # Bucket into time periods for the bar chart (by day)
    buckets: dict[str, int] = defaultdict(int)
    for e in events:
        d = e.get("date", "")
        if d and len(d) >= 10:
            day = d[:10]  # YYYY-MM-DD
            buckets[day] += 1

    sorted_buckets = [{"date": k, "count": v} for k, v in sorted(buckets.items())]

    return {
        "entity_id": entity_id,
        "entity_name": entity.get("name", ""),
        "events": events,
        "buckets": sorted_buckets,
        "date_range": date_range,
        "total_events": len(events),
    }
