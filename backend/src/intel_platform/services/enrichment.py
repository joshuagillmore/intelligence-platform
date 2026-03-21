from __future__ import annotations

import networkx as nx

from intel_platform.graph.store import GraphStore


def _build_networkx_graph(store: GraphStore, project_id: str) -> nx.Graph:
    data = store.get_full_graph(project_id=project_id, limit=10000)
    G = nx.Graph()
    for node in data["nodes"]:
        G.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
    for edge in data["edges"]:
        G.add_edge(edge["source_id"], edge["target_id"],
                   **{k: v for k, v in edge.items() if k not in ("source_id", "target_id")})
    return G


def compute_degree_centrality(store: GraphStore, project_id: str) -> list[dict]:
    G = _build_networkx_graph(store, project_id)
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


def compute_betweenness_centrality(store: GraphStore, project_id: str) -> list[dict]:
    G = _build_networkx_graph(store, project_id)
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


def detect_communities(store: GraphStore, project_id: str) -> list[dict]:
    G = _build_networkx_graph(store, project_id)
    if not G.nodes:
        return []
    try:
        import community as community_louvain
        partition = community_louvain.best_partition(G)
    except ImportError:
        from networkx.algorithms.community import greedy_modularity_communities
        communities = greedy_modularity_communities(G)
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


def compute_pagerank(store: GraphStore, project_id: str) -> list[dict]:
    G = _build_networkx_graph(store, project_id)
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


def compute_eigenvector_centrality(store: GraphStore, project_id: str) -> list[dict]:
    G = _build_networkx_graph(store, project_id)
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


def compute_all_statistics(store: GraphStore, project_id: str) -> dict:
    """Compute all network statistics in one call."""
    G = _build_networkx_graph(store, project_id)
    if not G.nodes:
        return {"nodes": 0, "edges": 0, "density": 0, "components": 0, "entities": []}

    # Graph-level stats
    stats = {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "density": round(nx.density(G), 6),
        "components": nx.number_connected_components(G),
    }

    # Per-node stats
    degree = dict(G.degree())
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
            "betweenness": round(bc.get(node_id, 0), 6),
            "eigenvector": round(ec.get(node_id, 0), 6),
            "pagerank": round(pr.get(node_id, 0), 6),
            "closeness": round(cc.get(node_id, 0), 6),
        })

    entities.sort(key=lambda x: x["pagerank"], reverse=True)
    stats["entities"] = entities
    return stats
