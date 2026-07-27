"""Tests for embedding providers and the factory function."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


from intel_platform.llm.embeddings import (
    CohereEmbeddingProvider,
    EmbeddingResult,
    OllamaEmbeddingProvider,
    OpenAIEmbeddingProvider,
    get_embedding_provider,
)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# OpenAI Embedding Provider
# ---------------------------------------------------------------------------

class TestOpenAIEmbeddingProvider:
    def test_name(self):
        with patch("openai.AsyncOpenAI"):
            provider = OpenAIEmbeddingProvider(api_key="k")
            assert provider.name() == "openai:text-embedding-3-small"

    def test_dimension(self):
        with patch("openai.AsyncOpenAI"):
            provider = OpenAIEmbeddingProvider(api_key="k")
            assert provider.dimension() == 1536

    def test_custom_model(self):
        with patch("openai.AsyncOpenAI"):
            provider = OpenAIEmbeddingProvider(api_key="k", model="text-embedding-3-large")
            assert provider.name() == "openai:text-embedding-3-large"

    def test_embed_calls_api(self):
        mock_client = MagicMock()
        mock_item = MagicMock()
        mock_item.embedding = [0.1] * 1536
        mock_response = MagicMock()
        mock_response.data = [mock_item]
        mock_response.usage.total_tokens = 42
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            provider = OpenAIEmbeddingProvider(api_key="k")
            result = run(provider.embed(["hello world"]))

        assert len(result.embeddings) == 1
        assert len(result.embeddings[0]) == 1536
        assert result.total_tokens == 42
        assert result.model == "text-embedding-3-small"
        mock_client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-small", input=["hello world"],
        )

    def test_embed_batch(self):
        mock_client = MagicMock()
        items = [MagicMock(embedding=[0.1] * 1536) for _ in range(3)]
        mock_response = MagicMock()
        mock_response.data = items
        mock_response.usage.total_tokens = 100
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            provider = OpenAIEmbeddingProvider(api_key="k")
            result = run(provider.embed(["a", "b", "c"]))

        assert len(result.embeddings) == 3


# ---------------------------------------------------------------------------
# Cohere Embedding Provider
# ---------------------------------------------------------------------------

class TestCohereEmbeddingProvider:
    def test_name(self):
        with patch("cohere.AsyncClientV2"):
            provider = CohereEmbeddingProvider(api_key="k")
            assert provider.name() == "cohere:embed-v4.0"

    def test_dimension(self):
        with patch("cohere.AsyncClientV2"):
            provider = CohereEmbeddingProvider(api_key="k")
            assert provider.dimension() == 1024

    def test_embed_passes_input_type(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.embeddings.float_ = [[0.2] * 1024]
        mock_response.meta.billed_units.input_tokens = 10
        mock_client.embed = AsyncMock(return_value=mock_response)

        with patch("cohere.AsyncClientV2", return_value=mock_client):
            provider = CohereEmbeddingProvider(api_key="k")

            # Index-time call
            run(provider.embed(["text"], input_type="search_document"))
            call_kwargs = mock_client.embed.call_args.kwargs
            assert call_kwargs["input_type"] == "search_document"

            # Query-time call
            run(provider.embed(["query"], input_type="search_query"))
            call_kwargs = mock_client.embed.call_args.kwargs
            assert call_kwargs["input_type"] == "search_query"


# ---------------------------------------------------------------------------
# Ollama Embedding Provider
# ---------------------------------------------------------------------------

class TestOllamaEmbeddingProvider:
    def test_name(self):
        provider = OllamaEmbeddingProvider()
        assert provider.name() == "ollama:nomic-embed-text"

    def test_dimension(self):
        provider = OllamaEmbeddingProvider()
        assert provider.dimension() == 768

    def test_embed_calls_api(self):

        mock_response = MagicMock()
        mock_response.json.return_value = {"embeddings": [[0.3] * 768]}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            provider = OllamaEmbeddingProvider(base_url="http://test:11434")
            result = run(provider.embed(["text"]))

        assert len(result.embeddings) == 1
        assert len(result.embeddings[0]) == 768


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestGetEmbeddingProvider:
    def test_returns_openai_by_default(self):
        mock_settings = MagicMock()
        mock_settings.embedding_provider = "openai"
        mock_settings.embedding_model = ""
        mock_settings.openai_api_key = "test-key"
        mock_settings.cohere_api_key = ""
        mock_settings.ollama_base_url = "http://localhost:11434"

        with patch("intel_platform.config.get_settings", return_value=mock_settings), \
             patch("openai.AsyncOpenAI"):
            provider = get_embedding_provider()
            assert "openai" in provider.name()

    def test_returns_cohere_when_configured(self):
        mock_settings = MagicMock()
        mock_settings.embedding_provider = "cohere"
        mock_settings.embedding_model = ""
        mock_settings.cohere_api_key = "test-key"
        mock_settings.openai_api_key = ""
        mock_settings.ollama_base_url = "http://localhost:11434"

        with patch("intel_platform.config.get_settings", return_value=mock_settings), \
             patch("cohere.AsyncClientV2"):
            provider = get_embedding_provider()
            assert "cohere" in provider.name()

    def test_returns_ollama_when_configured(self):
        mock_settings = MagicMock()
        mock_settings.embedding_provider = "ollama"
        mock_settings.embedding_model = "mxbai-embed-large"
        mock_settings.cohere_api_key = ""
        mock_settings.openai_api_key = ""
        mock_settings.ollama_base_url = "http://localhost:11434"

        with patch("intel_platform.config.get_settings", return_value=mock_settings):
            provider = get_embedding_provider()
            assert provider.name() == "ollama:mxbai-embed-large"

    def test_fallback_chain(self):
        mock_settings = MagicMock()
        mock_settings.embedding_provider = "openai"
        mock_settings.embedding_model = ""
        mock_settings.openai_api_key = ""  # not configured
        mock_settings.cohere_api_key = "fallback-key"
        mock_settings.ollama_base_url = "http://localhost:11434"

        with patch("intel_platform.config.get_settings", return_value=mock_settings), \
             patch("cohere.AsyncClientV2"):
            provider = get_embedding_provider()
            assert "cohere" in provider.name()


# ---------------------------------------------------------------------------
# pgvector column width (EMBEDDING_DIMENSIONS)
# ---------------------------------------------------------------------------

class TestEmbeddingColumnDimension:
    """The vector columns must be sized from settings, not a hardcoded 1536 —
    otherwise the 1024-d Cohere and 768-d Ollama providers can't store vectors."""

    def _dims(self, models):
        return [
            models.ChunkEmbedding.__table__.c.embedding.type,
            models.AttackTechniqueEmbedding.__table__.c.embedding.type,
        ]

    def test_matches_configured_dimensions(self):
        from intel_platform.config import get_settings
        from intel_platform.db import models

        expected = get_settings().embedding_dimensions
        for column_type in self._dims(models):
            assert getattr(column_type, "dim", expected) == expected

    def test_follows_a_changed_setting(self, monkeypatch):
        """Re-importing under EMBEDDING_DIMENSIONS=768 (Ollama) must give 768-d
        columns. Reloaded twice so the rest of the suite sees the original."""
        import importlib

        from intel_platform.config import get_settings
        from intel_platform.db import models

        if not hasattr(models.ChunkEmbedding.__table__.c.embedding.type, "dim"):
            return  # pgvector not installed — Text fallback has no dimension

        monkeypatch.setenv("EMBEDDING_DIMENSIONS", "768")
        get_settings.cache_clear()
        try:
            reloaded = importlib.reload(models)
            assert [t.dim for t in self._dims(reloaded)] == [768, 768]
        finally:
            monkeypatch.undo()
            get_settings.cache_clear()
            importlib.reload(models)


