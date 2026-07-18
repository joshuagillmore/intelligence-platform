"""Tests for per-document structured summarization (Quarry integration).

Covers ``_parse_json`` (fence stripping, brace-matching, malformed input) and
``summarize_document`` (provider contract, error isolation, output normalization).
"""
from __future__ import annotations

from types import SimpleNamespace

from intel_platform.services.summarization import _parse_json, summarize_document


# ---------------------------------------------------------------------------
# Fake LLM provider — duck-typed: async generate(...) -> object with .content
# ---------------------------------------------------------------------------

class FakeProvider:
    """Returns a fixed ``.content`` and records how generate() was called."""

    def __init__(self, content: str):
        self._content = content
        self.calls: list[dict] = []

    async def generate(self, messages, system, temperature, max_tokens):
        self.calls.append({
            "messages": messages,
            "system": system,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        return SimpleNamespace(content=self._content)


class RaisingProvider:
    async def generate(self, messages, system, temperature, max_tokens):
        raise RuntimeError("provider exploded")


# ---------------------------------------------------------------------------
# _parse_json
# ---------------------------------------------------------------------------

class TestParseJson:
    def test_plain_json(self):
        assert _parse_json('{"summary": "hi", "sentiment": "neutral"}') == {
            "summary": "hi", "sentiment": "neutral",
        }

    def test_json_fenced(self):
        text = '```json\n{"summary": "fenced"}\n```'
        assert _parse_json(text) == {"summary": "fenced"}

    def test_bare_fenced(self):
        text = '```\n{"summary": "bare fence"}\n```'
        assert _parse_json(text) == {"summary": "bare fence"}

    def test_brace_match_trailing_prose(self):
        # Direct json.loads fails on the trailing text; brace matching recovers.
        text = '{"summary": "ok", "topics": ["a", "b"]}\n\nHere is my explanation.'
        assert _parse_json(text) == {"summary": "ok", "topics": ["a", "b"]}

    def test_string_values_with_braces_and_escaped_quotes(self):
        # Braces and escaped quotes inside string values must not confuse the
        # brace matcher. Trailing prose forces the brace-matching path.
        text = '{"summary": "has {braces} and \\"quotes\\" inside"} trailing junk'
        assert _parse_json(text) == {"summary": 'has {braces} and "quotes" inside'}

    def test_malformed_returns_none(self):
        assert _parse_json('{"broken": }') is None
        assert _parse_json("not json at all {") is None

    def test_empty_returns_none(self):
        assert _parse_json("") is None
        assert _parse_json("   \n  ") is None


# ---------------------------------------------------------------------------
# summarize_document
# ---------------------------------------------------------------------------

class TestSummarizeDocument:
    async def test_none_provider_returns_none(self):
        assert await summarize_document("some content", None) is None

    async def test_empty_content_returns_none(self):
        provider = FakeProvider('{"summary": "x"}')
        assert await summarize_document("", provider) is None
        assert await summarize_document("   ", provider) is None
        # Provider must not be called when there is nothing to summarize.
        assert provider.calls == []

    async def test_happy_path(self):
        provider = FakeProvider(
            '{"summary": "A short summary.", '
            '"key_facts": ["fact one", "fact two"], '
            '"topics": ["topic a"], "sentiment": "positive"}'
        )
        result = await summarize_document("Real document content here.", provider)
        assert result == {
            "summary": "A short summary.",
            "key_facts": ["fact one", "fact two"],
            "topics": ["topic a"],
            "sentiment": "positive",
        }
        # Provider called once with the expected deterministic contract.
        assert len(provider.calls) == 1
        call = provider.calls[0]
        assert call["temperature"] == 0.0
        assert call["max_tokens"] == 1024
        assert call["system"]
        assert "Real document content here." in call["messages"][0]["content"]

    async def test_provider_raising_returns_none(self):
        assert await summarize_document("content", RaisingProvider()) is None

    async def test_unparseable_content_returns_none(self):
        assert await summarize_document("content", FakeProvider("not json")) is None

    async def test_non_dict_json_returns_none(self):
        # Valid JSON but not an object -> normalization can't apply.
        assert await summarize_document("content", FakeProvider('["a", "b"]')) is None

    async def test_normalization_caps_and_defaults(self):
        content_summary = "x" * 3000
        payload = {
            "summary": content_summary,
            # 25 truthy facts -> capped at 20
            "key_facts": [f"fact {i}" for i in range(25)],
            # mixed falsy + non-string -> falsy filtered, rest stringified
            "topics": ["t1", "", "t2", None, 0, 456],
            # sentiment omitted -> defaults to "neutral"
        }
        import json
        result = await summarize_document("content", FakeProvider(json.dumps(payload)))

        assert len(result["summary"]) == 2000
        assert len(result["key_facts"]) == 20
        assert result["topics"] == ["t1", "t2", "456"]
        assert result["sentiment"] == "neutral"
