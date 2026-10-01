"""An entity remembers every document that mentions it (review G-11).

`source_doc_id` was set once, when the entity was created. A later document
that mentioned the same entity merged into it and left no trace, so GraphRAG
and hybrid retrieval could only ever reach the first document — the rest of
the reporting on an entity was invisible to every question asked about it.

The fix: `source_doc_ids`, a list appended on merge, read by both retrievers.
`source_doc_id` stays the first document. Since contract 6 the retrievers read
the (:Document)-[:MENTIONS]->(:Entity) edges the same builds write; the list is
still kept for one release.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from intel_platform.models.entities import Document, Person
from intel_platform.services import graph_rag as graph_rag_module
from intel_platform.services.graph_builder import build_graph_from_extractions
from intel_platform.services.graph_rag import GraphRAGPipeline
from intel_platform.services.hybrid_retrieval import HybridRetriever
from tests.ids import tp

PROJECT = tp("entity-sources")
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
        hundreds of lookups per question.

        The documents now come from MENTIONS edges (contract 6): one ranked
        query, then one read of the budgeted few in full — never a lookup per
        document."""
        monkeypatch.setattr(graph_rag_module, "_MAX_SOURCE_DOCS", 3)
        person = Person(name="Hub Person", project_id=PROJECT)
        graph_store.create_entity(person)
        docs = [Document(name=f"Doc {i:02d}", project_id=PROJECT, content=f"Hub Person, item {i}") for i in range(20)]
        for doc in docs:
            graph_store.create_entity(doc)
        graph_store.record_mentions(PROJECT, {(d.id, person.id): 1 for d in docs})
        fetched: list[str] = []
        read_in_full: list[list[str]] = []
        real_get, real_content = graph_store.get_entity, graph_store.documents_content

        def counting(entity_id):
            fetched.append(entity_id)
            return real_get(entity_id)

        def counting_content(doc_ids, project_id):
            read_in_full.append(list(doc_ids))
            return real_content(doc_ids, project_id)

        monkeypatch.setattr(graph_store, "get_entity", counting)
        monkeypatch.setattr(graph_store, "documents_content", counting_content)
        retrieved = GraphRAGPipeline(graph_store).retrieve_context({"target_entities": [{"id": person.id}]}, PROJECT)
        assert not {d.id for d in docs} & set(fetched), "no per-document lookups"
        assert [len(batch) for batch in read_in_full] == [3]
        assert len(retrieved["doc_texts"]) == 3
        assert len(retrieved["document_ids"]) == 20, "the ranking still sees every document"

    async def test_hybrid_retrieval_ranks_the_later_document(self, graph_store):
        alpha, bravo = _docs(graph_store)
        build_graph_from_extractions(graph_store, ORION, [], project_id=PROJECT, source_doc_id=alpha.id)
        build_graph_from_extractions(graph_store, ORION, [], project_id=PROJECT, source_doc_id=bravo.id)
        pipeline = GraphRAGPipeline(graph_store)
        with patch("intel_platform.services.hybrid_retrieval.vector_search", new=AsyncMock(return_value=[])):
            result = await HybridRetriever(pipeline, session=None).retrieve("Orion Holdings", PROJECT)
        ranked = [m["document_id"] for m in result["merged_ranking"]]
        assert alpha.id in ranked and bravo.id in ranked
