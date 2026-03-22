from __future__ import annotations

import networkx as nx

from intel_platform.graph.store import GraphStore
from intel_platform.services.graph_cache import graph_cache


# Tactical relationship types that should have higher weight in analysis
_TACTICAL_REL_TYPES = {"TARGETS", "USES", "EXPLOITS", "COMMUNICATES_WITH", "ATTRIBUTED_TO", "COMMANDED_BY"}


def build_networkx_from_data(data: dict) -> nx.DiGraph:
    """Build NetworkX directed graph from already-fetched graph data.

    Edges are weighted by confidence and relationship type:
    - Tactical relationships (TARGETS, USES, EXPLOITS, etc.) get a 1.5x boost
    - Generic ASSOCIATED_WITH uses raw confidence (typically 0.5)
    """
    G = nx.DiGraph()
    for node in data.get("nodes", []):
        nid = node.get("id", "")
        if nid:
            G.add_node(nid, **{k: v for k, v in node.items() if k != "id" and not isinstance(v, (dict, list))})
    for edge in data.get("edges", []):
        sid = edge.get("source_id", "")
        tid = edge.get("target_id", "")
        if sid and tid:
            props = {k: v for k, v in edge.items() if k not in ("source_id", "target_id") and not isinstance(v, (dict, list))}
            # Weight edges by confidence and relationship type
            confidence = float(edge.get("confidence", 0.5))
            rel_type = edge.get("rel_type", "ASSOCIATED_WITH")
            weight = confidence * (1.5 if rel_type in _TACTICAL_REL_TYPES else 1.0)
            props["weight"] = round(weight, 4)
            G.add_edge(sid, tid, **props)
    return G


def _build_networkx_graph(store: GraphStore, project_id: str) -> nx.DiGraph:
    """Build (or retrieve from cache) the NetworkX DiGraph for a project."""
    def _builder() -> nx.DiGraph:
        data = store.get_full_graph(project_id=project_id, limit=10000)
        return build_networkx_from_data(data)

    return graph_cache.get_or_build_graph(project_id, _builder)


def compute_degree_centrality(store: GraphStore, project_id: str, *, graph: nx.DiGraph | None = None) -> list[dict]:
    G = graph if graph is not None else _build_networkx_graph(store, project_id)
    if not G.nodes:
        return []
    result = []
    for node_id, degree in G.degree():
        node_data = G.nodes[node_id]
        result.append({
            "id": node_id, "name": node_data.get("name", ""),
            "entity_type": node_data.get("entity_type", ""), "degree": degree,
        })
    return sorted(result, key=lambda x: x["degree"], reverse=True)


def compute_betweenness_centrality(store: GraphStore, project_id: str, *, graph: nx.DiGraph | None = None) -> list[dict]:
    G = graph if graph is not None else _build_networkx_graph(store, project_id)
    if not G.nodes:
        return []
    bc = nx.betweenness_centrality(G)
    result = []
    for node_id, score in bc.items():
        node_data = G.nodes[node_id]
        result.append({
            "id": node_id, "name": node_data.get("name", ""),
            "entity_type": node_data.get("entity_type", ""), "betweenness": round(score, 4),
        })
    return sorted(result, key=lambda x: x["betweenness"], reverse=True)


def detect_communities(store: GraphStore, project_id: str, *, graph: nx.DiGraph | None = None) -> list[dict]:
    G = graph if graph is not None else _build_networkx_graph(store, project_id)
    if not G.nodes:
        return []

    # Louvain requires an undirected graph
    G_undirected = G.to_undirected()

    try:
        import community as community_louvain
        partition = community_louvain.best_partition(G_undirected)
    except ImportError:
        from networkx.algorithms.community import greedy_modularity_communities
        communities = greedy_modularity_communities(G_undirected)
        partition = {}
        for i, comm in enumerate(communities):
            for node in comm:
                partition[node] = i

    community_groups: dict[int, list[dict]] = {}
    for node_id, comm_id in partition.items():
        node_data = G.nodes[node_id]
        entry = {"id": node_id, "name": node_data.get("name", ""),
                 "entity_type": node_data.get("entity_type", "")}
        community_groups.setdefault(comm_id, []).append(entry)

    return [
        {"community_id": comm_id, "members": members, "size": len(members)}
        for comm_id, members in community_groups.items()
    ]


