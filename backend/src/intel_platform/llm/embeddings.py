"""Embedding providers for vector search.

Follows the same pattern as LLMProvider — abstract base with concrete
implementations for OpenAI, Cohere, and Ollama.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class EmbeddingResult(BaseModel):
    embeddings: list[list[float]]
    model: str
    total_tokens: int = 0


class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed(self, texts: list[str], *, input_type: str = "search_document") -> EmbeddingResult:
        """Embed a batch of texts. input_type is 'search_document' for indexing,
        'search_query' for query-time embedding (matters for Cohere)."""
        ...

    @abstractmethod
    def dimension(self) -> int: ...

    @abstractmethod
    def name(self) -> str: ...


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._dim = 1536

    async def embed(self, texts: list[str], *, input_type: str = "search_document") -> EmbeddingResult:
        response = await self._client.embeddings.create(model=self._model, input=texts)
        vectors = [item.embedding for item in response.data]
        tokens = response.usage.total_tokens if response.usage else 0
        return EmbeddingResult(embeddings=vectors, model=self._model, total_tokens=tokens)

    def dimension(self) -> int:
        return self._dim

    def name(self) -> str:
        return f"openai:{self._model}"


# ---------------------------------------------------------------------------
# Cohere
# ---------------------------------------------------------------------------

class CohereEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str, model: str = "embed-v4.0"):
        import cohere
        self._client = cohere.AsyncClientV2(api_key=api_key)
        self._model = model
        self._dim = 1024

    async def embed(self, texts: list[str], *, input_type: str = "search_document") -> EmbeddingResult:
        response = await self._client.embed(
            texts=texts, model=self._model, input_type=input_type,
            embedding_types=["float"],
        )
        vectors = response.embeddings.float_ or []
        tokens = 0
        if hasattr(response, "meta") and response.meta:
            billed = getattr(response.meta, "billed_units", None)
            if billed:
                tokens = getattr(billed, "input_tokens", 0) or 0
        return EmbeddingResult(embeddings=vectors, model=self._model, total_tokens=tokens)

    def dimension(self) -> int:
        return self._dim

    def name(self) -> str:
        return f"cohere:{self._model}"


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

class OllamaEmbeddingProvider(EmbeddingProvider):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "nomic-embed-text"):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dim = 768

    async def embed(self, texts: list[str], *, input_type: str = "search_document") -> EmbeddingResult:
        import httpx
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._base_url}/api/embed",
                json={"model": self._model, "input": texts},
            )
            response.raise_for_status()
            data = response.json()
        vectors = data.get("embeddings", [])
        return EmbeddingResult(embeddings=vectors, model=self._model)

    def dimension(self) -> int:
        return self._dim

    def name(self) -> str:
        return f"ollama:{self._model}"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_embedding_provider() -> EmbeddingProvider:
    """Instantiate the configured embedding provider."""
    from intel_platform.config import get_settings
    s = get_settings()

    provider = s.embedding_provider.lower()
    model = s.embedding_model or None

    if provider == "cohere" and s.cohere_api_key:
        return CohereEmbeddingProvider(api_key=s.cohere_api_key, **({"model": model} if model else {}))
    if provider == "openai" and s.openai_api_key:
        return OpenAIEmbeddingProvider(api_key=s.openai_api_key, **({"model": model} if model else {}))
    if provider == "ollama":
        return OllamaEmbeddingProvider(base_url=s.ollama_base_url, **({"model": model} if model else {}))

    # Fallback chain: try any available provider
    if s.openai_api_key:
        return OpenAIEmbeddingProvider(api_key=s.openai_api_key)
    if s.cohere_api_key:
        return CohereEmbeddingProvider(api_key=s.cohere_api_key)
    return OllamaEmbeddingProvider(base_url=s.ollama_base_url)
