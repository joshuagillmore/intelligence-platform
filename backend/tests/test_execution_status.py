"""A dead collection must not report "running" forever.

`execution-status` once derived "running" purely from the absence of a
terminal event, so a process killed mid-collection kept claiming to run —
confirmed by restarting the backend and watching a dead plan keep saying so. It
cost two measurements during testing: an assessment ran against a graph that was
still being built, and reported the requirement unanswered.

Liveness is now the job row's heartbeat, refreshed every
`HEARTBEAT_SECONDS` by whichever process runs the job; silence past
`collection_stall_seconds` is `stalled`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from intel_platform.collection import job_runner
from intel_platform.db import jobs

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def _age_state(seconds: float) -> str:
    """The state of a running job whose last heartbeat was `seconds` ago."""
    job = SimpleNamespace(status=jobs.RUNNING, heartbeat_at=NOW - timedelta(seconds=seconds),
                          started_at=None, created_at=None, finished_at=None)
    return job_runner.run_state(job, NOW)


class TestStallDerivation:
    def test_recent_heartbeat_is_running(self):
        assert _age_state(5) == "running"
        assert _age_state(job_runner.stall_seconds() - 1) == "running"

    def test_prolonged_silence_is_stalled(self):
        assert _age_state(job_runner.stall_seconds() + 1) == "stalled"
        assert _age_state(3600) == "stalled"

    def test_threshold_exceeds_the_heartbeat_interval(self):
        """Must not cry wolf between heartbeats. The heartbeat comes from its
        own task every 10 s, independent of how slow a chunk's model call is,
        so the window only has to clear a few missed beats."""
        assert job_runner.stall_seconds() >= 3 * job_runner.HEARTBEAT_SECONDS

    def test_the_default_window_is_two_minutes(self):
        assert job_runner._DEFAULT_STALL_SECONDS == 120
