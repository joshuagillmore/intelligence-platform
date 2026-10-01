"""Subgraph and path traversal stay inside the project (review A-7, A-8, contract 2).

ATT&CK, CWE/CAPEC and D3FEND nodes are shared reference data with no
project_id. Every project that maps a TTP to T1566 links to the same
AttackTechnique node, so an unscoped two-hop walk from one project's TTP
crossed the catalog node into another project's entities, and GraphRAG then
pulled that project's documents into the LLM context.

The contract: with `project_id`, every non-catalog node on a path belongs to the
project, and a catalog node may only be a path endpoint. `hops` is clamped to
1..4 and path enumeration stops at a fixed budget.
"""
from __future__ import annotations

import uuid

import pytest

from intel_platform.graph import store as store_module
from intel_platform.models.entities import TTP, Document, Organization, Person
from intel_platform.models.relationships import Relationship
from intel_platform.services.graph_rag import GraphRAGPipeline
from tests.ids import tp

P1 = tp("scope-p1")
P2 = tp("scope-p2")


def _link(store, a, b, rel_type="ASSOCIATED_WITH"):
    store.create_relationship(Relationship(
        source_id=a.id, target_id=b.id, rel_type=rel_type, confidence=0.9,
    ))


@pytest.fixture
def two_projects_one_catalog(graph_store, neo4j_driver):
    """P1 and P2 each map a TTP to the same AttackTechnique; P2's TTP targets
    a victim whose source document says something P1 must never see."""
    attack_id = f"TTEST-{uuid.uuid4().hex[:8]}"
    p2_doc = Document(name="P2 dossier", project_id=P2,
                      content="SECRET-P2-CONTENT: Kestrel Bank was the phishing target.")
    ttp1 = TTP(name="Spearphishing P1", project_id=P1)
    ttp2 = TTP(name="Spearphishing P2", project_id=P2, source_doc_id=p2_doc.id)
    victim2 = Organization(name="Kestrel Bank", project_id=P2, source_doc_id=p2_doc.id)
    for e in (p2_doc, ttp1, ttp2, victim2):
        graph_store.create_entity(e)
    _link(graph_store, ttp2, victim2, "TARGETS")
    with neo4j_driver.session() as s:
        s.run(
            """
            MERGE (t:AttackTechnique {attack_id: $aid}) SET t.name = 'Phishing (test)'
            WITH t
            MATCH (x) WHERE x.id IN $ttps
            MERGE (x)-[:MAPS_TO]->(t)
            """,
            aid=attack_id, ttps=[ttp1.id, ttp2.id],
        )
    yield {"ttp1": ttp1, "ttp2": ttp2, "victim2": victim2, "doc2": p2_doc, "attack_id": attack_id}
    with neo4j_driver.session() as s:
        s.run("MATCH (t:AttackTechnique {attack_id: $aid}) DETACH DELETE t", aid=attack_id)


@pytest.fixture
def chain(graph_store):
    """x0 - x1 - x2 - x3 - x4 - x5, all in P1: five hops end to end."""
    nodes = [Person(name=f"Chain {i}", project_id=P1) for i in range(6)]
    for n in nodes:
        graph_store.create_entity(n)
    for a, b in zip(nodes, nodes[1:]):
        _link(graph_store, a, b)
    return nodes


def _ids(subgraph) -> set[str]:
    return {n.get("id") for n in subgraph["nodes"] if n.get("id")}


