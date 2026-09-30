"""An entity remembers every document that mentions it (review G-11).

`source_doc_id` was set once, when the entity was created. A later document
that mentioned the same entity merged into it and left no trace, so GraphRAG
and hybrid retrieval could only ever reach the first document — the rest of
the reporting on an entity was invisible to every question asked about it.

The fix: `source_doc_ids`, a list appended on merge, read by both retrievers.
`source_doc_id` stays the first document.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from intel_platform.models.entities import Document, Person
from intel_platform.services import graph_rag as graph_rag_module
from intel_platform.services.graph_builder import build_graph_from_extractions
from intel_platform.services.graph_rag import GraphRAGPipeline
from intel_platform.services.hybrid_retrieval import HybridRetriever

PROJECT = "test-entity-sources"
ORION = [{"name": "Orion Holdings", "entity_type": "Organization"}]


def _orion(store) -> dict:
    return next(n for n in store.search_entities(PROJECT, query="Orion Holdings") if n["name"] == "Orion Holdings")


def _docs(store):
    alpha = Document(name="Alpha report", project_id=PROJECT,
                     content="ALPHA-ONLY: Orion Holdings chartered the tanker in January.")
    bravo = Document(name="Bravo report", project_id=PROJECT,
                     content="BRAVO-ONLY: Orion Holdings re-flagged the tanker in March.")
    store.create_entity(alpha)
    store.create_entity(bravo)
    return alpha, bravo


class TestTheListIsKept:
    def test_a_new_entity_starts_with_its_document(self, graph_store):
        build_graph_from_extractions(graph_store, ORION, [], project_id=PROJECT, source_doc_id="doc-a")
        assert _orion(graph_store)["source_doc_ids"] == ["doc-a"]

    def test_a_later_document_is_appended_on_merge(self, graph_store):
        build_graph_from_extractions(graph_store, ORION, [], project_id=PROJECT, source_doc_id="doc-a")
        result = build_graph_from_extractions(graph_store, ORION, [], project_id=PROJECT, source_doc_id="doc-b")
        assert result["entities_merged"] == 1
        node = _orion(graph_store)
        assert node["source_doc_ids"] == ["doc-a", "doc-b"]
        assert node["source_doc_id"] == "doc-a", "the first document stays the primary"

    def test_the_same_document_is_recorded_once(self, graph_store):
        for doc in ("doc-a", "doc-b", "doc-b"):
            build_graph_from_extractions(graph_store, ORION, [], project_id=PROJECT, source_doc_id=doc)
        assert _orion(graph_store)["source_doc_ids"] == ["doc-a", "doc-b"]

    def test_an_entity_created_before_the_list_keeps_its_first_document(self, graph_store, neo4j_driver):
        build_graph_from_extractions(graph_store, ORION, [], project_id=PROJECT, source_doc_id="doc-legacy")
        with neo4j_driver.session() as s:
            s.run("MATCH (n {project_id: $p, name: 'Orion Holdings'}) REMOVE n.source_doc_ids", p=PROJECT)
        build_graph_from_extractions(graph_store, ORION, [], project_id=PROJECT, source_doc_id="doc-c")
        assert _orion(graph_store)["source_doc_ids"] == ["doc-legacy", "doc-c"]


class TestRetrieversReadIt:
    def test_graph_rag_reaches_the_later_document(self, graph_store):
        alpha, bravo = _docs(graph_store)
        build_graph_from_extractions(graph_store, ORION, [], project_id=PROJECT, source_doc_id=alpha.id)
        build_graph_from_extractions(graph_store, ORION, [], project_id=PROJECT, source_doc_id=bravo.id)
        pipeline = GraphRAGPipeline(graph_store)
        retrieved = pipeline.retrieve_context({"target_entities": [{"id": _orion(graph_store)["id"]}]}, PROJECT)
        assert {"Alpha report", "Bravo report"} <= set(retrieved["doc_texts"])
        assert "BRAVO-ONLY" in pipeline.assemble_context(retrieved)

    def test_graph_rag_bounds_how_many_documents_it_fetches(self, graph_store, monkeypatch):
        """A hub entity mentioned in hundreds of documents must not turn into
        hundreds of lookups per question."""
        monkeypatch.setattr(graph_rag_module, "_MAX_SOURCE_DOCS", 3)
        person = Person(name="Hub Person", project_id=PROJECT)
        graph_store.create_entity(person)
        graph_store.update_entity(person.id, {"source_doc_ids": [f"doc-{i}" for i in range(20)]})
        fetched: list[str] = []
        real = graph_store.get_entity

        def counting(entity_id):
            fetched.append(entity_id)
            return real(entity_id)

        monkeypatch.setattr(graph_store, "get_entity", counting)
        GraphRAGPipeline(graph_store).retrieve_context({"target_entities": [{"id": person.id}]}, PROJECT)
        assert len([f for f in fetched if f.startswith("doc-")]) == 3

    async def test_hybrid_retrieval_ranks_the_later_document(self, graph_store):
        alpha, bravo = _docs(graph_store)
        build_graph_from_extractions(graph_store, ORION, [], project_id=PROJECT, source_doc_id=alpha.id)
        build_graph_from_extractions(graph_store, ORION, [], project_id=PROJECT, source_doc_id=bravo.id)
        pipeline = GraphRAGPipeline(graph_store)
        with patch("intel_platform.services.hybrid_retrieval.vector_search", new=AsyncMock(return_value=[])):
            result = await HybridRetriever(pipeline, session=None).retrieve("Orion Holdings", PROJECT)
        ranked = [m["document_id"] for m in result["merged_ranking"]]
        assert alpha.id in ranked and bravo.id in ranked
