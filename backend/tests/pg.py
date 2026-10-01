"""A real Postgres for the tests that need one (collection jobs, the worker).

Not a test module: imported by the tests that use :func:`pg_factory`.

The suite's conftest points ``POSTGRES_URL`` at an unresolvable ``.invalid``
host unless one is exported, so on a workstation that has not opted in these
tests skip with that reason. CI exports a real database and runs them. When a
URL *is* exported and the server does not answer, the fixture errors rather
than skips: a configured database that is down is a failure, not an opt-out.

Each test gets its own engine (``NullPool``): pytest-asyncio gives every test a
fresh event loop, and a pooled asyncpg connection is bound to the loop that
opened it.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from intel_platform.db import jobs as _jobs  # noqa: F401  (registers collection_jobs on Base.metadata)
from intel_platform.db.models import Base, CollectionPlan

# Every plan a test here creates uses this project id prefix, so teardown can
# remove exactly what the tests made.
PROJECT = "test-wpw-jobs"


def postgres_url() -> str:
    return os.environ.get("POSTGRES_URL", "")


def _engine_url():
    """The exported URL, with ``localhost`` pinned to IPv4.

    Docker publishes the test databases on 127.0.0.1 only, and on Windows a
    refused ::1 attempt costs about two seconds before the IPv4 retry. Every
    test here opens fresh connections, so that was minutes per run.
    """
    from sqlalchemy.engine import make_url

    url = make_url(postgres_url())
    return url.set(host="127.0.0.1") if url.host == "localhost" else url


def postgres_configured() -> bool:
    return bool(postgres_url()) and ".invalid" not in postgres_url()


requires_postgres = pytest.mark.skipif(
    not postgres_configured(),
    reason="needs a real Postgres: export POSTGRES_URL (CI does)",
)


_schema_ready: set[str] = set()


@pytest.fixture(name="pg_factory")
async def pg_factory_fixture():
    """``pg_factory``: an async_sessionmaker on a fresh NullPool engine, schema created.

    Import ``pg_factory_fixture`` into a test module to use it; the fixture is
    registered under the shorter name so test parameters do not shadow the import.
    """
    if not postgres_configured():
        pytest.skip("needs a real Postgres: export POSTGRES_URL (CI does)")
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
    import uuid

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
