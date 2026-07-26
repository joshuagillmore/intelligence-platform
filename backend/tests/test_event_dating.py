"""Events are linked to the dates they happened on.

The timeline sorts by `Event.event_datetime`, falling back to ingestion time.
Measured across a 15-run campaign before this fix: 2 of 6,221 entities carried
an event_datetime and only 22 of 2,418 relationships were OCCURRED_ON, so every
timeline was an ingestion log rather than a chronology.

Root cause was not the linking code but its input: models name the event only in
the relationship and never extract it as an entity, and they emit the edge in
either direction.
"""
from __future__ import annotations

from intel_platform.services.extraction import _link_event_dates


def _date(name):
    return {"name": name, "entity_type": "Date", "attributes": {}}


def _event(name):
    return {"name": name, "entity_type": "Event", "attributes": {}}


def _rel(src, tgt):
    return {"source_name": src, "target_name": tgt, "rel_type": "OCCURRED_ON"}


class TestLinkEventDates:
    def test_event_to_date_is_resolved(self):
        ents = [_event("MV Northern Star strike"), _date("12 March 2026")]
        _link_event_dates(ents, [_rel("MV Northern Star strike", "12 March 2026")])
        assert ents[0]["attributes"]["event_datetime"].startswith("2026-03-12")

    def test_reversed_edge_is_oriented(self):
        """Observed live: "12 March 2026 OCCURRED_ON strike"."""
        ents = [_event("MV Northern Star strike"), _date("12 March 2026")]
        rels = [_rel("12 March 2026", "MV Northern Star strike")]
        _link_event_dates(ents, rels)
        assert ents[0]["attributes"]["event_datetime"].startswith("2026-03-12")
        # The relationship is corrected in place so the graph stores it one way.
        assert rels[0]["source_name"] == "MV Northern Star strike"
        assert rels[0]["target_name"] == "12 March 2026"

    def test_missing_event_entity_is_recovered(self):
        """The common live case: the event exists only as a relationship endpoint.

        Without recovery the edge names an entity that was never created, so
        graph_builder drops it and the date is lost.
        """
        ents = [_date("19 March 2026")]
        _link_event_dates(ents, [_rel("MT Coral Sky strike", "19 March 2026")])
        recovered = [e for e in ents if e["name"] == "MT Coral Sky strike"]
        assert len(recovered) == 1
        assert recovered[0]["entity_type"] == "Event"
        assert recovered[0]["attributes"]["event_datetime"].startswith("2026-03-19")

    def test_missing_event_recovered_from_reversed_edge(self):
        ents = [_date("January 2025")]
        _link_event_dates(ents, [_rel("January 2025", "Drone strike on tanker")])
        recovered = [e for e in ents if e["name"] == "Drone strike on tanker"]
        assert len(recovered) == 1
        assert recovered[0]["attributes"]["event_datetime"].startswith("2025-01")

    def test_unparseable_date_leaves_event_undated(self):
        ents = [_event("Some incident"), _date("sometime last year")]
        _link_event_dates(ents, [_rel("Some incident", "sometime last year")])
        assert "event_datetime" not in ents[0]["attributes"]

    def test_non_date_target_is_ignored(self):
        ents = [_event("Some incident"),
                {"name": "Red Sea", "entity_type": "Location", "attributes": {}}]
        _link_event_dates(ents, [_rel("Some incident", "Red Sea")])
        assert "event_datetime" not in ents[0]["attributes"]
        assert len(ents) == 2, "must not invent an entity for a non-date edge"

    def test_non_occurred_on_relationships_untouched(self):
        ents = [_date("12 March 2026")]
        rels = [{"source_name": "A", "target_name": "12 March 2026", "rel_type": "TARGETS"}]
        _link_event_dates(ents, rels)
        assert len(ents) == 1, "only OCCURRED_ON may recover an event"

    def test_existing_datetime_is_not_overwritten(self):
        ev = _event("Incident")
        ev["attributes"]["event_datetime"] = "2020-01-01T00:00:00+00:00"
        ents = [ev, _date("12 March 2026")]
        _link_event_dates(ents, [_rel("Incident", "12 March 2026")])
        assert ents[0]["attributes"]["event_datetime"].startswith("2020-01-01")

    def test_blank_endpoint_is_not_recovered(self):
        ents = [_date("12 March 2026")]
        _link_event_dates(ents, [_rel("   ", "12 March 2026")])
        assert len(ents) == 1
