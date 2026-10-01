"""A throwaway Postgres database for tests that need a real one.

Most of the suite runs against fakes (see tests/conftest.py, which points
POSTGRES_URL at a `.invalid` host unless one is exported). The Alembic and
AppSetting tests need the real thing, so these fixtures:

- skip when no Postgres is exported (the `.invalid` placeholder is in effect);
- never touch the exported database itself: a scratch database is created next
  to it on the same server for the session and dropped afterwards, because the
  migration tests reset their schema with `DROP SCHEMA public CASCADE`;
- point `intel_platform.db.engine` at that scratch database for the test.

Import the fixtures into a test module with
`from tests.pg_scratch import scratch_pg_url, pg_engine  # noqa: F401`.
"""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


def _exported_url():
    url = os.environ.get("POSTGRES_URL", "")
    if not url or ".invalid" in url:
        pytest.skip("needs a real Postgres: export POSTGRES_URL")
    return make_url(url)


async def _admin(url, statement: str) -> None:
    engine = create_async_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(text(statement))
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def scratch_pg_url():
    """URL of a scratch database, created once per session and dropped after."""
    server = _exported_url()
    name = f"{server.database}_scratch_{uuid.uuid4().hex[:8]}"
    asyncio.run(_admin(server, f'CREATE DATABASE "{name}"'))
    try:
        yield server.set(database=name).render_as_string(hide_password=False)
    finally:
        asyncio.run(_admin(server, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.fixture
async def pg_engine(scratch_pg_url, monkeypatch):
    """An engine on an empty scratch schema, installed as the app's engine."""
    from intel_platform.db import engine as engine_module

    engine = create_async_engine(scratch_pg_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    monkeypatch.setattr(engine_module, "_engine", engine)
    monkeypatch.setattr(engine_module, "_session_factory", async_sessionmaker(engine, expire_on_commit=False))
    try:
        yield engine
    finally:
        await engine.dispose()
