"""Whether topic labels came from a model or from raw keywords.

Refinement was wrapped in `except Exception: pass`, so a tree built entirely
from keyword fallbacks was indistinguishable from a fully refined one. Turning
that into a reported field immediately exposed what it had been hiding: on the
live stack every one of 31 label refinements was failing with HTTP 429 from a
Cohere trial key (20 calls/minute), and the endpoint was spending 19.3s of a
20.6s response failing. The visible symptom was topic names like
"wikipedia / wiki / org" — raw TF-IDF keywords off URL fragments.
"""
from __future__ import annotations

import asyncio

import pytest

from intel_platform.services import document_clustering as dc
from intel_platform.services.document_clustering import _is_rate_limited


class _TooManyRequestsError(Exception):
    """Shaped like cohere's, which carries a status_code attribute."""
    status_code = 429


class _RateLimitError(Exception):
    """Shaped like anthropic's / openai's, which are recognised by name."""


class TestRateLimitDetection:
    """Provider-agnostic on purpose: importing every SDK's exception class to
    catch it would couple this module to every provider."""

    def test_a_status_code_attribute_is_enough(self):
        assert _is_rate_limited(_TooManyRequestsError()) is True

    def test_the_class_name_is_enough(self):
        assert _is_rate_limited(_RateLimitError("slow down")) is True

    def test_the_message_is_enough(self):
        assert _is_rate_limited(RuntimeError("status_code: 429, body: ...")) is True

    @pytest.mark.parametrize("exc", [
        ValueError("malformed JSON in model reply"),
        RuntimeError("connection reset"),
        TimeoutError(),
    ])
    def test_ordinary_failures_are_not_rate_limits(self, exc):
        assert _is_rate_limited(exc) is False

    def test_a_404_is_not_a_rate_limit(self):
        class NotFound(Exception):
            status_code = 404
        assert _is_rate_limited(NotFound()) is False


class _Provider:
    """Counts calls and fails however the test asks."""

    def __init__(self, fail_with=None, fail_after=0):
        self.calls = 0
        self._fail_with = fail_with
        self._fail_after = fail_after

    def name(self):
        return "fake"

    async def generate(self, messages, system="", temperature=0.2, max_tokens=256):
        self.calls += 1
        # Captured before yielding. Refinement runs five at a time, so reading
        # self.calls after the await sees the count *all five* reached — which
        # made every call look like it was past the threshold and failed this
        # double's own arithmetic, not the code under test.
        nth = self.calls
        await asyncio.sleep(0)
        if self._fail_with and nth > self._fail_after:
            raise self._fail_with
        from types import SimpleNamespace
        return SimpleNamespace(content='{"topic_name": "Baltic Cable Sabotage", "summary": "s"}')


def _tree(n_children: int = 12) -> dict:
    return {
        "id": "topic-root", "entity_type": "topic", "keywords": ["cable"], "doc_ids": ["d1"],
        "children": [
            {"id": f"topic-{i}", "entity_type": "topic", "keywords": ["cable"], "doc_ids": ["d1"], "children": []}
            for i in range(n_children)
        ],
    }


@pytest.fixture
def patched(monkeypatch):
    def _install(provider):
        monkeypatch.setattr(dc, "_cloud_provider_from_env", lambda: provider, raising=False)
        monkeypatch.setattr(
            "intel_platform.llm.providers._cloud_provider_from_env", lambda: provider, raising=False
        )

        class _Loader:
            def get_system_prompt(self, *_a, **_kw):
                return "name the topic"

        monkeypatch.setattr("intel_platform.llm.skills.loader.SkillsLoader", _Loader, raising=False)
    return _install


class TestProvenanceIsReported:
    async def test_a_fully_refined_tree_says_llm(self, patched):
        patched(_Provider())
        tree = await dc.refine_labels_with_llm(_tree(4), [("d1", "text")])
        assert tree["label_source"] == "llm"
        assert tree["labels_failed"] == 0
        assert tree["labels_refined"] == 5

    async def test_no_provider_says_keywords_rather_than_looking_refined(self, patched):
        patched(None)
        tree = await dc.refine_labels_with_llm(_tree(4), [("d1", "text")])
        assert tree["label_source"] == "keywords"

    async def test_a_partly_refined_tree_is_named_as_such(self, patched):
        """The case with no other signal: some names are the model's, some are
        keywords, and the tree itself does not distinguish them."""
        patched(_Provider(fail_with=ValueError("bad reply"), fail_after=2))
        tree = await dc.refine_labels_with_llm(_tree(6), [("d1", "text")])
        assert tree["label_source"] == "partial"
        assert tree["labels_refined"] == 2
        assert tree["labels_failed"] == 5


class TestRateLimitStopsTheRun:
    async def test_refinement_is_abandoned_after_the_first_refusal(self, patched):
        """31 doomed requests cost 19.3s and produced the same keyword labels
        as stopping immediately."""
        provider = _Provider(fail_with=_TooManyRequestsError(), fail_after=0)
        patched(provider)
        tree = await dc.refine_labels_with_llm(_tree(30), [("d1", "text")])

        assert provider.calls < 31, f"kept calling a rate-limited provider ({provider.calls} times)"
        assert tree["label_source"] == "keywords"
        assert tree["labels_failed"] == 31

    async def test_an_ordinary_failure_does_not_abandon_the_rest(self, patched):
        """Only a refusal that will repeat justifies giving up on the tree; a
        malformed reply for one node says nothing about the others."""
        provider = _Provider(fail_with=ValueError("bad reply"), fail_after=0)
        patched(provider)
        await dc.refine_labels_with_llm(_tree(9), [("d1", "text")])
        assert provider.calls == 10, "every node should still have been attempted"
