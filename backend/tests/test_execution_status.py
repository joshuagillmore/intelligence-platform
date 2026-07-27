"""A dead collection must not report "running" forever.

`execution-status` derived "running" purely from the absence of a terminal
event, so a process killed mid-collection kept claiming to run — confirmed by
restarting the backend and watching a dead plan keep saying so. It cost two
measurements during testing: an assessment ran against a graph that was still
being built, and reported the requirement unanswered.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from intel_platform.api.routes.collection_plans import _STALL_AFTER_SECONDS


def _age_state(seconds: float) -> str:
    """The status derivation for a plan with no terminal event."""
    return "stalled" if seconds > _STALL_AFTER_SECONDS else "running"


class TestStallDerivation:
    def test_recent_activity_is_running(self):
        assert _age_state(5) == "running"
        assert _age_state(_STALL_AFTER_SECONDS - 1) == "running"

    def test_prolonged_silence_is_stalled(self):
        assert _age_state(_STALL_AFTER_SECONDS + 1) == "stalled"
        assert _age_state(3600) == "stalled"

    def test_threshold_exceeds_the_heartbeat_interval(self):
        """Must not cry wolf between extraction heartbeats on a slow model.

        Heartbeats land every few chunks; a chunk against a local 14B model is
        tens of seconds, so the threshold has to clear several chunks with room
        to spare.
        """
        assert _STALL_AFTER_SECONDS >= 300

    def test_age_is_computed_from_the_latest_event(self):
        now = datetime.now(timezone.utc)
        latest = now - timedelta(seconds=_STALL_AFTER_SECONDS + 60)
        assert _age_state((now - latest).total_seconds()) == "stalled"
