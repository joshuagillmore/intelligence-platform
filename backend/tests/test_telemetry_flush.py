"""Degraded counts across processes (WP-T, contract 3).

`services.telemetry` counts in memory, per process, so the collection worker's
outages never reached the admin card. Each process now flushes what it counted
since its last flush to `degraded_events` (every minute, at shutdown, and in the
worker at the end of each job), and `GET /api/admin/degraded` sums the last
24 hours of rows by process plus the API's own unflushed counts. `/health`
stays per process.

The first half fakes the database session; the second runs against a scratch
Postgres (tests/pg.py), migrated through Alembic, and skips without one.
"""
from __future__ import annotations

import asyncio
import socket
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text

from intel_platform.services import telemetry
from tests.pg import pg_engine, scratch_pg_url  # noqa: F401


@pytest.fixture(autouse=True)
def _fresh_counts():
    telemetry.reset()
    yield
    telemetry.reset()


class _FakeDb:
    def __init__(self, sink: list, fail: Exception | None, hang: asyncio.Event | None):
        self.sink, self.fail, self.hang = sink, fail, hang
        self.staged: list = []
        self.executed: list | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def add_all(self, rows):
        self.staged = list(rows)

    async def execute(self, statement):
        self.executed.append(statement)
        return SimpleNamespace(rowcount=0)

    async def commit(self):
        if self.hang is not None:
            await self.hang.wait()
        if self.fail is not None:
            raise self.fail
        self.sink.extend(self.staged)


def _factory(fail: Exception | None = None, hang: asyncio.Event | None = None):
    """A session factory whose commits land in ``factory.rows`` (or fail, or
    hang), and whose other statements (the prune) in ``factory.executed``."""
    rows: list = []
    calls: list = []
    executed: list = []

    def factory():
        calls.append(1)
        db = _FakeDb(rows, fail, hang)
        db.executed = executed
        return db

    factory.rows = rows
    factory.calls = calls
    factory.executed = executed
    return factory


def _summed(rows) -> dict:
    out: dict = {}
    for r in rows:
        bucket = out.setdefault(r.process, {}).setdefault(r.subsystem, {})
        bucket[r.reason] = bucket.get(r.reason, 0) + r.count
    return out


# ---------------------------------------------------------------------------
# Pending counts and draining
# ---------------------------------------------------------------------------

class TestPending:
    def test_pending_counts_reset_on_drain_and_lifetime_counts_do_not(self):
        telemetry.record_degraded("extraction", "TimeoutError")
        telemetry.record_degraded("extraction", "TimeoutError")
        assert telemetry.pending() == {"extraction": {"TimeoutError": 2}}

        batch = telemetry.drain()
        assert batch.counts == {"extraction": {"TimeoutError": 2}}
        assert batch.window_start <= batch.window_end
        assert telemetry.pending() == {}
        # /health and the lifetime snapshot still describe the whole process.
        assert telemetry.totals() == {"extraction": 2}

        telemetry.record_degraded("extraction", "TimeoutError")
        assert telemetry.pending() == {"extraction": {"TimeoutError": 1}}
        assert telemetry.totals() == {"extraction": 3}

    def test_windows_follow_on_from_each_other(self):
        first = telemetry.drain()
        second = telemetry.drain()
        assert second.window_start == first.window_end

    def test_overflowed_reasons_are_pending_under_the_overflow_reason(self):
        for i in range(telemetry.MAX_REASONS_PER_SUBSYSTEM + 3):
            telemetry.record_degraded("collection", f"reason-{i}")
        pending = telemetry.pending()["collection"]
        assert len(pending) == telemetry.MAX_REASONS_PER_SUBSYSTEM + 1
        assert pending[telemetry.OVERFLOW_REASON] == 3

    def test_pending_is_a_copy(self):
        telemetry.record_degraded("llm", "x")
        telemetry.pending()["llm"]["x"] = 99
        assert telemetry.pending() == {"llm": {"x": 1}}


