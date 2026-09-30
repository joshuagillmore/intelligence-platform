"""Topic summary SSE framing (contract 7).

R-1: the summary was streamed as raw 80-character slices, `data: {chunk}\n\n`,
with the model's newlines inside the payload. A client splitting on lines kept
only the lines starting `data: ` and never re-added the newlines, so a six-line
summary arrived as `## Key Findingsps`; a cache hit arrived as one line. The
error path streamed `str(e)` to the analyst.

Every `data:` payload is now a JSON string, the stream ends `data: [DONE]`, and
an error is `data: {"error": "Summary generation failed"}` with no exception
text. Cache hits are framed identically. The cache key includes `level` and the
conversation history, which it ignored.
"""
from __future__ import annotations

import json

import pytest

from intel_platform.llm.base import LLMProvider, LLMResponse
from intel_platform.services import topics as topics_svc
from intel_platform.services.topics import TopicTreeService

SUMMARY = (
    "## Key Findings\n"
    "- APT29 used spear-phishing against three ministries in March 2025.\n"
    "- A second wave reused the same loader.\n\n"
    "## Gaps\n"
    "No attribution statement from the targeted governments; \"quoted\" text and a \\ backslash."
)


class _Provider(LLMProvider):
    def __init__(self, text=SUMMARY, fail=False):
        self.text = text
        self.fail = fail
        self.calls = 0

    async def generate(self, messages, system="", temperature=0.3, max_tokens=4096):
        self.calls += 1
        if self.fail:
            raise RuntimeError("upstream said: bolt://10.0.0.7:7687 auth failed")
        return LLMResponse(content=self.text, model="fake", input_tokens=1, output_tokens=1)

    async def stream(self, *a, **k):
        yield self.text

    def name(self):
        return "fake"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    topics_svc._summary_cache.clear()
    monkeypatch.setattr(
        TopicTreeService, "get_topic_context",
        lambda self, entity_id, project_id: {
            "entity": {"name": "APT29"},
            "document_excerpts": [{"name": "doc-a", "content": "APT29 phishing"}],
            "keywords": ["apt29"],
        },
    )
    yield
    topics_svc._summary_cache.clear()


def _use(monkeypatch, provider):
    from intel_platform.llm import providers

    async def _get():
        return provider

    monkeypatch.setattr(providers, "_get_provider", _get)


async def _frames(**kwargs) -> list[str]:
    svc = TopicTreeService(store=None)
    args = {"entity_id": "topic-1", "project_id": "p1", **kwargs}
    return [frame async for frame in svc.stream_summary(**args)]


def _decode(frames: list[str]) -> tuple[str, list]:
    """What a client that follows the contract reconstructs."""
    raw = "".join(frames)
    assert raw.endswith("data: [DONE]\n\n")
    events = [e for e in raw.split("\n\n") if e]
    assert all(e.startswith("data: ") and "\n" not in e for e in events), events
    payloads = [e[len("data: "):] for e in events[:-1]]
    decoded = [json.loads(p) for p in payloads]
    text = "".join(d for d in decoded if isinstance(d, str))
    return text, [d for d in decoded if not isinstance(d, str)]


class TestFraming:
    async def test_every_payload_is_a_json_string_and_newlines_survive(self, monkeypatch):
        _use(monkeypatch, _Provider())
        frames = await _frames()
        text, others = _decode(frames)
        assert text == SUMMARY
        assert others == []
        assert len(frames) > 2, "long summaries still arrive in pieces"

    async def test_a_cache_hit_is_framed_the_same_way(self, monkeypatch):
        provider = _Provider()
        _use(monkeypatch, provider)
        await _frames()
        again = await _frames()
        assert provider.calls == 1
        assert _decode(again) == (SUMMARY, [])


class TestErrors:
    async def test_a_failure_is_one_error_event_without_detail(self, monkeypatch):
        _use(monkeypatch, _Provider(fail=True))
        frames = await _frames()
        text, others = _decode(frames)
        assert text == ""
        assert others == [{"error": "Summary generation failed"}]
        assert "10.0.0.7" not in "".join(frames)

    async def test_a_failure_is_not_cached(self, monkeypatch):
        _use(monkeypatch, _Provider(fail=True))
        await _frames()
        good = _Provider()
        _use(monkeypatch, good)
        assert _decode(await _frames())[0] == SUMMARY
        assert good.calls == 1

    async def test_an_empty_reply_is_an_error_not_an_empty_summary(self, monkeypatch):
        _use(monkeypatch, _Provider(text="   "))
        assert _decode(await _frames())[1] == [{"error": "Summary generation failed"}]

    async def test_no_provider_is_an_error_event(self, monkeypatch):
        _use(monkeypatch, None)
        assert _decode(await _frames())[1] == [{"error": "Summary generation failed"}]


class TestCacheKey:
    async def test_level_is_part_of_the_key(self, monkeypatch):
        provider = _Provider()
        _use(monkeypatch, provider)
        await _frames(level="topic")
        await _frames(level="corpus")
        assert provider.calls == 2

    async def test_conversation_history_is_part_of_the_key(self, monkeypatch):
        provider = _Provider()
        _use(monkeypatch, provider)
        await _frames(conversation_history=[{"role": "user", "content": "focus on Europe"}])
        await _frames(conversation_history=[{"role": "user", "content": "focus on Asia"}])
        await _frames(conversation_history=[{"role": "user", "content": "focus on Asia"}])
        assert provider.calls == 2


def test_the_route_streams_the_same_framing(monkeypatch):
    from fastapi.testclient import TestClient

    from intel_platform.api.app import app
    from intel_platform.api.deps import get_graph_store
    from intel_platform.config import settings

    _use(monkeypatch, _Provider())
    app.dependency_overrides[get_graph_store] = lambda: None
    try:
        resp = TestClient(app).post(
            "/api/topics/topic-1/summarize", json={"project_id": "p1"},
            headers={"Authorization": f"Bearer {settings.api_key}"},
        )
    finally:
        app.dependency_overrides.pop(get_graph_store, None)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert _decode([resp.text]) == (SUMMARY, [])
