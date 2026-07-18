from __future__ import annotations
from intel_platform.llm.base import LLMProvider, LLMResponse


class CohereProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "command-a-plus-05-2026"):
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
        chat_kwargs = dict(
            model=self._model, messages=msgs, temperature=temperature, max_tokens=max_tokens,
        )
        # Command A+ / reasoning models "think" by default; that reasoning shares
        # the output token budget and can crowd out the visible answer (empty
        # text). Fully disabling thinking returns a Cohere 500 for this model, so
        # instead cap the thinking budget and add headroom so the answer fits.
        if "command-a-plus" in self._model or "reasoning" in self._model:
            think_budget = 1024
            chat_kwargs["thinking"] = {"type": "enabled", "token_budget": think_budget}
            chat_kwargs["max_tokens"] = max_tokens + think_budget
        response = await self._client.chat(**chat_kwargs)
        content = ""
        if response.message and response.message.content:
            # Command A+ (reasoning/MoE) returns thinking items alongside text
            # items; collect .text from every item that has it (skips the
            # ThinkingAssistantMessageResponseContentItem reasoning trace).
            content = "".join(
                (getattr(item, "text", "") or "") for item in response.message.content
            )
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
        stream_kwargs = dict(
            model=self._model, messages=msgs, temperature=temperature, max_tokens=max_tokens,
        )
        if "command-a-plus" in self._model or "reasoning" in self._model:
            think_budget = 1024
            stream_kwargs["thinking"] = {"type": "enabled", "token_budget": think_budget}
            stream_kwargs["max_tokens"] = max_tokens + think_budget
        async for event in self._client.chat_stream(**stream_kwargs):
            if event.type == "content-delta" and event.delta and event.delta.message:
                content = event.delta.message.content
                text = getattr(content, "text", None) if content else None
                if text:
                    yield text

    def name(self) -> str:
        return f"cohere:{self._model}"
