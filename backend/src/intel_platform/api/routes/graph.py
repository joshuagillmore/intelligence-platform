from fastapi import APIRouter, Depends

from intel_platform.api.cache import cached
from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore
from intel_platform.services.enrichment import (
    compute_degree_centrality, detect_communities, compute_all_statistics,
)

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/graph")
def get_full_graph(project_id: str, limit: int = 500, store: GraphStore = Depends(get_graph_store)):
    return store.get_full_graph(project_id=project_id, limit=limit)


@router.get("/communities")
@cached(ttl=30)
def get_communities(project_id: str, store: GraphStore = Depends(get_graph_store)):
    return detect_communities(store, project_id)


@router.get("/graph/centrality")
def get_centrality(project_id: str, store: GraphStore = Depends(get_graph_store)):
    return compute_degree_centrality(store, project_id)


@router.get("/graph/statistics")
@cached(ttl=30)
def get_statistics(project_id: str, store: GraphStore = Depends(get_graph_store)):
    return compute_all_statistics(store, project_id)