# ---------------------------------------------------------------------------
# Flushing, with a fake session
# ---------------------------------------------------------------------------

class TestFlush:
    async def test_writes_one_row_per_reason_and_resets_pending(self):
        telemetry.record_degraded("extraction", "TimeoutError")
        telemetry.record_degraded("extraction", "TimeoutError")
        telemetry.record_degraded("topics", "label_failed")
        factory = _factory()

        assert await telemetry.flush(telemetry.API, db_factory=factory) == 2

        assert _summed(factory.rows) == {"api": {"extraction": {"TimeoutError": 2}, "topics": {"label_failed": 1}}}
        for row in factory.rows:
            assert row.host == socket.gethostname()
            assert row.window_start <= row.window_end
        assert len({(r.window_start, r.window_end) for r in factory.rows}) == 1, "one window per flush"
        assert telemetry.pending() == {}
        assert telemetry.totals() == {"extraction": 2, "topics": 1}

    async def test_nothing_pending_touches_no_database(self):
        factory = _factory()
        assert await telemetry.flush(telemetry.WORKER, db_factory=factory) == 0
        assert factory.calls == []

    async def test_a_failed_write_keeps_the_counts_for_the_next_flush(self):
        start = telemetry.drain().window_end   # where the window now pending begins
        telemetry.record_degraded("embeddings", "embed_failed")

        broken = _factory(fail=OSError("connection refused"))
        assert await telemetry.flush(telemetry.API, db_factory=broken) == 0   # no raise
        assert telemetry.pending() == {"embeddings": {"embed_failed": 1}}

        telemetry.record_degraded("embeddings", "embed_failed")
        working = _factory()
        assert await telemetry.flush(telemetry.API, db_factory=working) == 1
        (row,) = working.rows
        assert row.count == 2
        assert row.window_start == start, "the retried window starts where the failed one did"

    async def test_an_unreachable_postgres_is_a_no_op(self):
        """The `.invalid` host the suite uses when no Postgres is exported."""
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        engine = create_async_engine(
            "postgresql+asyncpg://intel:x@telemetry-flush-disabled.invalid:5432/none", poolclass=NullPool,
        )
        try:
            telemetry.record_degraded("llm", "call_failed")
            assert await telemetry.flush(telemetry.API, db_factory=async_sessionmaker(engine)) == 0
            assert telemetry.pending() == {"llm": {"call_failed": 1}}
        finally:
            await engine.dispose()

    async def test_an_unknown_process_is_not_flushed(self):
        telemetry.record_degraded("llm", "x")
        factory = _factory()
        assert await telemetry.flush("scheduler", db_factory=factory) == 0
        assert factory.calls == [] and telemetry.pending() == {"llm": {"x": 1}}

    async def test_a_cancelled_flush_keeps_the_counts(self):
        telemetry.record_degraded("topics", "label_failed")
        factory = _factory(hang=asyncio.Event())
        task = asyncio.create_task(telemetry.flush(telemetry.API, db_factory=factory))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert telemetry.pending() == {"topics": {"label_failed": 1}}

    async def test_a_flush_that_wrote_prunes_old_rows_at_most_hourly(self, monkeypatch):
        factory = _factory()
        telemetry.record_degraded("llm", "x")
        assert await telemetry.flush(telemetry.API, db_factory=factory) == 1
        (statement,) = factory.executed
        assert str(statement).startswith("DELETE FROM degraded_events WHERE degraded_events.window_end <")

        telemetry.record_degraded("llm", "x")
        assert await telemetry.flush(telemetry.API, db_factory=factory) == 1
        assert len(factory.executed) == 1, "not again within the hour"

        monkeypatch.setattr(telemetry, "_PRUNE_SECONDS", 0.0)
        assert await telemetry.flush(telemetry.API, db_factory=factory) == 0
        assert len(factory.executed) == 1, "a flush that wrote nothing does not prune"
        telemetry.record_degraded("llm", "x")
        assert await telemetry.flush(telemetry.API, db_factory=factory) == 1
        assert len(factory.executed) == 2

    async def test_a_failed_prune_does_not_undo_the_flush(self):
        class _NoDelete(_FakeDb):
            async def execute(self, statement):
                raise OSError("connection reset")

        rows: list = []
        telemetry.record_degraded("llm", "x")
        assert await telemetry.flush(telemetry.API, db_factory=lambda: _NoDelete(rows, None, None)) == 1
        assert len(rows) == 1
        assert telemetry.pending() == {}

    async def test_flushing_flushes_periodically_and_once_more_at_exit(self):
        factory = _factory()
        async with telemetry.flushing(telemetry.WORKER, interval=0.02, db_factory=factory):
            telemetry.record_degraded("collection", "source_failed")
            for _ in range(200):
                if factory.rows:
                    break
                await asyncio.sleep(0.01)
            assert _summed(factory.rows) == {"worker": {"collection": {"source_failed": 1}}}
            telemetry.record_degraded("collection", "no_usable_content")
        # The timer or the flush at exit wrote the second one; either way nothing is left.
        assert _summed(factory.rows) == {
            "worker": {"collection": {"source_failed": 1, "no_usable_content": 1}},
        }
        assert telemetry.pending() == {}

    async def test_a_hung_database_does_not_hold_up_shutdown(self, monkeypatch):
        monkeypatch.setattr(telemetry, "_SHUTDOWN_FLUSH_SECONDS", 0.05)
        factory = _factory(hang=asyncio.Event())
        async with telemetry.flushing(telemetry.API, interval=3600, db_factory=factory):
            telemetry.record_degraded("llm", "x")
        assert telemetry.pending() == {"llm": {"x": 1}}


