"""Relationship direction survives the read (review finding A-5 / A-11, contract 1).

`get_relationships` matched `(n {id})-[r]-(m)` undirected and always reported
the queried node as `source` and the neighbour as `target`. Every edge came back
pointing outward: an Organization LOCATED_AT a Location, read from the Location,
said the Location was located at the Organization. Entity merge then rebuilt
every incoming edge backwards, and the entity panel, snapshots and the cyber
page all drew arrows the wrong way.

The contract: `source_*` is the true start node, `target_*` the true end node,
and `direction` says which end the queried entity is.
"""
from __future__ import annotations

import pytest

from intel_platform.models.entities import Location, Organization
from intel_platform.models.relationships import Relationship

PROJECT = "test-rel-direction"


@pytest.fixture
def located(graph_store):
    """Kolvane Holdings -[LOCATED_AT]-> Gdansk. The edge points INTO Gdansk."""
    org = Organization(name="Kolvane Holdings", project_id=PROJECT)
    place = Location(name="Gdansk", project_id=PROJECT)
    graph_store.create_entity(org)
    graph_store.create_entity(place)
    graph_store.create_relationship(Relationship(
        source_id=org.id, target_id=place.id, rel_type="LOCATED_AT",
        confidence=0.8, evidence="Kolvane Holdings, based in Gdansk", source_doc_id="doc-1",
    ))
    return org, place


class TestSingleEntityRead:
    def test_an_incoming_edge_keeps_its_true_source(self, graph_store, located):
        org, place = located
        (rel,) = graph_store.get_relationships(place.id)
        assert rel["source_id"] == org.id
        assert rel["source_name"] == "Kolvane Holdings"
        assert rel["target_id"] == place.id
        assert rel["target_name"] == "Gdansk"
        assert rel["direction"] == "in"

    def test_an_outgoing_edge_says_out(self, graph_store, located):
        org, place = located
        (rel,) = graph_store.get_relationships(org.id)
        assert (rel["source_id"], rel["target_id"]) == (org.id, place.id)
        assert rel["direction"] == "out"

    def test_the_neighbour_is_named_whichever_way_the_edge_points(self, graph_store, located):
        """Callers that want "the other end" should not have to branch on
        direction to find it."""
        org, place = located
        (from_place,) = graph_store.get_relationships(place.id)
        (from_org,) = graph_store.get_relationships(org.id)
        assert (from_place["neighbor_id"], from_place["neighbor_name"]) == (org.id, "Kolvane Holdings")
        assert (from_org["neighbor_id"], from_org["neighbor_name"]) == (place.id, "Gdansk")

    def test_every_existing_key_is_kept(self, graph_store, located):
        _org, place = located
        (rel,) = graph_store.get_relationships(place.id)
        for key in ("rel_type", "source_id", "source_name", "target_id", "target_name",
                    "confidence", "evidence", "source_doc_id"):
            assert key in rel, key
        assert rel["rel_type"] == "LOCATED_AT"
        assert rel["evidence"] == "Kolvane Holdings, based in Gdansk"


class TestBulkRead:
    def test_an_incoming_edge_keeps_its_true_source(self, graph_store, located):
        org, place = located
        (rel,) = graph_store.get_relationships_bulk([place.id])[place.id]
        assert (rel["source_id"], rel["target_id"]) == (org.id, place.id)
        assert rel["direction"] == "in"

    def test_one_edge_is_read_from_each_end_with_opposite_directions(self, graph_store, located):
        org, place = located
        got = graph_store.get_relationships_bulk([org.id, place.id])
        (at_org,) = got[org.id]
        (at_place,) = got[place.id]
        assert (at_org["source_id"], at_org["target_id"]) == (at_place["source_id"], at_place["target_id"])
        assert (at_org["direction"], at_place["direction"]) == ("out", "in")

    def test_matches_the_single_read_shape(self, graph_store, located):
        _org, place = located
        (one,) = graph_store.get_relationships(place.id)
        (bulk,) = graph_store.get_relationships_bulk([place.id])[place.id]
        assert one == bulk
