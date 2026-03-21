from __future__ import annotations
from abc import ABC, abstractmethod
from pydantic import BaseModel, computed_field


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
