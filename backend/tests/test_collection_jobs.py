"""Collection jobs: the durable record that answers "is a run in flight?".

The answer used to come from an asyncio task registry and an in-memory tracker
in the API process. Neither survived a restart or was visible to a second
process, so a run could not move to a worker. It now comes from the latest
`collection_jobs` row, and these tests pin the rules:

* the state each row maps to (pure; no database),
* the row operations against a real Postgres: one live job per plan, the
  worker's `FOR UPDATE SKIP LOCKED` claim, heartbeats that only the owner can
  write, a terminal write that never overwrites a cancellation,
* review focus 1: a worker that dies mid-run with its row still `running`
  reads `stalled` once its heartbeat is older than the stall window, and
  `/execute` then accepts a new run.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from intel_platform.collection import job_runner
from intel_platform.db import jobs
from tests.pg import make_plan, pg_factory_fixture  # noqa: F401  (the pg_factory fixture)
from tests.ids import tp

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def _job(status, *, heartbeat_ago=None, started_ago=None, created_ago=0, finished=False):
    def ago(s):
        return None if s is None else NOW - timedelta(seconds=s)
    return SimpleNamespace(
        status=status, heartbeat_at=ago(heartbeat_ago), started_at=ago(started_ago),
        created_at=ago(created_ago), finished_at=NOW if finished else None,
    )


class TestRunStateRules:
    def test_no_job_is_idle(self):
        assert job_runner.run_state(None, None) == "idle"

    @pytest.mark.parametrize("status,expected", [
        (jobs.SUCCEEDED, "completed"), (jobs.FAILED, "failed"),
    ])
    def test_terminal_rows_report_themselves(self, status, expected):
        assert job_runner.run_state(_job(status, finished=True), NOW, 120) == expected

    def test_a_cancelled_run_that_has_stopped_is_cancelled(self):
        assert job_runner.run_state(_job(jobs.CANCELLED, heartbeat_ago=5, finished=True), NOW, 120) == "cancelled"

    def test_a_fresh_heartbeat_is_running(self):
        assert job_runner.run_state(_job(jobs.RUNNING, heartbeat_ago=5, started_ago=300), NOW, 120) == "running"

    def test_a_heartbeat_older_than_the_window_is_stalled(self):
        assert job_runner.run_state(_job(jobs.RUNNING, heartbeat_ago=121), NOW, 120) == "stalled"

    def test_the_heartbeat_not_the_start_decides(self):
        """A long run is not a dead one: started an hour ago, beat 5 s ago."""
        assert job_runner.run_state(_job(jobs.RUNNING, heartbeat_ago=5, started_ago=3600), NOW, 120) == "running"

    def test_a_queued_job_blocks_until_nobody_has_picked_it_up_for_the_window(self):
        """Queued counts as in flight (a second execute would queue a duplicate
        run), but a deployment with no worker must not refuse forever."""
        assert job_runner.run_state(_job(jobs.QUEUED, created_ago=10), NOW, 120) == "running"
        assert job_runner.run_state(_job(jobs.QUEUED, created_ago=500), NOW, 120) == "stalled"

    def test_a_cancelled_run_still_stopping_is_running(self):
        """Cancel is honoured between sources; until the run has stopped, a new
        one would collect alongside it."""
        assert job_runner.run_state(_job(jobs.CANCELLED, heartbeat_ago=5), NOW, 120) == "running"
        assert job_runner.run_state(_job(jobs.CANCELLED, heartbeat_ago=500), NOW, 120) == "stalled"


class TestSettings:
    """The settings are added by the platform package; until then (and when
    absent) the documented defaults apply."""

    def test_defaults(self, monkeypatch):
        monkeypatch.setattr(job_runner, "settings", SimpleNamespace())
        assert job_runner.worker_mode() == "inline"
        assert job_runner.stall_seconds() == 120

    def test_worker_mode_is_read(self, monkeypatch):
        monkeypatch.setattr(job_runner, "settings", SimpleNamespace(collection_worker_mode="WORKER"))
        assert job_runner.worker_mode() == "worker"

    def test_an_unknown_mode_runs_inline(self, monkeypatch):
        monkeypatch.setattr(job_runner, "settings", SimpleNamespace(collection_worker_mode="celery"))
        assert job_runner.worker_mode() == "inline"

    def test_the_stall_window_never_undercuts_the_heartbeat(self, monkeypatch):
        """A window at or below the heartbeat interval would flap a healthy run."""
        monkeypatch.setattr(job_runner, "settings", SimpleNamespace(collection_stall_seconds=5))
        assert job_runner.stall_seconds() >= 3 * job_runner.HEARTBEAT_SECONDS


class TestModel:
    def test_the_contracted_columns(self):
        assert jobs.CollectionJob.__tablename__ == "collection_jobs"
        assert set(jobs.CollectionJob.__table__.columns.keys()) == {
            "id", "plan_id", "project_id", "kind", "status", "worker_id",
            "heartbeat_at", "started_at", "finished_at", "error", "created_at",
            # Added at integration: per-run degraded counts (telemetry is per process).
            "degraded",
        }
        assert jobs.CollectionJob.__table__.c.degraded.nullable

    def test_it_is_on_the_shared_metadata(self):
        from intel_platform.db.models import Base

        assert "collection_jobs" in Base.metadata.tables

    def test_errors_are_bounded(self):
        assert jobs.sanitise_error("") is None
        assert len(jobs.sanitise_error("x" * 5000)) == jobs.ERROR_MAX


# ---------------------------------------------------------------------------
# Against Postgres
# ---------------------------------------------------------------------------

async def _row(factory, job_id):
    async with factory() as db:
        return (await db.execute(select(jobs.CollectionJob).where(jobs.CollectionJob.id == job_id))).scalar_one()


async def _insert(factory, plan_id, **kw):
    async with factory() as db:
        job_id = await jobs.insert_job(db, plan_id=plan_id, project_id=tp("wpw-jobs"),
                                       kind=kw.pop("kind", jobs.KIND_AGENTIC), **kw)
        await db.commit()
        return job_id


async def _age_heartbeat(factory, job_id, seconds):
    """What a dead worker leaves behind: a row still `running`, beat long ago."""
    async with factory() as db:
        await db.execute(text(
            "UPDATE collection_jobs SET heartbeat_at = now() - make_interval(secs => :s), "
            "started_at = now() - make_interval(secs => :s) WHERE id = :id"
        ), {"s": seconds, "id": job_id})
        await db.commit()


class TestJobRows:
    async def test_inline_insert_is_claimed_at_once(self, pg_factory):
        pid = await make_plan(pg_factory)
        job_id = await _insert(pg_factory, pid, claimed_by="api:host:1")
        row = await _row(pg_factory, job_id)
        assert row.status == jobs.RUNNING and row.worker_id == "api:host:1"
        assert row.heartbeat_at is not None and row.started_at is not None and row.created_at is not None

    async def test_a_worker_insert_is_queued(self, pg_factory):
        pid = await make_plan(pg_factory)
        row = await _row(pg_factory, await _insert(pg_factory, pid))
        assert row.status == jobs.QUEUED and row.worker_id is None and row.heartbeat_at is None

    async def test_one_live_job_per_plan(self, pg_factory):
        """The database refuses a second live job even if a caller skipped the
        plan-row lock the route takes."""
        pid = await make_plan(pg_factory)
        await _insert(pg_factory, pid)
        with pytest.raises(IntegrityError):
            await _insert(pg_factory, pid)

    async def test_a_finished_job_does_not_hold_the_plan(self, pg_factory):
        pid = await make_plan(pg_factory)
        first = await _insert(pg_factory, pid, claimed_by="w")
        async with pg_factory() as db:
            assert await jobs.finish(db, first, "w", jobs.SUCCEEDED)
        await _insert(pg_factory, pid)

    async def test_claim_skips_a_row_another_worker_holds(self, pg_factory):
        """FOR UPDATE SKIP LOCKED: a row locked by one claimer is invisible to
        the next, which neither blocks nor takes it."""
        pid = await make_plan(pg_factory)
        job_id = await _insert(pg_factory, pid)
        async with pg_factory() as holder:
            await holder.execute(select(jobs.CollectionJob).where(jobs.CollectionJob.id == job_id).with_for_update())
            async with pg_factory() as other:
                assert await jobs.claim_next(other, "worker-b") is None
            await holder.rollback()
        async with pg_factory() as db:
            assert await jobs.claim_next(db, "worker-b") == job_id
        row = await _row(pg_factory, job_id)
        assert row.status == jobs.RUNNING and row.worker_id == "worker-b" and row.heartbeat_at is not None

    async def test_two_workers_never_claim_the_same_job(self, pg_factory):
        import asyncio

        pid = await make_plan(pg_factory)
        job_id = await _insert(pg_factory, pid)

        async def claim(name):
            async with pg_factory() as db:
                return await jobs.claim_next(db, name)

        got = await asyncio.gather(claim("a"), claim("b"), claim("c"))
        assert [g for g in got if g == job_id] == [job_id]

    async def test_legacy_rows_are_never_claimed(self, pg_factory):
        legacy_key = uuid.uuid4()
        async with pg_factory() as db:
            await jobs.insert_job(db, plan_id=legacy_key, project_id=tp("wpw-jobs"), kind=jobs.KIND_LEGACY)
            await db.commit()
            assert await jobs.claim_next(db, "w") is None

    async def test_only_the_owner_can_heartbeat(self, pg_factory):
        pid = await make_plan(pg_factory)
        job_id = await _insert(pg_factory, pid, claimed_by="owner")
        async with pg_factory() as db:
            assert await jobs.heartbeat(db, job_id, "owner") == jobs.RUNNING
            assert await jobs.heartbeat(db, job_id, "impostor") is None

    async def test_finish_keeps_a_cancellation(self, pg_factory):
        pid = await make_plan(pg_factory)
        job_id = await _insert(pg_factory, pid, claimed_by="owner")
        async with pg_factory() as db:
            await jobs.cancel(db, job_id, still_running=True)
            await db.commit()
            assert await jobs.finish(db, job_id, "owner", jobs.SUCCEEDED)
        row = await _row(pg_factory, job_id)
        assert row.status == jobs.CANCELLED and row.finished_at is not None

    async def test_finish_after_being_superseded_writes_nothing(self, pg_factory):
        pid = await make_plan(pg_factory)
        job_id = await _insert(pg_factory, pid, claimed_by="owner")
        async with pg_factory() as db:
            await jobs.close_unfinished(db, pid, "Stalled")
            await db.commit()
            assert await jobs.finish(db, job_id, "owner", jobs.SUCCEEDED) is None
        row = await _row(pg_factory, job_id)
        assert row.status == jobs.FAILED and row.error == "Stalled"


class TestADeadWorker:
    """Review focus 1."""

    async def test_running_until_the_window_then_stalled_then_executable(self, pg_factory, monkeypatch):
        from intel_platform.api.routes import collection_plans as cp
        from intel_platform.collection import agentic

        pid = await make_plan(pg_factory)
        dead = await _insert(pg_factory, pid, claimed_by="worker:gone:1")

        async with pg_factory() as db:
            assert await cp.current_run_state(db, pid) == "running"
            with pytest.raises(HTTPException) as refused:
                await cp.execute_plan_endpoint(str(pid), None, db=db, store=None)
            assert refused.value.status_code == 409

        # The worker died: its row is still `running`, its last beat is old.
        await _age_heartbeat(pg_factory, dead, job_runner.stall_seconds() + 30)
        async with pg_factory() as db:
            assert await cp.current_run_state(db, pid) == "stalled"
            status = await cp.get_execution_status(str(pid), db=db)
            assert status["status"] == "stalled"
            assert status["seconds_since_heartbeat"] > job_runner.stall_seconds()

        # ...and a new run is accepted (queued for a worker, so nothing runs here).
        monkeypatch.setattr(job_runner, "worker_mode", lambda: job_runner.WORKER)
        called = []
        monkeypatch.setattr(agentic, "run_agentic_loop", lambda **kw: called.append(kw))
        async with pg_factory() as db:
            body = await cp.execute_plan_endpoint(str(pid), None, db=db, store=None)
        assert body["execution_status"] == "queued" and body["job_id"]
        assert called == []

        old = await _row(pg_factory, dead)
        assert old.status == jobs.FAILED and old.finished_at is not None
        assert old.error.startswith("Stalled: no heartbeat for")
        new = await _row(pg_factory, uuid.UUID(body["job_id"]))
        assert new.status == jobs.QUEUED
        async with pg_factory() as db:
            assert await cp.current_run_state(db, pid) == "running"

    async def test_the_dead_workers_late_heartbeat_finds_its_job_gone(self, pg_factory):
        """If the "dead" worker was only partitioned, it must stop, not collect
        alongside the run that replaced it."""
        pid = await make_plan(pg_factory)
        job_id = await _insert(pg_factory, pid, claimed_by="worker:slow:1")
        async with pg_factory() as db:
            await jobs.close_unfinished(db, pid, "Stalled: superseded")
            await db.commit()
            assert await jobs.heartbeat(db, job_id, "worker:slow:1") is None
