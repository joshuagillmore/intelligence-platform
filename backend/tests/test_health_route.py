import urllib.request
from types import SimpleNamespace

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


def _boom():
    raise AssertionError("_check_ollama was called when Ollama is on no code path")


@pytest.fixture
def no_ollama(monkeypatch):
    """Baseline: a deployment that touches Ollama on no code path at all.

    A cloud key is set because the absence of one makes Ollama the terminal
    fallback in both provider chains — without it this is not an
    Ollama-free deployment.
    """
    for field in _PROVIDER_FIELDS:
        monkeypatch.setattr(settings, field, "cohere")
    monkeypatch.setattr(settings, "cohere_api_key", "test-key")
    monkeypatch.setattr(health, "_probe_cache", None)
    # Neo4j is stubbed healthy so status assertions test the Ollama logic and
    # not whether a live database happened to be up.
    monkeypatch.setattr(
        health, "get_neo4j_driver", lambda: SimpleNamespace(verify_connectivity=lambda: None)
    )
    return monkeypatch


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ok", "degraded")
    assert "neo4j_connected" in data


def test_ollama_not_configured_when_no_path_uses_it(no_ollama):
    assert health._ollama_configured() is False
    assert health._ollama_is_fallback() is False


@pytest.mark.parametrize("field", _PROVIDER_FIELDS)
def test_any_provider_field_set_to_ollama_counts_as_configured(no_ollama, field):
    """The bug this covers: only ``default_llm_provider`` was consulted, so a
    cloud default with extraction/collection/embeddings offloaded to a local
    Ollama reported ``ollama_connected: false`` while Ollama was up and serving
    every document the platform ingested."""
    no_ollama.setattr(settings, field, "ollama")
    assert health._ollama_configured() is True


def test_provider_name_is_matched_case_insensitively(no_ollama):
    """``embeddings.py`` lowercases before comparing, so EMBEDDING_PROVIDER=Ollama
    really does route to Ollama."""
    no_ollama.setattr(settings, "embedding_provider", "Ollama")
    assert health._ollama_configured() is True


def test_admin_runtime_override_counts_as_configured(no_ollama):
    """``_get_provider`` obeys the admin override, not ``default_llm_provider``."""
    from intel_platform.api.routes import admin_config

    no_ollama.setattr(admin_config, "get_active_provider", lambda: "ollama")
    assert health._ollama_configured() is True


def test_no_cloud_key_means_the_fallback_chains_reach_ollama(no_ollama):
    for key in ("anthropic_api_key", "openai_api_key", "cohere_api_key"):
        no_ollama.setattr(settings, key, "")
    assert health._ollama_configured() is False
    assert health._ollama_is_fallback() is True


def test_connected_is_reported_when_ollama_is_used_and_reachable(no_ollama):
    no_ollama.setattr(settings, "extraction_llm_provider", "ollama")
    no_ollama.setattr(health, "_check_ollama", lambda: True)
    assert client.get("/health").json()["ollama_connected"] is True


def test_unreachable_ollama_degrades_status_when_it_is_depended_on(no_ollama):
    no_ollama.setattr(settings, "collection_llm_provider", "ollama")
    no_ollama.setattr(health, "_check_ollama", lambda: False)
    data = client.get("/health").json()
    assert data["neo4j_connected"] is True, "stub failed; status would be meaningless"
    assert data["status"] == "degraded"


def test_unused_ollama_is_never_probed(no_ollama):
    """An Ollama nobody talks to is not consulted at all.

    ``_check_ollama`` raises rather than returning False: a lambda returning
    False cannot tell "the probe was skipped" from "the probe ran and failed",
    which is the entire property under test.
    """
    no_ollama.setattr(health, "_check_ollama", _boom)
    data = client.get("/health").json()
    assert data["ollama_connected"] is False
    assert data["status"] == "ok"


def test_fallback_only_ollama_is_probed_but_never_degrades(no_ollama):
    """Reachability is inferred from missing env keys, but keys can live in the
    database — a guess must not manufacture a degraded status."""
    for key in ("anthropic_api_key", "openai_api_key", "cohere_api_key"):
        no_ollama.setattr(settings, key, "")
    no_ollama.setattr(health, "_check_ollama", lambda: False)
    data = client.get("/health").json()
    assert data["status"] == "ok"


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_probe_result_is_cached_between_requests(no_ollama):
    """The probe is a blocking 3s call and two UI components poll /health every
    30s, so a widened gate must not mean a network round trip per request."""
    calls = []

    def counting_urlopen(*args, **kwargs):
        calls.append(1)
        return _FakeResponse()

    no_ollama.setattr(settings, "extraction_llm_provider", "ollama")
    no_ollama.setattr(urllib.request, "urlopen", counting_urlopen)

    assert client.get("/health").json()["ollama_connected"] is True
    assert client.get("/health").json()["ollama_connected"] is True
    assert len(calls) == 1, f"probe ran {len(calls)} times across two requests"
