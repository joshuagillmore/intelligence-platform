from fastapi import APIRouter, Depends
from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore
from intel_platform.services.geocoding import geocode_all_locations

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/geo/locations")
def get_geo_locations(project_id: str, store: GraphStore = Depends(get_graph_store)):
    """Get all locations with coordinates and their relationships."""
    locations = geocode_all_locations(store, project_id)

    # Enrich with relationships
    for loc in locations:
        if loc.get("id"):
            rels = store.get_relationships(loc["id"])
            loc["relationships"] = [
                {"target_name": r.get("target_name"), "rel_type": r.get("rel_type"),
                 "confidence": r.get("confidence", r.get("props", {}).get("confidence"))}
                for r in rels
            ]
            loc["connection_count"] = len(rels)

    return {
        "locations": locations,
        "total": len(locations),
        "geocoded": sum(1 for l in locations if l.get("geocoded")),
    }
