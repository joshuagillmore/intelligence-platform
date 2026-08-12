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
"""
from __future__ import annotations

import pytest

from intel_platform.llm.providers import _get_topics_provider


@pytest.fixture
def cfg(monkeypatch):
    """Set settings attributes for the duration of a test."""
    from intel_platform.config import settings

    def _set(**kw):
        for k, v in kw.items():
            monkeypatch.setattr(settings, k, v, raising=False)
        return settings
    return _set


class TestLocalRouting:
    def test_ollama_is_used_when_asked_for(self, cfg):
        cfg(topics_llm_provider="ollama", topics_llm_model="", ollama_base_url="http://x:11434")
        provider = _get_topics_provider()
        assert provider is not None
        assert provider.__class__.__name__ == "OllamaProvider"

    def test_the_model_defaults_rather_than_being_blank(self, cfg):
        """A blank model reaching Ollama is a 404 at call time, which surfaces
        as "refinement failed" — indistinguishable from the rate limit."""
        cfg(topics_llm_provider="ollama", topics_llm_model="", ollama_base_url="http://x:11434")
        assert _get_topics_provider()._model == "qwen2.5:14b"

    def test_an_explicit_model_wins(self, cfg):
        cfg(topics_llm_provider="ollama", topics_llm_model="llama3.1:8b",
            ollama_base_url="http://x:11434")
        assert _get_topics_provider()._model == "llama3.1:8b"

    @pytest.mark.parametrize("value", ["Ollama", " OLLAMA ", "ollama"])
    def test_the_setting_is_read_forgivingly(self, cfg, value):
        """Case and stray whitespace in a .env value should not silently route
        back to a rate-limited cloud key."""
        cfg(topics_llm_provider=value, topics_llm_model="", ollama_base_url="http://x:11434")
        assert _get_topics_provider().__class__.__name__ == "OllamaProvider"


class TestUnsetBehaviourIsUnchanged:
    def test_it_falls_through_to_the_cloud_provider(self, cfg, monkeypatch):
        sentinel = object()
        monkeypatch.setattr(
            "intel_platform.llm.providers._cloud_provider_from_env", lambda: sentinel
        )
        cfg(topics_llm_provider="")
        assert _get_topics_provider() is sentinel

    def test_none_still_means_keep_keyword_labels(self, cfg, monkeypatch):
        """The caller treats None as "do not refine". That contract has to
        survive, or a deployment with no keys at all starts erroring instead of
        degrading."""
        monkeypatch.setattr(
            "intel_platform.llm.providers._cloud_provider_from_env", lambda: None
        )
        cfg(topics_llm_provider="")
        assert _get_topics_provider() is None

    def test_an_unrecognised_provider_does_not_route_locally(self, cfg, monkeypatch):
        """Only "ollama" means local. A typo should fall through to existing
        behaviour rather than quietly picking a different model."""
        sentinel = object()
        monkeypatch.setattr(
            "intel_platform.llm.providers._cloud_provider_from_env", lambda: sentinel
        )
        cfg(topics_llm_provider="olama")
        assert _get_topics_provider() is sentinel


class TestTheClusteringPathUsesIt:
    async def test_refinement_resolves_through_the_topics_provider(self, monkeypatch):
        """Guards the wiring, not the helper: document_clustering imported
        _cloud_provider_from_env directly, which is why a local model could not
        be used no matter how it was configured."""
        from intel_platform.services import document_clustering as dc

        called = {"n": 0}

        def _fake():
            called["n"] += 1
            return None

        monkeypatch.setattr("intel_platform.llm.providers._get_topics_provider", _fake)
        tree = {"id": "t", "entity_type": "topic", "keywords": ["cable"],
                "doc_ids": ["d1"], "children": []}
        out = await dc.refine_labels_with_llm(tree, [("d1", "text")])

        assert called["n"] == 1, "refinement did not go through _get_topics_provider"
        assert out["label_source"] == "keywords"
