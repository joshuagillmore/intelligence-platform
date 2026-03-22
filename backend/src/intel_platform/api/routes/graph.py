from fastapi import APIRouter, Depends

from intel_platform.api.cache import cached
from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore
from intel_platform.services.enrichment import (
    compute_degree_centrality, detect_communities, compute_all_statistics,
)

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/graph")
def get_full_graph(project_id: str, limit: int = 500, min_centrality: float = 0, store: GraphStore = Depends(get_graph_store)):
    data = store.get_full_graph(project_id=project_id, limit=limit)

    # Compute communities and attach to nodes
    import networkx as nx
    from intel_platform.services.enrichment import _build_networkx_graph

    try:
        G = _build_networkx_graph(store, project_id)

        # Get community assignments
        try:
            import community as community_louvain
            partition = community_louvain.best_partition(G)
        except ImportError:
            from networkx.algorithms.community import greedy_modularity_communities
            comms = greedy_modularity_communities(G)
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
            enriched_edges.append({
                "source_id": edge.get("source_id", ""),
                "target_id": edge.get("target_id", ""),
                "rel_type": edge.get("rel_type", ""),
                "confidence": edge.get("confidence", edge.get("props", {}).get("confidence", 0.5)),
            })

    return {
        "nodes": enriched_nodes,
        "edges": enriched_edges,
        "node_count": len(enriched_nodes),
        "edge_count": len(enriched_edges),
    }


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
