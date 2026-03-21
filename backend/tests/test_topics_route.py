from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}

def test_get_topic_tree():
    response = client.get("/api/topics", params={"project_id": "nonexistent"}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "children" in data
    assert "entity_count" in data

def test_get_topic_context_not_found():
    response = client.get("/api/topics/nonexistent", params={"project_id": "test"}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "error" in data
