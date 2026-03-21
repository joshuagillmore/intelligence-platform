from __future__ import annotations
import httpx
from intel_platform.llm.base import LLMProvider, LLMResponse


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def generate(self, messages: list[dict], system: str = "", temperature: float = 0.3, max_tokens: int = 4096) -> LLMResponse:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{self._base_url}/api/chat", json={"model": self._model, "messages": msgs, "stream": False, "options": {"temperature": temperature, "num_predict": max_tokens}})
            data = response.json()
            return LLMResponse(content=data.get("message", {}).get("content", ""), model=self._model, input_tokens=data.get("prompt_eval_count", 0), output_tokens=data.get("eval_count", 0))

    async def stream(self, messages: list[dict], system: str = "", temperature: float = 0.3, max_tokens: int = 4096):
        import json as json_mod
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", f"{self._base_url}/api/chat", json={"model": self._model, "messages": msgs, "stream": True, "options": {"temperature": temperature, "num_predict": max_tokens}}) as response:
                async for line in response.aiter_lines():
                    if line:
                        chunk = json_mod.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield content

    def name(self) -> str:
        return f"ollama:{self._model}"
