"""Low -> G: collection and topic providers resolve precedence in one place.

Two findings:

- ``collection/agentic.py::_get_agentic_provider`` re-implemented provider
  precedence and swapped Ollama for *any* cloud key, including when an admin
  had just chosen Ollama in the LLM hub. The precedence now lives in
  ``_get_collection_provider`` behind ``collection_llm_preference``
  ("cloud-first" by default, which keeps the swap for an Ollama that is only
  the configured default; "local-first" turns it off) and never overrides an
  explicit runtime choice of Ollama.
- The topics provider read env keys only, so a key stored through the admin
  UI was invisible to it, and it ignored the admin's provider override.
"""
from __future__ import annotations

import pytest

from intel_platform.api.routes import admin_config
from intel_platform.llm import providers
from intel_platform.llm.ollama import OllamaProvider


@pytest.fixture
def cfg(monkeypatch):
    """Pin every setting these functions read. Ambient config must not leak in:
    crawl4ai and litellm call load_dotenv() at import, which can pull a
    developer's real .env into the environment mid-suite."""
    from intel_platform.config import get_settings

    s = get_settings()

    def _set(**kw):
        base = dict(
            default_llm_provider="ollama", default_llm_model="qwen2.5:14b",
            collection_llm_provider="", collection_llm_model="",
            topics_llm_provider="", topics_llm_model="",
            ollama_base_url="http://ollama.test:11434",
            anthropic_api_key="", openai_api_key="", cohere_api_key="",
        )
        base.update(kw)
        for k, v in base.items():
            monkeypatch.setitem(s.__dict__, k, v)
        return s

    monkeypatch.setitem(admin_config._llm_override, "provider", "")
    monkeypatch.setitem(admin_config._llm_override, "model", "")
    return _set


@pytest.fixture
def keys(monkeypatch):
    """Keys as _resolve_api_key sees them (DB first, then env)."""
    def _set(**by_provider):
        async def _fake(name):
            return by_provider.get(name)
        monkeypatch.setattr(providers, "_resolve_api_key", _fake)
    return _set


def _override(monkeypatch, provider: str, model: str = ""):
    monkeypatch.setitem(admin_config._llm_override, "provider", provider)
    monkeypatch.setitem(admin_config._llm_override, "model", model)


# ---------------------------------------------------------------------------
# _get_collection_provider
# ---------------------------------------------------------------------------

