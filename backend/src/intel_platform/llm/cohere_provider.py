from __future__ import annotations
from intel_platform.llm.base import LLMProvider, LLMResponse


class CohereProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "command-a-03-2025"):
        import cohere
        self._client = cohere.AsyncClientV2(api_key=api_key)
        self._model = model

    async def generate(
        self, messages: list[dict], system: str = "", temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        response = await self._client.chat(
            model=self._model, messages=msgs, temperature=temperature, max_tokens=max_tokens,
        )
        content = ""
        if response.message and response.message.content:
            content = response.message.content[0].text if response.message.content else ""
        input_tokens = response.usage.tokens.input_tokens if response.usage and response.usage.tokens else 0
        output_tokens = response.usage.tokens.output_tokens if response.usage and response.usage.tokens else 0
        return LLMResponse(
            content=content, model=self._model,
            input_tokens=input_tokens, output_tokens=output_tokens,
        )

    async def stream(
        self, messages: list[dict], system: str = "", temperature: float = 0.3,
        max_tokens: int = 4096,
    ):
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        async for event in self._client.chat_stream(
            model=self._model, messages=msgs, temperature=temperature, max_tokens=max_tokens,
        ):
            if event.type == "content-delta" and event.delta and event.delta.message:
                content = event.delta.message.content
                if content and content.text:
                    yield content.text

    def name(self) -> str:
        return f"cohere:{self._model}"
