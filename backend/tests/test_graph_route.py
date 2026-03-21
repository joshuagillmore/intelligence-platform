from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}


def test_get_graph():
    response = client.get(
        "/api/graph", params={"project_id": "nonexistent"}, headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data


def test_get_communities():
    response = client.get(
        "/api/communities", params={"project_id": "nonexistent"}, headers=headers,
    )
    assert response.status_code == 200
