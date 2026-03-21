from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}

def test_list_personas():
    resp = client.get("/api/personas", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["personas"]) >= 4
    assert data["active_persona"]

def test_activate_persona():
    resp = client.post("/api/personas/cyber_analyst/activate", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["active_persona"] == "cyber_analyst"
