"""A plan generated with no sources because the model was unavailable must be
countable, and a run with nothing to collect against must say so in its
trail. Both used to end as clean-looking zeros."""
from __future__ import annotations

from intel_platform.api.routes.collection_plans import refinement
from intel_platform.services import telemetry


def test_generation_failures_are_counted_by_fixed_reason(monkeypatch):
    seen: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        telemetry, "record_degraded",
        lambda subsystem, reason, *, detail="": seen.append((subsystem, reason, detail)),
    )
    refinement._count_generation_failure("source generation failed (LLMProviderError)")
    refinement._count_generation_failure("refinement returned no usable requirement")
    assert seen == [
        ("collection", "source_generation_failed", "source generation failed (LLMProviderError)"),
        ("collection", "refinement_returned_no_usable_requirement", "refinement returned no usable requirement"),
    ]


async def test_a_requirement_with_no_elements_leaves_a_trail_event(monkeypatch):
    """`run_requirement_passes` on a PIR with no EEIs writes an activity event
    instead of returning silently."""
    import uuid
    from contextlib import asynccontextmanager

    from intel_platform.collection import requirement_loop

    plan_id = uuid.uuid4()
    pir_id = uuid.uuid4()
    added: list = []

    class _Plan:
        def __init__(self):
            self.id = plan_id
            self.pir_id = pir_id
            self.sources = []

    class _Pir:
        id = pir_id
        project_id = "p"
        eeis: list = []

    class _Db:
        async def get(self, model, key):
            return _Plan() if key == plan_id else _Pir()

        def add(self, row):
            added.append(row)

        async def commit(self):
            pass

    @asynccontextmanager
    async def _factory():
        yield _Db()

    async def _no_requirements(db, pir):
        return []

    monkeypatch.setattr(requirement_loop, "sync_requirements", _no_requirements)

    async def _acquire(*a, **k):  # pragma: no cover - never reached
        raise AssertionError("nothing should be collected")

    outcome = await requirement_loop.run_requirement_passes(
        plan_id, _factory, lambda: None, None, _acquire,
    )
    assert outcome.stopped_on == "no_elements"
    assert [row.event for row in added] == ["requirement_no_elements"]
    assert "no essential elements" in added[0].message
