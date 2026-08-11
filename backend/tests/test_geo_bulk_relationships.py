"""Relationships fetched once for the whole geo view.

/api/geo/locations read every location's relationships to enrich the markers,
then `_compute_location_edges` walked the same ground again to find shared
entities. On a project with 398 locations that was 796 round trips and 10.2s of
an 11.2s response — the map's own endpoint, so the wait was the map.
"""
from __future__ import annotations

import pytest

from intel_platform.api.routes.geo import _compute_location_edges
from intel_platform.models.entities import Location, Organization
from intel_platform.models.relationships import Relationship

PROJECT = "test-geo-bulk"


@pytest.fixture
def seeded(graph_store):
    """Two places sharing one organization, plus an unconnected place."""
    oslo = Location(name="Oslo", project_id=PROJECT)
    gdansk = Location(name="Gdansk", project_id=PROJECT)
    lonely = Location(name="Nowhere", project_id=PROJECT)
    shared = Organization(name="Shared Shipping", project_id=PROJECT)
    for e in (oslo, gdansk, lonely, shared):
        graph_store.create_entity(e)
    for place in (oslo, gdansk):
        graph_store.create_relationship(Relationship(
            source_id=place.id, target_id=shared.id, rel_type="ASSOCIATED_WITH",
            confidence=1.0, source="test", method="test",
        ))
    return {"oslo": oslo, "gdansk": gdansk, "lonely": lonely, "shared": shared}


class TestBulkFetch:
    def test_it_matches_the_per_entity_call(self, graph_store, seeded):
        """The bulk result must be the same data, or the view changes meaning."""
        oslo = seeded["oslo"]
        one = graph_store.get_relationships(oslo.id)
        bulk = graph_store.get_relationships_bulk([oslo.id])[oslo.id]
        assert sorted(r["target_id"] for r in one) == sorted(r["target_id"] for r in bulk)
        assert one[0].keys() == bulk[0].keys()

    def test_several_entities_come_back_keyed_by_id(self, graph_store, seeded):
        got = graph_store.get_relationships_bulk([seeded["oslo"].id, seeded["gdansk"].id])
        assert set(got) == {seeded["oslo"].id, seeded["gdansk"].id}

    def test_an_entity_with_no_relationships_is_absent_not_empty(self, graph_store, seeded):
        """Callers use .get(id, []) — absent means none, and the distinction
        matters more than saving them a default."""
        got = graph_store.get_relationships_bulk([seeded["lonely"].id])
        assert seeded["lonely"].id not in got

    def test_an_empty_request_makes_no_query(self, graph_store):
        assert graph_store.get_relationships_bulk([]) == {}

    def test_an_unknown_id_is_simply_absent(self, graph_store, seeded):
        got = graph_store.get_relationships_bulk(["no-such-entity"])
        assert got == {}


class TestEdgesUseTheSharedFetch:
    def _locations(self, seeded):
        return [
            {"id": seeded["oslo"].id, "name": "Oslo", "latitude": 59.9, "longitude": 10.7},
            {"id": seeded["gdansk"].id, "name": "Gdansk", "latitude": 54.4, "longitude": 18.6},
        ]

    def test_edges_are_the_same_whether_or_not_a_fetch_is_supplied(self, graph_store, seeded):
        """Passing the caller's fetch in must not change the answer."""
        locs = self._locations(seeded)
        without = _compute_location_edges(locs, graph_store)
        supplied = graph_store.get_relationships_bulk([loc["id"] for loc in locs])
        with_fetch = _compute_location_edges(locs, graph_store, supplied)
        assert [(e["source_id"], e["target_id"], e["weight"]) for e in without] == \
               [(e["source_id"], e["target_id"], e["weight"]) for e in with_fetch]

    def test_a_shared_entity_produces_an_edge(self, graph_store, seeded):
        locs = self._locations(seeded)
        edges = _compute_location_edges(locs, graph_store)
        assert len(edges) == 1
        assert edges[0]["weight"] == 1

    def test_the_supplied_fetch_is_used_rather_than_re_querying(self, graph_store, seeded):
        """The whole point: the endpoint already has this data."""
        calls = []
        original = graph_store.get_relationships_bulk

        def counting(ids):
            calls.append(list(ids))
            return original(ids)

        graph_store.get_relationships_bulk = counting
        try:
            locs = self._locations(seeded)
            supplied = original([loc["id"] for loc in locs])
            _compute_location_edges(locs, graph_store, supplied)
        finally:
            graph_store.get_relationships_bulk = original
        assert calls == [], "re-queried despite being handed the relationships"
