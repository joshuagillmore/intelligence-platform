"""R-12: PAUSED and ARCHIVED are read by the run, and the end of a run does not undo them.

The loop never read the plan's status, so Pause did nothing; completion then
wrote COMPLETED over PAUSED or ARCHIVED (un-archiving the plan), and a run that
failed outright also ended COMPLETED.

`plan_should_stop(db, plan_id)` is the check the collection loops call between
sources (the agentic loop in `collection/agentic.py` calls it too).
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from intel_platform.services import plan_executor as pe


class _Scalar:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _Db:
    """Session stand-in. `statuses` is what successive status reads return —
    the analyst's hand on the Pause button, between sources."""

    def __init__(self, plan=None, statuses=()):
        self.plan = plan
        self.statuses = list(statuses)
        self.commits = 0

    async def get(self, _model, _pid):
        return self.plan

    async def execute(self, _stmt):
        if self.statuses:
            value = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        else:
            value = self.plan.status if self.plan else None
        return _Scalar(value)

    async def commit(self):
        self.commits += 1

    def add(self, _obj):
        pass

    async def flush(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class TestPlanShouldStop:
    @pytest.mark.parametrize("status,expected", [
        ("PAUSED", True), ("ARCHIVED", True),
        ("ACTIVE", False), ("DRAFT", False), ("COMPLETED", False),
    ])
    async def test_by_status(self, status, expected):
        assert await pe.plan_should_stop(_Db(statuses=[status]), uuid.uuid4()) is expected

    async def test_a_deleted_plan_stops_the_run(self):
        assert await pe.plan_should_stop(_Db(statuses=[None]), uuid.uuid4()) is True

    async def test_accepts_a_string_id(self):
        assert await pe.plan_should_stop(_Db(statuses=["PAUSED"]), str(uuid.uuid4())) is True


class TestFinalStatus:
    @pytest.mark.parametrize("current", ["PAUSED", "ARCHIVED"])
    def test_a_hand_set_status_survives_the_end_of_a_run(self, current):
        assert pe.final_plan_status(current, failed=False) == current
        assert pe.final_plan_status(current, failed=True) == current

    def test_success_completes(self):
        assert pe.final_plan_status("ACTIVE", failed=False) == "COMPLETED"

    def test_failure_is_its_own_terminal_state(self):
        assert pe.final_plan_status("ACTIVE", failed=True) == pe.PLAN_FAILED == "FAILED"


def _plan(n_sources=2, status="ACTIVE"):
    return SimpleNamespace(
        id=uuid.uuid4(), project_id="p1", status=status, updated_at=None,
        sources=[
            SimpleNamespace(id=uuid.uuid4(), name=f"s{i}", enabled=True,
                            source_type="web_scrape", config={"url": f"https://e{i}.example"})
            for i in range(n_sources)
        ],
    )


@pytest.fixture
def run(monkeypatch):
    """Drive execute_plan with a scripted source outcome and session."""
    collected: list[str] = []

    def _go(plan, statuses=(), outcomes=None, raise_on=None):
        outcomes = outcomes or {}

        async def _fake_source(source, plan_, db, store, mode):
            if raise_on == source.name:
                raise RuntimeError("store went away")
            collected.append(source.name)
            return {"source_id": str(source.id), "source_name": source.name,
                    "result": outcomes.get(source.name, "success")}

        monkeypatch.setattr(pe, "_execute_source", _fake_source)
        db = _Db(plan, statuses)
        pe._running_executions.pop(str(plan.id), None)
        return db, pe.execute_plan(str(plan.id), lambda: db, store=None)

    _go.collected = collected
    return _go


class TestExecutePlanHonoursTheStatus:
    async def test_pause_between_sources_stops_the_run(self, run):
        plan = _plan(3)
        db, coro = run(plan, statuses=["ACTIVE", "PAUSED"])
        status = await coro
        assert run.collected == ["s0"]
        assert plan.status == "PAUSED"
        assert status.get("stopped_on_status") == "PAUSED"

    async def test_archive_during_the_run_is_not_undone(self, run):
        plan = _plan(2)
        db, coro = run(plan, statuses=["ACTIVE", "ACTIVE", "ARCHIVED"])
        await coro
        assert plan.status == "ARCHIVED"

    async def test_a_clean_run_completes(self, run):
        plan = _plan(2)
        _db, coro = run(plan, statuses=["ACTIVE"])
        await coro
        assert plan.status == "COMPLETED"

    async def test_every_source_failing_is_failed_not_completed(self, run):
        plan = _plan(2)
        _db, coro = run(plan, statuses=["ACTIVE"], outcomes={"s0": "failure", "s1": "failure"})
        await coro
        assert plan.status == "FAILED"

    async def test_a_run_that_raises_is_failed(self, monkeypatch):
        plan = _plan(2)

        async def _boom(*a, **k):
            raise RuntimeError("store went away")

        monkeypatch.setattr(pe, "_execute_source", _boom)
        status = await pe.execute_plan(str(plan.id), lambda: _Db(plan, ["ACTIVE"]), store=None)
        assert status["status"] == "error"
        assert plan.status == "FAILED"
