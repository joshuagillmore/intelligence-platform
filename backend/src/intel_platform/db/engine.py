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
    # Per-source status shipped after collection_sources did. NOT NULL in the
    # model, so existing rows take the model's default.
    "ALTER TABLE collection_sources ADD COLUMN IF NOT EXISTS collection_status "
    "VARCHAR(20) NOT NULL DEFAULT 'pending'",
)

# Data repairs. Same rules as above — idempotent, and safe to run on every boot.
#
# The requirement loop briefly wrote re-tasked sources with source_type="web",
# which is not in CONNECTOR_REGISTRY. Those rows are permanent members of their
# plan and fail on every subsequent run with "Unknown source type: web", so
# fixing the code does not recover them. They carry a valid single-URL config,
# which is exactly what web_scrape expects, so retyping restores them rather
# than discarding real collected leads.
_DATA_REPAIRS = (
    "UPDATE collection_sources SET source_type = 'web_scrape' WHERE source_type = 'web'",
)


# Set by init_db when the vector columns in Postgres were created at a
# different width from EMBEDDING_DIMENSIONS. Read by /health. A width mismatch
# does not stop the app (graph-only retrieval still works) but every embedding
# insert fails, so it must be visible somewhere other than a log line.
VECTOR_WIDTH_PROBLEM: str | None = None


def vector_width_problem(configured: int, actual: dict[str, int | None]) -> str | None:
    """Describe a mismatch between the configured embedding width and the
    columns that exist, or None when they agree.

    ``actual`` maps table name -> the column's declared vector width (None when
    the table or column is absent, which is not a mismatch).
    """
    wrong = {t: w for t, w in actual.items() if w is not None and w != configured}
    if not wrong:
        return None
    cols = ", ".join(f"{t}.embedding is vector({w})" for t, w in sorted(wrong.items()))
    return (
        f"EMBEDDING_DIMENSIONS={configured} but {cols}. Every embedding insert will fail "
        f"until they agree: set EMBEDDING_DIMENSIONS to the column width, or (on an empty "
        f"table) ALTER COLUMN embedding TYPE vector({configured})."
    )


async def _check_vector_width(logger) -> None:
    """Compare the live vector columns with the configured width."""
    global VECTOR_WIDTH_PROBLEM
    from sqlalchemy import text
    from intel_platform.config import get_settings
    from intel_platform.db.models import Base

    tables = [t.name for t in Base.metadata.sorted_tables if _uses_pgvector(t)]
    if not tables:
        return
    actual: dict[str, int | None] = {}
    async with get_engine().connect() as conn:
        for name in tables:
            row = (await conn.execute(text(
                "SELECT atttypmod FROM pg_attribute WHERE attrelid = to_regclass(:tbl) "
                "AND attname = 'embedding' AND NOT attisdropped"
            ), {"tbl": name})).first()
            # pgvector stores the dimension count directly in atttypmod.
            actual[name] = int(row[0]) if row and row[0] is not None and row[0] > 0 else None
    VECTOR_WIDTH_PROBLEM = vector_width_problem(get_settings().embedding_dimensions, actual)
    if VECTOR_WIDTH_PROBLEM:
        logger.error(VECTOR_WIDTH_PROBLEM)


def _uses_pgvector(table) -> bool:
    try:
        from pgvector.sqlalchemy import Vector
    except ImportError:  # models fall back to Text columns without pgvector
        return False
    return any(isinstance(column.type, Vector) for column in table.columns)


async def init_db():
    """Create all tables. Called once at startup.

    Without pgvector the app degrades to graph-only retrieval rather than
    failing to boot: the extension is tried in a transaction of its own
    (a failed statement aborts a Postgres transaction, which took create_all
    down with it), and the tables with vector columns are left out.
    """
    import logging
    from sqlalchemy import text
    from intel_platform.db.models import Base
    logger = logging.getLogger(__name__)
    vector_ok = True
    try:
        async with get_engine().begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    except Exception:
        vector_ok = False

    tables = None  # every table
    if not vector_ok:
        skipped = [t for t in Base.metadata.sorted_tables if _uses_pgvector(t)]
        tables = [t for t in Base.metadata.sorted_tables if t not in skipped]
        logger.warning(
            "pgvector extension not available — vector search disabled; not creating %s",
            ", ".join(t.name for t in skipped) or "no tables",
        )
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)

    if vector_ok:
        try:
            await _check_vector_width(logger)
        except Exception as exc:
            logger.warning("Could not verify vector column width: %s", exc)

    # Each statement runs in its own transaction: a failure in Postgres aborts the
    # whole transaction, so one bad statement must not take the others with it.
    for statement in _ADDITIVE_COLUMNS:
        try:
            async with get_engine().begin() as conn:
                await conn.execute(text(statement))
        except Exception as exc:
            logger.warning("Additive migration skipped (%s): %s", statement, exc)

    for statement in _DATA_REPAIRS:
        try:
            async with get_engine().begin() as conn:
                result = await conn.execute(text(statement))
                if result.rowcount:
                    # Worth a line: a silent repair leaves no way to tell whether
                    # the damage was ever there.
                    logger.info("Data repair applied to %d row(s): %s", result.rowcount, statement)
        except Exception as exc:
            logger.warning("Data repair skipped (%s): %s", statement, exc)
