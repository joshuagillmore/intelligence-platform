from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}


def test_list_skills():
    response = client.get("/api/llm/skills", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["skills"]) >= 7


def test_llm_query_with_skill():
    response = client.post("/api/llm/query", json={"messages": [{"role": "user", "content": "Assess APT-29"}], "skill_name": "threat_assessment"}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["skill_applied"] == "threat_assessment"
    assert "content" in data


def test_llm_query_without_skill():
    response = client.post("/api/llm/query", json={"messages": [{"role": "user", "content": "Hello"}]}, headers=headers)
    assert response.status_code == 200
