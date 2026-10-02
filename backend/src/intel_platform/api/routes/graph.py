from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from intel_platform.api.cache import cached
from intel_platform.api.deps import get_graph_store, project_exists, verify_api_key
from intel_platform.graph.store import GraphStore
from intel_platform.models.responses import (
    CentralityItem,
    CommunityItem,
    EgoNetworkResponse,
    GraphStatisticsResponse,
    GraphViewResponse,
    InfluenceResponse,
    StructuralHoleItem,
)
from intel_platform.services.enrichment import (
    build_networkx_from_data,
    compute_degree_centrality, detect_communities, compute_all_statistics,
    compute_structural_holes, extract_ego_network, compute_influence_propagation,
)

router = APIRouter(dependencies=[Depends(verify_api_key)])


def _edge_prop(edge: dict, key: str, default=None):
    """An edge property, whether the store flattened it or nested it under `props`."""
    value = edge.get(key, edge.get("props", {}).get(key))
    return default if value is None else value


@router.get("/graph", response_model=GraphViewResponse)
def get_full_graph(
    project_id: str,
    limit: int = Query(500, ge=1, le=10000),
    min_centrality: float = 0,
    store: GraphStore = Depends(get_graph_store),
):
    import networkx as nx

    data = store.get_full_graph(project_id=project_id, limit=limit)

    # Built from the fetched display slice and never cached. `graph_cache` holds
    # the analytics graph (centrality, communities, statistics) that expects the
    # whole project; caching this `limit`-truncated slice under the same key made
    # every analytic depend on which request came first — `/graph?limit=1`
    # poisoned them all for five minutes.
    G = build_networkx_from_data(data)

    try:
        # Get community assignments (Louvain needs undirected)
        G_undirected = G.to_undirected()
        try:
            import community as community_louvain
            partition = community_louvain.best_partition(G_undirected)
        except ImportError:
            from networkx.algorithms.community import greedy_modularity_communities
            comms = greedy_modularity_communities(G_undirected)
            partition = {}
            for i, comm in enumerate(comms):
                for node in comm:
                    partition[node] = i

        # Get centrality
        pr = nx.pagerank(G) if G.nodes else {}
        degree = dict(G.degree()) if G.nodes else {}
    except Exception:
        partition = {}
        pr = {}
        degree = {}

    # Enrich nodes with community and centrality
    enriched_nodes = []
    for node in data.get("nodes", []):
        nid = node.get("id", "")
        enriched = {
            "id": nid,
            "name": node.get("name", ""),
            "entity_type": node.get("entity_type", ""),
            "entity_category": node.get("entity_category", ""),
            "community_id": partition.get(nid, -1),
            "pagerank": round(pr.get(nid, 0), 6),
            "degree": degree.get(nid, 0),
            # When the thing happened, so the network view can be filtered on
            # real chronology. Deliberately not created_at: filtering a graph by
            # ingestion time draws a picture of when the crawler ran.
            "event_datetime": node.get("event_datetime") or "",
            "date_precision": node.get("date_precision", ""),
            "date_text": node.get("date_text", ""),
        }

        # Filter by min centrality if specified
        if min_centrality > 0 and enriched["pagerank"] < min_centrality:
            continue

        enriched_nodes.append(enriched)

    # Filter edges to only include visible nodes
    visible_ids = {n["id"] for n in enriched_nodes}
    enriched_edges = []
    for edge in data.get("edges", []):
        if edge.get("source_id") in visible_ids and edge.get("target_id") in visible_ids:
            # Contract 4: what the evidence panel needs about each edge. The
            # three identifying keys are unchanged — GraphVisualization reads them.
            enriched_edges.append({
                "source_id": edge.get("source_id", ""),
                "target_id": edge.get("target_id", ""),
                "rel_type": edge.get("rel_type", ""),
                "confidence": _edge_prop(edge, "confidence", 0.5),
                "evidence": str(_edge_prop(edge, "evidence", "")),
                "method": str(_edge_prop(edge, "method", "")),
                "source_doc_id": str(_edge_prop(edge, "source_doc_id", "")),
                # An edge written before polarity was recorded is an assertion.
                "polarity": _edge_prop(edge, "polarity", "asserts"),
                "first_seen": _edge_prop(edge, "first_seen"),
                "last_seen": _edge_prop(edge, "last_seen"),
            })

    # The same node set get_full_graph draws its slice from, counted in full, so
    # the view can say "showing N of M" with a real M.
    total_nodes = store.count_entities(project_id=project_id)
    return {
        "project_exists": project_exists(store, project_id),
        "nodes": enriched_nodes,
        "edges": enriched_edges,
        "node_count": len(enriched_nodes),
        "edge_count": len(enriched_edges),
        "total_nodes": total_nodes,
        # Whether the project holds more than this view shows. The store reports
        # it (contract 3); otherwise it follows from the true count.
        "truncated": bool(data.get("truncated", total_nodes > len(data.get("nodes", [])))),
    }


@router.get("/communities", response_model=list[CommunityItem])
@cached(ttl=30)
def get_communities(project_id: str, store: GraphStore = Depends(get_graph_store)):
    return detect_communities(store, project_id)


@router.get("/graph/centrality", response_model=list[CentralityItem])
def get_centrality(project_id: str, store: GraphStore = Depends(get_graph_store)):
    return compute_degree_centrality(store, project_id)


@router.get("/graph/statistics", response_model=GraphStatisticsResponse)
@cached(ttl=30)
def get_statistics(project_id: str, store: GraphStore = Depends(get_graph_store)):
    # `project_exists` is added only where the response is already an object.
    # /communities and /graph/centrality return bare lists, and wrapping those
    # to carry the flag would be the breaking change this approach exists to
    # avoid — callers can read it from /graph or /graph/statistics instead.
    return {
        **compute_all_statistics(store, project_id),
        "project_exists": project_exists(store, project_id),
    }


@router.get("/graph/structural-holes", response_model=list[StructuralHoleItem])
@cached(ttl=30)
def get_structural_holes(
    project_id: str, top_n: int = Query(20, ge=1, le=1000), store: GraphStore = Depends(get_graph_store),
):
    return compute_structural_holes(store, project_id, top_n=top_n)


@router.get("/graph/ego-network/{entity_id}", response_model=EgoNetworkResponse, response_model_exclude_unset=True)
def get_ego_network(
    entity_id: str, project_id: str, hops: int = Query(2, ge=1, le=4),
    store: GraphStore = Depends(get_graph_store),
):
    return extract_ego_network(store, project_id, entity_id, hops=hops)


class InfluenceRequest(BaseModel):
    """Typed so a malformed body is a 422 rather than a failure inside the walk."""

    project_id: str
    seed_ids: list[str]
    steps: int = Field(default=3, ge=1, le=10)
    threshold: float = Field(default=0.3, ge=0.0, le=1.0)


@router.post("/graph/influence", response_model=InfluenceResponse, response_model_exclude_unset=True)
def post_influence_propagation(
    body: InfluenceRequest,
    store: GraphStore = Depends(get_graph_store),
):
    return compute_influence_propagation(
        store, body.project_id, body.seed_ids, steps=body.steps, threshold=body.threshold
    )
