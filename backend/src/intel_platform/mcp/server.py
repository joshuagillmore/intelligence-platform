"""MCP tools over the knowledge graph.

Served over authenticated streamable HTTP by ``intel_platform.mcp.transport``.
Every tool is async and runs the sync Neo4j ``GraphStore`` (and any other
blocking work) in a worker thread, so a tool call never stalls the API's event
loop. Graph traversals are scoped to one project and bounded to 1..4 hops.

No ``from __future__ import annotations`` here: FastMCP builds each tool's
argument schema from the live annotations.
"""
import asyncio
import inspect

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Intelligence Platform")

_MIN_HOPS, _MAX_HOPS = 1, 4


def _store():
    """A GraphStore on the process-wide driver (a seam for tests)."""
    from intel_platform.api.deps import get_neo4j_driver
    from intel_platform.graph.store import GraphStore

    return GraphStore(get_neo4j_driver())


def _clamp_hops(hops) -> int:
    """Hops bounded to 1..4: deeper traversals through shared ATT&CK hubs
    enumerate paths without limit, and a negative value is a Cypher error."""
    try:
        value = int(hops)
    except (TypeError, ValueError):
        value = _MIN_HOPS
    return max(_MIN_HOPS, min(_MAX_HOPS, value))


def _project_of(store, entity_id: str) -> str:
    entity = store.get_entity(entity_id) or {}
    return str(entity.get("project_id") or "")


def _scope(method, project_id: str) -> dict:
    """``project_id=`` for a store method that accepts it (contract 2).

    A store that predates project scoping gets no argument rather than a
    TypeError; it then traverses unscoped, as it always has.
    """
    if project_id and "project_id" in inspect.signature(method).parameters:
        return {"project_id": project_id}
    return {}


def _subgraph(store, entity_id: str, hops: int, project_id: str) -> dict:
    project_id = project_id or _project_of(store, entity_id)
    return store.get_subgraph(entity_id, hops=_clamp_hops(hops), **_scope(store.get_subgraph, project_id))


@mcp.tool()
async def search_entities(project_id: str, query: str = "", entity_type: str | None = None) -> dict:
    """Search for entities in the knowledge graph by name or type."""
    store = _store()
    results = await asyncio.to_thread(
        store.search_entities, project_id=project_id, query=query, entity_type=entity_type, limit=20,
    )
    return {"entities": results, "count": len(results)}


@mcp.tool()
async def get_subgraph(entity_id: str, hops: int = 1, project_id: str = "") -> dict:
    """Get the subgraph around an entity (1-4 hops), within its project.

    ``project_id`` defaults to the entity's own project.
    """
    store = _store()
    return await asyncio.to_thread(_subgraph, store, entity_id, hops, project_id)


def _connections(store, entity_id_1: str, entity_id_2: str, project_id: str) -> dict:
    project_id = project_id or _project_of(store, entity_id_1)
    sg1 = _subgraph(store, entity_id_1, 2, project_id)
    sg2 = _subgraph(store, entity_id_2, 2, project_id)
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
async def find_connections(entity_id_1: str, entity_id_2: str, project_id: str = "") -> dict:
    """Find the entities two entities share within two hops, within one project.

    ``project_id`` defaults to the first entity's project.
    """
    store = _store()
    return await asyncio.to_thread(_connections, store, entity_id_1, entity_id_2, project_id)


@mcp.tool()
async def get_communities(project_id: str) -> dict:
    """Detect and return communities in the knowledge graph using Louvain algorithm."""
    from intel_platform.services.enrichment import detect_communities

    communities = await asyncio.to_thread(detect_communities, _store(), project_id)
    return {"communities": communities, "count": len(communities)}


@mcp.tool()
async def query_corpus(project_id: str, query: str) -> dict:
    """Query the knowledge graph using Graph RAG to answer intelligence questions."""
    from intel_platform.services.graph_rag import GraphRAGPipeline

    pipeline = GraphRAGPipeline(_store())
    return await pipeline.query(query, project_id)


