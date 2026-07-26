"""PIR satisfaction assessment — EEI capture and verdict parsing.

The assessor is what closes the collection loop: it decides whether a
requirement was answered or whether collection merely ran out of sources, and
names the elements still outstanding. Both halves are text-parsing against
model output, which is exactly where it breaks silently.
"""
from __future__ import annotations

from intel_platform.api.routes.pirs import extract_eeis, parse_verdicts


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

    def test_refinement_commentary_is_not_a_criterion(self):
        """Observed live: the model's note about its own rewrite became an EEI.

        Collection can never satisfy it, so it would sit in unmet_criteria
        forever and make the requirement permanently unsatisfiable.
        """
        analysis = (
            "### EEIs\n"
            "1. Which border regions have seen expansion?\n"
            "2. The refined version provides a clearer focus on coastal regions.\n"
        )
        assert extract_eeis(analysis) == ["Which border regions have seen expansion?"]

    def test_substantive_eei_mentioning_a_revision_survives(self):
        """The filter must not eat a real criterion that happens to say 'revised'."""
        analysis = "EEIs:\n1. Which sanctions lists were revised after the incident?\n"
        assert extract_eeis(analysis) == [
            "Which sanctions lists were revised after the incident?"
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


class TestParseVerdicts:
    """The `N | VERDICT | justification` contract the assessor reads back.

    A missed verdict is indistinguishable from an unassessed requirement, so
    every label shape a model has actually produced is covered here.
    """

    EEIS = ["Which vessels?", "Who attributed it?", "Which facilities?"]

    def test_plain_lines_under_one_header(self):
        narrative = (
            "EEI_ASSESSMENT:\n"
            "1 | SATISFIED | Three sources name MV Aurora Trader.\n"
            "2 | UNMET | No collected document addresses attribution.\n"
        )
        got = parse_verdicts(narrative, self.EEIS)
        assert [g["verdict"] for g in got] == ["SATISFIED", "UNMET"]
        assert got[0]["eei"] == "Which vessels?"

    def test_header_repeated_on_every_line(self):
        """Observed live from command-a-plus: the label prefixes each verdict."""
        narrative = (
            "EEI_ASSESSMENT: 1 | UNMET | No identification of the top three groups.\n"
            "EEI_ASSESSMENT: 2 | UNMET | No mapping of initial access vectors.\n"
            "EEI_ASSESSMENT: 3 | UNMET | Data leak site usage is absent.\n"
        )
        got = parse_verdicts(narrative, self.EEIS)
        assert len(got) == 3
        assert all(g["verdict"] == "UNMET" for g in got)

    def test_bold_wrapped_and_lowercase(self):
        narrative = (
            "**2 | partial | Only one of two facilities identified.**\n"
        )
        got = parse_verdicts(narrative, self.EEIS)
        assert got == [{
            "index": 1, "eei": "Who attributed it?", "verdict": "PARTIAL",
            "justification": "Only one of two facilities identified.",
        }]

    def test_eei_prefixed_index(self):
        got = parse_verdicts("EEI 3 | SATISFIED | Both sites named.", self.EEIS)
        assert got and got[0]["index"] == 2

    def test_prose_and_headers_ignored(self):
        narrative = (
            "The first element is well covered by the reporting.\n"
            "EEI_ASSESSMENT:\n"
            "Some concluding remarks about collection.\n"
        )
        assert parse_verdicts(narrative, self.EEIS) == []

    def test_out_of_range_index_dropped(self):
        """A model that invents a 9th EEI must not index past the list."""
        assert parse_verdicts("9 | SATISFIED | Invented element.", self.EEIS) == []

    def test_duplicate_index_keeps_first(self):
        narrative = (
            "1 | SATISFIED | First verdict.\n"
            "1 | UNMET | Contradictory second verdict.\n"
        )
        got = parse_verdicts(narrative, self.EEIS)
        assert len(got) == 1 and got[0]["verdict"] == "SATISFIED"

    def test_empty_narrative(self):
        assert parse_verdicts("", self.EEIS) == []
