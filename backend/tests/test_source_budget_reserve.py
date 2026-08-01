"""Part of the source budget is held back for follow-up collection.

The requirement loop could not run at the default. A planner sizes its source
list to the budget it is given, so the planned pass spent all of it and the loop
opened with nothing:

    requirement_budget_reached | Source budget of 4 reached with 3 element(s) still open
    requirement_loop_done      | 0/3 answered after 0 pass(es); 0 source(s) added

It reported that honestly, which is why it went unnoticed — "honest about doing
nothing" is not the same as working. Re-tasking only ever ran when I passed a
budget larger than the planned list by hand.

The analyst's number stays the total ceiling; this only stops the uninformed
half of the run consuming all of it.
"""
from __future__ import annotations

import pytest

from intel_platform.services.plan_executor import (
    over_source_budget,
    planned_source_budget,
)


class TestPlannedBudgetLeavesRoom:
    @pytest.mark.parametrize("total", [2, 3, 4, 5, 8, 12, 30])
    def test_some_budget_always_survives_the_planned_pass(self, total):
        planned = planned_source_budget(total)
        assert planned < total, f"planned pass may spend all {total} sources"
        assert total - planned >= 1, "nothing left for re-tasking"

    @pytest.mark.parametrize("total", [2, 3, 4, 5, 8, 12, 30])
    def test_the_planned_pass_can_still_collect(self, total):
        assert planned_source_budget(total) >= 1

    def test_an_unbounded_budget_stays_unbounded(self):
        assert planned_source_budget(None) is None

    @pytest.mark.parametrize("total", [0, 1])
    def test_budgets_too_small_to_split_are_left_whole(self, total):
        """Reserving from 1 would leave the planned pass unable to collect."""
        assert planned_source_budget(total) == total

    def test_the_reported_case_now_leaves_room(self):
        """Budget 4 with 4 planned sources: the loop used to get zero."""
        planned = planned_source_budget(4)
        assert planned == 3
        assert 4 - planned == 1

    def test_the_reserve_scales_with_the_budget(self):
        assert 12 - planned_source_budget(12) >= 3


class TestGateUsesThePlannedBudget:
    def test_planned_pass_stops_at_the_planned_budget(self):
        planned = planned_source_budget(10)
        assert over_source_budget(planned, planned) is True
        assert over_source_budget(planned - 1, planned) is False

    def test_total_ceiling_is_never_exceeded(self):
        """The reserve is carved out of the total, not added to it."""
        total = 10
        planned = planned_source_budget(total)
        reserve = total - planned
        assert planned + reserve == total
