"""Whether a plan's run is in flight, failed, or startable — answered from the job table.

R-3: a run that crashed read "running" for the stall window, then "stalled",
never "failed", and `/execute` answered 409 throughout. The run now writes its
own terminal status to its `collection_jobs` row, so a crash reads `failed` as
soon as the run has ended.

R-4: the execute guard was check-then-act across awaits, and two POSTs both
saw "idle" and both started a loop. The route now locks the plan row for the
whole check-and-insert, across every API process, and the table allows one
live job per plan.

Also here: `/execution-status` agreeing with the guard, a run without
`source_limit` not inheriting the previous run's, a PIR-linked plan with no
automated sources still running the requirement loop, the cancel endpoint, and
the worker/inline split of `/execute`.

Everything below runs the routes against a real Postgres, with the agentic
loop replaced (it needs a model and the web).
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from intel_platform.api.routes import collection_plans as cp
from intel_platform.collection import agentic, job_runner
from intel_platform.db import jobs
from intel_platform.db.models import CollectionActivity, CollectionPlan
from tests.pg import make_plan, pg_factory_fixture  # noqa: F401  (the pg_factory fixture)


@pytest.fixture(autouse=True)
async def _no_leaked_runs():
    yield
    for task in list(job_runner._background):
        task.cancel()
    if job_runner._background:
        await asyncio.gather(*job_runner._background, return_exceptions=True)


@pytest.fixture
async def fake_loop(monkeypatch, pg_factory):
    """Inline mode, with an agentic loop that stays live until released.

    `outcome` is what the loop returns (a failure reason, or None); `raises`
    makes it crash instead. Every run is released and awaited before the
    database fixture removes the rows it writes to.
    """
    from intel_platform.db import engine

    state = SimpleNamespace(calls=[], release=asyncio.Event(), outcome=None, raises=None)

    async def _loop(**kwargs):
        state.calls.append(kwargs)
        await state.release.wait()
        if state.raises:
            raise state.raises
        return state.outcome

    monkeypatch.setattr(agentic, "run_agentic_loop", _loop)
    monkeypatch.setattr(engine, "get_session_factory", lambda: pg_factory)
    monkeypatch.setattr(job_runner, "worker_mode", lambda: job_runner.INLINE)
    yield state
    state.release.set()
    await asyncio.wait_for(asyncio.gather(*list(job_runner._background), return_exceptions=True), 10)


async def _execute(factory, pid, body=None):
    async with factory() as db:
        return await cp.execute_plan_endpoint(str(pid), body, db=db, store=None)


async def _state(factory, pid):
    async with factory() as db:
        return await cp.current_run_state(db, pid)


async def _status(factory, pid):
    async with factory() as db:
        return await cp.get_execution_status(str(pid), db=db)


async def _cancel(factory, pid):
    async with factory() as db:
        return await cp.cancel_plan_run(str(pid), db=db)


async def _job(factory, job_id):
    async with factory() as db:
        return (await db.execute(
            select(jobs.CollectionJob).where(jobs.CollectionJob.id == uuid.UUID(str(job_id)))
        )).scalar_one()


async def _plan_row(factory, pid):
    async with factory() as db:
        return await db.get(CollectionPlan, pid)


async def _finish_inline():
    await asyncio.gather(*list(job_runner._background), return_exceptions=True)


async def _until_called(state, n: int = 1, timeout: float = 10.0) -> None:
    """Wait for the inline run to reach the loop (it loads the job and the plan first)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while len(state.calls) < n:
        assert loop.time() < deadline, f"the loop was called {len(state.calls)} time(s), expected {n}"
        await asyncio.sleep(0.02)


async def _settle() -> None:
    """Long enough for an inline run that was wrongly started to reach the loop."""
    await asyncio.sleep(0.5)


