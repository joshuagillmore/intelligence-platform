import pytest
from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.api.routes import health
from intel_platform.config import settings

client = TestClient(app)

_PROVIDER_FIELDS = (
    "default_llm_provider",
    "extraction_llm_provider",
    "collection_llm_provider",
    "embedding_provider",
)


@pytest.fixture
def no_ollama(monkeypatch):
    """Baseline: a deployment that touches Ollama on no code path at all."""
    for field in _PROVIDER_FIELDS:
        monkeypatch.setattr(settings, field, "cohere")
    return monkeypatch


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ok", "degraded")
    assert "neo4j_connected" in data


def test_ollama_not_in_use_when_no_path_uses_it(no_ollama):
    assert health._ollama_in_use() is False


@pytest.mark.parametrize("field", _PROVIDER_FIELDS)
def test_any_provider_field_set_to_ollama_counts_as_in_use(no_ollama, field):
    """The bug this covers: only ``default_llm_provider`` was consulted, so a
    cloud default with extraction/collection/embeddings offloaded to a local
    Ollama reported ``ollama_connected: false`` while Ollama was up and serving
    every document the platform ingested."""
    no_ollama.setattr(settings, field, "ollama")
    assert health._ollama_in_use() is True


def test_connected_is_reported_when_ollama_is_used_and_reachable(no_ollama, monkeypatch):
    monkeypatch.setattr(settings, "extraction_llm_provider", "ollama")
    monkeypatch.setattr(health, "_check_ollama", lambda: True)
    assert client.get("/health").json()["ollama_connected"] is True


def test_unreachable_ollama_degrades_status_when_it_is_depended_on(no_ollama, monkeypatch):
    monkeypatch.setattr(settings, "collection_llm_provider", "ollama")
    monkeypatch.setattr(health, "_check_ollama", lambda: False)
    assert client.get("/health").json()["status"] == "degraded"


def test_unused_ollama_does_not_degrade_status(no_ollama, monkeypatch):
    """An Ollama nobody talks to being down is not a degradation."""
    monkeypatch.setattr(health, "_check_ollama", lambda: False)
    data = client.get("/health").json()
    assert data["ollama_connected"] is False
    if data["neo4j_connected"]:
        assert data["status"] == "ok"
