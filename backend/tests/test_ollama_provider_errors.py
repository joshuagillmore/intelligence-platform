"""G-3 / contract 14: an Ollama failure is an exception, not an empty answer.

Ollama answers a missing model with HTTP 404 and ``{"error": "model
'qwen2.5:14b' not found"}`` — on both the streaming and non-streaming chat
endpoints. The provider never looked at the status or the ``error`` key, so
that became ``LLMResponse(content="")``: extraction dropped silently to NLP,
GraphRAG returned raw context labelled with the model's name, and every "no
LLM provider" branch downstream was unreachable. It also sent no ``num_ctx``,
so Ollama's 2048-token default truncated long prompts without a word.

All tests use a fake transport; none needs a running Ollama.
"""
from __future__ import annotations

import json

import httpx
import pytest

from intel_platform.llm.base import LLMProviderError
from intel_platform.llm.ollama import OllamaProvider

MISSING_MODEL = {"error": "model 'qwen2.5:14b' not found"}
MSGS = [{"role": "user", "content": "hi"}]


def _provider(handler) -> OllamaProvider:
    return OllamaProvider(
        base_url="http://ollama.test:11434", model="qwen2.5:14b",
        transport=httpx.MockTransport(handler),
    )


def _ndjson(*objs: dict) -> bytes:
    return b"".join(json.dumps(o).encode() + b"\n" for o in objs)


class TestTheErrorType:
    def test_it_is_a_runtime_error(self):
        """Callers already catch Exception; a RuntimeError subclass keeps them
        working while letting the ones that care catch it by name."""
        err = LLMProviderError("boom", provider="ollama:x", status_code=404)
        assert isinstance(err, RuntimeError)
        assert err.provider == "ollama:x"
        assert err.status_code == 404
        assert "boom" in str(err)


class TestGenerate:
    async def test_a_missing_model_raises_instead_of_returning_empty(self):
        p = _provider(lambda req: httpx.Response(404, json=MISSING_MODEL))
        with pytest.raises(LLMProviderError) as exc:
            await p.generate(MSGS)
        assert exc.value.status_code == 404
        assert "not found" in str(exc.value)

    async def test_an_error_key_on_a_200_raises(self):
        p = _provider(lambda req: httpx.Response(200, json={"error": "out of memory"}))
        with pytest.raises(LLMProviderError, match="out of memory"):
            await p.generate(MSGS)

    async def test_a_5xx_with_a_non_json_body_raises_the_provider_error(self):
        p = _provider(lambda req: httpx.Response(500, text="Internal Server Error"))
        with pytest.raises(LLMProviderError) as exc:
            await p.generate(MSGS)
        assert exc.value.status_code == 500

    async def test_a_rate_limit_keeps_its_status_code(self):
        """document_clustering stops refining on a 429 by reading status_code."""
        p = _provider(lambda req: httpx.Response(429, json={"error": "busy"}))
        with pytest.raises(LLMProviderError) as exc:
            await p.generate(MSGS)
        assert exc.value.status_code == 429

    async def test_an_unparseable_200_raises(self):
        p = _provider(lambda req: httpx.Response(200, text="<html>proxy login</html>"))
        with pytest.raises(LLMProviderError):
            await p.generate(MSGS)

    async def test_a_good_reply_still_returns_content(self):
        p = _provider(lambda req: httpx.Response(200, json={
            "message": {"role": "assistant", "content": "hello"},
            "prompt_eval_count": 3, "eval_count": 1,
        }))
        r = await p.generate(MSGS)
        assert r.content == "hello"
        assert r.input_tokens == 3 and r.output_tokens == 1


def _num_ctx_setting(monkeypatch, value=None):
    """Pin (or remove) ollama_num_ctx on both the proxy and the instance, so
    neither an ambient OLLAMA_NUM_CTX nor another test's residue decides it."""
    from intel_platform.config import get_settings, settings as proxy

    for d in (vars(proxy), get_settings().__dict__):
        if value is None:
            monkeypatch.delitem(d, "ollama_num_ctx", raising=False)
        else:
            monkeypatch.setitem(d, "ollama_num_ctx", value)


class TestContextWindow:
    async def test_num_ctx_defaults_to_16384(self, monkeypatch):
        _num_ctx_setting(monkeypatch, None)
        seen: dict = {}

        def handler(req: httpx.Request) -> httpx.Response:
            seen.update(json.loads(req.content))
            return httpx.Response(200, json={"message": {"content": "ok"}})

        await _provider(handler).generate(MSGS)
        assert seen["options"]["num_ctx"] == 16384

    async def test_num_ctx_follows_the_setting(self, monkeypatch):
        # Not yet a Settings field (config.py is another package's); the
        # provider reads it with getattr, so plant it directly.
        _num_ctx_setting(monkeypatch, 8192)
        seen: dict = {}

        def handler(req: httpx.Request) -> httpx.Response:
            seen.update(json.loads(req.content))
            return httpx.Response(200, json={"message": {"content": "ok"}})

        await _provider(handler).generate(MSGS)
        assert seen["options"]["num_ctx"] == 8192

    async def test_stream_sends_num_ctx_too(self, monkeypatch):
        _num_ctx_setting(monkeypatch, None)
        seen: dict = {}

        def handler(req: httpx.Request) -> httpx.Response:
            seen.update(json.loads(req.content))
            return httpx.Response(200, content=_ndjson({"message": {"content": "a"}, "done": True}))

        _ = [c async for c in _provider(handler).stream(MSGS)]
        assert seen["options"]["num_ctx"] == 16384


class TestStream:
    async def test_a_missing_model_raises(self):
        p = _provider(lambda req: httpx.Response(404, json=MISSING_MODEL))
        with pytest.raises(LLMProviderError, match="not found") as exc:
            _ = [c async for c in p.stream(MSGS)]
        assert exc.value.status_code == 404

    async def test_an_error_mid_stream_raises_after_what_arrived(self):
        body = _ndjson(
            {"message": {"content": "partial "}},
            {"error": "model runner has unexpectedly stopped"},
        )
        p = _provider(lambda req: httpx.Response(200, content=body))
        got: list[str] = []
        with pytest.raises(LLMProviderError, match="unexpectedly stopped"):
            async for chunk in p.stream(MSGS):
                got.append(chunk)
        assert got == ["partial "]

    async def test_a_good_stream_yields_its_chunks(self):
        body = _ndjson(
            {"message": {"content": "hel"}},
            {"message": {"content": "lo"}},
            {"done": True},
        )
        p = _provider(lambda req: httpx.Response(200, content=body))
        assert [c async for c in p.stream(MSGS)] == ["hel", "lo"]
