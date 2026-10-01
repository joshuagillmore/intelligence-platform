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


# ---------------------------------------------------------------------------
# A run started by another API process is visible only through its job row.
# ---------------------------------------------------------------------------

class _JobRow:
    def __init__(self, status: str, seconds_ago: int):
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        self.status = status
        self.heartbeat_at = now - timedelta(seconds=seconds_ago)
        self.started_at = self.heartbeat_at
        self.created_at = self.heartbeat_at
        self.finished_at = None
        self.now = now


def _patch_job_table(monkeypatch, row: _JobRow | None, *, raise_error: bool = False):
    """Point the route's job-table read at an in-memory row (or a failure)."""
    from contextlib import asynccontextmanager

    from intel_platform.api.routes import collections as route
    from intel_platform.db import jobs

    @asynccontextmanager
    async def _session():
        yield object()

    class _Factory:
        def __call__(self):
            return _session()

    async def _latest(db, plan_id):
        if raise_error:
            raise RuntimeError("postgres is away")
        return (row, row.now) if row else (None, None)

    monkeypatch.setattr(route, "get_session_factory", lambda: _Factory(), raising=False)
    import intel_platform.db.engine as engine_module

    monkeypatch.setattr(engine_module, "get_session_factory", lambda: _Factory())
    monkeypatch.setattr(jobs, "latest_job", _latest)


def test_a_live_job_row_from_another_process_blocks(monkeypatch):
    monkeypatch.setattr("intel_platform.api.routes.collections.CollectionRunner", _NoopRunner)
    cid = _approved_collection()
    _patch_job_table(monkeypatch, _JobRow("running", seconds_ago=5))
    resp = client.post(f"/api/collections/{cid}/execute", headers=headers)
    assert resp.status_code == 409


def test_a_stalled_job_row_does_not_block(monkeypatch):
    monkeypatch.setattr("intel_platform.api.routes.collections.CollectionRunner", _NoopRunner)
    cid = _approved_collection()
    _patch_job_table(monkeypatch, _JobRow("running", seconds_ago=10_000))
    resp = client.post(f"/api/collections/{cid}/execute", headers=headers)
    assert resp.status_code == 202


def test_an_unreadable_job_table_means_not_live(monkeypatch):
    """The legacy path never needed Postgres; a database error must not become a 500."""
    monkeypatch.setattr("intel_platform.api.routes.collections.CollectionRunner", _NoopRunner)
    cid = _approved_collection()
    _patch_job_table(monkeypatch, None, raise_error=True)
    resp = client.post(f"/api/collections/{cid}/execute", headers=headers)
    assert resp.status_code == 202
