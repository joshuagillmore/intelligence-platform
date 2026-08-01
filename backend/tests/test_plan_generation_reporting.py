"""A thin plan must say why it is thin.

Observed live in the UI. A refinement returned a refined PIR plus a "Why this
version works" critique and no Essential Elements section at all, while still
referring to "the EEIs". The result:

  * refined_text stored, plan created, step marked complete — all green;
  * eeis == 0, so satisfaction cannot be measured and the collection loop has
    nothing to re-task against;
  * the backend logged `Plan generation failed: ` — %s on an exception whose
    str() is empty, losing the type and the traceback;
  * the endpoint returned 200 OK with a source-less plan;
  * the UI told the analyst "The LLM may have been rate-limited", which was a
    guess, and wrong.

Every layer reported success while the requirement spine was empty.
"""
from __future__ import annotations

from intel_platform.api.routes.pirs import extract_eeis


class TestEeiExtractionOnRealRefinements:
    def test_a_refinement_with_no_elements_section_yields_none(self):
        """The exact live output. It mentions EEIs without ever listing them,
        so a parser looking for the word alone would wrongly find some."""
        refinement = (
            "**  \n\n> **Refined PIR:** *From 1 January 2024 to the present, identify all "
            "commercial and military vessels suspected of involvement in sabotage of Baltic "
            "Sea undersea telecommunications cables.*\n\n"
            "**Why this version works:**\n\n"
            "- **Specificity:** Defines the vessel categories.\n"
            "- **Actionability:** Gives a clear closure condition (all EEIs answered or gaps "
            "identified).\n\n"
            "Use the EEIs and suggested analytic techniques to operationalize this refined PIR."
        )
        assert extract_eeis(refinement) == [], (
            "a passing mention of 'EEIs' must not be read as a decomposition"
        )

    def test_a_refinement_with_a_real_elements_section_yields_them(self):
        refinement = (
            "Refined PIR: Identify vessels implicated in Baltic cable damage since 2024.\n\n"
            "3. **Essential Elements of Information (EEIs)**\n"
            "1. Which vessels are named in incident reporting?\n"
            "2. What evidence links each vessel to a specific cable break?\n"
            "3. What diplomatic or legal responses followed each incident?\n"
        )
        captured = extract_eeis(refinement)
        assert len(captured) == 3
        assert any("vessels" in c.lower() for c in captured)

    def test_elements_are_found_wherever_the_split_puts_them(self):
        """The capture now searches the refined half as well as the analysis
        half; a model that puts the list above the split point previously had
        it discarded, and the requirement looked undecomposed."""
        above_the_split = (
            "Essential Elements of Information:\n"
            "1. Which vessels?\n"
            "2. What evidence?\n\n"
            "Refined PIR: Identify vessels implicated in cable damage.\n"
        )
        assert len(extract_eeis(above_the_split)) == 2
