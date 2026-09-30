"""Embedding providers for vector search.

Follows the same pattern as LLMProvider — abstract base with concrete
implementations for OpenAI, Cohere, and Ollama.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class EmbeddingConfigError(RuntimeError):
    """The configured embedding provider cannot produce vectors the store accepts.

    Raised by :func:`get_embedding_provider` instead of substituting a
    different provider: vectors of another width fail in the database, on
    the caller's session, long after the substitution was made.
    """


# Output widths of models these providers are commonly pointed at.
# ``dimension()`` is what the factory checks against the column, so a
# non-default model must not report the default model's width (mxbai-embed-large
# is 1024, not nomic's 768). An unlisted model keeps its provider's default,
# and the insert-time width check in vector_search is the backstop.
_KNOWN_DIMENSIONS = {
    "text-embedding-3-small": 1536, "text-embedding-3-large": 3072, "text-embedding-ada-002": 1536,
    "embed-english-v3.0": 1024, "embed-multilingual-v3.0": 1024,
    "embed-english-light-v3.0": 384, "embed-multilingual-light-v3.0": 384,
    "nomic-embed-text": 768, "mxbai-embed-large": 1024, "all-minilm": 384,
    "snowflake-arctic-embed": 1024, "bge-m3": 1024,
}


def _width(model: str, default: int) -> int:
    # Ollama tags ("nomic-embed-text:latest") do not change the width.
    return _KNOWN_DIMENSIONS.get(model.split(":", 1)[0], default)


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
        self._dim = _width(model, 1536)

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
        self._dim = _width(model, 1024)

    async def embed(self, texts: list[str], *, input_type: str = "search_document") -> EmbeddingResult:
        kwargs: dict = {}
        # embed-v4 returns 1536 dimensions unless told otherwise, while this
        # provider declares 1024 — so every vector was wider than the column
        # sized from that declaration. Ask for the declared width. v3 models are
        # natively 1024 and reject the parameter.
        if self._model.startswith("embed-v4"):
            kwargs["output_dimension"] = self._dim
        response = await self._client.embed(
            texts=texts, model=self._model, input_type=input_type,
            embedding_types=["float"], **kwargs,
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
        self._dim = _width(model, 768)

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
    """Instantiate the configured embedding provider, or refuse.

    Exactly the provider ``EMBEDDING_PROVIDER`` names, and only if its width is
    ``EMBEDDING_DIMENSIONS`` — the width the pgvector columns were created
    with. There is deliberately no fallback to another provider: the three
    produce 1536, 1024 and 768 dimensions, so a substitute's vectors fail in the
    database instead of here, where the error can say what to change.

    Raises :class:`EmbeddingConfigError`.
    """
    from intel_platform.config import get_settings
    s = get_settings()

    name = (s.embedding_provider or "").strip().lower()
    model = s.embedding_model or None
    model_kw = {"model": model} if model else {}

    if name == "openai":
        if not s.openai_api_key:
            raise EmbeddingConfigError("EMBEDDING_PROVIDER=openai but OPENAI_API_KEY is not set")
        provider: EmbeddingProvider = OpenAIEmbeddingProvider(api_key=s.openai_api_key, **model_kw)
    elif name == "cohere":
        if not s.cohere_api_key:
            raise EmbeddingConfigError("EMBEDDING_PROVIDER=cohere but COHERE_API_KEY is not set")
        provider = CohereEmbeddingProvider(api_key=s.cohere_api_key, **model_kw)
    elif name == "ollama":
        provider = OllamaEmbeddingProvider(base_url=s.ollama_base_url, **model_kw)
    else:
        raise EmbeddingConfigError(
            f"EMBEDDING_PROVIDER={s.embedding_provider!r} is not one of openai, cohere, ollama"
        )

    expected = int(s.embedding_dimensions)
    if provider.dimension() != expected:
        raise EmbeddingConfigError(
            f"{provider.name()} produces {provider.dimension()}-dimensional vectors but "
            f"EMBEDDING_DIMENSIONS={expected}. Set EMBEDDING_DIMENSIONS={provider.dimension()} "
            "(and recreate the embedding tables) or choose a provider of that width."
        )
    return provider
