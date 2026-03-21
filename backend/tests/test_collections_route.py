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
