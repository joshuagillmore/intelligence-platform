"""Execution is refused for a run in flight, not for a status flag.

The old guard allowed DRAFT and PAUSED only. Two consequences, both seen live:

  * "Activate" — the button an analyst naturally presses before running
    something — sets ACTIVE, which made the plan unrunnable. Execute returned
    400 "Cannot execute plan in ACTIVE status", and the only recovery was to
    press Pause, which nobody would guess.
  * Execution itself sets ACTIVE, so any plan whose run died was stranded
    permanently unexecutable.

`plan.status` is a lifecycle flag an analyst edits by hand; the activity trail
is evidence. The guard now uses the trail, shared with the endpoint that reports
progress so the two cannot disagree.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from intel_platform.api.routes.collection_plans import (
    _STALL_AFTER_SECONDS,
    run_state_from_events,
)


@pytest.fixture(autouse=True)
def _process_started_long_ago(monkeypatch):
    """Pin process start far enough back that the "died with the previous
    process" rule does not decide these outcomes.

    Without this the tests below would pass for the wrong reason: every
    timestamp built from `now - n` predates the import that stamps
    _PROCESS_STARTED_AT, so everything would read stalled regardless of the
    threshold logic under test. TestRunsLostToARestart sets its own value.
    """
    from intel_platform.api.routes import collection_plans as cp

    monkeypatch.setattr(cp, "_PROCESS_STARTED_AT", datetime.now(timezone.utc) - timedelta(days=1))


def ev(event: str, ago_seconds: int = 0):
    return SimpleNamespace(
        event=event,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=ago_seconds),
        message="",
    )


class TestRunState:
    def test_no_events_is_idle(self):
        assert run_state_from_events([]) == "idle"

    def test_recent_activity_is_running(self):
        assert run_state_from_events([ev("source_collecting", 5)]) == "running"

    def test_a_completed_run_is_not_running(self):
        assert run_state_from_events([ev("source_collecting", 60), ev("plan_completed", 30)]) == "completed"

    def test_a_failed_run_is_reported_as_failed(self):
        assert run_state_from_events([ev("plan_failed", 30)]) == "failed"

    def test_silence_past_the_threshold_is_stalled(self):
        """A process killed mid-collection reported running forever."""
        assert run_state_from_events([ev("doc_extracting", _STALL_AFTER_SECONDS + 60)]) == "stalled"

    def test_a_later_run_supersedes_an_earlier_terminal_event(self):
        """Re-running a completed plan must read as running again."""
        events = [ev("plan_completed", 500), ev("source_collecting", 5)]
        assert run_state_from_events(events) == "running"


class TestWhatTheGuardPermits:
    """The states that must NOT block a new execution."""

    @pytest.mark.parametrize("state_events,expected", [
        ([], "idle"),
        ([ev("plan_completed", 30)], "completed"),
        ([ev("plan_failed", 30)], "failed"),
        ([ev("doc_extracting", _STALL_AFTER_SECONDS + 60)], "stalled"),
    ])
    def test_non_running_states_are_executable(self, state_events, expected):
        state = run_state_from_events(state_events)
        assert state == expected
        assert state != "running", "only an in-flight run may block execution"

    def test_a_stalled_run_does_not_strand_the_plan(self):
        """Past the silence threshold the previous attempt is presumed dead;
        refusing forever is how the old guard stranded plans."""
        assert run_state_from_events([ev("url_fetching", 4000)]) != "running"


class _Result:
    def __init__(self, row):
        self._row = row

    def scalars(self):
        return self

    def first(self):
        return self._row


class _Db:
    """Minimal stand-in for the async session: returns one activity row."""

    def __init__(self, row=None):
        self._row = row
        self.queries = 0

    async def execute(self, _stmt):
        self.queries += 1
        return _Result(self._row)


class TestCurrentRunState:
    """The guard and the status endpoint must read the same evidence, in the
    same precedence order: in-memory tracker first, activity trail second."""

    async def test_falls_back_to_the_activity_trail(self):
        from intel_platform.api.routes.collection_plans import current_run_state
        import uuid

        db = _Db(ev("source_collecting", 5))
        assert await current_run_state(db, uuid.uuid4()) == "running"

    async def test_no_activity_is_idle(self):
        from intel_platform.api.routes.collection_plans import current_run_state
        import uuid

        assert await current_run_state(_Db(None), uuid.uuid4()) == "idle"

    async def test_only_one_row_is_loaded(self):
        """A plan with thousands of activity rows must not be read whole just to
        answer 'is something running?'."""
        from intel_platform.api.routes.collection_plans import current_run_state
        import uuid

        db = _Db(ev("plan_completed", 10))
        await current_run_state(db, uuid.uuid4())
        assert db.queries == 1

    async def test_in_memory_tracker_wins_over_the_trail(self):
        """plan_executor's synchronous path records progress in memory, not to
        CollectionActivity; a run in flight there must still block."""
        from intel_platform.api.routes.collection_plans import current_run_state
        from intel_platform.services import plan_executor
        import uuid

        pid = uuid.uuid4()
        plan_executor._running_executions[str(pid)] = {"status": "running"}
        try:
            # Trail says the last run finished; memory says one is in flight.
            assert await current_run_state(_Db(ev("plan_completed", 900)), pid) == "running"
        finally:
            plan_executor._running_executions.pop(str(pid), None)

    async def test_a_finished_in_memory_run_does_not_block(self):
        from intel_platform.api.routes.collection_plans import current_run_state
        from intel_platform.services import plan_executor
        import uuid

        pid = uuid.uuid4()
        plan_executor._running_executions[str(pid)] = {"status": "completed"}
        try:
            assert await current_run_state(_Db(None), pid) != "running"
        finally:
            plan_executor._running_executions.pop(str(pid), None)


class TestPerRunCounts:
    """Progress counts describe the current run, not the whole trail.

    Seen live after the guard fix made re-running possible: a re-run of a plan
    reported "2 succeeded, 2 failed" from the previous run before it had
    collected anything.
    """

    def test_a_single_unfinished_run_counts_everything(self):
        from intel_platform.api.routes.collection_plans import current_run_events

        events = [ev("plan_started", 60), ev("source_succeeded", 30)]
        assert current_run_events(events) == events

    def test_an_earlier_run_is_excluded(self):
        from intel_platform.api.routes.collection_plans import current_run_events

        first = [ev("source_succeeded", 900), ev("source_failed", 880), ev("plan_completed", 870)]
        second = [ev("plan_started", 60), ev("source_succeeded", 30)]
        got = current_run_events(first + second)
        assert got == second
        assert sum(1 for e in got if e.event == "source_failed") == 0

    def test_a_finished_run_reports_its_own_totals(self):
        """When the trail ends on a terminal event, the counts are that run's —
        not zero, and not the previous run's added in."""
        from intel_platform.api.routes.collection_plans import current_run_events

        first = [ev("source_succeeded", 900), ev("plan_completed", 890)]
        second = [ev("source_succeeded", 60), ev("source_succeeded", 50), ev("plan_completed", 40)]
        got = current_run_events(first + second)
        assert sum(1 for e in got if e.event == "source_succeeded") == 2

    def test_a_failed_run_is_a_boundary_too(self):
        from intel_platform.api.routes.collection_plans import current_run_events

        events = [ev("source_failed", 900), ev("plan_failed", 890), ev("source_succeeded", 30)]
        got = current_run_events(events)
        assert [e.event for e in got] == ["source_succeeded"]


