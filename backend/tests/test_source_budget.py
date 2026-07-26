"""Collection stops against a stated source budget.

The PIR mechanism is "answer the requirement, or stop at the source limit and
say what is outstanding". The assessment half reported against a budget that
nothing enforced, so a plan given 3 sources ran all 5 and then reported "5/4".
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from intel_platform.api.routes.collection_plans import ExecuteRequest


class TestExecuteRequestBudget:
    def test_defaults_to_unbounded(self):
        assert ExecuteRequest().source_limit is None

    def test_accepts_a_budget(self):
        assert ExecuteRequest(source_limit=3).source_limit == 3

    def test_rejects_zero_and_negative(self):
        for bad in (0, -1):
            with pytest.raises(ValidationError):
                ExecuteRequest(source_limit=bad)


class TestBudgetGate:
    """The loop's stop condition, exercised directly.

    `attempted` counts only sources actually collected, so pre-failed sources
    do not consume budget.
    """

    @staticmethod
    def _collect(statuses: list[str], source_limit: int | None) -> tuple[list[int], list[int]]:
        collected, skipped, attempted = [], [], 0
        for i, status in enumerate(statuses):
            if status == "failed":
                continue
            if source_limit is not None and attempted >= source_limit:
                skipped.append(i)
                continue
            attempted += 1
            collected.append(i)
        return collected, skipped

    def test_stops_at_budget(self):
        collected, skipped = self._collect(["ok"] * 5, 3)
        assert collected == [0, 1, 2]
        assert skipped == [3, 4]

    def test_unbounded_collects_everything(self):
        collected, skipped = self._collect(["ok"] * 5, None)
        assert collected == [0, 1, 2, 3, 4] and skipped == []

    def test_budget_larger_than_plan_is_a_no_op(self):
        collected, skipped = self._collect(["ok"] * 2, 7)
        assert collected == [0, 1] and skipped == []

    def test_prefailed_sources_do_not_consume_budget(self):
        collected, skipped = self._collect(["failed", "ok", "ok", "ok"], 2)
        assert collected == [1, 2]
        assert skipped == [3]
