"""Timeline route shape, and that an unknown project_id is not a silent empty."""
from fastapi.testclient import TestClient

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from intel_platform.api.app import app
from intel_platform.api.deps import get_graph_store
from intel_platform.api.routes import timeline as timeline_routes
from intel_platform.config import settings
from tests.ids import tp

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}


class _Store:
    """Graph store stub: one project that exists and holds one entity."""

    def get_project(self, project_id):
        return {"id": project_id, "name": "Real"} if project_id == "real" else None

    def search_entities(self, project_id, **kw):
        if project_id != "real":
            return []
        return [{
            "id": "e1", "name": "Some incident", "entity_type": "Event",
            "created_at": "2026-03-12T00:00:00+00:00",
            "event_datetime": "2026-03-12T00:00:00+00:00",
            "date_precision": "day", "date_text": "12 March 2026",
        }]


_REAL_PAGE = timeline_routes._timeline_page


def _stub_page(store, project_id, limit, offset):
    """The ranked Cypher read is exercised against Neo4j below; here it is the stub's list."""
    rows = store.search_entities(project_id)
    return rows[offset:offset + limit], len(rows), sorted({r["entity_type"] for r in rows})


def _override():
    app.dependency_overrides[get_graph_store] = lambda: _Store()
    timeline_routes._timeline_page = _stub_page


def _clear():
    app.dependency_overrides.pop(get_graph_store, None)
    timeline_routes._timeline_page = _REAL_PAGE


def test_timeline_shape():
    _override()
    try:
        resp = client.get("/api/timeline", params={"project_id": "real"}, headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "events" in body and "count" in body
        assert body["count"] == 1
        assert body["events"][0]["date_precision"] == "day"
    finally:
        _clear()


def test_unknown_project_is_flagged_not_silently_empty():
    """An id with nothing under it must not read as "the collection found nothing".

    Still 200 with an empty list — that contract is deliberate — but the caller
    can now tell an unknown project from an empty one.
    """
    _override()
    try:
        resp = client.get("/api/timeline", params={"project_id": "never-existed"}, headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 0
        assert body["project_exists"] is False
    finally:
        _clear()


def test_real_project_is_flagged_as_existing():
    _override()
    try:
        body = client.get("/api/timeline", params={"project_id": "real"}, headers=headers).json()
        assert body["project_exists"] is True
    finally:
        _clear()


def test_histogram_shape():
    _override()
    try:
        resp = client.get(
            "/api/timeline/histogram",
            params={"project_id": "real", "bucket": "month"}, headers=headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["dated"] == 1
        assert body["bins"][0]["key"] == "2026-03"
    finally:
        _clear()


# ---------------------------------------------------------------------------
# Contract 10 / P-9: the timeline is the newest events, not the newest of an
# alphabetical slice. It was `search_entities(limit=500)` — ordered by name —
# sorted by date afterwards, and `count` was the length of that slice, so a
# large project's "Recent Activity" was whatever happened to sort early.
# ---------------------------------------------------------------------------

@pytest.fixture
def dated_project(graph_store):
    from intel_platform.models.entities import Event, Organization, ThreatActor

    pid = tp(f"timeline-{uuid.uuid4().hex[:8]}")
    utc = timezone.utc
    graph_store.create_entity(Event(name="Aardvark incident", project_id=pid,
                                    event_datetime=datetime(2020, 5, 1, tzinfo=utc)))
    graph_store.create_entity(Event(name="Zulu incident", project_id=pid,
                                    event_datetime=datetime(2025, 3, 12, tzinfo=utc)))
    # No event date: falls back to ingestion time, which is now — the newest.
    graph_store.create_entity(Organization(name="Middle Org", project_id=pid))
    # Oldest of all, and the only entity of its type.
    graph_store.create_entity(ThreatActor(name="Bravo Group", project_id=pid,
                                          event_datetime=datetime(2019, 1, 1, tzinfo=utc)))
    return pid


def _timeline(graph_store, pid, **params):
    app.dependency_overrides[get_graph_store] = lambda: graph_store
    try:
        return client.get("/api/timeline", params={"project_id": pid, **params}, headers=headers).json()
    finally:
        app.dependency_overrides.pop(get_graph_store, None)


def test_newest_first_across_the_whole_project(graph_store, dated_project):
    body = _timeline(graph_store, dated_project)
    assert [e["name"] for e in body["events"]] == [
        "Middle Org", "Zulu incident", "Aardvark incident", "Bravo Group",
    ]
    assert body["events"][0]["event_type"] == "entity_created"
    assert body["events"][1]["event_type"] == "event"


def test_a_page_reports_the_true_total(graph_store, dated_project):
    body = _timeline(graph_store, dated_project, limit=2)
    assert [e["name"] for e in body["events"]] == ["Middle Org", "Zulu incident"]
    assert body["count"] == 2
    assert body["total"] == 4
    assert body["truncated"] is True


def test_types_present_covers_the_project_not_the_page(graph_store, dated_project):
    body = _timeline(graph_store, dated_project, limit=1)
    assert body["types_present"] == ["Event", "Organization", "ThreatActor"]


def test_offset_pages_on(graph_store, dated_project):
    body = _timeline(graph_store, dated_project, limit=2, offset=2)
    assert [e["name"] for e in body["events"]] == ["Aardvark incident", "Bravo Group"]
    assert body["truncated"] is False


def test_a_whole_project_is_not_truncated(graph_store, dated_project):
    body = _timeline(graph_store, dated_project)
    assert (body["count"], body["total"], body["truncated"]) == (4, 4, False)


def test_no_document_content_is_shipped(graph_store, dated_project):
    from intel_platform.models.entities import Document

    graph_store.create_entity(Document(name="big page", content="x" * 20000, project_id=dated_project))
    body = _timeline(graph_store, dated_project)
    assert all("content" not in e for e in body["events"])


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 100000}, {"offset": -1}])
def test_paging_is_bounded(params):
    _override()
    try:
        assert client.get("/api/timeline", params={"project_id": "real", **params},
                          headers=headers).status_code == 422
    finally:
        _clear()


def test_now_is_newer_than_any_extracted_date(graph_store, dated_project):
    """Guard on the fixture itself: `created_at` is ingestion time (now)."""
    body = _timeline(graph_store, dated_project, limit=1)
    ts = body["events"][0]["timestamp"]
    assert datetime.fromisoformat(ts.replace("Z", "+00:00")) > datetime.now(timezone.utc) - timedelta(hours=1)
