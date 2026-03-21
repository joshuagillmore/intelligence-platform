from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}

def test_create_and_list_snapshots():
    resp = client.post("/api/snapshots", json={
        "project_id": "test", "name": "Test Snapshot", "entity_ids": ["fake-id-1", "fake-id-2"]
    }, headers=headers)
    assert resp.status_code == 200
    snapshot_id = resp.json()["id"]

    # List
    resp = client.get("/api/snapshots", params={"project_id": "test"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1

    # Delete
    resp = client.delete(f"/api/snapshots/{snapshot_id}", headers=headers)
    assert resp.status_code == 200

def test_snapshot_not_found():
    resp = client.get("/api/snapshots/nonexistent", headers=headers)
    assert resp.status_code == 404
