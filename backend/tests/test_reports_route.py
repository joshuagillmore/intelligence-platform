from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}

def test_save_and_list_reports():
    # Create project first
    proj = client.post("/api/projects", json={"name": "Report Test"}, headers=headers).json()
    pid = proj["id"]

    # Save report
    resp = client.post("/api/reports", json={
        "project_id": pid, "title": "Test Report", "content": "Test content", "report_type": "INTSUM"
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["report_id"]

    # List reports
    resp = client.get("/api/reports", params={"project_id": pid}, headers=headers)
    assert resp.status_code == 200

    # Cleanup
    client.delete(f"/api/projects/{pid}", headers=headers)

def test_report_not_found():
    resp = client.get("/api/reports/nonexistent", headers=headers)
    assert resp.status_code == 404
