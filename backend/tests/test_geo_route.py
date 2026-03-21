from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}

def test_geo_locations():
    resp = client.get("/api/geo/locations", params={"project_id": "test"}, headers=headers)
    assert resp.status_code == 200
    assert "locations" in resp.json()
    assert "total" in resp.json()
