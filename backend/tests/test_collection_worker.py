"""The collection worker, run for real against Postgres.

`run_worker` is the loop `python -m intel_platform.worker` runs: claim the
oldest queued job (`FOR UPDATE SKIP LOCKED`), stamp `worker_id`, heartbeat it
from a background task while the agentic loop runs, write a terminal status and
a sanitised error. Only the agentic loop itself is faked (it needs a model and
the web); the claim, the heartbeat task, the terminal write and the process
entrypoint all run against the database.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from intel_platform import worker
from intel_platform.collection import agentic, job_runner
from intel_platform.db import jobs
from tests.pg import PROJECT, _engine_url, make_plan, pg_factory_fixture, requires_postgres  # noqa: F401

BACKEND = Path(__file__).resolve().parents[1]


async def _row(factory, job_id):
    async with factory() as db:
        return (await db.execute(select(jobs.CollectionJob).where(jobs.CollectionJob.id == job_id))).scalar_one()


async def _queue(factory, plan_id, project_id=PROJECT):
    async with factory() as db:
        job_id = await jobs.insert_job(db, plan_id=plan_id, project_id=project_id, kind=jobs.KIND_AGENTIC)
        await db.commit()
        return job_id


def _start_worker(factory, **kw):
    stop = asyncio.Event()
    kw.setdefault("worker_id", "worker:test:1")
    kw.setdefault("poll_seconds", 0.05)
    kw.setdefault("heartbeat_seconds", 0.05)
    task = asyncio.create_task(worker.run_worker(stop=stop, db_factory=factory, get_store=lambda: None, **kw))
    return stop, task


async def _until(predicate, timeout=10.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        value = await predicate()
        if value:
            return value
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not reached in time")
        await asyncio.sleep(0.05)


class _Loop:
    """Stand-in for agentic.run_agentic_loop that stays live until told."""

    def __init__(self, result=None, raises=None):
        self.result, self.raises = result, raises
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False
        self.kwargs: dict = {}

    async def __call__(self, **kwargs):
        self.kwargs = kwargs
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        if self.raises:
            raise self.raises
        return self.result


class TestTheWorkerLoop:
    async def test_claims_heartbeats_and_records_success(self, pg_factory, monkeypatch):
        pid = await make_plan(pg_factory, routing_rules={"source_limit": 3, "max_results_per_source": 7})
        job_id = await _queue(pg_factory, pid)
        loop = _Loop()
        monkeypatch.setattr(agentic, "run_agentic_loop", loop)
        _stop, task = _start_worker(pg_factory, once=True)

        await asyncio.wait_for(loop.started.wait(), 10)
        claimed = await _row(pg_factory, job_id)
        assert claimed.status == jobs.RUNNING and claimed.worker_id == "worker:test:1"
        assert claimed.started_at is not None and claimed.heartbeat_at is not None

        async def beat_advanced():
            return (await _row(pg_factory, job_id)).heartbeat_at > claimed.heartbeat_at
        await _until(beat_advanced)

        loop.release.set()
        assert await asyncio.wait_for(task, 10) == 1
        done = await _row(pg_factory, job_id)
        assert done.status == jobs.SUCCEEDED and done.finished_at is not None and done.error is None
        # The run's parameters reached the worker through the plan's routing rules.
        assert loop.kwargs["plan_id"] == pid
        assert loop.kwargs["source_limit"] == 3 and loop.kwargs["max_results_per_source"] == 7

    async def test_a_recorded_failure_is_the_jobs_error(self, pg_factory, monkeypatch):
        pid = await make_plan(pg_factory)
        job_id = await _queue(pg_factory, pid)
        loop = _Loop(result="No LLM provider available (RuntimeError); see server logs")
        loop.release.set()
        monkeypatch.setattr(agentic, "run_agentic_loop", loop)
        _stop, task = _start_worker(pg_factory, once=True)
        await asyncio.wait_for(task, 10)
        row = await _row(pg_factory, job_id)
        assert row.status == jobs.FAILED and row.error == loop.result

    async def test_an_escaped_exception_is_sanitised(self, pg_factory, monkeypatch):
        """The error column is shown to analysts: it names the exception type,
        never its text, which carries internals."""
        pid = await make_plan(pg_factory)
        job_id = await _queue(pg_factory, pid)
        loop = _Loop(raises=RuntimeError("password=hunter2 at /srv/secret/path"))
        loop.release.set()
        monkeypatch.setattr(agentic, "run_agentic_loop", loop)
        _stop, task = _start_worker(pg_factory, once=True)
        await asyncio.wait_for(task, 10)
        row = await _row(pg_factory, job_id)
        assert row.status == jobs.FAILED
        assert "RuntimeError" in row.error and "hunter2" not in row.error and "/srv" not in row.error

    async def test_stopping_the_worker_fails_the_job_in_hand(self, pg_factory, monkeypatch):
        """SIGTERM must not leave the plan `running` for the stall window."""
        pid = await make_plan(pg_factory)
        job_id = await _queue(pg_factory, pid)
        loop = _Loop()
        monkeypatch.setattr(agentic, "run_agentic_loop", loop)
        stop, task = _start_worker(pg_factory)
        await asyncio.wait_for(loop.started.wait(), 10)
        stop.set()
        await asyncio.wait_for(task, 10)
        assert loop.cancelled, "the run was not stopped"
        row = await _row(pg_factory, job_id)
        assert row.status == jobs.FAILED and "worker stopped" in row.error
        assert row.finished_at is not None

    async def test_a_superseded_job_stops_its_run(self, pg_factory, monkeypatch):
        """Closed as stalled while its worker was merely slow: the next
        heartbeat finds the job gone, and the run stops instead of collecting
        alongside its replacement. The closing reason is left as written."""
        pid = await make_plan(pg_factory)
        job_id = await _queue(pg_factory, pid)
        loop = _Loop()
        monkeypatch.setattr(agentic, "run_agentic_loop", loop)
        _stop, task = _start_worker(pg_factory, once=True)
        await asyncio.wait_for(loop.started.wait(), 10)
        async with pg_factory() as db:
            await jobs.close_unfinished(db, pid, "Stalled: superseded by a new run")
            await db.commit()
        await asyncio.wait_for(task, 10)
        assert loop.cancelled
        row = await _row(pg_factory, job_id)
        assert row.status == jobs.FAILED and row.error == "Stalled: superseded by a new run"

    async def test_a_job_for_a_deleted_plan_fails_cleanly(self, pg_factory, monkeypatch):
        job_id = await _queue(pg_factory, uuid.uuid4())
        monkeypatch.setattr(agentic, "run_agentic_loop", _Loop())
        _stop, task = _start_worker(pg_factory, once=True)
        await asyncio.wait_for(task, 10)
        row = await _row(pg_factory, job_id)
        assert row.status == jobs.FAILED and row.error == "The plan no longer exists"

    async def test_it_waits_for_work_and_takes_jobs_in_order(self, pg_factory, monkeypatch):
        ran: list = []

        async def loop(**kw):
            ran.append(kw["plan_id"])

        monkeypatch.setattr(agentic, "run_agentic_loop", loop)
        stop, task = _start_worker(pg_factory)
        await asyncio.sleep(0.2)  # idle polls
        first, second = await make_plan(pg_factory), await make_plan(pg_factory)
        await _queue(pg_factory, first)
        await _queue(pg_factory, second)

        async def both_ran():
            return len(ran) == 2
        await _until(both_ran)
        stop.set()
        assert await asyncio.wait_for(task, 10) == 2
        assert ran == [first, second]

    async def test_an_unreachable_database_is_retried_not_fatal(self):
        attempts = []

        def broken_factory():
            attempts.append(1)
            raise OSError("connection refused")

        stop = asyncio.Event()
        task = asyncio.create_task(worker.run_worker(stop=stop, db_factory=broken_factory, poll_seconds=0.01))
        await asyncio.sleep(0.3)
        stop.set()
        assert await asyncio.wait_for(task, 5) == 0
        assert len(attempts) >= 2


@requires_postgres
class TestTheEntrypoint:
    async def test_python_dash_m_runs_a_job_and_exits(self, pg_factory):
        """`python -m intel_platform.worker --once` as a real process: it claims
        the queued job, runs it to a terminal status and exits 0. The plan does
        not exist, so no model, crawler or graph is needed to finish it."""
        job_id = await _queue(pg_factory, uuid.uuid4())
        env = dict(os.environ)
        env["POSTGRES_URL"] = _engine_url().render_as_string(hide_password=False)
        proc = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "intel_platform.worker", "--once", "--poll-seconds", "0.1"],
            cwd=BACKEND, env=env, capture_output=True, text=True, timeout=180,
        )
        assert proc.returncode == 0, proc.stderr[-2000:]
        assert "claimed job" in proc.stderr
        row = await _row(pg_factory, job_id)
        assert row.status == jobs.FAILED and row.error == "The plan no longer exists"
        assert row.worker_id.startswith("worker:")


def test_worker_ids_are_unique_within_a_process():
    assert worker.new_worker_id() != worker.new_worker_id()
    assert job_runner.process_worker_id("api").startswith("api:")
