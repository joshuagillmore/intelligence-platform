"""Merging entities must move each edge as it was, or not delete the source.

The merge recreated every edge as `primary -> other`, reversing every incoming
edge; it dropped evidence, source_doc_id and polarity; `create_relationship`
refused the catalog types (MAPS_TO, HAS_WEAKNESS, ENABLES) with a ValueError the
route swallowed right before DETACH DELETE; and the response said success.

`get_relationships` is patched here to the shape the store package ships under
contract 1 (true start/end node plus `direction`), so these tests pin the route
against that contract rather than against today's undirected read.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from intel_platform.api.app import app
from intel_platform.api.routes import entities as entities_route
from intel_platform.config import settings
from intel_platform.graph.store import GraphStore
from intel_platform.models.entities import Organization, Person, ThreatActor
from intel_platform.models.relationships import Relationship
from tests.ids import tp

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}
PID = tp("a5-merge")


def _contract_get_relationships(self, entity_id: str) -> list[dict]:
    """Contract 1: the true start/end nodes, and direction relative to entity_id."""
    with self._driver.session() as session:
        result = session.run(
            """
            MATCH (n {id: $id})-[r]-(m)
            RETURN type(r) AS rel_type, properties(r) AS props,
                   startNode(r).id AS source_id, startNode(r).name AS source_name,
                   endNode(r).id AS target_id, endNode(r).name AS target_name,
                   CASE WHEN startNode(r) = n THEN 'out' ELSE 'in' END AS direction
            """,
            id=entity_id,
        )
        return [
            {"rel_type": r["rel_type"], "source_id": r["source_id"], "source_name": r["source_name"],
             "target_id": r["target_id"], "target_name": r["target_name"], "direction": r["direction"],
             **r["props"]}
            for r in result
        ]


@pytest.fixture(autouse=True)
def _contract_store(monkeypatch):
    monkeypatch.setattr(GraphStore, "get_relationships", _contract_get_relationships)


def _edges(graph_store, entity_id: str) -> list[dict]:
    with graph_store._driver.session() as session:
        return [dict(r) for r in session.run(
            """
            MATCH (a)-[r]->(b) WHERE a.id = $id OR b.id = $id
            RETURN a.id AS src, type(r) AS type, b.id AS tgt, properties(r) AS props
            """,
            id=entity_id,
        )]


def _exists(graph_store, entity_id: str) -> bool:
    return graph_store.get_entity(entity_id) is not None


def _merge(primary: str, merge_ids: list[str]) -> dict:
    resp = client.post(
        "/api/entities/merge",
        json={"primary_id": primary, "merge_ids": merge_ids, "project_id": PID},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture
def world(graph_store):
    primary = ThreatActor(name="APT Example", project_id=PID)
    dup = ThreatActor(name="APT-Example", project_id=PID)
    victim = Organization(name="Kolvane Holdings", project_id=PID)
    handler = Person(name="Marek Ilyas", project_id=PID)
    for e in (primary, dup, victim, handler):
        graph_store.create_entity(e)
    return {"primary": primary.id, "dup": dup.id, "victim": victim.id, "handler": handler.id}


def _rel(src, tgt, rel_type, **kw):
    return Relationship(source_id=src, target_id=tgt, rel_type=rel_type, confidence=0.8,
                        source="test", method="llm", **kw)


class TestMergeKeepsEachEdgeAsItWas:
    def test_incoming_edges_stay_incoming(self, graph_store, world):
        graph_store.create_relationship(_rel(world["handler"], world["dup"], "COMMANDED_BY"))
        out = _merge(world["primary"], [world["dup"]])
        edges = _edges(graph_store, world["primary"])
        assert [(e["src"], e["type"], e["tgt"]) for e in edges] == [
            (world["handler"], "COMMANDED_BY", world["primary"]),
        ]
        assert out["relationships_transferred"] == 1

    def test_outgoing_edges_stay_outgoing(self, graph_store, world):
        graph_store.create_relationship(_rel(world["dup"], world["victim"], "TARGETS"))
        _merge(world["primary"], [world["dup"]])
        edges = _edges(graph_store, world["primary"])
        assert [(e["src"], e["type"], e["tgt"]) for e in edges] == [
            (world["primary"], "TARGETS", world["victim"]),
        ]

    def test_evidence_provenance_and_polarity_survive(self, graph_store, world):
        graph_store.create_relationship(_rel(
            world["dup"], world["victim"], "TARGETS",
            evidence="APT-Example targeted Kolvane in March.",
            source_doc_id="doc-123", polarity="denies",
        ))
        _merge(world["primary"], [world["dup"]])
        props = _edges(graph_store, world["primary"])[0]["props"]
        assert props["evidence"] == "APT-Example targeted Kolvane in March."
        assert props["source_doc_id"] == "doc-123"
        assert props["polarity"] == "denies"
        assert props["method"] == "llm"

    def test_catalog_edge_types_are_transferred_not_dropped(self, graph_store, world):
        """MAPS_TO is outside create_relationship's allowlist; the merge swallowed
        the ValueError and then deleted the node that held the edge."""
        with graph_store._driver.session() as session:
            session.run(
                "CREATE (t:AttackTechnique {id: $tid, name: 'Phishing', project_id: $pid})",
                tid=tp("a5-T1566"), pid=PID,
            )
            session.run(
                "MATCH (a {id: $a}), (t {id: $tid}) "
                "CREATE (a)-[:MAPS_TO {method: 'tcode', confidence: 1.0}]->(t)",
                a=world["dup"], tid=tp("a5-T1566"),
            )
        out = _merge(world["primary"], [world["dup"]])
        edges = _edges(graph_store, world["primary"])
        assert [(e["src"], e["type"], e["tgt"]) for e in edges] == [
            (world["primary"], "MAPS_TO", tp("a5-T1566")),
        ]
        assert edges[0]["props"]["method"] == "tcode"
        assert out["dropped_edges"] == 0
        assert not _exists(graph_store, world["dup"])

    def test_an_edge_to_the_primary_does_not_become_a_self_loop(self, graph_store, world):
        graph_store.create_relationship(_rel(world["dup"], world["primary"], "ASSOCIATED_WITH"))
        _merge(world["primary"], [world["dup"]])
        assert _edges(graph_store, world["primary"]) == []


class TestAFailedEdgeKeepsTheNode:
    def test_the_merged_entity_survives_when_an_edge_could_not_be_moved(self, graph_store, world, monkeypatch):
        graph_store.create_relationship(_rel(world["dup"], world["victim"], "TARGETS"))
        graph_store.create_relationship(_rel(world["handler"], world["dup"], "COMMANDED_BY"))

        real = entities_route._transfer_edge

        def flaky(store, rel, source_id, target_id, project_id):
            if rel["rel_type"] == "COMMANDED_BY":
                return False
            return real(store, rel, source_id, target_id, project_id)

        monkeypatch.setattr(entities_route, "_transfer_edge", flaky)
        out = _merge(world["primary"], [world["dup"]])

        assert _exists(graph_store, world["dup"]), "an edge was lost; the node must not be deleted"
        assert out["entities_merged"] == 0
        assert out["dropped_edges"] == 1
        assert out["entities_not_merged"] == [world["dup"]]
        assert out["complete"] is False

    def test_a_clean_merge_reports_complete(self, graph_store, world):
        graph_store.create_relationship(_rel(world["dup"], world["victim"], "TARGETS"))
        out = _merge(world["primary"], [world["dup"]])
        assert out["complete"] is True
        assert out["entities_merged"] == 1
        assert out["entities_not_merged"] == []
