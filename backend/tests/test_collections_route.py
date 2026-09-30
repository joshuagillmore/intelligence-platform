from fastapi.testclient import TestClient

from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}


def test_create_collection():
    response = client.post(
        "/api/collections", json={"project_id": "test-proj", "pir": "Find info about APT-29"}, headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["project_id"] == "test-proj"
    assert data["status"] == "PENDING"


def test_get_collection():
    create_resp = client.post("/api/collections", json={"project_id": "test-proj"}, headers=headers)
    task_id = create_resp.json()["id"]
    response = client.get(f"/api/collections/{task_id}", headers=headers)
    assert response.status_code == 200


def test_get_collection_status():
    create_resp = client.post("/api/collections", json={"project_id": "test-proj"}, headers=headers)
    task_id = create_resp.json()["id"]
    response = client.get(f"/api/collections/{task_id}/status", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "PENDING"


def test_cancel_collection():
    create_resp = client.post("/api/collections", json={"project_id": "test-proj"}, headers=headers)
    task_id = create_resp.json()["id"]
    response = client.post(f"/api/collections/{task_id}/cancel", headers=headers)
    assert response.status_code == 200


def test_list_collections():
    response = client.get("/api/collections", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_collection_not_found():
    response = client.get("/api/collections/nonexistent", headers=headers)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# C-14: whether a run is in flight is answered by the process, not the flag
# ---------------------------------------------------------------------------

def _approved_collection(status: str | None = None) -> str:
    plan = [{"id": 1, "description": "x", "source_type": "web_search", "approved": True}]
    task_id = client.post(
        "/api/collections", json={"project_id": "test-proj", "plan": plan}, headers=headers,
    ).json()["id"]
    if status:
        client.put(f"/api/collections/{task_id}", json={"status": status}, headers=headers)
    return task_id


class _NoopRunner:
    calls: list = []

    def __init__(self, store):
        pass

    async def execute(self, collection_id, **kwargs):
        _NoopRunner.calls.append(collection_id)
        return {"status": "SUCCESS"}


def test_a_status_left_behind_by_a_restart_does_not_lock_the_collection(monkeypatch):
    """STARTED written by a process that has since died used to 409 forever."""
    monkeypatch.setattr("intel_platform.api.routes.collections.CollectionRunner", _NoopRunner)
    _NoopRunner.calls = []
    task_id = _approved_collection(status="STARTED")

    response = client.post(f"/api/collections/{task_id}/execute", headers=headers)
    assert response.status_code == 202
    assert _NoopRunner.calls == [task_id]


def test_a_run_in_flight_in_this_process_still_blocks(monkeypatch):
    from intel_platform.api.routes import collections as route

    monkeypatch.setattr(route, "CollectionRunner", _NoopRunner)
    task_id = _approved_collection()
    monkeypatch.setattr(route, "_running_collections", {task_id})

    response = client.post(f"/api/collections/{task_id}/execute", headers=headers)
    assert response.status_code == 409


def test_a_finished_run_leaves_nothing_in_flight(monkeypatch):
    from intel_platform.api.routes import collections as route

    monkeypatch.setattr(route, "CollectionRunner", _NoopRunner)
    task_id = _approved_collection()
    client.post(f"/api/collections/{task_id}/execute", headers=headers)
    assert task_id not in route._running_collections


def test_accepting_a_run_marks_it_started_even_after_a_cancel(monkeypatch):
    """A cancelled collection can be run again: the route writes STARTED when
    it accepts the run, which is what replaces the old REVOKED."""
    monkeypatch.setattr("intel_platform.api.routes.collections.CollectionRunner", _NoopRunner)
    task_id = _approved_collection(status="REVOKED")

    assert client.post(f"/api/collections/{task_id}/execute", headers=headers).status_code == 202
    assert client.get(f"/api/collections/{task_id}/status", headers=headers).json()["status"] == "STARTED"


def test_cancel_records_revoked():
    task_id = _approved_collection()
    client.post(f"/api/collections/{task_id}/cancel", headers=headers)
    assert client.get(f"/api/collections/{task_id}/status", headers=headers).json()["status"] == "REVOKED"
