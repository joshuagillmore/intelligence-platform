"""Async SQLAlchemy engine and session factory for PostgreSQL, and the schema
bootstrap (`init_db`), which runs the Alembic migrations at startup."""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import SetColumnComment

from intel_platform.config import get_settings

logger = logging.getLogger(__name__)

_engine = None
_session_factory = None

# pg_advisory_xact_lock key serialising schema migrations: the API and the
# collection worker may both boot against one database. Arbitrary but fixed
# (the bytes of "intelmig").
MIGRATION_LOCK_KEY = 0x696E74656C6D6967


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


# ---------------------------------------------------------------------------
# Migrations
#
# The schema is owned by Alembic (backend/alembic). init_db runs `upgrade head`
# on every boot; a schema change is a new revision (`uv run alembic revision
# --autogenerate`), never an edit here. See "Postgres schema migrations" in
# backend/CLAUDE.md.
# ---------------------------------------------------------------------------

# backend/src/intel_platform/db/engine.py -> backend/. The images keep the same
# layout (/app/src/intel_platform/... -> /app), so alembic/ ships next to src/.
_BACKEND_DIR = Path(__file__).resolve().parents[3]
ALEMBIC_DIR = _BACKEND_DIR / "alembic"

# The revision whose schema is what `create_all` built before Alembic existed.
# A database with these tables and no alembic_version is adopted at it.
BASELINE_REVISION = "0001"
BASELINE_TABLES = (
    "acquisition_log",
    "api_keys",
    "app_settings",
    "attack_d3fend_cache",
    "attack_technique_embeddings",
    "chunk_embeddings",
    "collection_activity",
    "collection_plans",
    "collection_sources",
    "data_catalog",
    "enrichment_records",
    "pir_requirements",
    "pirs",
    "topic_edits",
)

# The pre-Alembic bootstrap's additive columns, frozen. They run only while
# adopting a legacy database, so one last booted before a column existed reaches
# the baseline before it is stamped. Never add to this: new columns are revisions.
_LEGACY_ADDITIVE_COLUMNS = (
    # PIR spine: links a collection plan to the requirement it was raised against.
    "ALTER TABLE collection_plans ADD COLUMN IF NOT EXISTS pir_id UUID",
    "CREATE INDEX IF NOT EXISTS ix_collection_plans_pir_id ON collection_plans (pir_id)",
    # Per-source status shipped after collection_sources did. NOT NULL in the
    # model, so existing rows take the model's default.
    "ALTER TABLE collection_sources ADD COLUMN IF NOT EXISTS collection_status "
    "VARCHAR(20) NOT NULL DEFAULT 'pending'",
)
# Columns the statements above add without the comment the baseline gives them;
# set from the model so an adopted database compares clean under `alembic check`.
_LEGACY_COMMENTED_COLUMNS = (("collection_plans", "pir_id"), ("collection_sources", "collection_status"))

# Data repairs. Idempotent, and safe to run on every boot.
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


def alembic_config(connection=None):
    """Alembic Config for the migrations, optionally bound to a sync connection.

    Built without alembic.ini: the CLI's logging section must not replace the
    app's logging when this runs inside it. With ``connection``, env.py runs the
    migrations on it, inside whatever transaction it is already in.
    """
    from alembic.config import Config

    if not (ALEMBIC_DIR / "env.py").is_file():
        raise RuntimeError(
            f"Alembic migrations not found at {ALEMBIC_DIR}. backend/alembic/ (and alembic.ini) "
            "must be shipped next to src/ in every image that runs the API or the worker."
        )
    cfg = Config()
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    if connection is not None:
        cfg.attributes["connection"] = connection
    return cfg


def ensure_vector_extension(connection) -> bool:
    """Install pgvector if it can be; True when it is installed.

    The attempt runs in a SAVEPOINT: a failed statement aborts a Postgres
    transaction, and the migration it runs inside must survive it.
    """
    try:
        with connection.begin_nested():
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    except Exception as exc:
        logger.debug("CREATE EXTENSION vector failed: %s", exc)
    return connection.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).first() is not None


