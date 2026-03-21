from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Intelligence Platform")


@mcp.tool()
def search_entities(project_id: str, query: str = "", entity_type: str | None = None) -> dict:
    """Search for entities in the knowledge graph by name or type."""
    from intel_platform.api.deps import get_neo4j_driver
    from intel_platform.graph.store import GraphStore
    driver = get_neo4j_driver()
    store = GraphStore(driver)
    results = store.search_entities(project_id=project_id, query=query, entity_type=entity_type, limit=20)
    return {"entities": results, "count": len(results)}


@mcp.tool()
def get_subgraph(entity_id: str, hops: int = 1) -> dict:
    """Get the subgraph around an entity, including connected nodes and relationships."""
    from intel_platform.api.deps import get_neo4j_driver
    from intel_platform.graph.store import GraphStore
    driver = get_neo4j_driver()
    store = GraphStore(driver)
    return store.get_subgraph(entity_id, hops=hops)


@mcp.tool()
def find_connections(entity_id_1: str, entity_id_2: str) -> dict:
    """Find all connections between two entities in the knowledge graph."""
    from intel_platform.api.deps import get_neo4j_driver
    from intel_platform.graph.store import GraphStore
    driver = get_neo4j_driver()
    store = GraphStore(driver)
    # Get subgraphs for both and find overlap
    sg1 = store.get_subgraph(entity_id_1, hops=2)
    sg2 = store.get_subgraph(entity_id_2, hops=2)
    ids1 = {n.get("id") for n in sg1.get("nodes", [])}
    ids2 = {n.get("id") for n in sg2.get("nodes", [])}
    shared = ids1 & ids2
    shared_nodes = [n for n in sg1.get("nodes", []) + sg2.get("nodes", []) if n.get("id") in shared]
    # Deduplicate
    seen = set()
    unique_nodes = []
    for n in shared_nodes:
        if n.get("id") not in seen:
            seen.add(n.get("id"))
            unique_nodes.append(n)
    return {"shared_nodes": unique_nodes, "count": len(unique_nodes)}


@mcp.tool()
def get_communities(project_id: str) -> dict:
    """Detect and return communities in the knowledge graph using Louvain algorithm."""
    from intel_platform.api.deps import get_neo4j_driver
    from intel_platform.graph.store import GraphStore
    from intel_platform.services.enrichment import detect_communities
    driver = get_neo4j_driver()
    store = GraphStore(driver)
    communities = detect_communities(store, project_id)
    return {"communities": communities, "count": len(communities)}


@mcp.tool()
def query_corpus(project_id: str, query: str) -> dict:
    """Query the knowledge graph using Graph RAG to answer intelligence questions."""
    from intel_platform.api.deps import get_neo4j_driver
    from intel_platform.graph.store import GraphStore
    from intel_platform.services.graph_rag import GraphRAGPipeline
    driver = get_neo4j_driver()
    store = GraphStore(driver)
    pipeline = GraphRAGPipeline(store)
    return pipeline.query(query, project_id)


@mcp.tool()
def assess_entity(entity_id: str, project_id: str, judgment: str, probability: float) -> dict:
    """Create an intelligence assessment for an entity with a probability rating."""
    from intel_platform.api.deps import get_neo4j_driver
    from intel_platform.graph.store import GraphStore
    from intel_platform.services.assessment import AssessmentService
    driver = get_neo4j_driver()
    store = GraphStore(driver)
    svc = AssessmentService(store)
    return svc.create_assessment(
        entity_id=entity_id, project_id=project_id,
        judgment=judgment, probability=probability,
    )


def get_mcp_app():
    """Get the MCP Starlette app for mounting in FastAPI."""
    return mcp.streamable_http_app()