class TestRecentWhileFlushing:
    async def test_a_flush_during_the_read_is_counted_once(self, monkeypatch):
        """The read sees the table before a flush commits, and memory after it
        drained: without a re-read those counts would be in neither."""
        telemetry.record_degraded("llm", "x")
        reads: list = []

        async def stored(since, db_factory):
            reads.append(1)
            if len(reads) == 1:
                telemetry.drain()                 # a flush took the counts...
                telemetry._flushes_done += 1      # ...and committed after this read began
                return {}
            return {"api": {"llm": {"x": 1}}}

        monkeypatch.setattr(telemetry, "_stored", stored)
        body = await telemetry.recent()
        assert len(reads) == 2
        assert body["processes"]["api"] == {"llm": {"x": 1}}
        assert body["total"] == {"llm": {"x": 1}}


# ---------------------------------------------------------------------------
# Against Postgres
# ---------------------------------------------------------------------------

async def _migrated(pg_engine):  # noqa: F811
    from intel_platform.db import engine as engine_module

    await engine_module.init_db()
    return engine_module.get_session_factory()


async def _rows(factory):
    from intel_platform.db.models import DegradedEvent

    async with factory() as db:
        return (await db.execute(select(DegradedEvent))).scalars().all()


async def _insert(factory, process, subsystem, reason, count, ended):
    from intel_platform.db.models import DegradedEvent

    async with factory() as db:
        db.add(DegradedEvent(process=process, host="test-host", subsystem=subsystem, reason=reason, count=count,
                             window_start=ended - timedelta(minutes=1), window_end=ended))
        await db.commit()


