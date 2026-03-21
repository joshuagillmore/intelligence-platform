from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}


def test_search_entities():
    response = client.get(
        "/api/entities", params={"project_id": "nonexistent"}, headers=headers,
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_entity_not_found():
    response = client.get("/api/entities/nonexistent-id", headers=headers)
    assert response.status_code == 404
