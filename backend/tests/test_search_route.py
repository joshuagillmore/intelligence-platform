from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}

def test_search():
    resp = client.get("/api/search", params={"project_id": "test", "q": "test"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "entities" in data
    assert "documents" in data
    assert "total" in data
