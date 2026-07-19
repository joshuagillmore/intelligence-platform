"""Tests for vector search service — embed, store, search logic.

Since pgvector requires a real PostgreSQL instance, these tests mock the DB
layer and verify the service logic (batching, error handling, data flow).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock


from intel_platform.llm.embeddings import EmbeddingResult
from intel_platform.services.vector_search import (
    _EMBED_BATCH_SIZE,
    embed_and_store_chunks,
    delete_document_embeddings,
)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _mock_provider(dim: int = 1536, num_texts: int = 1) -> MagicMock:
    """Create a mock embedding provider."""
    provider = MagicMock()
    provider.name.return_value = "mock:test-model"
    provider.dimension.return_value = dim

    async def _embed(texts, *, input_type="search_document"):
        vecs = [[0.1] * dim for _ in texts]
        return EmbeddingResult(embeddings=vecs, model="test-model", total_tokens=len(texts) * 10)

    provider.embed = AsyncMock(side_effect=_embed)
    return provider


def _mock_session() -> MagicMock:
    """Create a mock AsyncSession."""
    session = MagicMock()
    session.add_all = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# embed_and_store_chunks
# ---------------------------------------------------------------------------

class TestEmbedAndStoreChunks:
    def test_stores_correct_number_of_chunks(self):
        chunks = [{"content": f"chunk {i}"} for i in range(5)]
        session = _mock_session()
        provider = _mock_provider()

        count = run(embed_and_store_chunks(
            chunks, "doc-1", "proj-1", session, provider=provider,
        ))

        assert count == 5
        session.add_all.assert_called_once()
        rows = session.add_all.call_args[0][0]
        assert len(rows) == 5
        assert rows[0].document_id == "doc-1"
        assert rows[0].project_id == "proj-1"
        assert rows[0].embedding_model == "mock:test-model"
        session.flush.assert_called_once()

    def test_empty_chunks_returns_zero(self):
        session = _mock_session()
        count = run(embed_and_store_chunks([], "doc-1", "proj-1", session))
        assert count == 0

    def test_chunk_index_preserved(self):
        chunks = [
            {"content": "a", "chunk_index": 10},
            {"content": "b", "chunk_index": 20},
        ]
        session = _mock_session()
        provider = _mock_provider()

        run(embed_and_store_chunks(chunks, "doc-1", "proj-1", session, provider=provider))

        rows = session.add_all.call_args[0][0]
        assert rows[0].chunk_index == 10
        assert rows[1].chunk_index == 20

    def test_chunk_index_defaults_to_sequential(self):
        chunks = [{"content": "a"}, {"content": "b"}, {"content": "c"}]
        session = _mock_session()
        provider = _mock_provider()

        run(embed_and_store_chunks(chunks, "doc-1", "proj-1", session, provider=provider))

        rows = session.add_all.call_args[0][0]
        assert [r.chunk_index for r in rows] == [0, 1, 2]

    def test_embedding_failure_returns_zero(self):
        """If embedding API fails, return 0 instead of crashing."""
        provider = MagicMock()
        provider.embed = AsyncMock(side_effect=RuntimeError("API down"))
        provider.name.return_value = "mock:test"

        session = _mock_session()
        chunks = [{"content": "text"}]

        count = run(embed_and_store_chunks(chunks, "doc-1", "proj-1", session, provider=provider))

        assert count == 0
        session.add_all.assert_not_called()

    def test_vector_count_mismatch_returns_zero(self):
        """If provider returns wrong number of vectors, return 0."""
        provider = MagicMock()
        provider.name.return_value = "mock:test"

        async def _bad_embed(texts, *, input_type="search_document"):
            return EmbeddingResult(embeddings=[[0.1]], model="test")  # only 1 vector

        provider.embed = AsyncMock(side_effect=_bad_embed)

        session = _mock_session()
        chunks = [{"content": "a"}, {"content": "b"}]  # 2 chunks

        count = run(embed_and_store_chunks(chunks, "doc-1", "proj-1", session, provider=provider))

        assert count == 0

    def test_batching_for_large_inputs(self):
        """Chunks exceeding _EMBED_BATCH_SIZE should be split into batches."""
        num_chunks = _EMBED_BATCH_SIZE + 10
        chunks = [{"content": f"chunk {i}"} for i in range(num_chunks)]
        session = _mock_session()
        provider = _mock_provider()

        count = run(embed_and_store_chunks(chunks, "doc-1", "proj-1", session, provider=provider))

        assert count == num_chunks
        # Should have been called twice (96 + 10)
        assert provider.embed.call_count == 2

    def test_metadata_passed_through(self):
        chunks = [{"content": "text", "metadata": {"source_url": "https://example.com"}}]
        session = _mock_session()
        provider = _mock_provider()

        run(embed_and_store_chunks(chunks, "doc-1", "proj-1", session, provider=provider))

        rows = session.add_all.call_args[0][0]
        assert rows[0].metadata_ == {"source_url": "https://example.com"}


# ---------------------------------------------------------------------------
# delete_document_embeddings
# ---------------------------------------------------------------------------

class TestDeleteDocumentEmbeddings:
    def test_delete_returns_count(self):
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.rowcount = 5
        session.execute = AsyncMock(return_value=mock_result)

        count = run(delete_document_embeddings("doc-1", session))

        assert count == 5
        session.flush.assert_called_once()

    def test_delete_no_rows(self):
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        session.execute = AsyncMock(return_value=mock_result)

        count = run(delete_document_embeddings("doc-1", session))
        assert count == 0