class TestCollectionProvider:
    async def test_a_dedicated_ollama_collection_provider_is_used(self, cfg, keys):
        cfg(collection_llm_provider="ollama", collection_llm_model="llama3.1:8b")
        keys(cohere="c-key")
        p = await providers._get_collection_provider()
        assert isinstance(p, OllamaProvider) and p._model == "llama3.1:8b"

    async def test_cloud_first_swaps_a_default_ollama_for_a_cloud_key(self, cfg, keys):
        """The behaviour agentic relied on: .env ships DEFAULT_LLM_PROVIDER=ollama,
        and structured collection output is more reliable from a cloud model."""
        cfg()
        keys(cohere="c-key")
        p = await providers._get_collection_provider()
        assert p.name().startswith("cohere:")

    async def test_the_key_is_read_through_the_key_store(self, cfg, keys):
        """A key saved in the admin UI (DB) counts, not only env keys."""
        cfg(cohere_api_key="")
        keys(anthropic="db-stored-key")
        p = await providers._get_collection_provider()
        assert p.name().startswith("anthropic:")

    async def test_an_explicit_runtime_ollama_choice_is_honoured(self, cfg, keys, monkeypatch):
        """The bug: an admin picks Ollama in the LLM hub and collection still
        goes to the cloud because a key happens to exist."""
        cfg(default_llm_provider="anthropic")
        keys(anthropic="a-key", cohere="c-key")
        _override(monkeypatch, "ollama", "qwen2.5:7b")
        p = await providers._get_collection_provider()
        assert isinstance(p, OllamaProvider) and p._model == "qwen2.5:7b"

    @pytest.mark.parametrize("pref", ["local-first", "local_first", " Local-First "])
    async def test_local_first_keeps_ollama(self, cfg, keys, monkeypatch, pref):
        cfg(collection_llm_preference=pref)
        keys(cohere="c-key")
        p = await providers._get_collection_provider()
        assert isinstance(p, OllamaProvider)

    async def test_a_cloud_default_is_returned_as_is(self, cfg, keys):
        cfg(default_llm_provider="anthropic", default_llm_model="claude-x")
        keys(anthropic="a-key", cohere="c-key")
        p = await providers._get_collection_provider()
        assert p.name() == "anthropic:claude-x"

    async def test_a_non_ollama_collection_provider_is_not_swapped(self, cfg, keys):
        """Any explicit collection provider disables the swap (agentic's rule)."""
        cfg(collection_llm_provider="cohere")
        keys(cohere="c-key")
        p = await providers._get_collection_provider()
        assert isinstance(p, OllamaProvider)  # the default provider, unswapped

    async def test_no_cloud_key_leaves_ollama(self, cfg, keys):
        cfg()
        keys()
        p = await providers._get_collection_provider()
        assert isinstance(p, OllamaProvider)

    async def test_a_failing_key_lookup_leaves_ollama_rather_than_raising(self, cfg, monkeypatch):
        cfg()
        calls = {"n": 0}

        async def _boom(name):
            calls["n"] += 1
            if calls["n"] == 1:
                return None  # _get_provider's own lookups succeed
            raise ConnectionError("postgres down")

        monkeypatch.setattr(providers, "_resolve_api_key", _boom)
        p = await providers._get_collection_provider()
        assert isinstance(p, OllamaProvider)


# ---------------------------------------------------------------------------
# _get_topics_provider
# ---------------------------------------------------------------------------

class TestTopicsProvider:
    async def test_a_db_stored_key_is_used(self, cfg, keys):
        cfg(cohere_api_key="")
        keys(cohere="db-key")
        p = await providers._get_topics_provider()
        assert p is not None and p.name().startswith("cohere:")

    async def test_the_admin_override_provider_and_model_win(self, cfg, keys, monkeypatch):
        cfg()
        keys(cohere="c-key", anthropic="a-key")
        _override(monkeypatch, "anthropic", "claude-override")
        p = await providers._get_topics_provider()
        assert p.name() == "anthropic:claude-override"

    async def test_an_admin_ollama_choice_routes_locally(self, cfg, keys, monkeypatch):
        cfg()
        keys(cohere="c-key")
        _override(monkeypatch, "ollama", "")
        p = await providers._get_topics_provider()
        assert isinstance(p, OllamaProvider)

    async def test_a_cloud_default_provider_uses_its_configured_model(self, cfg, keys):
        cfg(default_llm_provider="openai", default_llm_model="gpt-x")
        keys(openai="o-key", cohere="c-key")
        p = await providers._get_topics_provider()
        assert p.name() == "openai:gpt-x"

    async def test_an_ollama_default_model_is_not_sent_to_a_cloud_provider(self, cfg, keys):
        """DEFAULT_LLM_MODEL=qwen2.5:14b belongs to the Ollama default; a cloud
        fallback uses its own default model."""
        cfg(default_llm_provider="ollama", default_llm_model="qwen2.5:14b")
        keys(cohere="c-key")
        p = await providers._get_topics_provider()
        assert p.name().startswith("cohere:") and "qwen" not in p.name()

    async def test_no_key_anywhere_is_none(self, cfg, keys):
        """None means keep keyword labels; a deployment with no keys degrades."""
        cfg()
        keys()
        assert await providers._get_topics_provider() is None

    async def test_a_key_store_outage_falls_back_to_env_keys(self, cfg, monkeypatch):
        cfg(cohere_api_key="env-key")

        async def _down(name):
            raise ConnectionError("postgres down")

        monkeypatch.setattr(providers, "_resolve_api_key", _down)
        p = await providers._get_topics_provider()
        assert p is not None and p.name().startswith("cohere:")
