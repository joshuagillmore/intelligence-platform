"""Whether a plan's run is in flight, failed, or startable — answered by looking.

R-3: `register_run`'s done-callback discarded `task.exception()`, so a run that
crashed read "running" for the ten-minute stall window, then "stalled", never
"failed", and `/execute` answered 409 throughout.

R-4: the execute guard was check-then-act across awaits. Two POSTs both saw
"idle" and both started a loop, and the first task's callback then popped the
second task's registry entry, so the live run became invisible.

Also here: `/execution-status` agreeing with the guard (it skipped the live-task
check), a run without `source_limit` not inheriting the previous run's, and a
PIR-linked plan with no automated sources still running the requirement loop.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from intel_platform.api.routes import collection_plans as cp


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    monkeypatch.setattr(cp, "_PROCESS_STARTED_AT", datetime.now(timezone.utc) - timedelta(days=1))
    yield
    for task in list(cp._inflight_runs.values()):
        task.cancel()
    cp._inflight_runs.clear()
    getattr(cp, "_failed_runs", {}).clear()


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

    def first(self):
        return self._rows[-1] if self._rows else None

    def all(self):
        return list(self._rows)


class _Db:
    """Async session stand-in. Every call is a real await point, as a database
    round trip is — which is what lets two requests interleave."""

    def __init__(self, plan=None, events=()):
        self.plan = plan
        self.events = list(events)
        self.commits = 0

    async def get(self, _model, pid):
        await asyncio.sleep(0)
        return self.plan if self.plan is not None and pid == self.plan.id else None

    async def execute(self, _stmt):
        await asyncio.sleep(0)
        return _Result(self.events)

    async def commit(self):
        self.commits += 1
        await asyncio.sleep(0)

    async def refresh(self, _obj):
        await asyncio.sleep(0)


def _source(**over):
    base = dict(
        id=uuid.uuid4(), plan_id=None, name="src", source_type="web_scrape",
        config={"url": "https://example.com"}, collection_status="pending",
        schedule_cron="", enabled=True, last_success_at=None, last_failure_at=None,
        last_error="", total_records_acquired=0, acquisition_count=0,
        next_run_at=None, created_at=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _plan(sources=None, pir_id=None, routing_rules=None, status="DRAFT"):
    return SimpleNamespace(
        id=uuid.uuid4(), project_id="p1", name="plan", description="", requirement="",
        pir="", pir_id=pir_id, refined_pir="", status=status,
        routing_rules=routing_rules if routing_rules is not None else {"extract_entities": True},
        created_by="t", assigned_to="", schedule_cron="", next_run_at=None,
        created_at=None, updated_at=None,
        sources=[_source()] if sources is None else sources,
    )


@pytest.fixture
def fake_loop(monkeypatch):
    """Replace the agentic loop with one that stays live until released."""
    from intel_platform.collection import agentic
    from intel_platform.db import engine

    calls: list[dict] = []
    release = asyncio.Event()

    async def _loop(**kwargs):
        calls.append(kwargs)
        await release.wait()

    monkeypatch.setattr(agentic, "run_agentic_loop", _loop)
    monkeypatch.setattr(engine, "get_session_factory", lambda: None)
    return SimpleNamespace(calls=calls, release=release)


async def _settle():
    for _ in range(3):
        await asyncio.sleep(0)


class TestAFailedRunReadsFailed:
    async def test_a_crashed_run_is_failed_immediately(self, caplog):
        pid = uuid.uuid4()

        async def _boom():
            raise RuntimeError("collector exploded")

        task = asyncio.create_task(_boom())
        cp.register_run(pid, task)
        with caplog.at_level(logging.ERROR), contextlib.suppress(RuntimeError):
            await task
            await _settle()
        # The trail looks alive — a crash leaves no terminal event behind it.
        assert await cp.current_run_state(_Db(events=[_ev("source_collecting", 5)]), pid) == "failed"
        assert any("collector exploded" in (r.exc_text or "") or r.exc_info for r in caplog.records), \
            "the exception must be logged, not discarded"

    async def test_a_cancelled_run_is_not_running(self):
        pid = uuid.uuid4()
        task = asyncio.create_task(asyncio.Event().wait())
        cp.register_run(pid, task)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await _settle()
        assert await cp.current_run_state(_Db(events=[_ev("source_collecting", 5)]), pid) == "failed"

    async def test_a_clean_finish_records_no_failure(self):
        pid = uuid.uuid4()

        async def _ok():
            return None

        task = asyncio.create_task(_ok())
        cp.register_run(pid, task)
        await task
        await _settle()
        assert await cp.current_run_state(_Db(events=[_ev("plan_completed", 5)]), pid) == "completed"

    async def test_a_new_run_clears_the_previous_failure(self):
        pid = uuid.uuid4()

        async def _boom():
            raise RuntimeError("x")

        first = asyncio.create_task(_boom())
        cp.register_run(pid, first)
        with contextlib.suppress(RuntimeError):
            await first
        await _settle()
        second = asyncio.create_task(asyncio.Event().wait())
        cp.register_run(pid, second)
        assert await cp.current_run_state(_Db(), pid) == "running"


class TestRegistryBelongsToTheLatestRun:
    async def test_an_earlier_runs_callback_does_not_unregister_a_later_one(self):
        pid = uuid.uuid4()
        done_first = asyncio.Event()
        first = asyncio.create_task(done_first.wait())
        cp.register_run(pid, first)
        second = asyncio.create_task(asyncio.Event().wait())
        cp.register_run(pid, second)

        done_first.set()
        await first
        await _settle()
        assert cp._inflight_runs.get(pid) is second
        assert cp.has_live_run(pid)


class TestConcurrentExecute:
    async def test_two_posts_start_one_run(self, fake_loop):
        plan = _plan()
        results = await asyncio.gather(
            cp.execute_plan_endpoint(str(plan.id), None, db=_Db(plan), store=None),
            cp.execute_plan_endpoint(str(plan.id), None, db=_Db(plan), store=None),
            return_exceptions=True,
        )
        await _settle()
        assert len(fake_loop.calls) == 1, "only one collection loop may start"
        refused = [r for r in results if isinstance(r, HTTPException)]
        assert [r.status_code for r in refused] == [409]
        fake_loop.release.set()


class TestExecutionStatusAgreesWithTheGuard:
    async def test_a_live_run_with_no_trail_yet_is_running(self):
        pid = uuid.uuid4()
        cp.register_run(pid, asyncio.create_task(asyncio.Event().wait()))
        body = await cp.get_execution_status(str(pid), db=_Db())
        assert body["status"] == "running"

    async def test_a_live_rerun_does_not_report_the_previous_runs_completion(self):
        pid = uuid.uuid4()
        cp.register_run(pid, asyncio.create_task(asyncio.Event().wait()))
        trail = [_ev("source_succeeded", 90), _ev("plan_completed", 80)]
        body = await cp.get_execution_status(str(pid), db=_Db(events=trail))
        assert body["status"] == "running"
        assert body["sources_succeeded"] == 0

    async def test_a_crashed_run_reports_failed(self):
        pid = uuid.uuid4()

        async def _boom():
            raise RuntimeError("x")

        task = asyncio.create_task(_boom())
        cp.register_run(pid, task)
        with contextlib.suppress(RuntimeError):
            await task
        await _settle()
        body = await cp.get_execution_status(str(pid), db=_Db(events=[_ev("source_collecting", 5)]))
        assert body["status"] == "failed"


class TestExecuteRecordsOnlyThisRunsBudget:
    async def test_no_limit_clears_the_previous_runs(self, fake_loop):
        plan = _plan(routing_rules={"extract_entities": True, "source_limit": 3})
        await cp.execute_plan_endpoint(str(plan.id), None, db=_Db(plan), store=None)
        assert "source_limit" not in plan.routing_rules
        assert plan.routing_rules["extract_entities"] is True
        fake_loop.release.set()

    async def test_a_new_limit_replaces_it(self, fake_loop):
        plan = _plan(routing_rules={"source_limit": 3})
        await cp.execute_plan_endpoint(
            str(plan.id), cp.ExecuteRequest(source_limit=5), db=_Db(plan), store=None,
        )
        assert plan.routing_rules["source_limit"] == 5
        fake_loop.release.set()


class TestNoAutomatedSources:
    async def test_a_pir_linked_plan_still_runs_the_requirement_loop(self, fake_loop):
        plan = _plan(sources=[], pir_id=uuid.uuid4())
        body = await cp.execute_plan_endpoint(str(plan.id), None, db=_Db(plan), store=None)
        await _settle()
        assert len(fake_loop.calls) == 1
        assert body["execution_status"] == "started"
        fake_loop.release.set()

    async def test_without_a_pir_nothing_is_launched(self, fake_loop):
        plan = _plan(sources=[])
        body = await cp.execute_plan_endpoint(str(plan.id), None, db=_Db(plan), store=None)
        await _settle()
        assert fake_loop.calls == []
        assert body["execution_status"] == "no_executable_sources"
