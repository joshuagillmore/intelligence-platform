from __future__ import annotations

import json

import httpx

from intel_platform.llm.base import LLMProvider, LLMProviderError, LLMResponse

# Ollama's own default context window is 2048 tokens, and a prompt longer than
# that is truncated from the front without an error. The extraction and
# GraphRAG prompts routinely exceed it, so the window is set on every call.
_DEFAULT_NUM_CTX = 16384


def _num_ctx() -> int:
    # Read at call time, with a default: `ollama_num_ctx` is not yet a Settings
    # field on every branch, and tests adjust it per call.
    from intel_platform.config import settings

    return int(getattr(settings, "ollama_num_ctx", _DEFAULT_NUM_CTX) or _DEFAULT_NUM_CTX)


def _error_text(body: bytes) -> str:
    """The ``error`` message from a failed response, else a short raw excerpt."""
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        data = None
    if isinstance(data, dict) and data.get("error"):
        return str(data["error"])
    return body[:200].decode("utf-8", errors="replace").strip() or "empty response body"


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        # Injected only by tests, so they can answer as Ollama does without one.
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=120, transport=self._transport)

    def _payload(self, messages: list[dict], system: str, temperature: float, max_tokens: int, stream: bool) -> dict:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        return {
            "model": self._model,
            "messages": msgs,
            "stream": stream,
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": _num_ctx()},
        }

    def _failure(self, message: str, status_code: int | None = None) -> LLMProviderError:
        where = f"HTTP {status_code}: " if status_code is not None else ""
        return LLMProviderError(f"{self.name()} failed: {where}{message}", provider=self.name(), status_code=status_code)

    async def generate(self, messages: list[dict], system: str = "", temperature: float = 0.3, max_tokens: int = 4096) -> LLMResponse:
        payload = self._payload(messages, system, temperature, max_tokens, stream=False)
        async with self._client() as client:
            response = await client.post(f"{self._base_url}/api/chat", json=payload)
        # A missing model is a 404 with {"error": "model '…' not found"}; read
        # as a success it used to become an empty completion.
        if not response.is_success:
            raise self._failure(_error_text(response.content), response.status_code)
        try:
            data = response.json()
        except ValueError as exc:
            raise self._failure(f"unparseable response: {_error_text(response.content)}", response.status_code) from exc
        if not isinstance(data, dict):
            raise self._failure("response was not a JSON object", response.status_code)
        if data.get("error"):
            raise self._failure(str(data["error"]))
        return LLMResponse(
            content=(data.get("message") or {}).get("content", ""),
            model=self._model,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
        )

    async def stream(self, messages: list[dict], system: str = "", temperature: float = 0.3, max_tokens: int = 4096):
        payload = self._payload(messages, system, temperature, max_tokens, stream=True)
        async with self._client() as client:
            async with client.stream("POST", f"{self._base_url}/api/chat", json=payload) as response:
                if not response.is_success:
                    body = await response.aread()
                    raise self._failure(_error_text(body), response.status_code)
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except ValueError as exc:
                        raise self._failure(f"unparseable stream line: {line[:200]}") from exc
                    # Ollama reports a failure that happens after streaming has
                    # begun (a crashed runner, an OOM) as an `error` line.
                    if isinstance(chunk, dict) and chunk.get("error"):
                        raise self._failure(str(chunk["error"]))
                    content = (chunk.get("message") or {}).get("content", "") if isinstance(chunk, dict) else ""
                    if content:
                        yield content

    def name(self) -> str:
        return f"ollama:{self._model}"
