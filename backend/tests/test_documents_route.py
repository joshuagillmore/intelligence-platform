from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}

def test_list_documents():
    resp = client.get("/api/documents", params={"project_id": "test"}, headers=headers)
    assert resp.status_code == 200
    assert "documents" in resp.json()

def test_get_document_not_found():
    resp = client.get("/api/documents/nonexistent", headers=headers)
    assert resp.status_code == 404
