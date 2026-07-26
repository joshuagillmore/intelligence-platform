"""PIR satisfaction assessment — EEI capture and verdict parsing.

The assessor is what closes the collection loop: it decides whether a
requirement was answered or whether collection merely ran out of sources, and
names the elements still outstanding. Both halves are text-parsing against
model output, which is exactly where it breaks silently.
"""
from __future__ import annotations

from intel_platform.api.routes.pirs import extract_eeis


class TestExtractEeis:
    def test_numbered_list_under_heading(self):
        analysis = (
            "## Assessment\nThe requirement is broad.\n\n"
            "### Essential Elements of Information\n"
            "1. Which vessels were attacked in the Bab-el-Mandeb since March?\n"
            "2. What weapon systems were employed?\n"
            "3. Which actor claimed responsibility?\n"
        )
        eeis = extract_eeis(analysis)
        assert len(eeis) == 3
        assert eeis[0].startswith("Which vessels")
        assert eeis[2] == "Which actor claimed responsibility?"

    def test_bulleted_list(self):
        analysis = (
            "EEIs:\n"
            "- Identify the C2 infrastructure in use\n"
            "- Determine the initial access vector\n"
        )
        eeis = extract_eeis(analysis)
        assert eeis == [
            "Identify the C2 infrastructure in use",
            "Determine the initial access vector",
        ]

    def test_bold_markdown_is_stripped(self):
        eeis = extract_eeis("**EEIs**\n1. **Who operates the facility?**\n")
        assert eeis == ["Who operates the facility?"]

    def test_inline_after_heading_colon(self):
        eeis = extract_eeis("Essential Elements of Information: Who funds the group?\n")
        assert eeis == ["Who funds the group?"]

    def test_prose_before_heading_is_not_captured(self):
        """Numbered analysis paragraphs above the EEI section must not leak in."""
        analysis = (
            "1. This requirement lacks a time bound.\n"
            "2. It does not specify a geography.\n\n"
            "### EEIs\n"
            "1. What is the timeframe of interest?\n"
        )
        assert extract_eeis(analysis) == ["What is the timeframe of interest?"]

    def test_double_labelled_line_strips_inner_marker(self):
        """Observed live: the model writes "3. EEI 3: ..." and both markers must go."""
        analysis = (
            "### EEIs\n"
            "1. Specific TTPs employed by APT44 since 2024.\n"
            "3. EEI 3: Specific ICS devices compromised since January 2024.\n"
        )
        eeis = extract_eeis(analysis)
        assert eeis == [
            "Specific TTPs employed by APT44 since 2024.",
            "Specific ICS devices compromised since January 2024.",
        ]

    def test_bare_eei_marker_line(self):
        assert extract_eeis("EEIs:\nEEI 1: Who controls the port?\n") == [
            "Who controls the port?"
        ]

    def test_section_label_is_not_a_criterion(self):
        """Observed live: "Refined PIR:" was captured as an EEI and then assessed."""
        analysis = (
            "### EEIs\n"
            "1. Which ICS protocols were targeted?\n"
            "2. Refined PIR:\n"
        )
        assert extract_eeis(analysis) == ["Which ICS protocols were targeted?"]

    def test_inline_bold_is_removed(self):
        """Observed live: "**Initial Access Vectors:** Determine…" kept its markers."""
        analysis = "EEIs:\n1. **Initial Access Vectors:** Determine the primary methods used.\n"
        assert extract_eeis(analysis) == [
            "Initial Access Vectors: Determine the primary methods used."
        ]

    def test_deduplicates_case_insensitively(self):
        analysis = "EEIs:\n- Who leads the unit?\n- who leads the unit?\n- Where is it based?\n"
        assert extract_eeis(analysis) == ["Who leads the unit?", "Where is it based?"]

    def test_respects_limit(self):
        analysis = "EEIs:\n" + "\n".join(f"{i}. Question number {i} about the target?" for i in range(1, 15))
        assert len(extract_eeis(analysis, limit=5)) == 5

    def test_no_eei_section_returns_empty(self):
        assert extract_eeis("The requirement is clear and needs no refinement.") == []

    def test_empty_input(self):
        assert extract_eeis("") == []
        assert extract_eeis(None) == []


class TestVerdictLineParsing:
    """The `N | VERDICT | justification` contract the assessor parses back."""

    import re as _re

    PATTERN = _re.compile(
        r"^\s*\**\s*(\d+)\s*\|\s*(SATISFIED|PARTIAL|UNMET)\s*\|\s*(.+?)\s*\**\s*$",
        _re.IGNORECASE,
    )

    def test_plain_line(self):
        m = self.PATTERN.match("1 | SATISFIED | Three sources name MV Aurora Trader.")
        assert m and m.group(2) == "SATISFIED"

    def test_bold_wrapped_line(self):
        m = self.PATTERN.match("**2 | UNMET | No collected document addresses attribution.**")
        assert m and m.group(1) == "2" and m.group(2) == "UNMET"

    def test_lowercase_verdict(self):
        m = self.PATTERN.match("3 | partial | Only one of two facilities identified.")
        assert m and m.group(2).upper() == "PARTIAL"

    def test_prose_line_is_ignored(self):
        assert self.PATTERN.match("The first element is well covered by the reporting.") is None

    def test_header_line_is_ignored(self):
        assert self.PATTERN.match("EEI_ASSESSMENT:") is None
