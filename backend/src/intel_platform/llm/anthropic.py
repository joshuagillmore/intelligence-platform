from __future__ import annotations
from intel_platform.llm.base import LLMProvider, LLMResponse


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        import anthropic
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def generate(self, messages: list[dict], system: str = "", temperature: float = 0.3, max_tokens: int = 4096) -> LLMResponse:
        kwargs = {"model": self._model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        if system:
            kwargs["system"] = system
        response = await self._client.messages.create(**kwargs)
        return LLMResponse(content=response.content[0].text, model=self._model, input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens)

    async def stream(self, messages: list[dict], system: str = "", temperature: float = 0.3, max_tokens: int = 4096):
        kwargs = {"model": self._model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        if system:
            kwargs["system"] = system
        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    def name(self) -> str:
        return f"anthropic:{self._model}"
