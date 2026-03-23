from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore

router = APIRouter(dependencies=[Depends(verify_api_key)])


class WatchlistRequest(BaseModel):
    project_id: str
    entity_id: str


@router.post("/watchlist/add")
def add_to_watchlist(req: WatchlistRequest, store: GraphStore = Depends(get_graph_store)):
    entity = store.get_entity(req.entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    with store._driver.session() as session:
        session.run(
            """
            MERGE (w:Watchlist {project_id: $project_id, entity_id: $entity_id})
            ON CREATE SET w.created_at = datetime()
            """,
            project_id=req.project_id, entity_id=req.entity_id,
        )

    # Count watchlist entries for this project
    with store._driver.session() as session:
        result = session.run(
            "MATCH (w:Watchlist {project_id: $pid}) RETURN count(w) as cnt",
            pid=req.project_id,
        )
        count = result.single()["cnt"]

    return {
        "entity_id": req.entity_id,
        "entity_name": entity.get("name"),
        "status": "watching",
        "watchlist_size": count,
    }


@router.post("/watchlist/remove")
def remove_from_watchlist(req: WatchlistRequest, store: GraphStore = Depends(get_graph_store)):
    with store._driver.session() as session:
        session.run(
            "MATCH (w:Watchlist {project_id: $project_id, entity_id: $entity_id}) DELETE w",
            project_id=req.project_id, entity_id=req.entity_id,
        )
    return {"entity_id": req.entity_id, "status": "removed"}


@router.get("/watchlist")
def get_watchlist(project_id: str, store: GraphStore = Depends(get_graph_store)):
    with store._driver.session() as session:
        result = session.run(
            """
            MATCH (w:Watchlist {project_id: $pid})
            MATCH (e {id: w.entity_id})
            OPTIONAL MATCH (e)-[r]-()
            RETURN w.entity_id as eid, e.name as name, e.entity_type as entity_type, count(r) as rel_count
            """,
            pid=project_id,
        )
        watched = []
        for record in result:
            watched.append({
                "id": record["eid"],
                "name": record["name"],
                "entity_type": record["entity_type"],
                "relationship_count": record["rel_count"],
            })
    return {"watched_entities": watched, "count": len(watched)}
