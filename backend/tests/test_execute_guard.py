"""Execution is refused for a run in flight, not for a status flag.

The old guard allowed DRAFT and PAUSED only. Two consequences, both seen live:

  * "Activate" — the button an analyst naturally presses before running
    something — sets ACTIVE, which made the plan unrunnable. Execute returned
    400 "Cannot execute plan in ACTIVE status", and the only recovery was to
    press Pause, which nobody would guess.
  * Execution itself sets ACTIVE, so any plan whose run died was stranded
    permanently unexecutable.

`plan.status` is a lifecycle flag an analyst edits by hand; the run's job row
is evidence. The guard reads the job table through `current_run_state`, which
the progress endpoint shares, so the two cannot disagree.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from intel_platform.api.routes import collection_plans as cp
from intel_platform.collection import job_runner
from intel_platform.db import jobs
from tests.pg import make_plan, pg_factory_fixture  # noqa: F401  (the pg_factory fixture)


def ev(event: str, ago_seconds: int = 0):
    return SimpleNamespace(
        event=event,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=ago_seconds),
        message="",
    )


@pytest.fixture
def queue_only(monkeypatch):
    """Worker mode: /execute only inserts the job, so nothing runs here."""
    monkeypatch.setattr(job_runner, "worker_mode", lambda: job_runner.WORKER)


async def _job_in(factory, pid, status, *, heartbeat_ago=0):
    async with factory() as db:
        job_id = await jobs.insert_job(db, plan_id=pid, project_id="test-wpw-jobs", kind=jobs.KIND_AGENTIC,
                                       claimed_by="worker:t:1")
        await db.execute(text(
            "UPDATE collection_jobs SET status = :st, heartbeat_at = now() - make_interval(secs => :ago), "
            "finished_at = CASE WHEN :done THEN now() END WHERE id = :id"
        ), {"st": status, "ago": heartbeat_ago, "id": job_id,
            "done": status in (jobs.SUCCEEDED, jobs.FAILED, jobs.CANCELLED)})
        await db.commit()
        return job_id


async def _execute(factory, pid):
    async with factory() as db:
        return await cp.execute_plan_endpoint(str(pid), None, db=db, store=None)


class TestWhatTheGuardPermits:
    """Every state but `running` accepts a new run."""

    @pytest.mark.parametrize("plan_status", ["DRAFT", "ACTIVE", "PAUSED", "COMPLETED", "FAILED"])
    async def test_the_lifecycle_flag_does_not_decide(self, pg_factory, queue_only, plan_status):
        pid = await make_plan(pg_factory, status=plan_status)
        assert (await _execute(pg_factory, pid))["execution_status"] == "queued"

    @pytest.mark.parametrize("job_status,state", [
        ("succeeded", "completed"), ("failed", "failed"), ("cancelled", "cancelled"),
    ])
    async def test_a_finished_run_does_not_block(self, pg_factory, queue_only, job_status, state):
        pid = await make_plan(pg_factory, status="ACTIVE")
        await _job_in(pg_factory, pid, job_status)
        async with pg_factory() as db:
            assert await cp.current_run_state(db, pid) == state
        assert (await _execute(pg_factory, pid))["job_id"]

    async def test_a_stalled_run_does_not_strand_the_plan(self, pg_factory, queue_only):
        """Past the silence threshold the previous attempt is presumed dead;
        refusing forever is how the old guard stranded plans."""
        pid = await make_plan(pg_factory, status="ACTIVE")
        await _job_in(pg_factory, pid, "running", heartbeat_ago=job_runner.stall_seconds() + 60)
        assert (await _execute(pg_factory, pid))["job_id"]

    async def test_a_live_run_blocks(self, pg_factory, queue_only):
        pid = await make_plan(pg_factory, status="ACTIVE")
        await _job_in(pg_factory, pid, "running", heartbeat_ago=1)
        with pytest.raises(HTTPException) as err:
            await _execute(pg_factory, pid)
        assert err.value.status_code == 409

    async def test_archived_is_refused_separately(self, pg_factory, queue_only):
        pid = await make_plan(pg_factory, status="ARCHIVED")
        with pytest.raises(HTTPException) as err:
            await _execute(pg_factory, pid)
        assert err.value.status_code == 400


class TestPerRunCounts:
    """Progress counts describe the current run, not the whole trail.

    Seen live after the guard fix made re-running possible: a re-run of a plan
    reported "2 succeeded, 2 failed" from the previous run before it had
    collected anything.
    """

    def test_a_single_unfinished_run_counts_everything(self):
        events = [ev("plan_started", 60), ev("source_succeeded", 30)]
        assert cp.current_run_events(events) == events

    def test_an_earlier_run_is_excluded(self):
        first = [ev("source_succeeded", 900), ev("source_failed", 880), ev("plan_completed", 870)]
        second = [ev("plan_started", 60), ev("source_succeeded", 30)]
        got = cp.current_run_events(first + second)
        assert got == second
        assert sum(1 for e in got if e.event == "source_failed") == 0

    def test_a_finished_run_reports_its_own_totals(self):
        """When the trail ends on a terminal event, the counts are that run's —
        not zero, and not the previous run's added in."""
        first = [ev("source_succeeded", 900), ev("plan_completed", 890)]
        second = [ev("source_succeeded", 60), ev("source_succeeded", 50), ev("plan_completed", 40)]
        got = cp.current_run_events(first + second)
        assert sum(1 for e in got if e.event == "source_succeeded") == 2

    def test_a_failed_run_is_a_boundary_too(self):
        events = [ev("source_failed", 900), ev("plan_failed", 890), ev("source_succeeded", 30)]
        got = cp.current_run_events(events)
        assert [e.event for e in got] == ["source_succeeded"]


class TestNothingIsAnsweredFromMemory:
    """The in-process registry and the synchronous path's tracker are gone:
    a second API process, or one started after a restart, sees the same state."""

    def test_the_registries_are_gone(self):
        from intel_platform.services import plan_executor

        for name in ("_inflight_runs", "_failed_runs", "register_run", "_execute_locks"):
            assert not hasattr(cp, name), name
        for name in ("_running_executions", "get_execution_status"):
            assert not hasattr(plan_executor, name), name

    async def test_a_fresh_session_sees_a_run_another_process_started(self, pg_factory):
        pid = await make_plan(pg_factory, status="ACTIVE")
        await _job_in(pg_factory, pid, "running", heartbeat_ago=2)
        async with pg_factory() as db:
            assert await cp.current_run_state(db, pid) == "running"
