"""Embed the global MITRE ATT&CK® technique catalog into pgvector.

Phase 2 maps prose TTPs to techniques via RAG: to retrieve candidate techniques
by semantic similarity we first index every ``AttackTechnique`` node's
``"<name>. <description>"`` text into the ``attack_technique_embeddings`` table
(one row per canonical technique id). This is an explicit, idempotent admin step
(``POST /attack/embed``) — embedding ~700 techniques costs provider calls, so it
is opt-in rather than folded into ingest. Re-running upserts in place.

Mirrors the ``services/vector_search`` embedding pattern (batched calls via the
:class:`EmbeddingProvider` orchestrator) and ``ChunkEmbedding``'s Vector(1536)
dimension handling.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from neo4j import Driver
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.db.models import AttackTechniqueEmbedding
from intel_platform.llm.embeddings import EmbeddingProvider, get_embedding_provider

logger = logging.getLogger(__name__)

# Texts per embedding API call (mirrors vector_search; providers cap ~96-2048).
_EMBED_BATCH_SIZE = 96


def _fetch_techniques(driver: Driver) -> list[dict]:
    """Read every global technique (id/name/description) from Neo4j (blocking)."""
    with driver.session() as session:
        return session.run(
            """
            MATCH (t:AttackTechnique)
            RETURN t.attack_id AS attack_id, coalesce(t.name, '') AS name,
                   coalesce(t.description, '') AS description
            ORDER BY t.attack_id
            """
        ).data()


def _technique_text(t: dict) -> str:
    name = (t.get("name") or "").strip()
    desc = (t.get("description") or "").strip()
    return f"{name}. {desc}".strip() if desc else name


async def embed_techniques(
    session: AsyncSession,
    driver: Driver,
    *,
    provider: EmbeddingProvider | None = None,
) -> int:
    """Embed every ATT&CK technique and UPSERT into ``attack_technique_embeddings``.

    Idempotent (upsert on ``technique_id``). Offloads the sync Neo4j read via
    ``asyncio.to_thread``. Degrades to ``0`` (never raises) when embedding fails,
    so a missing/unreachable embedding provider doesn't 500 the admin endpoint.
    Returns the number of techniques embedded. The caller commits the session.
    """
    techniques = await asyncio.to_thread(_fetch_techniques, driver)
    if not techniques:
        return 0

    if provider is None:
        try:
            provider = get_embedding_provider()
        except Exception:
            logger.warning("No embedding provider available for ATT&CK embed", exc_info=True)
            return 0

    texts = [_technique_text(t) for t in techniques]
    vectors: list[list[float]] = []
    try:
        for i in range(0, len(texts), _EMBED_BATCH_SIZE):
            result = await provider.embed(texts[i : i + _EMBED_BATCH_SIZE], input_type="search_document")
            vectors.extend(result.embeddings)
    except Exception:
        logger.warning("ATT&CK technique embedding failed — skipped", exc_info=True)
        return 0

    if len(vectors) != len(techniques):
        logger.warning("Embedding count mismatch: %d vectors for %d techniques", len(vectors), len(techniques))
        return 0

    now = datetime.now(timezone.utc)
    rows = [
        {"technique_id": t["attack_id"], "text": txt, "embedding": vec, "updated_at": now}
        for t, txt, vec in zip(techniques, texts, vectors)
    ]

    stmt = pg_insert(AttackTechniqueEmbedding).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["technique_id"],
        set_={
            "text": stmt.excluded.text,
            "embedding": stmt.excluded.embedding,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    await session.execute(stmt)
    await session.flush()
    return len(rows)
