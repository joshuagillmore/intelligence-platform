"""Postgres schema migrations (WP-P task 1; review focus 3).

`init_db` used to run `create_all` plus a list of hand-written `ADD COLUMN IF
NOT EXISTS` statements. It now runs `alembic upgrade head`, and every existing
deployment is a database `create_all` populated with no `alembic_version`: that
database must be adopted (stamped), never fail and never be re-created.

These run against a scratch database on the exported Postgres (tests/pg_scratch.py)
and skip when none is exported.
"""
from __future__ import annotations

import logging

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from intel_platform.db import engine as engine_module
from intel_platform.db.models import Base
from tests.pg_scratch import pg_engine, scratch_pg_url  # noqa: F401

VECTOR_TABLES = {"chunk_embeddings", "attack_technique_embeddings"}


async def _tables(engine) -> set[str]:
    async with engine.connect() as conn:
        return set(await conn.run_sync(lambda c: inspect(c).get_table_names()))


async def _columns(engine, table: str) -> set[str]:
    async with engine.connect() as conn:
        return {c["name"] for c in await conn.run_sync(lambda c: inspect(c).get_columns(table))}


async def _version(engine) -> str | None:
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar_one_or_none()


def _head() -> str:
    return ScriptDirectory.from_config(engine_module.alembic_config()).get_current_head()


async def _check(engine) -> None:
    """`alembic check`: raises when the models and the database disagree."""
    async with engine.connect() as conn:
        await conn.run_sync(lambda c: command.check(engine_module.alembic_config(c)))


async def _create_all_like_the_old_init_db(engine) -> None:
    """The schema a pre-Alembic deployment has: exactly the baseline tables.

    `Base.metadata` keeps growing (collection_jobs arrived with its own
    revision), so a bare `create_all` would build tables no old deployment
    ever had and the later revisions would then collide with them.
    """
    baseline = [t for t in Base.metadata.sorted_tables if t.name in engine_module.BASELINE_TABLES]
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=baseline))


class TestEmptyDatabase:
    async def test_upgrades_to_head(self, pg_engine):  # noqa: F811
        await engine_module.init_db()
        assert await _version(pg_engine) == _head()
        assert set(Base.metadata.tables) <= await _tables(pg_engine)

    async def test_models_and_migrations_agree(self, pg_engine):  # noqa: F811
        await engine_module.init_db()
        await _check(pg_engine)

    async def test_a_second_boot_is_a_no_op(self, pg_engine):  # noqa: F811
        await engine_module.init_db()
        await engine_module.init_db()
        assert await _version(pg_engine) == _head()

    async def test_two_processes_booting_at_once_both_succeed(self, pg_engine):  # noqa: F811
        """The API and the worker can boot together on an empty database: the
        advisory lock makes the second wait, then find nothing to do."""
        import asyncio

        await asyncio.gather(engine_module.init_db(), engine_module.init_db())
        assert await _version(pg_engine) == _head()
        await _check(pg_engine)

    async def test_vector_columns_take_the_configured_width(self, pg_engine):  # noqa: F811
        from intel_platform.config import get_settings

        await engine_module.init_db()
        async with pg_engine.connect() as conn:
            width = (await conn.execute(text(
                "SELECT atttypmod FROM pg_attribute WHERE attrelid = 'chunk_embeddings'::regclass "
                "AND attname = 'embedding'"
            ))).scalar_one()
        assert width == get_settings().embedding_dimensions
        assert engine_module.VECTOR_WIDTH_PROBLEM is None


