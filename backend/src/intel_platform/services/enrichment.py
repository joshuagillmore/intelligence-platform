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


def compute_structural_holes(
    store: GraphStore, project_id: str, *, graph: nx.DiGraph | None = None, top_n: int = 20
) -> list[dict]:
    """Compute Burt's structural-hole metrics (constraint & effective size).

    Entities with LOW constraint and HIGH effective size sit in structural holes —
    they bridge otherwise disconnected groups (brokers, gatekeepers, intermediaries).
    """
    G = graph if graph is not None else _build_networkx_graph(store, project_id)
    if not G.nodes:
        return []

    constraint = nx.constraint(G)
    eff_size = nx.effective_size(G)

    result = []
    for node_id in G.nodes:
        node_data = G.nodes[node_id]
        c = constraint.get(node_id, 0.0)
        es = eff_size.get(node_id, 0.0)
        # Skip isolates (no structural hole relevance)
        if G.degree(node_id) == 0:
            continue
        result.append({
            "id": node_id,
            "name": node_data.get("name", ""),
            "entity_type": node_data.get("entity_type", ""),
            "constraint": round(c, 6) if c == c else 0.0,  # guard NaN
            "effective_size": round(es, 4) if es == es else 0.0,
            "degree": G.degree(node_id),
            "is_broker": c < 0.5 and es > 1.5 and G.degree(node_id) >= 3,
        })
    result.sort(key=lambda x: x["constraint"])
    return result[:top_n]


def extract_ego_network(
    store: GraphStore,
    project_id: str,
    entity_id: str,
    *,
    hops: int = 2,
    graph: nx.DiGraph | None = None,
) -> dict:
    """Extract the k-hop ego network around a target entity.

    Returns the subgraph nodes, edges, and per-node metrics relative to
    the ego entity (distance, local centrality).
    """
    G = graph if graph is not None else _build_networkx_graph(store, project_id)
    if entity_id not in G:
        return {"center": entity_id, "nodes": [], "edges": [], "hops": hops}

    # BFS to find nodes within k hops (respects direction outward, but also inward)
    ego_nodes: dict[str, int] = {entity_id: 0}
    frontier = [entity_id]
    for depth in range(1, hops + 1):
        next_frontier: list[str] = []
        for nid in frontier:
            for neighbor in set(G.successors(nid)) | set(G.predecessors(nid)):
                if neighbor not in ego_nodes:
                    ego_nodes[neighbor] = depth
                    next_frontier.append(neighbor)
        frontier = next_frontier

    # Build subgraph
    sub = G.subgraph(ego_nodes.keys()).copy()

    # Compute local metrics on the subgraph
    local_pr = nx.pagerank(sub) if sub.nodes else {}
    local_bc = nx.betweenness_centrality(sub) if sub.nodes else {}

    nodes = []
    for nid, dist in ego_nodes.items():
        nd = G.nodes[nid]
        nodes.append({
            "id": nid,
            "name": nd.get("name", ""),
            "entity_type": nd.get("entity_type", ""),
            "hop_distance": dist,
            "local_pagerank": round(local_pr.get(nid, 0), 6),
            "local_betweenness": round(local_bc.get(nid, 0), 6),
        })

    edges = []
    for u, v, data in sub.edges(data=True):
        edges.append({
            "source_id": u,
            "target_id": v,
            "rel_type": data.get("rel_type", "ASSOCIATED_WITH"),
            "confidence": data.get("confidence", 0.5),
            "weight": data.get("weight", 0.5),
        })

    return {
        "center": entity_id,
        "hops": hops,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": sorted(nodes, key=lambda x: x["hop_distance"]),
        "edges": edges,
    }


def compute_influence_propagation(
    store: GraphStore,
    project_id: str,
    seed_ids: list[str],
    *,
    steps: int = 3,
    threshold: float = 0.3,
    graph: nx.DiGraph | None = None,
) -> dict:
    """Simulate influence propagation using a weighted Independent Cascade model.

    Starting from seed entities, propagates influence along directed edges.
    At each step, an activated node activates each inactive neighbor with
    probability = edge weight (capped by threshold). Returns per-step
    activation results and final reach statistics.
    """
    G = graph if graph is not None else _build_networkx_graph(store, project_id)
    if not G.nodes:
        return {"seeds": seed_ids, "steps": [], "total_activated": 0, "reach_ratio": 0}

    import random
    random.seed(42)  # deterministic for reproducibility

    activated: set[str] = set()
    step_results: list[dict] = []

    # Validate seeds
    valid_seeds = [s for s in seed_ids if s in G]
    if not valid_seeds:
        return {"seeds": seed_ids, "steps": [], "total_activated": 0, "reach_ratio": 0}

    newly_activated = set(valid_seeds)
    activated.update(newly_activated)

    step_results.append({
        "step": 0,
        "newly_activated": [
            {"id": nid, "name": G.nodes[nid].get("name", ""), "entity_type": G.nodes[nid].get("entity_type", "")}
            for nid in newly_activated
        ],
        "cumulative_count": len(activated),
    })

    for step in range(1, steps + 1):
        next_activated: set[str] = set()
        for nid in newly_activated:
            for neighbor in G.successors(nid):
                if neighbor in activated:
                    continue
                edge_weight = G[nid][neighbor].get("weight", 0.5)
                prob = min(edge_weight, 1.0)
                if prob >= threshold and random.random() < prob:
                    next_activated.add(neighbor)

        activated.update(next_activated)
        newly_activated = next_activated

        step_results.append({
            "step": step,
            "newly_activated": [
                {"id": nid, "name": G.nodes[nid].get("name", ""), "entity_type": G.nodes[nid].get("entity_type", "")}
                for nid in next_activated
            ],
            "cumulative_count": len(activated),
        })

        if not next_activated:
            break  # No more propagation

    total = G.number_of_nodes()
    return {
        "seeds": valid_seeds,
        "steps": step_results,
        "total_activated": len(activated),
        "reach_ratio": round(len(activated) / total, 4) if total > 0 else 0,
        "total_nodes": total,
    }
