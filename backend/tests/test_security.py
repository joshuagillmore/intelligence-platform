from fastapi.testclient import TestClient
from intel_platform.api.app import app

client = TestClient(app)

def test_security_headers():
    resp = client.get("/health")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"

def test_unauthorized_access():
    resp = client.get("/api/projects", headers={"Authorization": "Bearer wrong-key"})
    assert resp.status_code == 401

def test_missing_auth():
    resp = client.get("/api/projects")
    assert resp.status_code == 401  # Missing authorization header
