"""Where topic-label refinement sends its calls.

Refinement is one LLM call per cluster node. On a live run all 31 failed with
HTTP 429 from a Cohere trial key capped at 20/minute, the endpoint spent 19.3s
of a 20.6s response failing, and the UI showed topics named "wikipedia / wiki /
org" — the raw TF-IDF keywords. A local model was running the whole time and
could not be used, because refinement resolved its provider through
``_cloud_provider_from_env`` and that helper deliberately never returns Ollama.

``topics_llm_provider`` is the way out, mirroring ``collection_llm_provider``
for the same reason: high-volume, low-value-per-call work should not have to
share a rate-limited key with the work that matters.

The provider is async now: it reads keys from the key store as well as the
environment (see test_provider_precedence.py).
"""
from __future__ import annotations

import pytest

from intel_platform.api.routes import admin_config
from intel_platform.llm import providers
from intel_platform.llm.providers import _get_topics_provider


@pytest.fixture
def cfg(monkeypatch):
    """Pin settings on the Settings instance for the duration of a test.

    Every setting the provider reads is pinned, not only the ones a test
    changes: crawl4ai and litellm call load_dotenv() at import, which can pull
    a developer's real .env (TOPICS_LLM_PROVIDER=ollama, say) into the process
    and made these tests order-dependent.
    """
    from intel_platform.config import get_settings

    s = get_settings()
    monkeypatch.setitem(admin_config._llm_override, "provider", "")
    monkeypatch.setitem(admin_config._llm_override, "model", "")

    def _set(**kw):
        base = dict(
            topics_llm_provider="", topics_llm_model="", ollama_base_url="http://x:11434",
            default_llm_provider="ollama", default_llm_model="",
            cohere_api_key="", anthropic_api_key="", openai_api_key="",
        )
        base.update(kw)
        for k, v in base.items():
            monkeypatch.setitem(s.__dict__, k, v)
        return s
    return _set


@pytest.fixture
def keys(monkeypatch):
    def _set(**by_provider):
        async def _fake(name):
            return by_provider.get(name)
        monkeypatch.setattr(providers, "_resolve_api_key", _fake)
    return _set


class TestLocalRouting:
    async def test_ollama_is_used_when_asked_for(self, cfg, keys):
        cfg(topics_llm_provider="ollama")
        keys(cohere="k")
        provider = await _get_topics_provider()
        assert provider is not None
        assert provider.__class__.__name__ == "OllamaProvider"

    async def test_the_model_defaults_rather_than_being_blank(self, cfg, keys):
        """A blank model reaching Ollama is a 404 at call time, which surfaces
        as "refinement failed" — indistinguishable from the rate limit."""
        cfg(topics_llm_provider="ollama")
        keys()
        assert (await _get_topics_provider())._model == "qwen2.5:14b"

    async def test_an_explicit_model_wins(self, cfg, keys):
        cfg(topics_llm_provider="ollama", topics_llm_model="llama3.1:8b")
        keys()
        assert (await _get_topics_provider())._model == "llama3.1:8b"

    @pytest.mark.parametrize("value", ["Ollama", " OLLAMA ", "ollama"])
    async def test_the_setting_is_read_forgivingly(self, cfg, keys, value):
        """Case and stray whitespace in a .env value should not silently route
        back to a rate-limited cloud key."""
        cfg(topics_llm_provider=value)
        keys(cohere="k")
        assert (await _get_topics_provider()).__class__.__name__ == "OllamaProvider"


class TestUnsetBehaviourIsUnchanged:
    async def test_it_falls_through_to_the_cloud_provider(self, cfg, keys):
        cfg(topics_llm_provider="")
        keys(cohere="k")
        assert (await _get_topics_provider()).name().startswith("cohere:")

    async def test_none_still_means_keep_keyword_labels(self, cfg, keys):
        """The caller treats None as "do not refine". That contract has to
        survive, or a deployment with no keys at all starts erroring instead of
        degrading."""
        cfg(topics_llm_provider="")
        keys()
        assert await _get_topics_provider() is None

    async def test_an_unrecognised_provider_does_not_route_locally(self, cfg, keys):
        """Only "ollama" means local. A typo should fall through to existing
        behaviour rather than quietly picking a different model."""
        cfg(topics_llm_provider="olama")
        keys(cohere="k")
        assert (await _get_topics_provider()).name().startswith("cohere:")


class TestTheClusteringPathUsesIt:
    async def test_refinement_resolves_through_the_topics_provider(self, monkeypatch):
        """Guards the wiring, not the helper: document_clustering imported
        _cloud_provider_from_env directly, which is why a local model could not
        be used no matter how it was configured."""
        from intel_platform.services import document_clustering as dc

        called = {"n": 0}

        async def _fake():
            called["n"] += 1
            return None

        monkeypatch.setattr("intel_platform.llm.providers._get_topics_provider", _fake)
        tree = {"id": "t", "entity_type": "topic", "keywords": ["cable"],
                "doc_ids": ["d1"], "children": []}
        out = await dc.refine_labels_with_llm(tree, [("d1", "text")])

        assert called["n"] == 1, "refinement did not go through _get_topics_provider"
        assert out["label_source"] == "keywords"
