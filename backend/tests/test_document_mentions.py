"""Documents are linked to the entities they mention by an edge (contract 6).

Which documents mention an entity lived only in `source_doc_id(s)` properties.
Every reader scanned every entity in the project to invert that list — the
document list counted entities that way, the document page found its entities
that way — and the network page's evidence chain looped over documents one
request at a time. An edge answers the question from either end with an index
seek.

`graph_builder` now writes `(:Document)-[:MENTIONS {count, first_seen}]->(:Entity)`
on both the create and the merge path; `schema.ensure_mentions_edges` backfills
it from `source_doc_ids`; `GET /entities/{id}/documents` serves the evidence
chain in one call; `GET /documents/{id}`, GraphRAG and hybrid retrieval read the
edges. `source_doc_ids` is still written for one release.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from intel_platform.api.app import app
from intel_platform.config import settings
from intel_platform.graph.schema import ensure_mentions_edges
from intel_platform.models.entities import Document, Organization, Person
from intel_platform.models.relationships import Relationship
from intel_platform.services.graph_builder import build_graph_from_extractions

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}
PROJECT = "test-doc-mentions"
OTHER = "test-doc-mentions-other"


def _mentions(driver, entity_id: str) -> dict[str, dict]:
    with driver.session() as s:
        return {
            r["doc"]: dict(r["m"]) for r in s.run(
                "MATCH (d:Document)-[m:MENTIONS]->(e:Entity {id: $id}) RETURN d.id AS doc, m",
                id=entity_id,
            )
        }


def _doc(store, name: str, content: str, project: str = PROJECT, **props) -> Document:
    doc = Document(name=name, project_id=project, content=content, **props)
    store.create_entity(doc)
    return doc


def _entity_id(store, name: str, project: str = PROJECT) -> str:
    return next(n["id"] for n in store.search_entities(project, query=name) if n["name"] == name)


class TestTheBuildWritesThem:
    def test_a_created_entity_is_mentioned_by_its_document(self, graph_store, neo4j_driver):
        doc = _doc(graph_store, "Alpha", "Orion Holdings chartered the tanker.")
        build_graph_from_extractions(
            graph_store, [{"name": "Orion Holdings", "entity_type": "Organization"}], [],
            project_id=PROJECT, source_doc_id=doc.id,
        )
        edges = _mentions(neo4j_driver, _entity_id(graph_store, "Orion Holdings"))
        assert set(edges) == {doc.id}
        assert edges[doc.id]["count"] == 1
        assert edges[doc.id]["first_seen"]

    def test_a_merged_entity_is_mentioned_by_the_later_document_too(self, graph_store, neo4j_driver):
        alpha = _doc(graph_store, "Alpha", "Orion Holdings chartered the tanker.")
        bravo = _doc(graph_store, "Bravo", "Orion Holdings re-flagged the tanker.")
        ents = [{"name": "Orion Holdings", "entity_type": "Organization"}]
        build_graph_from_extractions(graph_store, ents, [], project_id=PROJECT, source_doc_id=alpha.id)
        result = build_graph_from_extractions(graph_store, ents, [], project_id=PROJECT, source_doc_id=bravo.id)
        assert result["entities_merged"] == 1
        assert set(_mentions(neo4j_driver, _entity_id(graph_store, "Orion Holdings"))) == {alpha.id, bravo.id}

    def test_every_mention_in_a_document_is_counted(self, graph_store, neo4j_driver):
        doc = _doc(graph_store, "Alpha", "Orion Holdings ... Orion Holdings ... orion holdings")
        ents = [{"name": "Orion Holdings", "entity_type": "Organization"}] * 2 + [
            {"name": "orion holdings", "entity_type": "Organization"},
        ]
        build_graph_from_extractions(graph_store, ents, [], project_id=PROJECT, source_doc_id=doc.id)
        assert _mentions(neo4j_driver, _entity_id(graph_store, "Orion Holdings"))[doc.id]["count"] == 3

    def test_a_source_that_is_not_a_document_writes_no_edge(self, graph_store, neo4j_driver):
        result = build_graph_from_extractions(
            graph_store, [{"name": "Inline Org", "entity_type": "Organization"}], [],
            project_id=PROJECT, source_doc_id="inline",
        )
        assert result["entities_created"] == 1
        assert _mentions(neo4j_driver, _entity_id(graph_store, "Inline Org")) == {}

    def test_a_document_in_another_project_is_never_linked(self, graph_store, neo4j_driver):
        foreign = _doc(graph_store, "Foreign", "Orion Holdings", project=OTHER)
        build_graph_from_extractions(
            graph_store, [{"name": "Orion Holdings", "entity_type": "Organization"}], [],
            project_id=PROJECT, source_doc_id=foreign.id,
        )
        assert _mentions(neo4j_driver, _entity_id(graph_store, "Orion Holdings")) == {}

    def test_source_doc_ids_is_still_written(self, graph_store):
        doc = _doc(graph_store, "Alpha", "Orion Holdings")
        build_graph_from_extractions(
            graph_store, [{"name": "Orion Holdings", "entity_type": "Organization"}], [],
            project_id=PROJECT, source_doc_id=doc.id,
        )
        node = graph_store.get_entity(_entity_id(graph_store, "Orion Holdings"))
        assert node["source_doc_ids"] == [doc.id]


class TestTheyAreNotKnowledgeGraphEdges:
    """Provenance, not a claim: the analytic reads must not see them."""

    @pytest.fixture
    def built(self, graph_store):
        doc = _doc(graph_store, "Alpha", "Orion Holdings hired Marek Ilyas.")
        build_graph_from_extractions(
            graph_store,
            [{"name": "Orion Holdings", "entity_type": "Organization"},
             {"name": "Marek Ilyas", "entity_type": "Person"}],
            [], project_id=PROJECT, source_doc_id=doc.id,
        )
        return doc, _entity_id(graph_store, "Orion Holdings"), _entity_id(graph_store, "Marek Ilyas")

    def test_relationships(self, graph_store, built):
        _, orion, _ = built
        assert graph_store.get_relationships(orion) == []
        assert graph_store.get_relationships_bulk([orion]) == {}

    def test_subgraph_does_not_walk_through_a_document(self, graph_store, built):
        _, orion, _ = built
        assert graph_store.get_subgraph(orion, hops=2, project_id=PROJECT)["edge_count"] == 0

    def test_two_entities_in_one_document_are_not_a_path(self, graph_store, built):
        _, orion, marek = built
        assert graph_store.find_shortest_path(orion, marek, project_id=PROJECT)["found"] is False

    def test_full_graph_and_stats(self, graph_store, built):
        assert graph_store.get_full_graph(PROJECT)["edge_count"] == 0
        assert graph_store.get_project_stats(PROJECT)["relationship_count"] == 0

    def test_a_reports_mentions_stay_visible(self, graph_store, built):
        """Report -> entity MENTIONS edges are analyst links and were always shown."""
        from intel_platform.models.entities import Report

        _, orion, _ = built
        report = Report(name="Weekly", project_id=PROJECT)
        graph_store.create_entity(report)
        graph_store.create_relationship(Relationship(
            source_id=report.id, target_id=orion, rel_type="MENTIONS", project_id=PROJECT,
        ))
        assert [r["source_id"] for r in graph_store.get_relationships(orion)] == [report.id]


class TestBackfill:
    def test_edges_are_built_from_source_doc_ids(self, graph_store, neo4j_driver):
        alpha = _doc(graph_store, "Alpha", "x")
        bravo = _doc(graph_store, "Bravo", "y")
        foreign = _doc(graph_store, "Foreign", "z", project=OTHER)
        legacy = Person(name="Legacy Person", project_id=PROJECT, source_doc_id=alpha.id)
        graph_store.create_entity(legacy)
        graph_store.update_entity(legacy.id, {"source_doc_ids": [alpha.id, bravo.id, foreign.id, "doc-gone"]})

        created = ensure_mentions_edges(neo4j_driver)

        assert created >= 2
        edges = _mentions(neo4j_driver, legacy.id)
        assert set(edges) == {alpha.id, bravo.id}, "only documents that exist in the entity's project"
        assert all(e["count"] == 1 and e["first_seen"] for e in edges.values())

    def test_it_is_idempotent(self, graph_store, neo4j_driver):
        alpha = _doc(graph_store, "Alpha", "x")
        legacy = Person(name="Legacy Person", project_id=PROJECT, source_doc_id=alpha.id)
        graph_store.create_entity(legacy)
        ensure_mentions_edges(neo4j_driver)
        assert ensure_mentions_edges(neo4j_driver) == 0
        assert _mentions(neo4j_driver, legacy.id)[alpha.id]["count"] == 1


class TestEntityDocumentsEndpoint:
    @pytest.fixture
    def chain(self, graph_store):
        alpha = _doc(graph_store, "Alpha report",
                     "Orion Holdings chartered the tanker. Later Orion Holdings re-flagged it. "
                     "Orion Holdings denied it. Orion Holdings again.",
                     url="https://example.org/alpha")
        bravo = _doc(graph_store, "Bravo report", "A short note naming orion holdings once.")
        ents = [{"name": "Orion Holdings", "entity_type": "Organization"}]
        build_graph_from_extractions(graph_store, ents * 2, [], project_id=PROJECT, source_doc_id=alpha.id)
        build_graph_from_extractions(graph_store, ents, [], project_id=PROJECT, source_doc_id=bravo.id)
        return {"alpha": alpha, "bravo": bravo, "orion": _entity_id(graph_store, "Orion Holdings")}

    def _get(self, entity_id: str, **params):
        return client.get(f"/api/entities/{entity_id}/documents", params=params, headers=headers)

    def test_the_response_shape(self, chain):
        resp = self._get(chain["orion"])
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {"documents", "count", "total"}
        assert body["count"] == 2 and body["total"] == 2
        first = body["documents"][0]
        assert set(first) == {"id", "name", "url", "source_doc_id", "mention_count", "passages"}
        assert first["id"] == chain["alpha"].id, "most mentions first"
        assert first["url"] == "https://example.org/alpha"
        assert first["mention_count"] == 2
        for passage in first["passages"]:
            assert set(passage) == {"text", "offset"}

    def test_at_most_three_passages_per_document(self, chain):
        alpha = self._get(chain["orion"]).json()["documents"][0]
        assert len(alpha["passages"]) == 3
        content = chain["alpha"].content
        for passage in alpha["passages"]:
            assert content[passage["offset"]:].startswith("Orion Holdings")
            assert "Orion Holdings" in passage["text"]

    def test_a_mention_in_another_case_still_yields_a_passage(self, chain):
        bravo = self._get(chain["orion"]).json()["documents"][1]
        assert bravo["id"] == chain["bravo"].id
        assert len(bravo["passages"]) == 1
        assert "orion holdings" in bravo["passages"][0]["text"]

    def test_pagination(self, chain):
        page = self._get(chain["orion"], limit=1, offset=1).json()
        assert page["count"] == 1 and page["total"] == 2
        assert page["documents"][0]["id"] == chain["bravo"].id

    def test_an_unknown_entity_is_404(self):
        assert self._get("no-such-entity").status_code == 404

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 1000}, {"offset": -1}])
    def test_bounds_are_enforced(self, chain, params):
        assert self._get(chain["orion"], **params).status_code == 422


class TestDocumentPage:
    def test_detail_lists_entities_by_mention(self, graph_store):
        doc = _doc(graph_store, "Alpha", "Orion Holdings hired Marek Ilyas.")
        build_graph_from_extractions(
            graph_store,
            [{"name": "Orion Holdings", "entity_type": "Organization"},
             {"name": "Marek Ilyas", "entity_type": "Person"}],
            [], project_id=PROJECT, source_doc_id=doc.id,
        )
        data = client.get(f"/api/documents/{doc.id}", headers=headers).json()
        assert [e["name"] for e in data["entities"]] == ["Marek Ilyas", "Orion Holdings"]
        assert all(e["relationship"] == "EXTRACTED_FROM" for e in data["entities"])
        listed = client.get("/api/documents", params={"project_id": PROJECT}, headers=headers).json()
        assert {d["id"]: d["entity_count"] for d in listed["documents"]}[doc.id] == 2

    def test_the_edge_decides_not_the_property(self, graph_store):
        """Linked by MENTIONS alone, an entity is listed; by source_doc_ids alone, it is not."""
        doc = _doc(graph_store, "Alpha", "Edge Only Org and Property Only Org.")
        edge_only = Organization(name="Edge Only Org", project_id=PROJECT)
        property_only = Organization(name="Property Only Org", project_id=PROJECT, source_doc_id=doc.id)
        graph_store.create_entity(edge_only)
        graph_store.create_entity(property_only)
        graph_store.record_mentions(PROJECT, {(doc.id, edge_only.id): 1})

        data = client.get(f"/api/documents/{doc.id}", headers=headers).json()
        assert [e["name"] for e in data["entities"]] == ["Edge Only Org"]
        assert data["entity_count"] == 1
        listed = client.get("/api/documents", params={"project_id": PROJECT}, headers=headers).json()
        assert {d["id"]: d["entity_count"] for d in listed["documents"]}[doc.id] == 1


class TestMergeMovesMentions:
    def test_the_survivor_is_mentioned_by_both_documents(self, graph_store, neo4j_driver):
        alpha = _doc(graph_store, "Alpha", "Orion Holdings")
        bravo = _doc(graph_store, "Bravo", "Orion Holdings Ltd")
        build_graph_from_extractions(
            graph_store, [{"name": "Orion Holdings", "entity_type": "Organization"}], [],
            project_id=PROJECT, source_doc_id=alpha.id,
        )
        primary = _entity_id(graph_store, "Orion Holdings")
        dup = Organization(name="Orion Holdings Ltd", project_id=PROJECT, source_doc_id=bravo.id)
        graph_store.create_entity(dup)
        graph_store.record_mentions(PROJECT, {(bravo.id, dup.id): 2, (alpha.id, dup.id): 1})
        target = Person(name="Merge Target", project_id=PROJECT)
        graph_store.create_entity(target)
        # Project-stamped, as every edge graph_builder writes is.
        graph_store.create_relationship(Relationship(
            source_id=dup.id, target_id=target.id, rel_type="TARGETS", project_id=PROJECT,
        ))

        resp = client.post(
            "/api/entities/merge",
            json={"primary_id": primary, "merge_ids": [dup.id], "project_id": PROJECT},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["complete"] is True
        edges = _mentions(neo4j_driver, primary)
        assert set(edges) == {alpha.id, bravo.id}
        assert edges[alpha.id]["count"] == 2, "counts from both entities add up"
        assert edges[bravo.id]["count"] == 2
        assert graph_store.get_entity(primary)["source_doc_ids"] == [alpha.id, bravo.id]
        assert [r["target_id"] for r in graph_store.get_relationships(primary)] == [target.id]


class TestRetrievalReadsTheEdges:
    @pytest.fixture
    def linked(self, graph_store):
        edge_doc = _doc(graph_store, "Edge report", "EDGE-ONLY: Orion Holdings chartered the tanker.")
        prop_doc = _doc(graph_store, "Property report", "PROPERTY-ONLY: Orion Holdings re-flagged it.")
        orion = Organization(name="Orion Holdings", project_id=PROJECT, source_doc_id=prop_doc.id)
        graph_store.create_entity(orion)
        graph_store.record_mentions(PROJECT, {(edge_doc.id, orion.id): 1})
        return {"edge": edge_doc, "prop": prop_doc, "orion": orion.id}

    def test_graph_rag_quotes_the_documents_that_mention_the_entity(self, graph_store, linked):
        from intel_platform.services.graph_rag import GraphRAGPipeline

        retrieved = GraphRAGPipeline(graph_store).retrieve_context(
            {"target_entities": [{"id": linked["orion"]}]}, PROJECT,
        )
        assert set(retrieved["doc_texts"]) == {"Edge report"}
        assert retrieved["document_ids"] == [linked["edge"].id]

    async def test_hybrid_ranks_the_documents_that_mention_the_entity(self, graph_store, linked):
        from unittest.mock import AsyncMock, patch

        from intel_platform.services.graph_rag import GraphRAGPipeline
        from intel_platform.services.hybrid_retrieval import HybridRetriever

        with patch("intel_platform.services.hybrid_retrieval.vector_search", new=AsyncMock(return_value=[])):
            result = await HybridRetriever(GraphRAGPipeline(graph_store), session=None).retrieve(
                "Orion Holdings", PROJECT,
            )
        assert [m["document_id"] for m in result["merged_ranking"]] == [linked["edge"].id]

