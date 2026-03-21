from fastapi import APIRouter, Depends, HTTPException

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/entities")
def search_entities(
    project_id: str, query: str = "", entity_type: str | None = None,
    limit: int = 50, offset: int = 0,
    store: GraphStore = Depends(get_graph_store),
):
    return store.search_entities(
        project_id=project_id, query=query, entity_type=entity_type,
        limit=limit, offset=offset,
    )


@router.get("/entities/{entity_id}")
def get_entity(entity_id: str, store: GraphStore = Depends(get_graph_store)):
    entity = store.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    relationships = store.get_relationships(entity_id)
    return {"entity": entity, "relationships": relationships}


@router.get("/subgraph/{entity_id}")
def get_subgraph(entity_id: str, hops: int = 1, store: GraphStore = Depends(get_graph_store)):
    return store.get_subgraph(entity_id, hops=hops)


@router.get("/paths/{entity_id_1}/{entity_id_2}")
def find_shortest_path(entity_id_1: str, entity_id_2: str, store: GraphStore = Depends(get_graph_store)):
    return store.find_shortest_path(entity_id_1, entity_id_2)
