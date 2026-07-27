"""Timeline route shape, and that an unknown project_id is not a silent empty."""
from fastapi.testclient import TestClient

from intel_platform.api.app import app
from intel_platform.api.deps import get_graph_store
from intel_platform.config import settings

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


def _override():
    app.dependency_overrides[get_graph_store] = lambda: _Store()


def _clear():
    app.dependency_overrides.pop(get_graph_store, None)


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


def test_unknown_project_is_404_not_an_empty_timeline():
    """An id with nothing under it must not read as "the collection found nothing"."""
    _override()
    try:
        resp = client.get("/api/timeline", params={"project_id": "never-existed"}, headers=headers)
        assert resp.status_code == 404
        assert "never-existed" in resp.json()["detail"]
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
