from fastapi import APIRouter, Depends

from intel_platform.api.cache import cached
from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore
from intel_platform.services.enrichment import (
    build_networkx_from_data,
    compute_degree_centrality, detect_communities, compute_all_statistics,
)
from intel_platform.services.graph_cache import graph_cache

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/graph")
def get_full_graph(project_id: str, limit: int = 500, min_centrality: float = 0, store: GraphStore = Depends(get_graph_store)):
    import networkx as nx

    data = store.get_full_graph(project_id=project_id, limit=limit)

    # PERF: reuse already-fetched data for building the NetworkX graph
    # instead of issuing a second query to Neo4j
    G = graph_cache.get_or_build_graph(
        project_id,
        lambda: build_networkx_from_data(data),
    )

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
                "first_seen": edge.get("first_seen", edge.get("props", {}).get("first_seen")),
                "last_seen": edge.get("last_seen", edge.get("props", {}).get("last_seen")),
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
