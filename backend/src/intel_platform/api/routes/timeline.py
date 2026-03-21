from fastapi import APIRouter, Depends
from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/timeline")
def get_timeline(project_id: str, store: GraphStore = Depends(get_graph_store)):
    """Get a timeline of all entities and events ordered by creation/ingestion time."""
    entities = store.search_entities(project_id=project_id, limit=500)

    timeline_events = []
    for e in entities:
        created = e.get("created_at", "")
        # Handle Neo4j datetime objects
        if isinstance(created, dict):
            # Neo4j returns complex datetime objects
            dt = created.get("_DateTime__date", {})
            tm = created.get("_DateTime__time", {})
            year = dt.get("_Date__year", 2026)
            month = dt.get("_Date__month", 1)
            day = dt.get("_Date__day", 1)
            hour = tm.get("_Time__hour", 0)
            minute = tm.get("_Time__minute", 0)
            created = f"{year}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00Z"
        elif hasattr(created, "isoformat"):
            created = created.isoformat()
        else:
            created = str(created) if created else ""

        timeline_events.append({
            "id": e.get("id", ""),
            "name": e.get("name", ""),
            "entity_type": e.get("entity_type", ""),
            "timestamp": created,
            "event_type": "entity_created",
        })

    # Sort by timestamp
    timeline_events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return {"events": timeline_events, "count": len(timeline_events)}