def compute_pagerank(store: GraphStore, project_id: str, *, graph: nx.DiGraph | None = None) -> list[dict]:
    G = graph if graph is not None else _build_networkx_graph(store, project_id)
    if not G.nodes:
        return []
    pr = nx.pagerank(G)
    result = []
    for node_id, score in pr.items():
        node_data = G.nodes[node_id]
        result.append({
            "id": node_id, "name": node_data.get("name", ""),
            "entity_type": node_data.get("entity_type", ""), "pagerank": round(score, 6),
        })
    return sorted(result, key=lambda x: x["pagerank"], reverse=True)


def compute_eigenvector_centrality(store: GraphStore, project_id: str, *, graph: nx.DiGraph | None = None) -> list[dict]:
    G = graph if graph is not None else _build_networkx_graph(store, project_id)
    if not G.nodes or not G.edges:
        return []
    try:
        ec = nx.eigenvector_centrality(G, max_iter=1000)
    except nx.PowerIterationFailedConvergence:
        return []
    result = []
    for node_id, score in ec.items():
        node_data = G.nodes[node_id]
        result.append({
            "id": node_id, "name": node_data.get("name", ""),
            "entity_type": node_data.get("entity_type", ""), "eigenvector": round(score, 6),
        })
    return sorted(result, key=lambda x: x["eigenvector"], reverse=True)


def compute_all_statistics(store: GraphStore, project_id: str, *, graph: nx.DiGraph | None = None) -> dict:
    """Compute all network statistics in one call."""
    G = graph if graph is not None else _build_networkx_graph(store, project_id)
    if not G.nodes:
        return {"nodes": 0, "edges": 0, "density": 0, "components": 0, "entities": []}

    # Check metrics cache
    cached = graph_cache.get_metric(project_id, "all_statistics")
    if cached is not None:
        return cached

    # Graph-level stats (use weakly_connected_components for DiGraph)
    stats = {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "density": round(nx.density(G), 6),
        "components": nx.number_weakly_connected_components(G),
    }

    # Per-node stats
    degree = dict(G.degree())
    in_degree = dict(G.in_degree())
    out_degree = dict(G.out_degree())
    bc = nx.betweenness_centrality(G)
    pr = nx.pagerank(G)

    try:
        ec = nx.eigenvector_centrality(G, max_iter=1000)
    except (nx.PowerIterationFailedConvergence, nx.NetworkXError):
        ec = {n: 0.0 for n in G.nodes}

    try:
        cc = nx.closeness_centrality(G)
    except nx.NetworkXError:
        cc = {n: 0.0 for n in G.nodes}

    entities = []
    for node_id in G.nodes:
        node_data = G.nodes[node_id]
        entities.append({
            "id": node_id,
            "name": node_data.get("name", ""),
            "entity_type": node_data.get("entity_type", ""),
            "degree": degree.get(node_id, 0),
            "in_degree": in_degree.get(node_id, 0),
            "out_degree": out_degree.get(node_id, 0),
            "betweenness": round(bc.get(node_id, 0), 6),
            "eigenvector": round(ec.get(node_id, 0), 6),
            "pagerank": round(pr.get(node_id, 0), 6),
            "closeness": round(cc.get(node_id, 0), 6),
        })

    entities.sort(key=lambda x: x["pagerank"], reverse=True)
    stats["entities"] = entities

    # Cache the computed result
    graph_cache.set_metric(project_id, "all_statistics", stats)

    return stats