class TestAFinishedRunReadsAsItEnded:
    async def test_a_crashed_run_is_failed_as_soon_as_it_ends(self, fake_loop, pg_factory):
        pid = await make_plan(pg_factory)
        body = await _execute(pg_factory, pid)
        assert await _state(pg_factory, pid) == "running"
        fake_loop.raises = RuntimeError("collector exploded")
        fake_loop.release.set()
        await _finish_inline()
        assert await _state(pg_factory, pid) == "failed"
        job = await _job(pg_factory, body["job_id"])
        assert job.status == jobs.FAILED and "RuntimeError" in job.error and "exploded" not in job.error

    async def test_a_recorded_failure_is_failed(self, fake_loop, pg_factory):
        pid = await make_plan(pg_factory)
        await _execute(pg_factory, pid)
        fake_loop.outcome = "Collection run failed (KeyError); see server logs"
        fake_loop.release.set()
        await _finish_inline()
        assert await _state(pg_factory, pid) == "failed"
        status = await _status(pg_factory, pid)
        assert status["status"] == "failed" and status["error"] == fake_loop.outcome

    async def test_a_cancelled_task_is_not_running(self, fake_loop, pg_factory):
        pid = await make_plan(pg_factory)
        await _execute(pg_factory, pid)
        await _until_called(fake_loop)
        for task in list(job_runner._background):
            task.cancel()
        await _finish_inline()
        assert await _state(pg_factory, pid) == "failed"

    async def test_a_clean_finish_is_completed_and_frees_the_plan(self, fake_loop, pg_factory):
        pid = await make_plan(pg_factory)
        first = await _execute(pg_factory, pid)
        fake_loop.release.set()
        await _finish_inline()
        assert await _state(pg_factory, pid) == "completed"
        assert (await _job(pg_factory, first["job_id"])).status == jobs.SUCCEEDED

        fake_loop.release = asyncio.Event()
        second = await _execute(pg_factory, pid)
        assert second["job_id"] != first["job_id"]
        assert await _state(pg_factory, pid) == "running"
        fake_loop.release.set()


class TestConcurrentExecute:
    async def test_two_posts_start_one_run(self, fake_loop, pg_factory):
        pid = await make_plan(pg_factory)
        results = await asyncio.gather(
            _execute(pg_factory, pid), _execute(pg_factory, pid), return_exceptions=True,
        )
        await _until_called(fake_loop)
        await _settle()
        assert len(fake_loop.calls) == 1, "only one collection loop may start"
        refused = [r for r in results if isinstance(r, HTTPException)]
        assert [r.status_code for r in refused] == [409]
        async with pg_factory() as db:
            rows = (await db.execute(select(jobs.CollectionJob).where(jobs.CollectionJob.plan_id == pid))).all()
        assert len(rows) == 1
        fake_loop.release.set()


class TestExecuteModes:
    async def test_inline_claims_the_job_in_this_process(self, fake_loop, pg_factory):
        pid = await make_plan(pg_factory)
        body = await _execute(pg_factory, pid)
        assert body["execution_status"] == "started" and body["worker_mode"] == "inline"
        job = await _job(pg_factory, body["job_id"])
        assert job.status == jobs.RUNNING and job.worker_id.startswith("api:") and job.kind == jobs.KIND_AGENTIC
        await _until_called(fake_loop)
        assert fake_loop.calls[0]["plan_id"] == pid
        fake_loop.release.set()

    async def test_worker_mode_only_enqueues(self, fake_loop, pg_factory, monkeypatch):
        monkeypatch.setattr(job_runner, "worker_mode", lambda: job_runner.WORKER)
        pid = await make_plan(pg_factory)
        body = await _execute(pg_factory, pid)
        await _settle()
        assert fake_loop.calls == [], "worker mode must not run the loop in the API process"
        assert body["execution_status"] == "queued" and "worker" in body["message"]
        job = await _job(pg_factory, body["job_id"])
        assert job.status == jobs.QUEUED and job.worker_id is None
        status = await _status(pg_factory, pid)
        assert status["status"] == "running" and status["job_status"] == "queued"
        assert status["message"] == "Queued; waiting for a collection worker"

    async def test_archived_plans_are_refused(self, fake_loop, pg_factory):
        pid = await make_plan(pg_factory, status="ARCHIVED")
        with pytest.raises(HTTPException) as err:
            await _execute(pg_factory, pid)
        assert err.value.status_code == 400

    async def test_an_unknown_plan_is_404(self, fake_loop, pg_factory):
        with pytest.raises(HTTPException) as err:
            await _execute(pg_factory, uuid.uuid4())
        assert err.value.status_code == 404


