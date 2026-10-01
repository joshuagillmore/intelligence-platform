"""A real Postgres for the tests that need one. Not a test module.

Most of the suite runs against fakes: ``tests/conftest.py`` points
``POSTGRES_URL`` at an unresolvable ``.invalid`` host unless one is exported.
The tests that need the real thing import their fixtures from here:

- ``pg_factory`` (collection jobs, the worker, the execute guard): an
  ``async_sessionmaker`` on the exported database, schema created once per
  process; teardown removes only the plans and jobs this run made (project id
  :data:`PROJECT`, which is per run, so a concurrent suite keeps its rows).
  Import ``pg_factory_fixture``; it is registered under the shorter name so test
  parameters do not shadow the import.
- ``scratch_pg_url`` / ``pg_engine`` (Alembic, persisted settings): a scratch
  database created next to the exported one for the session and dropped after,
  because those tests reset their schema with ``DROP SCHEMA public CASCADE``;
  ``pg_engine`` installs an engine on it as the app's engine for the test.

Both skip, with the same reason, when no Postgres is exported (CI exports one).
When a URL *is* exported and the server does not answer they error rather than
skip: a configured database that is down is a failure, not an opt-out.

Every engine is ``NullPool``: pytest-asyncio gives every test a fresh event
loop, and a pooled asyncpg connection is bound to the loop that opened it.
"""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy import delete, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from intel_platform.db import jobs as _jobs  # noqa: F401  (registers collection_jobs on Base.metadata)
from intel_platform.db.models import Base, CollectionPlan
from tests.ids import tp

# Every plan a pg_factory test creates uses this project id prefix, so teardown
# can remove exactly what this run made.
PROJECT = tp("wpw-jobs")

_SKIP_REASON = "needs a real Postgres: export POSTGRES_URL (CI does)"


def postgres_url() -> str:
    return os.environ.get("POSTGRES_URL", "")


def postgres_configured() -> bool:
    return bool(postgres_url()) and ".invalid" not in postgres_url()


def _engine_url():
    """The exported URL, with ``localhost`` pinned to IPv4.

    Docker publishes the test databases on 127.0.0.1 only, and on Windows a
    refused ::1 attempt costs about two seconds before the IPv4 retry. Every
    test here opens fresh connections, so that was minutes per run.
    """
    url = make_url(postgres_url())
    return url.set(host="127.0.0.1") if url.host == "localhost" else url


requires_postgres = pytest.mark.skipif(not postgres_configured(), reason=_SKIP_REASON)


# ---------------------------------------------------------------------------
# pg_factory: the exported database itself
# ---------------------------------------------------------------------------

_schema_ready: set[str] = set()


@pytest.fixture(name="pg_factory")
async def pg_factory_fixture():
    """``pg_factory``: an async_sessionmaker on a fresh NullPool engine, schema created."""
    if not postgres_configured():
        pytest.skip(_SKIP_REASON)
    engine = create_async_engine(_engine_url(), poolclass=NullPool)
    if postgres_url() not in _schema_ready:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _schema_ready.add(postgres_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        async with factory() as db:
            plan_ids = (await db.execute(
                text("SELECT id FROM collection_plans WHERE project_id LIKE :p"), {"p": PROJECT + "%"}
            )).scalars().all()
            await db.execute(delete(_jobs.CollectionJob).where(_jobs.CollectionJob.project_id.like(PROJECT + "%")))
            if plan_ids:
                await db.execute(delete(_jobs.CollectionJob).where(_jobs.CollectionJob.plan_id.in_(plan_ids)))
            await db.execute(delete(CollectionPlan).where(CollectionPlan.project_id.like(PROJECT + "%")))
            await db.commit()
        await engine.dispose()


async def make_plan(factory, *, sources: int = 1, pir_id=None, status: str = "DRAFT",
                    routing_rules: dict | None = None, suffix: str = ""):
    """Insert a plan (and `sources` web_scrape sources); return its id."""
    from intel_platform.db.models import CollectionSource

    async with factory() as db:
        plan = CollectionPlan(
            id=uuid.uuid4(), project_id=PROJECT + suffix, name="wp-w plan", status=status,
            pir_id=pir_id, routing_rules=routing_rules if routing_rules is not None else {"extract_entities": True},
        )
        db.add(plan)
        await db.flush()
        for i in range(sources):
            db.add(CollectionSource(
                plan_id=plan.id, name=f"src{i}", source_type="web_scrape",
                config={"url": f"https://example.com/{i}"},
            ))
        await db.commit()
        return plan.id


# ---------------------------------------------------------------------------
# scratch_pg_url / pg_engine: a throwaway database next to the exported one
# ---------------------------------------------------------------------------

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
    if not postgres_configured():
        pytest.skip(_SKIP_REASON)
    server = _engine_url()
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