@mcp.tool()
async def assess_entity(entity_id: str, project_id: str, judgment: str, probability: float) -> dict:
    """Create an intelligence assessment for an entity with a probability rating."""
    from intel_platform.services.assessment import AssessmentService

    svc = AssessmentService(_store())
    return await asyncio.to_thread(
        svc.create_assessment,
        entity_id=entity_id, project_id=project_id,
        judgment=judgment, probability=probability,
    )


@mcp.tool()
async def ingest_document(project_id: str, content: str, source_name: str = "mcp_input", reliability_rating: str = "C3", extraction_mode: str = "") -> dict:
    """Ingest a document into the knowledge graph with entity extraction.

    Args:
        extraction_mode: "nlp", "llm", or "hybrid". Defaults to the configured extraction_mode setting.
    """
    from intel_platform.config import settings
    from intel_platform.models.entities import Document
    from intel_platform.services import graph_builder, ingestion

    store = _store()
    mode = extraction_mode or settings.extraction_mode

    chunks = ingestion.ingest_text(content, settings.chunk_size, settings.chunk_overlap)
    doc = Document(
        name=source_name, content=content,
        reliability_rating=reliability_rating, project_id=project_id,
    )
    await asyncio.to_thread(store.create_entity, doc)

    all_entities, all_rels = [], []
    for chunk in chunks:
        entities, rels = await _mcp_extract(chunk["content"], doc.id, mode)
        all_entities.extend(entities)
        all_rels.extend(rels)

    # Sync store writes in a worker thread; the loop is handed over so the
    # (default-off) auto-enrich hook can schedule onto it from there.
    result = await asyncio.to_thread(
        graph_builder.build_graph_from_extractions,
        store, all_entities, all_rels, project_id,
        auto_enrich_loop=asyncio.get_running_loop(),
    )
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
        return await asyncio.to_thread(extract_entities_nlp, text, doc_id)  # spaCy blocks


@mcp.tool()
async def get_graph_stats(project_id: str) -> dict:
    """Get graph statistics including node count, edge count, density, and centrality metrics."""
    from intel_platform.services.enrichment import compute_all_statistics

    return await asyncio.to_thread(compute_all_statistics, _store(), project_id)


def _shortest_path(store, entity_id_1: str, entity_id_2: str, project_id: str) -> dict:
    project_id = project_id or _project_of(store, entity_id_1)
    return store.find_shortest_path(
        entity_id_1, entity_id_2, **_scope(store.find_shortest_path, project_id),
    )


@mcp.tool()
async def find_shortest_path(entity_id_1: str, entity_id_2: str, project_id: str = "") -> dict:
    """Find the shortest path between two entities, within one project.

    ``project_id`` defaults to the first entity's project.
    """
    store = _store()
    return await asyncio.to_thread(_shortest_path, store, entity_id_1, entity_id_2, project_id)


@mcp.tool()
async def get_topic_tree(project_id: str) -> dict:
    """Get the topic tree showing all entities organized by type."""
    from intel_platform.services.topics import TopicTreeService

    return await TopicTreeService(_store()).build_topic_tree(project_id)


@mcp.tool()
async def get_geo_locations(project_id: str) -> dict:
    """Get all geocoded locations with their relationships."""
    from intel_platform.services.geocoding import geocode_all_locations

    locations = await asyncio.to_thread(geocode_all_locations, _store(), project_id)
    return {"locations": locations, "total": len(locations)}


def get_mcp_app():
    """Deprecated: use ``intel_platform.mcp.build_authenticated_app(settings)``.

    Kept so an ``app.py`` that still calls this mounts the *authenticated* app;
    it never returns FastMCP's bare, unauthenticated Starlette app.
    """
    from intel_platform.config import settings
    from intel_platform.mcp.transport import build_authenticated_app

    return build_authenticated_app(settings)
