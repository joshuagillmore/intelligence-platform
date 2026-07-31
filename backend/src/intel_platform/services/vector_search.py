"""Vector search service — embed, store, and query document chunks via pgvector."""
from __future__ import annotations

import logging

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.db.models import ChunkEmbedding
from intel_platform.llm.embeddings import EmbeddingProvider, get_embedding_provider

logger = logging.getLogger(__name__)

# Maximum texts per embedding API call (most providers cap at ~96-2048)
_EMBED_BATCH_SIZE = 96

# chunk_embeddings.embedding is Vector(1536) (db/models.ChunkEmbedding). The
# configured providers advertise 1536, 1024 and 768, so a caller supplying its
# own vector can hand pgvector a width the column cannot accept — a database
# error raised from inside a search, rather than a search that returns nothing.
_EMBEDDING_DIM = 1536


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------

async def embed_and_store_chunks(
    chunks: list[dict],
    document_id: str,
    project_id: str,
    session: AsyncSession,
    provider: EmbeddingProvider | None = None,
) -> int:
    """Embed chunks and insert into chunk_embeddings. Returns count stored.

    Each chunk dict must have 'content' and optionally 'chunk_index'.
    If embedding fails, logs a warning and returns 0 (non-fatal).
    """
    if not chunks:
        return 0

    if provider is None:
        provider = get_embedding_provider()

    texts = [c["content"] for c in chunks]
    all_vectors: list[list[float]] = []

    try:
        # Batch embedding calls
        for i in range(0, len(texts), _EMBED_BATCH_SIZE):
            batch = texts[i : i + _EMBED_BATCH_SIZE]
            result = await provider.embed(batch, input_type="search_document")
            all_vectors.extend(result.embeddings)
    except Exception:
        logger.warning("Embedding failed for document %s — chunks stored without vectors", document_id, exc_info=True)
        return 0

    if len(all_vectors) != len(chunks):
        logger.warning("Embedding count mismatch: %d vectors for %d chunks", len(all_vectors), len(chunks))
        return 0

    rows = []
    for idx, (chunk, vec) in enumerate(zip(chunks, all_vectors)):
        rows.append(ChunkEmbedding(
            document_id=document_id,
            project_id=project_id,
            chunk_index=chunk.get("chunk_index", idx),
            chunk_text=chunk["content"],
            embedding=vec,
            embedding_model=provider.name(),
            metadata_=chunk.get("metadata", {}),
        ))

    session.add_all(rows)
    await session.flush()
    return len(rows)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

async def vector_search(
    query: str,
    project_id: str,
    session: AsyncSession,
    limit: int = 20,
    similarity_threshold: float = 0.3,
    provider: EmbeddingProvider | None = None,
    query_vector: list[float] | None = None,
) -> list[dict]:
    """Embed query and search chunk_embeddings by cosine similarity.

    Returns list of {chunk_text, document_id, chunk_index, similarity, metadata}.

    Pass ``query_vector`` to reuse an embedding already computed elsewhere. A
    caller searching several related queries at once — the PIR assessor runs one
    per element of a requirement — can then embed them in a single batched call
    instead of paying one round trip per query.
    """
    if query_vector is not None:
        if len(query_vector) != _EMBEDDING_DIM:
            # A vector from a differently-sized model would otherwise reach the
            # `CAST(:query_vec AS vector)` below and fail in the database.
            logger.warning(
                "Ignoring query_vector of width %d; chunk_embeddings expects %d",
                len(query_vector), _EMBEDDING_DIM,
            )
            return []
        query_vec = query_vector
    else:
        if provider is None:
            provider = get_embedding_provider()

        try:
            result = await provider.embed([query], input_type="search_query")
            query_vec = result.embeddings[0]
        except Exception:
            logger.warning("Query embedding failed", exc_info=True)
            return []

    # pgvector cosine distance: <=> returns distance (0 = identical),
    # similarity = 1 - distance
    stmt = text("""
        SELECT id, document_id, chunk_index, chunk_text, metadata,
               1 - (embedding <=> CAST(:query_vec AS vector)) AS similarity
        FROM chunk_embeddings
        WHERE project_id = :project_id
        ORDER BY embedding <=> CAST(:query_vec AS vector)
        LIMIT :limit
    """)

    rows = await session.execute(stmt, {
        "query_vec": str(query_vec),
        "project_id": project_id,
        "limit": limit,
    })

    results = []
    for row in rows:
        sim = float(row.similarity)
        if sim < similarity_threshold:
            continue
        results.append({
            "chunk_text": row.chunk_text,
            "document_id": row.document_id,
            "chunk_index": row.chunk_index,
            "similarity": round(sim, 4),
            "metadata": row.metadata or {},
        })

    return results


# ---------------------------------------------------------------------------
# Re-indexing
# ---------------------------------------------------------------------------

async def reindex_project(
    project_id: str,
    session: AsyncSession,
    document_texts: dict[str, list[dict]],
    provider: EmbeddingProvider | None = None,
) -> int:
    """Re-embed all documents in a project.

    document_texts: {document_id: [{"content": ..., "chunk_index": ...}, ...]}
    Deletes existing embeddings for the project, then re-embeds.
    """
    # Delete existing embeddings
    await session.execute(
        delete(ChunkEmbedding).where(ChunkEmbedding.project_id == project_id)
    )
    await session.flush()

    total = 0
    for doc_id, chunks in document_texts.items():
        count = await embed_and_store_chunks(chunks, doc_id, project_id, session, provider)
        total += count

    return total


async def delete_document_embeddings(
    document_id: str,
    session: AsyncSession,
) -> int:
    """Delete all embeddings for a specific document. Returns count deleted."""
    result = await session.execute(
        delete(ChunkEmbedding).where(ChunkEmbedding.document_id == document_id)
    )
    await session.flush()
    return result.rowcount or 0
