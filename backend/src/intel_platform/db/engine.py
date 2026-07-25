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


# Additive, idempotent column migrations. `create_all` only ever creates missing
# tables — it never ALTERs one that already exists — so a column added to a model
# after its table shipped has to be backfilled here (there is no Alembic flow).
# Keep these strictly additive and `IF NOT EXISTS`; never drop or retype.
_ADDITIVE_COLUMNS = (
    # PIR spine: links a collection plan to the requirement it was raised against.
    "ALTER TABLE collection_plans ADD COLUMN IF NOT EXISTS pir_id UUID",
    "CREATE INDEX IF NOT EXISTS ix_collection_plans_pir_id ON collection_plans (pir_id)",
)


async def init_db():
    """Create all tables. Called once at startup."""
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

    # Each statement runs in its own transaction: a failure in Postgres aborts the
    # whole transaction, so one bad statement must not take the others with it.
    for statement in _ADDITIVE_COLUMNS:
        try:
            async with get_engine().begin() as conn:
                await conn.execute(text(statement))
        except Exception as exc:
            logger.warning("Additive migration skipped (%s): %s", statement, exc)
