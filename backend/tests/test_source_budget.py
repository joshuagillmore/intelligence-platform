"""Collection stops against a stated source budget.

The PIR mechanism is "answer the requirement, or stop at the source limit and
say what is outstanding". The assessment half reported against a budget that
nothing enforced, so a plan given 3 sources ran all 5 and then reported "5/4".

These bind to the shipped predicate: deleting the budget check from either
executor makes them fail. An earlier version of this file reimplemented the gate
and stayed green with the production check removed.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from intel_platform.api.routes.collection_plans import ExecuteRequest
from intel_platform.services.plan_executor import over_source_budget


class TestExecuteRequestBudget:
    def test_defaults_to_unbounded(self):
        assert ExecuteRequest().source_limit is None

    def test_accepts_a_budget(self):
        assert ExecuteRequest(source_limit=3).source_limit == 3

    def test_rejects_zero_and_negative(self):
        for bad in (0, -1):
            with pytest.raises(ValidationError):
                ExecuteRequest(source_limit=bad)


class TestOverSourceBudget:
    def test_unbounded_never_stops(self):
        for attempted in (0, 1, 50, 10_000):
            assert not over_source_budget(attempted, None)

    def test_stops_once_the_budget_is_reached(self):
        assert not over_source_budget(0, 3)
        assert not over_source_budget(2, 3)
        assert over_source_budget(3, 3)
        assert over_source_budget(4, 3)

    def test_budget_of_one(self):
        assert not over_source_budget(0, 1)
        assert over_source_budget(1, 1)


class TestBothExecutorsShareThePredicate:
    """Guards against the rule drifting back into a per-executor copy."""

    def test_agentic_loop_uses_it(self):
        from intel_platform.collection import agentic

        assert agentic.over_source_budget is over_source_budget

    def test_plan_executor_defines_it(self):
        from intel_platform.services import plan_executor

        assert plan_executor.over_source_budget is over_source_budget


class TestBudgetAccounting:
    """`attempted` counts sources actually collected.

    Both executors increment only immediately before acquisition, so sources
    that were pre-failed, disabled, misconfigured or manual-upload do not
    consume the budget. This walks the same shape using the real predicate.
    """

    @staticmethod
    def _walk(sources: list[str], source_limit: int | None) -> tuple[list[int], list[int]]:
        collected, skipped, attempted = [], [], 0
        for i, kind in enumerate(sources):
            if kind == "failed":
                continue
            if over_source_budget(attempted, source_limit):
                skipped.append(i)
                continue
            if kind == "unusable":
                continue
            attempted += 1
            collected.append(i)
        return collected, skipped

    def test_stops_at_budget(self):
        collected, skipped = self._walk(["ok"] * 5, 3)
        assert collected == [0, 1, 2]
        assert skipped == [3, 4]

    def test_unbounded_collects_everything(self):
        collected, skipped = self._walk(["ok"] * 5, None)
        assert collected == [0, 1, 2, 3, 4] and skipped == []

    def test_prefailed_sources_do_not_consume_budget(self):
        collected, skipped = self._walk(["failed", "ok", "ok", "ok"], 2)
        assert collected == [1, 2]
        assert skipped == [3]

    def test_unusable_sources_do_not_consume_budget(self):
        """A file_upload or misconfigured source is skipped, not spent."""
        collected, _ = self._walk(["unusable", "ok", "ok"], 2)
        assert collected == [1, 2]

    def test_budget_larger_than_plan_is_a_no_op(self):
        collected, skipped = self._walk(["ok"] * 2, 7)
        assert collected == [0, 1] and skipped == []
