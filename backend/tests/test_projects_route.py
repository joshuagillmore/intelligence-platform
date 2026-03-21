from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}


def test_create_project():
    response = client.post(
        "/api/projects",
        json={"name": "Test Route Project", "description": "Testing"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Route Project"
    assert data["status"] == "active"
    client.delete(f"/api/projects/{data['id']}", headers=headers)


def test_list_projects():
    response = client.get("/api/projects", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_unauthorized():
    response = client.get("/api/projects", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401
