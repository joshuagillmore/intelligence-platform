from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore

router = APIRouter(dependencies=[Depends(verify_api_key)])

# In-memory watchlist (per project)
_watchlists: dict[str, set[str]] = {}


class WatchlistRequest(BaseModel):
    project_id: str
    entity_id: str


@router.post("/watchlist/add")
def add_to_watchlist(req: WatchlistRequest, store: GraphStore = Depends(get_graph_store)):
    entity = store.get_entity(req.entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    if req.project_id not in _watchlists:
        _watchlists[req.project_id] = set()
    _watchlists[req.project_id].add(req.entity_id)

    return {
        "entity_id": req.entity_id,
        "entity_name": entity.get("name"),
        "status": "watching",
        "watchlist_size": len(_watchlists[req.project_id]),
    }


@router.post("/watchlist/remove")
def remove_from_watchlist(req: WatchlistRequest):
    if req.project_id in _watchlists:
        _watchlists[req.project_id].discard(req.entity_id)
    return {"entity_id": req.entity_id, "status": "removed"}


@router.get("/watchlist")
def get_watchlist(project_id: str, store: GraphStore = Depends(get_graph_store)):
    entity_ids = _watchlists.get(project_id, set())
    watched = []
    for eid in entity_ids:
        entity = store.get_entity(eid)
        if entity:
            rels = store.get_relationships(eid)
            watched.append({
                "id": eid,
                "name": entity.get("name"),
                "entity_type": entity.get("entity_type"),
                "relationship_count": len(rels),
            })
    return {"watched_entities": watched, "count": len(watched)}
