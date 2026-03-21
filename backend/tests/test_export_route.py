from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}

def test_export_graph():
    resp = client.get("/api/export/graph", params={"project_id": "test"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data

def test_export_entities():
    resp = client.get("/api/export/entities", params={"project_id": "test"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "csv" in data

def test_export_stix():
    resp = client.get("/api/export/stix", params={"project_id": "test"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "bundle"
