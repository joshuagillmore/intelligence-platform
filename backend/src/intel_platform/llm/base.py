from __future__ import annotations
from abc import ABC, abstractmethod
from pydantic import BaseModel, computed_field


class LLMProviderError(RuntimeError):
    """A provider answered with a failure instead of a completion.

    Raised rather than returning an empty ``LLMResponse``: an empty answer is
    indistinguishable from a model that had nothing to say, so every caller
    that read ``content`` quietly carried on (extraction degraded to NLP with no
    marker, GraphRAG returned raw context under the model's name). A
    ``RuntimeError`` subclass, so callers that already catch ``Exception`` keep
    working and callers that must surface the failure can catch it by name.

    ``status_code`` is the HTTP status when there was one (``None`` for an
    ``error`` key in a 200, or an error reported mid-stream); a 429 here is
    what rate-limit handling reads.
    """

    def __init__(self, message: str, *, provider: str = "", status_code: int | None = None):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


class LLMResponse(BaseModel):
    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0

    @computed_field
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, messages: list[dict], system: str = "", temperature: float = 0.3, max_tokens: int = 4096) -> LLMResponse: ...
    @abstractmethod
    async def stream(self, messages: list[dict], system: str = "", temperature: float = 0.3, max_tokens: int = 4096): ...
    @abstractmethod
    def name(self) -> str: ...