class TestExecutionStatusAgreesWithTheGuard:
    async def test_a_live_run_with_no_trail_yet_is_running(self, fake_loop, pg_factory):
        pid = await make_plan(pg_factory)
        await _execute(pg_factory, pid)
        body = await _status(pg_factory, pid)
        assert body["status"] == "running" and body["message"] == "Run starting"
        assert body["job_status"] == "running" and body["seconds_since_heartbeat"] is not None
        assert "worker_id" not in body, "host names and pids stay server-side"
        fake_loop.release.set()

    async def test_a_live_rerun_does_not_report_the_previous_runs_completion(self, fake_loop, pg_factory):
        pid = await make_plan(pg_factory)
        async with pg_factory() as db:
            db.add(CollectionActivity(plan_id=pid, event="source_succeeded", message="old",
                                      created_at=datetime.now(timezone.utc) - timedelta(seconds=90)))
            db.add(CollectionActivity(plan_id=pid, event="plan_completed", message="old run done",
                                      created_at=datetime.now(timezone.utc) - timedelta(seconds=80)))
            await db.commit()
        await _execute(pg_factory, pid)
        body = await _status(pg_factory, pid)
        assert body["status"] == "running"
        assert body["sources_succeeded"] == 0
        assert body["message"] == "Run starting"
        fake_loop.release.set()

    async def test_no_job_is_idle(self, pg_factory):
        pid = await make_plan(pg_factory)
        body = await _status(pg_factory, pid)
        assert body["status"] == "idle" and body["job_id"] is None


class TestExecuteRecordsOnlyThisRunsBudget:
    async def test_no_limit_clears_the_previous_runs(self, fake_loop, pg_factory):
        pid = await make_plan(pg_factory, routing_rules={"extract_entities": True, "source_limit": 3})
        await _execute(pg_factory, pid)
        rules = (await _plan_row(pg_factory, pid)).routing_rules
        assert "source_limit" not in rules
        assert rules["extract_entities"] is True
        fake_loop.release.set()

    async def test_a_new_limit_replaces_it_and_reaches_the_run(self, fake_loop, pg_factory):
        pid = await make_plan(pg_factory, routing_rules={"source_limit": 3})
        await _execute(pg_factory, pid, cp.ExecuteRequest(source_limit=5, max_results_per_source=40))
        rules = (await _plan_row(pg_factory, pid)).routing_rules
        assert rules["source_limit"] == 5
        assert rules["max_results_per_source"] == 25, "clamped to 1..25"
        await _until_called(fake_loop)
        assert fake_loop.calls[0]["source_limit"] == 5
        assert fake_loop.calls[0]["max_results_per_source"] == 25
        fake_loop.release.set()


class TestNoAutomatedSources:
    async def test_a_pir_linked_plan_still_runs_the_requirement_loop(self, fake_loop, pg_factory):
        pid = await make_plan(pg_factory, sources=0, pir_id=uuid.uuid4())
        body = await _execute(pg_factory, pid)
        await _until_called(fake_loop)
        assert body["execution_status"] == "started"
        assert (await _job(pg_factory, body["job_id"])).kind == jobs.KIND_REQUIREMENTS
        fake_loop.release.set()

    async def test_without_a_pir_nothing_is_launched(self, fake_loop, pg_factory):
        pid = await make_plan(pg_factory, sources=0)
        body = await _execute(pg_factory, pid)
        await _settle()
        assert fake_loop.calls == []
        assert body["execution_status"] == "no_executable_sources" and body["job_id"] is None
        assert (await _plan_row(pg_factory, pid)).status == "ACTIVE"


