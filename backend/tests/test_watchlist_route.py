from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings
from tests.ids import tp

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}

def test_watchlist_empty():
    resp = client.get("/api/watchlist", params={"project_id": tp("wl")}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 0
