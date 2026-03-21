from __future__ import annotations
from intel_platform.llm.base import LLMProvider, LLMResponse


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def generate(self, messages: list[dict], system: str = "", temperature: float = 0.3, max_tokens: int = 4096) -> LLMResponse:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        response = await self._client.chat.completions.create(model=self._model, messages=msgs, max_tokens=max_tokens, temperature=temperature)
        return LLMResponse(content=response.choices[0].message.content or "", model=self._model, input_tokens=response.usage.prompt_tokens if response.usage else 0, output_tokens=response.usage.completion_tokens if response.usage else 0)

    async def stream(self, messages: list[dict], system: str = "", temperature: float = 0.3, max_tokens: int = 4096):
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        response = await self._client.chat.completions.create(model=self._model, messages=msgs, max_tokens=max_tokens, temperature=temperature, stream=True)
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def name(self) -> str:
        return f"openai:{self._model}"
