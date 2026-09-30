"""ACH hypotheses and Admiralty ratings, read the way models actually write them.

Low -> R: both parsers accepted the requested shape and a markdown table, and
silently dropped bold fields and numbered lines; the ACH parser clamped an
out-of-range 1.5 to 1.0, recording "Almost Certain" for a value the model never
gave. A value outside 0..1 is now dropped, not clamped.
"""
from __future__ import annotations

import pytest

from intel_platform.services.analytic_agents import AnalyticAgentService, _find_rating

parse = AnalyticAgentService._parse_hypotheses


class TestHypotheses:
    @pytest.mark.parametrize("line", [
        "H1 | The ministry breach was APT29 | 0.70",                      # requested shape
        "| H1 | The ministry breach was APT29 | 0.70 |",                  # table row
        "**H1** | **The ministry breach was APT29** | **0.70**",          # bold fields
        "1. H1 | The ministry breach was APT29 | 0.70",                   # numbered
        "- H1 | The ministry breach was APT29 | 0.70",                    # bulleted
        "| H1 | The ministry breach was APT29 | 0.70 | Likely |",         # extra column
    ])
    def test_every_layout_reads_the_same(self, line):
        got = parse("HYPOTHESES:\n" + line)
        assert [(h["id"], h["statement"], h["probability"]) for h in got] == [
            ("H1", "The ministry breach was APT29", 0.70)
        ]

    @pytest.mark.parametrize("value", ["1.5", "70", "15%", "12.5%", "-0.2"])
    def test_an_out_of_range_probability_is_dropped_not_clamped(self, value):
        assert parse(f"H1 | Something happened | {value}") == []

    def test_the_table_header_and_rule_are_not_hypotheses(self):
        table = (
            "| ID | Hypothesis | Probability |\n"
            "|----|------------|-------------|\n"
            "| H1 | Insider | 0.2 |\n"
            "| H2 | External actor | 0.8 |\n"
        )
        assert [h["id"] for h in parse(table)] == ["H1", "H2"]

    def test_prose_only_reply_yields_nothing(self):
        prose = (
            "H1 is more likely than H2 given the evidence; I would put H1 at about "
            "seventy percent and H2 at thirty."
        )
        assert parse(prose) == []

    def test_a_repeated_id_keeps_the_first(self):
        assert [h["probability"] for h in parse("H1 | a | 0.3\nH1 | b | 0.9")] == [0.3]


class TestAdmiraltyRating:
    DOC = "4f2c9a1e-doc"

    @pytest.mark.parametrize("text", [
        f"{DOC}: B2",
        f"| {DOC} | B2 |",
        f"**{DOC}**: **B2**",
        f"`{DOC}` — B-2",
        f"- {DOC}: b2",
    ])
    def test_every_layout_reads_the_same(self, text):
        assert _find_rating("RATINGS:\n" + text, self.DOC) == "B2"

    def test_an_invalid_grade_is_not_read(self):
        assert _find_rating(f"{self.DOC}: G7", self.DOC) == ""
        assert _find_rating(f"{self.DOC}: B23", self.DOC) == ""

    def test_prose_without_a_rating_line_is_nothing(self):
        assert _find_rating(f"The source {self.DOC} seems fairly reliable overall.", self.DOC) == ""