class TestCancel:
    async def test_a_running_job_stops_before_its_next_source(self, fake_loop, pg_factory):
        from intel_platform.services.plan_executor import plan_should_stop

        pid = await make_plan(pg_factory)
        body = await _execute(pg_factory, pid)
        async with pg_factory() as db:
            assert await plan_should_stop(db, pid) is False

        cancelled = await _cancel(pg_factory, pid)
        assert cancelled == {
            "plan_id": str(pid), "job_id": body["job_id"], "status": "cancelled",
            "previous_status": "running", "stopping": True,
            "message": "Cancelled; the run stops before its next source",
        }
        async with pg_factory() as db:
            assert await plan_should_stop(db, pid) is True
        # Still stopping: a new run now would collect alongside it.
        assert await _state(pg_factory, pid) == "running"
        with pytest.raises(HTTPException) as again:
            await _cancel(pg_factory, pid)
        assert again.value.status_code == 409 and "already stopping" in again.value.detail
        status = await _status(pg_factory, pid)
        assert status["status"] == "running" and status["job_status"] == "cancelled"
        assert status["last_event"] == "run_cancelled"

        fake_loop.release.set()
        await _finish_inline()
        job = await _job(pg_factory, body["job_id"])
        assert job.status == jobs.CANCELLED and job.finished_at is not None
        assert await _state(pg_factory, pid) == "cancelled"
        fake_loop.release = asyncio.Event()
        await _execute(pg_factory, pid)  # and the plan can run again
        fake_loop.release.set()

    async def test_a_queued_job_is_finished_at_once(self, fake_loop, pg_factory, monkeypatch):
        monkeypatch.setattr(job_runner, "worker_mode", lambda: job_runner.WORKER)
        pid = await make_plan(pg_factory)
        body = await _execute(pg_factory, pid)
        cancelled = await _cancel(pg_factory, pid)
        assert cancelled["stopping"] is False and cancelled["previous_status"] == "queued"
        assert await _state(pg_factory, pid) == "cancelled"
        async with pg_factory() as db:
            assert await jobs.claim_next(db, "worker:test:9") is None, "a cancelled job must not be claimed"
        assert (await _job(pg_factory, body["job_id"])).finished_at is not None

    async def test_nothing_in_flight_is_409(self, pg_factory):
        pid = await make_plan(pg_factory)
        with pytest.raises(HTTPException) as err:
            await _cancel(pg_factory, pid)
        assert err.value.status_code == 409

    async def test_an_unknown_plan_is_404(self, pg_factory):
        with pytest.raises(HTTPException) as err:
            await _cancel(pg_factory, uuid.uuid4())
        assert err.value.status_code == 404

    async def test_the_cancel_is_in_the_trail(self, fake_loop, pg_factory, monkeypatch):
        monkeypatch.setattr(job_runner, "worker_mode", lambda: job_runner.WORKER)
        pid = await make_plan(pg_factory)
        await _execute(pg_factory, pid)
        await _cancel(pg_factory, pid)
        async with pg_factory() as db:
            events = (await db.execute(
                select(CollectionActivity.event).where(CollectionActivity.plan_id == pid)
            )).scalars().all()
        assert "run_cancelled" in events


# ---------------------------------------------------------------------------
# Activity paging (no database: the statement is what is under test)
# ---------------------------------------------------------------------------

def _ev(event: str, ago: int = 0):
    return SimpleNamespace(
        event=event, message=event,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=ago),
    )


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _StmtDb:
    """Records the statement it is asked to run and returns the given rows."""

    def __init__(self, rows):
        self.rows = rows
        self.stmt = None

    async def execute(self, stmt):
        self.stmt = stmt
        return _Result(self.rows)


def _row(event: str, ago: int):
    ev = _ev(event, ago)
    ev.id = uuid.uuid4()
    ev.plan_id = uuid.uuid4()
    ev.source_id = None
    return ev


class TestActivityIsPaged:
    """Low -> R: the UI polls the trail every 3 s and every poll loaded all of
    it — thousands of rows on a long-running plan. A malformed `since` was
    ignored, which also meant "load all of it"."""

    async def test_without_since_it_is_the_latest_page_oldest_first(self):
        db = _StmtDb([_row("e3", 1), _row("e2", 2)])        # the DESC query's order
        out = await cp.get_activity(str(uuid.uuid4()), since=None, limit=2, db=db)
        assert [o["event"] for o in out] == ["e2", "e3"]
        compiled = db.stmt.compile()
        assert " DESC" in str(compiled) and 2 in compiled.params.values()

    async def test_with_since_it_pages_forward(self):
        db = _StmtDb([_row("e4", 2), _row("e5", 1)])
        since = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        out = await cp.get_activity(str(uuid.uuid4()), since=since, limit=50, db=db)
        assert [o["event"] for o in out] == ["e4", "e5"]
        compiled = db.stmt.compile()
        assert " ASC" in str(compiled) and 50 in compiled.params.values()

    async def test_an_offset_whose_plus_was_decoded_to_a_space_is_accepted(self):
        db = _StmtDb([])
        await cp.get_activity(str(uuid.uuid4()), since="2026-09-30T12:00:00.123456 00:00", limit=5, db=db)
        assert db.stmt is not None

    async def test_a_malformed_since_is_rejected_not_ignored(self):
        with pytest.raises(HTTPException) as err:
            await cp.get_activity(str(uuid.uuid4()), since="yesterday", limit=50, db=_StmtDb([]))
        assert err.value.status_code == 400
