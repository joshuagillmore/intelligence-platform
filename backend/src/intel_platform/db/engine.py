"""Async SQLAlchemy engine and session factory for PostgreSQL."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from intel_platform.config import get_settings

_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_settings().postgres_url,
            echo=False,
            pool_size=10,
            max_overflow=20,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_db() -> AsyncSession:
    """FastAPI dependency that yields an async session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def init_db():
    """Create all tables. Called once at startup. Also runs idempotent schema patches
    for columns the model has but the deployed table may not (since create_all never
    ALTERs existing tables and we have no Alembic migrations).
    """
    import logging
    from sqlalchemy import text
    from intel_platform.db.models import Base
    logger = logging.getLogger(__name__)
    async with get_engine().begin() as conn:
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except Exception:
            logger.warning("pgvector extension not available — vector search disabled")
        await conn.run_sync(Base.metadata.create_all)

        # Idempotent ADD COLUMN IF NOT EXISTS patches for known drift on
        # agentic collection tables (fields added after their initial create_all).
        patches = [
            "ALTER TABLE collection_sources ADD COLUMN IF NOT EXISTS collection_status VARCHAR(32) DEFAULT 'queued' NOT NULL",
            "ALTER TABLE collection_sources ADD COLUMN IF NOT EXISTS last_success_at TIMESTAMP WITH TIME ZONE",
            "ALTER TABLE collection_sources ADD COLUMN IF NOT EXISTS last_failure_at TIMESTAMP WITH TIME ZONE",
            "ALTER TABLE collection_sources ADD COLUMN IF NOT EXISTS last_error TEXT DEFAULT '' NOT NULL",
            "ALTER TABLE collection_sources ADD COLUMN IF NOT EXISTS total_records_acquired INTEGER DEFAULT 0 NOT NULL",
            "ALTER TABLE collection_sources ADD COLUMN IF NOT EXISTS acquisition_count INTEGER DEFAULT 0 NOT NULL",
            "ALTER TABLE collection_sources ADD COLUMN IF NOT EXISTS next_run_at TIMESTAMP WITH TIME ZONE",
        ]
        for sql in patches:
            try:
                await conn.execute(text(sql))
            except Exception as e:
                logger.warning("Schema patch skipped (%s): %s", sql[:70], e)
