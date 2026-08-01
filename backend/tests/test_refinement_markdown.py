"""The requirement must survive the markdown a model wraps it in.

This was filed as cosmetic and is not. The stored requirement is the text the
source resolver searches against, so a requirement reading

    (Actionable, Specific, Measurable, Time-bounded)** > **

sent collection after MCWP 2-1 Intelligence Operations and "Commander's
Critical Information Requirements" — doctrine on how to write requirements —
instead of the subject the analyst asked about. It also became the PIR title and
the plan name, so the collection-plans list showed three entries all beginning
"PIR: ** > **Refined PIR:** *From 1 January...".

The samples below are real replies observed on live runs.
"""
from __future__ import annotations

import pytest

from intel_platform.api.routes.collection_plans import _split_refinement
from intel_platform.api.routes.pirs import derive_title

# Observed live. Note the bare "**" first line, the blockquoted label, the
# italicised requirement, and the model's critique of its own rewrite.
SAMPLE_BLOCKQUOTED = (
    "**  \n\n"
    "> **Refined PIR:** *From 1 January 2024 to the present, identify all commercial "
    "and military vessels suspected of involvement in sabotage of Baltic Sea undersea "
    "telecommunications cables.*  \n\n"
    "**Why this version works:**  \n\n"
    "- **Specificity:** Defines the vessel categories.\n"
    "- **Measurability:** Provides clear metrics.\n"
)

# Observed live. The model echoed the prompt's own criteria above the label.
SAMPLE_ECHOED_CRITERIA = (
    "(Actionable, Specific, Measurable, Time-bounded)**  \n\n"
    "> **Priority Intelligence Requirement (PIR):** Identify all incidents of "
    "vessel-caused damage to Baltic Sea undersea cables during 2024.\n\n"
    "**Why this version works:**\n- Specific.\n"
)


class TestTheRequirementIsRecovered:
    def test_blockquoted_sample_yields_the_requirement(self):
        refined, _ = _split_refinement(SAMPLE_BLOCKQUOTED, "FALLBACK")
        assert refined.startswith("From 1 January 2024")
        assert "**" not in refined and ">" not in refined

    def test_echoed_criteria_do_not_win_by_appearing_first(self):
        """The fragment above the label is not the requirement."""
        refined, _ = _split_refinement(SAMPLE_ECHOED_CRITERIA, "FALLBACK")
        assert refined.startswith("Identify all incidents")
        assert "Actionable" not in refined

    def test_the_critique_stays_out_of_the_requirement(self):
        """"Why this version works" is analysis, not the thing to collect against."""
        for sample in (SAMPLE_BLOCKQUOTED, SAMPLE_ECHOED_CRITERIA):
            refined, analysis = _split_refinement(sample, "FALLBACK")
            assert "Why this version works" not in refined
            assert "Why this version works" in analysis

    def test_a_markdown_only_line_is_never_the_requirement(self):
        refined, _ = _split_refinement("**  \n\nIdentify vessels near the shoal.", "FALLBACK")
        assert refined == "Identify vessels near the shoal."

    def test_a_plain_reply_is_unchanged(self):
        refined, analysis = _split_refinement(
            "Identify vessels implicated in cable damage.\nSome analysis follows.", "FALLBACK"
        )
        assert refined == "Identify vessels implicated in cable damage."
        assert analysis == "Some analysis follows."

    def test_an_empty_reply_falls_back(self):
        assert _split_refinement("", "ORIGINAL")[0] == "ORIGINAL"

    def test_a_reply_of_only_markdown_falls_back(self):
        assert _split_refinement("**\n\n>\n\n---", "ORIGINAL")[0] == "ORIGINAL"

    @pytest.mark.parametrize("label", [
        "Refined PIR:", "**Refined PIR:**", "> **Refined PIR:**",
        "PRIORITY INTELLIGENCE REQUIREMENT:", "Priority Intelligence Requirement (PIR):",
    ])
    def test_label_variants_are_all_recognised(self, label):
        refined, _ = _split_refinement(f"{label} Track vessel movements.", "FALLBACK")
        assert refined == "Track vessel movements."


class TestTitlesAreReadable:
    def test_markdown_is_stripped_from_a_derived_title(self):
        title = derive_title("> **Refined PIR:** *Identify vessels near the shoal.*")
        assert "**" not in title and not title.startswith(">")

    def test_the_observed_broken_title_is_repaired(self):
        assert derive_title("(Actionable, Specific, Measurable, Time-bounded)**  ") == (
            "(Actionable, Specific, Measurable, Time-bounded)"
        )

    def test_a_clean_title_is_untouched(self):
        assert derive_title("Baltic cable damage attribution") == (
            "Baltic cable damage attribution"
        )

    def test_long_titles_are_still_truncated(self):
        assert derive_title("x" * 400).endswith("...")