class TestDatabaseCreateAllAlreadyPopulated:
    """Review focus 3: the Railway case."""

    async def test_is_stamped_and_upgrade_is_a_no_op(self, pg_engine):  # noqa: F811
        await _create_all_like_the_old_init_db(pg_engine)
        async with pg_engine.begin() as conn:
            await conn.execute(text("INSERT INTO app_settings (key, value, updated_at) VALUES ('k', 'kept', now())"))

        await engine_module.init_db()

        assert await _version(pg_engine) == _head()
        async with pg_engine.connect() as conn:
            kept = (await conn.execute(text("SELECT value FROM app_settings WHERE key = 'k'"))).scalar_one()
        assert kept == "kept", "adoption must not recreate tables"
        await _check(pg_engine)

    async def test_is_stamped_at_the_baseline_then_upgraded(self, pg_engine, monkeypatch):  # noqa: F811
        """Stamped at the revision create_all's schema matches, not blindly at
        head: a later revision must still run on an adopted database."""
        await _create_all_like_the_old_init_db(pg_engine)
        stamped: list[str] = []
        real_stamp = command.stamp
        monkeypatch.setattr(command, "stamp", lambda cfg, rev, **kw: (stamped.append(rev), real_stamp(cfg, rev, **kw)))
        await engine_module.init_db()
        assert stamped == [engine_module.BASELINE_REVISION]

    async def test_an_older_database_gains_the_columns_added_after_its_tables(self, pg_engine):  # noqa: F811
        """A database last booted before the additive columns existed."""
        await _create_all_like_the_old_init_db(pg_engine)
        async with pg_engine.begin() as conn:
            await conn.execute(text("ALTER TABLE collection_plans DROP COLUMN pir_id"))
            await conn.execute(text("ALTER TABLE collection_sources DROP COLUMN collection_status"))
            await conn.execute(text("DROP TABLE topic_edits"))

        await engine_module.init_db()

        assert "pir_id" in await _columns(pg_engine, "collection_plans")
        assert "collection_status" in await _columns(pg_engine, "collection_sources")
        assert "topic_edits" in await _tables(pg_engine)
        await _check(pg_engine)

    async def test_adoption_is_logged(self, pg_engine, caplog):  # noqa: F811
        await _create_all_like_the_old_init_db(pg_engine)
        with caplog.at_level(logging.INFO, logger="intel_platform.db.engine"):
            await engine_module.init_db()
        assert any("stamp" in r.getMessage().lower() for r in caplog.records)


class TestWithoutPgvector:
    """The app degrades to graph-only retrieval rather than failing to boot."""

    async def test_boots_without_the_vector_tables(self, pg_engine, monkeypatch, caplog):  # noqa: F811
        monkeypatch.setattr(engine_module, "ensure_vector_extension", lambda connection: False)
        with caplog.at_level(logging.WARNING, logger="intel_platform.db.engine"):
            await engine_module.init_db()
        tables = await _tables(pg_engine)
        assert not tables & VECTOR_TABLES
        assert {"collection_sources", "pirs", "app_settings"} <= tables
        assert await _version(pg_engine) == _head()
        logged = " ".join(r.getMessage() for r in caplog.records)
        assert all(name in logged for name in VECTOR_TABLES), "the skipped tables must be named"

    async def test_vector_tables_appear_once_pgvector_does(self, pg_engine, monkeypatch):  # noqa: F811
        available = False
        real = engine_module.ensure_vector_extension
        monkeypatch.setattr(
            engine_module, "ensure_vector_extension", lambda connection: available and real(connection),
        )
        await engine_module.init_db()
        assert not await _tables(pg_engine) & VECTOR_TABLES
        available = True
        await engine_module.init_db()
        assert VECTOR_TABLES <= await _tables(pg_engine)
        await _check(pg_engine)


class TestBaseline:
    async def test_baseline_tables_are_what_the_baseline_revision_creates(self, pg_engine):  # noqa: F811
        """Adoption creates missing tables from BASELINE_TABLES before stamping
        the baseline, so the two must agree. A regenerated baseline that adds a
        table (rather than a new revision) fails here."""
        async with pg_engine.begin() as conn:
            await conn.run_sync(lambda c: command.upgrade(engine_module.alembic_config(c), engine_module.BASELINE_REVISION))
        assert await _tables(pg_engine) - {"alembic_version"} == set(engine_module.BASELINE_TABLES)

    def test_the_cli_path_migrates(self, scratch_pg_url):  # noqa: F811
        """`uv run alembic upgrade head` from backend/, through alembic.ini."""
        import asyncio
        from pathlib import Path

        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        async def reset():
            engine = create_async_engine(scratch_pg_url, poolclass=NullPool)
            async with engine.begin() as conn:
                await conn.execute(text("DROP SCHEMA public CASCADE"))
                await conn.execute(text("CREATE SCHEMA public"))
            await engine.dispose()

        async def version():
            engine = create_async_engine(scratch_pg_url, poolclass=NullPool)
            try:
                return await _version(engine)
            finally:
                await engine.dispose()

        asyncio.run(reset())
        cfg = Config(str(Path(engine_module.__file__).resolve().parents[3] / "alembic.ini"))
        cfg.set_main_option("sqlalchemy.url", scratch_pg_url.replace("%", "%%"))
        command.upgrade(cfg, "head")
        assert asyncio.run(version()) == _head()