class TestInterruptedExecution:
    """A cancelled run must not leave the tracker claiming "running".

    CancelledError is a BaseException, so it escapes `except Exception` — the
    in-memory entry would say "running" for the life of the process, and the
    execute guard reads that as a run in flight. The plan would be permanently
    unexecutable: the same trap the status-flag guard created.
    """

    async def test_cancellation_clears_the_running_state(self):
        import asyncio
        from intel_platform.services import plan_executor

        plan_id = "11111111-2222-3333-4444-555555555555"

        async def _never_returns(*_a, **_kw):
            await asyncio.sleep(3600)

        class _Factory:
            def __call__(self):
                return self

            async def __aenter__(self):
                await _never_returns()

            async def __aexit__(self, *_):
                return False

        task = asyncio.create_task(
            plan_executor.execute_plan(plan_id, _Factory(), None, None)
        )
        try:
            await asyncio.sleep(0.05)
            assert plan_executor._running_executions[plan_id]["status"] == "running"
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

            state = plan_executor._running_executions[plan_id]["status"]
            assert state != "running", "a cancelled run would block execution forever"
            assert state == "interrupted"
        finally:
            plan_executor._running_executions.pop(plan_id, None)


class TestRunsLostToARestart:
    """A run that died with the previous process must not block for the full
    stall window.

    Agentic runs are asyncio tasks inside the API process, so a restart kills
    them — but the trail's last event can still be seconds old, which read as
    "running" and refused a re-run for ten minutes. Seen live: restarting the
    backend mid-collection and being refused with 409 immediately afterwards.
    """

    def test_activity_older_than_this_process_is_stalled(self, monkeypatch):
        from intel_platform.api.routes import collection_plans as cp

        # The process restarted 30 seconds ago; the run last wrote 60 seconds
        # ago — recent in wall-clock terms, but by a process that is gone.
        monkeypatch.setattr(cp, "_PROCESS_STARTED_AT", datetime.now(timezone.utc) - timedelta(seconds=30))
        assert cp.run_state_from_events([ev("url_fetching", 60)]) == "stalled"

    def test_activity_since_this_process_started_still_runs(self, monkeypatch):
        from intel_platform.api.routes import collection_plans as cp

        monkeypatch.setattr(cp, "_PROCESS_STARTED_AT", datetime.now(timezone.utc) - timedelta(seconds=120))
        assert cp.run_state_from_events([ev("url_fetching", 60)]) == "running"


class TestLiveTaskRegistry:
    """Whether a run is in flight is answered by looking at the task, not by
    inferring from timestamps."""

    async def test_a_live_task_blocks_and_a_finished_one_does_not(self):
        import asyncio
        import uuid
        from intel_platform.api.routes import collection_plans as cp

        pid = uuid.uuid4()
        assert cp.has_live_run(pid) is False

        gate = asyncio.Event()
        task = asyncio.create_task(gate.wait())
        cp.register_run(pid, task)
        try:
            assert cp.has_live_run(pid) is True
            # Blocks even though the trail says the last run finished.
            assert await cp.current_run_state(_Db(ev("plan_completed", 900)), pid) == "running"

            gate.set()
            await task
            await asyncio.sleep(0)  # let the done-callback run
            assert cp.has_live_run(pid) is False
        finally:
            cp._inflight_runs.pop(pid, None)

    async def test_the_registry_does_not_leak_finished_runs(self):
        import asyncio
        import uuid
        from intel_platform.api.routes import collection_plans as cp

        pid = uuid.uuid4()
        task = asyncio.create_task(asyncio.sleep(0))
        cp.register_run(pid, task)
        await task
        await asyncio.sleep(0)
        assert pid not in cp._inflight_runs
