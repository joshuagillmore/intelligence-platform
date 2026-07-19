import pytest
from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.api.routes import llm as llm_routes
from intel_platform.config import settings
from intel_platform.llm.base import LLMProvider, LLMResponse

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}


class FakeLLMProvider(LLMProvider):
    """Deterministic provider double for route tests — no network I/O.

    Mirrors the ``MockProvider`` pattern used in test_llm_orchestrator.py,
    plus records the last call so tests can assert the route wired the
    skill/system prompt through correctly.
    """

    def __init__(self, response_text: str = "Mock response", model: str = "fake-model"):
        self._response_text = response_text
        self._model = model
        self.last_messages: list[dict] | None = None
        self.last_system: str | None = None

    async def generate(self, messages, system="", temperature=0.3, max_tokens=4096):
        self.last_messages = messages
        self.last_system = system
        return LLMResponse(content=self._response_text, model=self._model, input_tokens=10, output_tokens=5)

    async def stream(self, messages, system="", temperature=0.3, max_tokens=4096):
        for word in self._response_text.split():
            yield word + " "

    def name(self):
        return "fake"


@pytest.fixture
def fake_provider(monkeypatch):
    """Patch the route's provider seam (`_get_provider`) so /llm/query never hits the network."""
    provider = FakeLLMProvider(response_text="PROBABILITY: 0.75\nMocked assessment content.")

    async def _fake_get_provider():
        return provider

    monkeypatch.setattr(llm_routes, "_get_provider", _fake_get_provider)
    return provider


def test_list_skills():
    response = client.get("/api/llm/skills", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["skills"]) >= 7


def test_llm_query_with_skill(fake_provider):
    response = client.post(
        "/api/llm/query",
        json={"messages": [{"role": "user", "content": "Assess APT-29"}], "skill_name": "threat_assessment"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["skill_applied"] == "threat_assessment"
    assert data["content"] == fake_provider._response_text
    assert data["model"] == "fake-model"
    # PROBABILITY line is parsed out of the (mocked) content for this skill.
    assert data["probability"] == 0.75
    # The route resolved the skill's system prompt and passed it to the provider.
    assert fake_provider.last_system
    assert "threat" in fake_provider.last_system.lower()
    assert fake_provider.last_messages == [{"role": "user", "content": "Assess APT-29"}]


def test_llm_query_without_skill(fake_provider):
    response = client.post(
        "/api/llm/query",
        json={"messages": [{"role": "user", "content": "Hello"}]},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["skill_applied"] is None
    assert data["content"] == fake_provider._response_text
    assert "probability" not in data
    # No skill requested -> no system prompt injected.
    assert fake_provider.last_system == ""
