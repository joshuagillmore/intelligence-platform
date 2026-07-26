"""Dates are properties of the entity they date, not nodes in the graph.

A date has no agency — it cannot act, be targeted, or be attributed — so as a
node it only dilutes centrality and returns useless Graph-RAG context. As a
property it is directly filterable, which is what the network-graph brush needs.

Precision matters: "March 2026" parsed to a point lands on the 1st, and a corpus
of month-precision dates then draws a false spike on the 1st of every month.
"""
from __future__ import annotations

from intel_platform.api.routes.timeline import _bucket_key
from intel_platform.services.graph_builder import _types_compatible, resolve_entity_name
from intel_platform.services.extraction import (
    _date_bounds,
    _date_precision,
    _link_event_dates,
    resolve_date_text,
)
from datetime import datetime, timezone


class TestDatePrecision:
    def test_full_date_is_day_precision(self):
        assert _date_precision("12 March 2026") == "day"
        assert _date_precision("2026-03-12") == "day"

    def test_month_and_year_is_month_precision(self):
        assert _date_precision("March 2026") == "month"

    def test_year_only_is_year_precision(self):
        assert _date_precision("2024") == "year"

    def test_no_year_is_not_a_usable_date(self):
        """"last Tuesday" must not silently anchor to today."""
        for text in ("last Tuesday", "yesterday", "next week"):
            assert _date_precision(text) == "", text


class TestDateBounds:
    def test_year_spans_the_whole_year(self):
        start, end = _date_bounds(datetime(2024, 1, 1, tzinfo=timezone.utc), "year")
        assert start.startswith("2024-01-01")
        assert end.startswith("2024-12-31")

    def test_month_spans_the_whole_month(self):
        start, end = _date_bounds(datetime(2026, 3, 1, tzinfo=timezone.utc), "month")
        assert start.startswith("2026-03-01")
        assert end.startswith("2026-03-31")

    def test_december_rolls_the_year(self):
        start, end = _date_bounds(datetime(2026, 12, 1, tzinfo=timezone.utc), "month")
        assert start.startswith("2026-12-01")
        assert end.startswith("2026-12-31")

    def test_day_spans_one_day(self):
        start, end = _date_bounds(datetime(2026, 3, 12, tzinfo=timezone.utc), "day")
        assert start.startswith("2026-03-12")
        assert end.startswith("2026-03-12")


class TestResolveDateText:
    def test_keeps_the_source_wording(self):
        got = resolve_date_text("March 2026")
        assert got["date_text"] == "March 2026"
        assert got["date_precision"] == "month"
        assert got["t_start"].startswith("2026-03-01")
        assert got["t_end"].startswith("2026-03-31")

    def test_year_only_becomes_an_interval_not_a_point(self):
        """The whole reason precision is stored: 2024 is not 1 January 2024."""
        got = resolve_date_text("2024")
        assert got["t_start"].startswith("2024-01-01")
        assert got["t_end"].startswith("2024-12-31")
        assert got["date_precision"] == "year"

    def test_unusable_text_returns_none(self):
        assert resolve_date_text("last Tuesday") is None
        assert resolve_date_text("") is None


class TestAbsorption:
    def test_date_is_marked_absorbed(self):
        ents = [
            {"name": "MV Northern Star strike", "entity_type": "Event", "attributes": {}},
            {"name": "12 March 2026", "entity_type": "Date", "attributes": {}},
        ]
        _link_event_dates(ents, [{
            "source_name": "MV Northern Star strike",
            "target_name": "12 March 2026", "rel_type": "OCCURRED_ON",
        }])
        event, date = ents[0], ents[1]
        assert event["attributes"]["date_precision"] == "day"
        assert event["attributes"]["date_text"] == "12 March 2026"
        assert date["attributes"]["_absorbed"] is True

    def test_unresolvable_date_is_not_absorbed(self):
        """A date we could not resolve must stay a node rather than vanish."""
        ents = [
            {"name": "Some incident", "entity_type": "Event", "attributes": {}},
            {"name": "last Tuesday", "entity_type": "Date", "attributes": {}},
        ]
        _link_event_dates(ents, [{
            "source_name": "Some incident", "target_name": "last Tuesday",
            "rel_type": "OCCURRED_ON",
        }])
        assert "_absorbed" not in ents[1]["attributes"]


class TestBucketKey:
    def test_bucket_keys(self):
        dt = datetime(2026, 3, 12, 14, 30, tzinfo=timezone.utc)
        assert _bucket_key(dt, "day") == "2026-03-12"
        assert _bucket_key(dt, "month") == "2026-03"
        assert _bucket_key(dt, "year") == "2026"


class TestCrossTypeMergeIsBlocked:
    """Fuzzy resolution must not merge an event into the thing it happened to.

    Measured live: "MV Northern Star strike" (Event) scored ~0.95 Jaro-Winkler
    against "MV Northern Star" (Ship) on the shared prefix and was merged into
    it, destroying the event and the date attached to it — two of three dated
    events lost on a single passage.
    """

    def test_event_does_not_merge_into_a_ship(self):
        got = resolve_entity_name(
            "MV Northern Star strike", ["MV Northern Star"],
            entity_type="Event", existing_types={"MV Northern Star": "Ship"},
        )
        assert got is None

    def test_same_type_still_merges(self):
        got = resolve_entity_name(
            "MV Northern Starr", ["MV Northern Star"],
            entity_type="Ship", existing_types={"MV Northern Star": "Ship"},
        )
        assert got == "MV Northern Star"

    def test_same_parent_category_still_merges(self):
        """"Commander" and "Person" share a parent, so they may still merge."""
        assert _types_compatible("Commander", "Person")
        assert _types_compatible("Person", "Person")

    def test_unknown_type_stays_permissive(self):
        assert _types_compatible("", "Ship")
        assert _types_compatible("Ship", "")

    def test_distinct_categories_are_incompatible(self):
        assert not _types_compatible("Event", "Ship")
        assert not _types_compatible("Location", "Person")
