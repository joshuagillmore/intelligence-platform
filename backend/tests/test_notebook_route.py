from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}

def test_create_and_list_notes():
    # Create project
    proj = client.post("/api/projects", json={"name": "Notebook Test"}, headers=headers).json()
    pid = proj["id"]

    # Create note
    resp = client.post("/api/notebook", json={
        "project_id": pid, "title": "Test Note", "content": "Test content", "note_type": "observation"
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "Test Note"

    # Cleanup
    client.delete(f"/api/projects/{pid}", headers=headers)