class TestProjectScope:
    def test_a_catalog_node_may_end_a_path(self, graph_store, two_projects_one_catalog):
        f = two_projects_one_catalog
        sg = graph_store.get_subgraph(f["ttp1"].id, hops=1, project_id=P1)
        assert f["attack_id"] in {n.get("attack_id") for n in sg["nodes"]}

    @pytest.mark.parametrize("hops", [2, 3, 4])
    def test_a_catalog_node_is_never_passed_through(self, graph_store, two_projects_one_catalog, hops):
        f = two_projects_one_catalog
        sg = graph_store.get_subgraph(f["ttp1"].id, hops=hops, project_id=P1)
        leaked = _ids(sg) & {f["ttp2"].id, f["victim2"].id}
        assert not leaked, f"P1's subgraph reached P2 through the catalog at hops={hops}"

    def test_an_entity_of_another_project_is_not_a_starting_point(self, graph_store, two_projects_one_catalog):
        f = two_projects_one_catalog
        sg = graph_store.get_subgraph(f["ttp2"].id, hops=2, project_id=P1)
        assert sg["nodes"] == [] and sg["edges"] == []

    def test_without_a_project_the_walk_is_unscoped_as_before(self, graph_store, two_projects_one_catalog):
        """Scoping is opt-in: callers that pass no project keep today's reach."""
        f = two_projects_one_catalog
        sg = graph_store.get_subgraph(f["ttp1"].id, hops=2)
        assert f["ttp2"].id in _ids(sg)


class TestHopsAreBounded:
    def test_hops_above_four_are_clamped_to_four(self, graph_store, chain):
        sg = graph_store.get_subgraph(chain[0].id, hops=10, project_id=P1)
        got = _ids(sg)
        assert chain[4].id in got
        assert chain[5].id not in got, "five hops away must be out of reach"

    @pytest.mark.parametrize("hops", [0, -1])
    def test_hops_below_one_are_clamped_to_one(self, graph_store, chain, hops):
        """A negative hop count used to reach Cypher as `[*1..-1]`: a syntax
        error and a 500."""
        sg = graph_store.get_subgraph(chain[0].id, hops=hops, project_id=P1)
        assert _ids(sg) == {chain[0].id, chain[1].id}


class TestPathBudget:
    def test_enumeration_stops_at_the_budget_and_says_so(self, graph_store, monkeypatch):
        hub = Organization(name="Budget Hub", project_id=P1)
        graph_store.create_entity(hub)
        for i in range(5):
            leaf = Person(name=f"Leaf {i}", project_id=P1)
            graph_store.create_entity(leaf)
            _link(graph_store, hub, leaf)
        monkeypatch.setattr(store_module, "_MAX_SUBGRAPH_PATHS", 3)
        sg = graph_store.get_subgraph(hub.id, hops=1, project_id=P1)
        assert sg["truncated"] is True
        assert sg["node_count"] <= 4

    def test_a_small_walk_is_not_truncated(self, graph_store, chain):
        sg = graph_store.get_subgraph(chain[0].id, hops=2, project_id=P1)
        assert sg["truncated"] is False


class TestShortestPath:
    def test_a_path_through_the_catalog_into_another_project_is_not_found(
        self, graph_store, two_projects_one_catalog,
    ):
        f = two_projects_one_catalog
        got = graph_store.find_shortest_path(f["ttp1"].id, f["victim2"].id, project_id=P1)
        assert got["found"] is False

    def test_unscoped_it_is_still_found(self, graph_store, two_projects_one_catalog):
        f = two_projects_one_catalog
        got = graph_store.find_shortest_path(f["ttp1"].id, f["victim2"].id)
        assert got["found"] is True and got["path_length"] == 3

    def test_a_path_inside_the_project_is_found(self, graph_store, chain):
        got = graph_store.find_shortest_path(chain[0].id, chain[3].id, project_id=P1)
        assert got["found"] is True and got["path_length"] == 3


class TestGraphRagStaysInProject:
    def test_another_projects_entities_and_documents_never_reach_the_context(
        self, graph_store, two_projects_one_catalog,
    ):
        f = two_projects_one_catalog
        pipeline = GraphRAGPipeline(graph_store)
        retrieved = pipeline.retrieve_context(
            {"target_entities": [{"id": f["ttp1"].id}]}, P1, max_hops=2,
        )
        names = {n.get("name") for n in retrieved["nodes"]}
        assert "Spearphishing P2" not in names and "Kestrel Bank" not in names
        context = pipeline.assemble_context(retrieved)
        assert "SECRET-P2-CONTENT" not in context