class TestAgainstPostgres:
    async def test_the_api_flush_writes_rows_and_resets_pending(self, pg_engine):  # noqa: F811
        factory = await _migrated(pg_engine)
        telemetry.record_degraded("enrichment", "rdap: http 503")
        telemetry.record_degraded("enrichment", "rdap: http 503")
        telemetry.record_degraded("llm", "report_call_failed")

        assert await telemetry.flush(telemetry.API) == 2   # the app's own session factory

        rows = await _rows(factory)
        assert _summed(rows) == {"api": {"enrichment": {"rdap: http 503": 2}, "llm": {"report_call_failed": 1}}}
        assert all(r.host == socket.gethostname() and r.window_start <= r.window_end for r in rows)
        assert telemetry.pending() == {}
        assert await telemetry.flush(telemetry.API) == 0
        assert len(await _rows(factory)) == 2

    async def test_the_window_is_the_last_24_hours(self, pg_engine):  # noqa: F811
        factory = await _migrated(pg_engine)
        now = datetime.now(timezone.utc)
        await _insert(factory, "worker", "collection", "source_failed", 5, now - timedelta(hours=25))
        await _insert(factory, "worker", "collection", "source_failed", 2, now - timedelta(hours=1))
        await _insert(factory, "api", "topics", "label_failed", 1, now - timedelta(hours=23, minutes=50))

        body = await telemetry.recent()

        assert body["processes"] == {
            "api": {"topics": {"label_failed": 1}},
            "worker": {"collection": {"source_failed": 2}},
        }
        assert body["total"] == {"topics": {"label_failed": 1}, "collection": {"source_failed": 2}}
        assert body["history_available"] is True

    async def test_the_endpoint_combines_the_processes(self, pg_engine):  # noqa: F811
        import httpx

        from intel_platform.api.app import app
        from intel_platform.config import settings

        factory = await _migrated(pg_engine)
        # What the worker flushed, what the API flushed, and what the API has not flushed yet.
        telemetry.record_degraded("extraction", "nlp_fallback")
        assert await telemetry.flush(telemetry.WORKER) == 1
        telemetry.record_degraded("extraction", "nlp_fallback")
        telemetry.record_degraded("extraction", "nlp_fallback")
        assert await telemetry.flush(telemetry.API) == 1
        telemetry.record_degraded("embeddings", "embed_failed")
        assert len(await _rows(factory)) == 2

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/degraded", headers={"Authorization": f"Bearer {settings.api_key}"})
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {"since", "processes", "total", "history_available"}
        assert body["processes"] == {
            "api": {"extraction": {"nlp_fallback": 2}, "embeddings": {"embed_failed": 1}},
            "worker": {"extraction": {"nlp_fallback": 1}},
        }
        assert body["total"] == {"extraction": {"nlp_fallback": 3}, "embeddings": {"embed_failed": 1}}
        assert body["history_available"] is True

    async def test_a_database_at_the_previous_head_gains_the_table(self, pg_engine):  # noqa: F811
        from alembic import command
        from alembic.script import ScriptDirectory

        from intel_platform.db import engine as engine_module

        async with pg_engine.begin() as conn:
            await conn.run_sync(lambda c: command.upgrade(engine_module.alembic_config(c), "99f913170802"))
        async with pg_engine.connect() as conn:
            assert (await conn.execute(text("SELECT to_regclass('degraded_events')"))).scalar_one() is None

        await engine_module.init_db()

        head = ScriptDirectory.from_config(engine_module.alembic_config()).get_current_head()
        async with pg_engine.connect() as conn:
            assert (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar_one() == head
            assert (await conn.execute(text("SELECT to_regclass('degraded_events')"))).scalar_one() is not None
            await conn.run_sync(lambda c: command.check(engine_module.alembic_config(c)))

    async def test_a_flush_deletes_rows_past_retention(self, pg_engine):  # noqa: F811
        factory = await _migrated(pg_engine)
        now = datetime.now(timezone.utc)
        await _insert(factory, "worker", "collection", "source_failed", 3,
                      now - timedelta(days=telemetry.RETAIN_DAYS, hours=1))
        await _insert(factory, "worker", "collection", "source_failed", 2, now - timedelta(days=2))

        telemetry.record_degraded("llm", "call_failed")
        assert await telemetry.flush(telemetry.API) == 1

        assert sorted((r.process, r.count) for r in await _rows(factory)) == [("api", 1), ("worker", 2)]

    async def test_rows_refuse_an_unknown_process(self, pg_engine):  # noqa: F811
        from sqlalchemy.exc import IntegrityError

        factory = await _migrated(pg_engine)
        with pytest.raises(IntegrityError):
            await _insert(factory, "scheduler", "llm", "x", 1, datetime.now(timezone.utc))