def _uses_pgvector(table) -> bool:
    try:
        from pgvector.sqlalchemy import Vector
    except ImportError:  # models fall back to Text columns without pgvector
        return False
    return any(isinstance(column.type, Vector) for column in table.columns)


def _adopt_legacy_schema(connection, cfg, existing: set[str]) -> None:
    """Stamp a database `create_all` built (every pre-Alembic deployment).

    Replays what the old bootstrap's next boot would have done — create any
    baseline table still missing, add the additive columns — so the database
    is at the baseline, then stamps it there. `upgrade head` afterwards runs
    only the revisions that came later; for a database from the last
    pre-Alembic build it does nothing at all.
    """
    from alembic import command

    from intel_platform.db.models import Base

    vector_ok = ensure_vector_extension(connection)
    missing = [
        Base.metadata.tables[name] for name in BASELINE_TABLES
        if name not in existing and name in Base.metadata.tables
        and (vector_ok or not _uses_pgvector(Base.metadata.tables[name]))
    ]
    if missing:
        Base.metadata.create_all(connection, tables=missing)
    for statement in _LEGACY_ADDITIVE_COLUMNS:
        connection.execute(text(statement))
    for table, column in _LEGACY_COMMENTED_COLUMNS:
        connection.execute(SetColumnComment(Base.metadata.tables[table].c[column]))
    command.stamp(cfg, BASELINE_REVISION)
    logger.info(
        "Adopted a database created before migrations: stamped at baseline %s%s",
        BASELINE_REVISION, f" after creating {', '.join(t.name for t in missing)}" if missing else "",
    )


def _create_missing_vector_tables(connection) -> None:
    """Create the baseline's vector tables when pgvector arrived after it ran.

    The baseline leaves them out on a database without the extension; this is
    what `create_all` used to do on the next boot once it was installed.
    """
    from intel_platform.db.models import Base

    existing = set(inspect(connection).get_table_names())
    missing = [
        t for t in Base.metadata.sorted_tables
        if t.name in BASELINE_TABLES and t.name not in existing and _uses_pgvector(t)
    ]
    if missing:
        Base.metadata.create_all(connection, tables=missing)
        logger.info("pgvector is available: created %s", ", ".join(t.name for t in missing))


def _migrate(connection) -> bool:
    """Bring the schema to head inside the caller's transaction.

    Returns whether pgvector is installed. Holds an advisory lock for the whole
    transaction, so a second process booting at the same time waits and then
    finds nothing to do.
    """
    from alembic import command

    connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK_KEY})
    cfg = alembic_config(connection)
    existing = set(inspect(connection).get_table_names())
    if "alembic_version" not in existing and existing & set(BASELINE_TABLES):
        _adopt_legacy_schema(connection, cfg, existing)
    command.upgrade(cfg, "head")
    vector_ok = ensure_vector_extension(connection)
    if vector_ok:
        _create_missing_vector_tables(connection)
    return vector_ok


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


async def init_db():
    """Migrate the schema to head (`alembic upgrade head`). Called once at startup.

    A database that predates Alembic is adopted first (see _adopt_legacy_schema).
    Without pgvector the app degrades to graph-only retrieval rather than
    failing to boot: the vector tables are left out until the extension exists.
    """
    from intel_platform.db.models import Base

    async with get_engine().begin() as conn:
        vector_ok = await conn.run_sync(_migrate)

    if vector_ok:
        try:
            await _check_vector_width(logger)
        except Exception as exc:
            logger.warning("Could not verify vector column width: %s", exc)
    else:
        logger.warning(
            "pgvector extension not available — vector search disabled; not creating %s",
            ", ".join(t.name for t in Base.metadata.sorted_tables if _uses_pgvector(t)) or "no tables",
        )

    # Each statement runs in its own transaction: a failure in Postgres aborts the
    # whole transaction, so one bad statement must not take the others with it.
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
