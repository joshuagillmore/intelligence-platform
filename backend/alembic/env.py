"""Alembic environment for intel_platform's Postgres schema.

Two ways in:

- **The CLI** (`uv run alembic upgrade head`, from backend/): builds an async
  engine from ``Settings.postgres_url`` and runs the migrations on one of its
  connections.
- **Programmatically** (``db.engine.init_db`` at startup, and the tests): the
  caller passes a synchronous ``Connection`` in ``config.attributes["connection"]``,
  already inside a transaction. Alembic joins that transaction instead of
  opening its own, so the caller's advisory lock, the legacy-schema adoption and
  the upgrade commit or roll back together.

The URL is never read from alembic.ini: Settings is the one source of config.
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from intel_platform.db.engine import MIGRATION_LOCK_KEY
from intel_platform.db.models import Base

config = context.config

# Only the CLI has a config file. Configuring logging from it inside the app
# would replace the app's own logging setup, so the programmatic path, which
# has no file, skips it.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
    from intel_platform.config import get_settings

    return config.get_main_option("sqlalchemy.url") or get_settings().postgres_url


def run_migrations_offline() -> None:
    """Emit the SQL (`alembic upgrade head --sql`) without a database."""
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        # Two processes booting against one empty database (the API and the
        # collection worker) would otherwise both try to create every table.
        # Transaction-scoped, and re-entrant for a session that already holds it
        # (init_db takes it before deciding whether to adopt a legacy schema).
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK_KEY})
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(_url(), poolclass=pool.NullPool)
    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
            await connection.commit()
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is None:
        asyncio.run(run_async_migrations())
    else:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
