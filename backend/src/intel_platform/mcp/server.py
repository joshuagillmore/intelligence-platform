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


@mcp.tool()
async def ingest_document(project_id: str, content: str, source_name: str = "mcp_input", reliability_rating: str = "C3", extraction_mode: str = "") -> dict:
    """Ingest a document into the knowledge graph with entity extraction.

    Args:
        extraction_mode: "nlp", "llm", or "hybrid". Defaults to the configured extraction_mode setting.
    """
    from intel_platform.api.deps import get_neo4j_driver
    from intel_platform.graph.store import GraphStore
    from intel_platform.models.entities import Document
    from intel_platform.services.ingestion import ingest_text
    from intel_platform.services.graph_builder import build_graph_from_extractions
    from intel_platform.config import settings

    driver = get_neo4j_driver()
    store = GraphStore(driver)

    mode = extraction_mode or settings.extraction_mode

    chunks = ingest_text(content, settings.chunk_size, settings.chunk_overlap)
    doc = Document(
        name=source_name, content=content,
        reliability_rating=reliability_rating, project_id=project_id,
    )
    store.create_entity(doc)

    all_entities, all_rels = [], []
    for chunk in chunks:
        entities, rels = await _mcp_extract(chunk["content"], doc.id, mode)
        all_entities.extend(entities)
        all_rels.extend(rels)

    result = build_graph_from_extractions(store, all_entities, all_rels, project_id)
    return {"document_id": doc.id, "chunks": len(chunks), "extraction_mode": mode, **result}


async def _mcp_extract(text: str, doc_id: str, mode: str):
    """Dispatch extraction based on mode (mirrors the API route logic)."""
    if mode == "llm":
        from intel_platform.services.extraction import extract_entities_llm
        return await extract_entities_llm(text, doc_id)
    elif mode == "hybrid":
        from intel_platform.services.extraction import extract_entities_hybrid
        return await extract_entities_hybrid(text, doc_id)
    else:
        from intel_platform.services.extraction import extract_entities_nlp
        return extract_entities_nlp(text, doc_id)


@mcp.tool()
def get_graph_stats(project_id: str) -> dict:
    """Get graph statistics including node count, edge count, density, and centrality metrics."""
    from intel_platform.api.deps import get_neo4j_driver
    from intel_platform.graph.store import GraphStore
    from intel_platform.services.enrichment import compute_all_statistics
    driver = get_neo4j_driver()
    store = GraphStore(driver)
    return compute_all_statistics(store, project_id)


@mcp.tool()
def find_shortest_path(entity_id_1: str, entity_id_2: str) -> dict:
    """Find the shortest path between two entities in the knowledge graph."""
    from intel_platform.api.deps import get_neo4j_driver
    from intel_platform.graph.store import GraphStore
    driver = get_neo4j_driver()
    store = GraphStore(driver)
    return store.find_shortest_path(entity_id_1, entity_id_2)


@mcp.tool()
async def get_topic_tree(project_id: str) -> dict:
    """Get the topic tree showing all entities organized by type."""
    from intel_platform.api.deps import get_neo4j_driver
    from intel_platform.graph.store import GraphStore
    from intel_platform.services.topics import TopicTreeService
    driver = get_neo4j_driver()
    store = GraphStore(driver)
    return await TopicTreeService(store).build_topic_tree(project_id)


@mcp.tool()
def get_geo_locations(project_id: str) -> dict:
    """Get all geocoded locations with their relationships."""
    from intel_platform.api.deps import get_neo4j_driver
    from intel_platform.graph.store import GraphStore
    from intel_platform.services.geocoding import geocode_all_locations
    driver = get_neo4j_driver()
    store = GraphStore(driver)
    locations = geocode_all_locations(store, project_id)
    return {"locations": locations, "total": len(locations)}


def get_mcp_app():
    """Get the MCP Starlette app for mounting in FastAPI."""
    return mcp.streamable_http_app()
