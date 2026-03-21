from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}


def test_ingest_text():
    proj = client.post(
        "/api/projects",
        json={"name": "Ingest Test Project"},
        headers=headers,
    ).json()

    response = client.post(
        "/api/ingest",
        data={
            "project_id": proj["id"],
            "content": "John Smith from Microsoft met with officials in Washington.",
            "reliability_rating": "B2",
        },
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"]
    assert data["chunks"] >= 1
    client.delete(f"/api/projects/{proj['id']}", headers=headers)
