from collections import defaultdict
from fastapi import APIRouter, Depends
from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore
from intel_platform.services.geocoding import geocode_all_locations

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
        if loc.get("geocoded") and loc.get("latitude") and loc.get("longitude"):
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
    """Get all locations with coordinates, relationships, and inter-location edges."""
    locations = geocode_all_locations(store, project_id)

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

    # Compute location-to-location edges via shared entities
    geo_edges = _compute_location_edges(locations, store)

    return {
        "locations": locations,
        "edges": geo_edges,
        "total": len(locations),
        "geocoded": sum(1 for l in locations if l.get("geocoded")),
        "edge_count": len(geo_edges),
    }
