from fastapi import APIRouter, Depends
from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore
from intel_platform.services.text_utils import normalize_datetime

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/timeline")
def get_timeline(project_id: str, store: GraphStore = Depends(get_graph_store)):
    """Get a timeline of entities and events, ordered by real event date when known.

    Entities with a populated ``event_datetime`` (extraction resolved a real-world
    date from the source text) are timestamped and labeled by that; everything
    else falls back to ``created_at`` (ingestion time) — the same fallback
    pattern geo.py's entity-timeline endpoint uses.
    """
    entities = store.search_entities(project_id=project_id, limit=500)

    timeline_events = []
    for e in entities:
        event_dt = normalize_datetime(e.get("event_datetime"))
        if event_dt:
            timestamp = event_dt
            event_type = "event"
        else:
            timestamp = normalize_datetime(e.get("created_at"))
            event_type = "entity_created"

        timeline_events.append({
            "id": e.get("id", ""),
            "name": e.get("name", ""),
            "entity_type": e.get("entity_type", ""),
            "timestamp": timestamp,
            "event_type": event_type,
        })

    # Sort by timestamp
    timeline_events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return {"events": timeline_events, "count": len(timeline_events)}
