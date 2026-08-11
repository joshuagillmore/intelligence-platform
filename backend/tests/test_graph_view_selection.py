"""Which slice of a large project the graph view shows.

`limit` is a display budget: a 5,486-entity project renders 500 nodes. Selection
was `MATCH (n) WHERE n.project_id = $p RETURN ... LIMIT $limit` with no
ordering, so the 500 an analyst saw were whatever the scan produced first. URL
nodes outnumber everything else, so Network Analysis rendered 500 nodes joined
by 82 edges — 439 isolated dots, 211 of them URLs.

Spending the budget on the connected core first turns the same view into 500
nodes and 500 edges of Organizations, Campaigns, Locations, Events and People.
"""
from __future__ import annotations

import pytest

from intel_platform.models.entities import Organization, Person
from intel_platform.models.relationships import Relationship

PROJECT = "test-graph-selection"


@pytest.fixture
def wired(graph_store):
    """A few connected entities among many isolated ones."""
    connected = [Person(name=f"Linked {i}", project_id=PROJECT) for i in range(4)]
    hub = Organization(name="Hub", project_id=PROJECT)
    isolated = [Organization(name=f"Isolated {i}", project_id=PROJECT) for i in range(20)]
    for e in [*connected, hub, *isolated]:
        graph_store.create_entity(e)
    for p in connected:
        graph_store.create_relationship(Relationship(
            source_id=hub.id, target_id=p.id, rel_type="ASSOCIATED_WITH",
            confidence=1.0, source="test", method="test",
        ))
    return {"hub": hub, "connected": connected, "isolated": isolated}


class TestBudgetGoesToTheConnectedCore:
    def test_a_small_budget_spends_itself_on_connected_nodes(self, graph_store, wired):
        """The defect, inverted: with room for 5 of 25 nodes, all 5 should be
        ones that have an edge, not an arbitrary scan prefix."""
        g = graph_store.get_full_graph(PROJECT, limit=5)
        names = {n["name"] for n in g["nodes"]}
        assert names == {"Hub", "Linked 0", "Linked 1", "Linked 2", "Linked 3"}
        assert not any(n.startswith("Isolated") for n in names)

    def test_the_most_connected_node_is_never_cut(self, graph_store, wired):
        g = graph_store.get_full_graph(PROJECT, limit=1)
        assert [n["name"] for n in g["nodes"]] == ["Hub"]

    def test_isolated_entities_still_appear_when_there_is_room(self, graph_store, wired):
        """An entity with no links is a finding, not something to hide — it just
        does not get to crowd out the graph."""
        g = graph_store.get_full_graph(PROJECT, limit=25)
        names = {n["name"] for n in g["nodes"]}
        assert len(g["nodes"]) == 25
        assert any(n.startswith("Isolated") for n in names)


class TestEdgesDescribeReturnedNodes:
    def test_no_edge_refers_to_a_node_the_caller_never_got(self, graph_store, wired):
        """The edge query used to run its own LIMIT over the whole project, so
        nothing stopped it describing nodes outside the returned set."""
        g = graph_store.get_full_graph(PROJECT, limit=3)
        ids = {n["id"] for n in g["nodes"]}
        for e in g["edges"]:
            assert e["source_id"] in ids
            assert e["target_id"] in ids

    def test_edges_between_returned_nodes_are_present(self, graph_store, wired):
        g = graph_store.get_full_graph(PROJECT, limit=5)
        assert len(g["edges"]) == 4, "every hub->person edge is within the returned set"

    def test_counts_match_the_payload(self, graph_store, wired):
        g = graph_store.get_full_graph(PROJECT, limit=10)
        assert g["node_count"] == len(g["nodes"])
        assert g["edge_count"] == len(g["edges"])


class TestEdges:
    def test_an_empty_project_is_empty_not_an_error(self, graph_store):
        g = graph_store.get_full_graph("test-graph-selection-empty", limit=50)
        assert g == {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0}

    def test_another_projects_nodes_never_appear(self, graph_store, wired):
        graph_store.create_entity(Organization(name="Elsewhere", project_id="test-graph-other"))
        g = graph_store.get_full_graph(PROJECT, limit=100)
        assert "Elsewhere" not in {n["name"] for n in g["nodes"]}
