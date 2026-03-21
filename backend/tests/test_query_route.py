from fastapi.testclient import TestClient

from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}


def test_graph_rag_query():
    response = client.post(
        "/api/query",
        json={"project_id": "nonexistent", "query": "test query"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "context" in data
    assert "query" in data
