from intel_platform.services.graph_rag import GraphRAGPipeline
from intel_platform.models.entities import Person, Organization
from intel_platform.models.relationships import Relationship


def test_understand_query(graph_store):
    p = Person(name="Alpha Target", project_id="test-proj-rag")
    graph_store.create_entity(p)
    pipeline = GraphRAGPipeline(graph_store)
    result = pipeline.understand_query("Tell me about Alpha Target", "test-proj-rag")
    assert len(result["target_entities"]) >= 1


def test_retrieve_context(graph_store):
    a = Person(name="RAG Person", project_id="test-proj-rag2")
    b = Organization(name="RAG Org", project_id="test-proj-rag2")
    graph_store.create_entity(a)
    graph_store.create_entity(b)
    graph_store.create_relationship(
        Relationship(
            source_id=a.id,
            target_id=b.id,
            rel_type="BELONGS_TO",
            confidence=0.9,
            source="d",
            method="t",
        )
    )
    pipeline = GraphRAGPipeline(graph_store)
    understanding = {"target_entities": [{"id": a.id}]}
    result = pipeline.retrieve_context(understanding, "test-proj-rag2")
    assert result["node_count"] >= 2


def test_assemble_context(graph_store):
    pipeline = GraphRAGPipeline(graph_store)
    retrieved = {
        "nodes": [{"id": "1", "name": "Test", "entity_type": "Person"}],
        "edges": [],
    }
    context = pipeline.assemble_context(retrieved)
    assert "Test" in context


async def test_full_query(graph_store):
    p = Person(name="Query Target", project_id="test-proj-rag3")
    graph_store.create_entity(p)
    pipeline = GraphRAGPipeline(graph_store)
    result = await pipeline.query("Tell me about Query Target", "test-proj-rag3")
    assert "context" in result
    assert result["context_nodes"] >= 1