# ---------------------------------------------------------------------------
# EmbeddingResult model
# ---------------------------------------------------------------------------

class TestEmbeddingResult:
    def test_basic(self):
        r = EmbeddingResult(embeddings=[[0.1, 0.2]], model="test", total_tokens=5)
        assert len(r.embeddings) == 1
        assert r.model == "test"
        assert r.total_tokens == 5

    def test_defaults(self):
        r = EmbeddingResult(embeddings=[], model="m")
        assert r.total_tokens == 0


class TestTheGuardFollowsTheColumn:
    """A width guard with its own copy of the number is worse than none.

    The column is sized from EMBEDDING_DIMENSIONS. A guard hardcoded to 1536
    would reject every query on a deployment that set it to 768 — the column
    would accept the vector and the guard would not, so semantic search would
    fail on exactly the local-only setup the setting exists to enable.
    """

    def test_the_search_guard_and_the_column_are_the_same_number(self):
        from intel_platform.db import models
        from intel_platform.services import vector_search

        assert vector_search._EMBEDDING_DIM == models._EMBEDDING_DIM

    def test_both_follow_the_configured_dimension(self):
        from intel_platform.config import get_settings
        from intel_platform.services import vector_search

        assert vector_search._EMBEDDING_DIM == get_settings().embedding_dimensions
