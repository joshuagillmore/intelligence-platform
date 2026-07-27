"""The stored probability must match the one the assessment states.

Observed live: the model replies "**PROBABILITY:** 0.78 / **CONFIDENCE_LABEL:**
Likely", the pattern could not cross the emphasis markers, and the assessment
was saved at the 0.5 fallback — "Roughly Even Chance". The structured field the
UI renders then contradicted the narrative sitting beside it, which for a tool
built on ICD 203 language is a judgement error, not a formatting one.
"""
from __future__ import annotations

from intel_platform.api.routes.assess import extract_probability
from intel_platform.models.entities import probability_to_label


class TestExtractProbability:
    def test_plain(self):
        assert extract_probability("PROBABILITY: 0.78", 0.5) == 0.78

    def test_bold_wrapped_label(self):
        """The exact live form."""
        text = "**PROBABILITY:** 0.78  \n**CONFIDENCE_LABEL:** Likely"
        assert extract_probability(text, 0.5) == 0.78

    def test_bold_outside_the_colon(self):
        assert extract_probability("**PROBABILITY**: 0.65", 0.5) == 0.65

    def test_leading_dot(self):
        assert extract_probability("PROBABILITY: .85", 0.5) == 0.85

    def test_spacing_and_case(self):
        assert extract_probability("probability :  0.42", 0.5) == 0.42

    def test_found_at_the_end_of_a_long_assessment(self):
        body = ("## 1. Entity Overview\n" + "Narrative text. " * 200
                + "\n\n**PROBABILITY:** 0.91\n**CONFIDENCE_LABEL:** Almost Certain")
        assert extract_probability(body, 0.5) == 0.91

    def test_missing_falls_back(self):
        assert extract_probability("No probability stated anywhere.", 0.33) == 0.33

    def test_empty_content_falls_back(self):
        assert extract_probability("", 0.4) == 0.4
        assert extract_probability(None, 0.4) == 0.4

    def test_percent_style_is_not_silently_clamped(self):
        """"PROBABILITY: 78" means percent; clamping it would invent a judgement."""
        assert extract_probability("PROBABILITY: 78", 0.5) == 0.5

    def test_zero_is_rejected(self):
        """0.0 is outside the ICD 203 scale and is not a usable judgement."""
        assert extract_probability("PROBABILITY: 0.0", 0.5) == 0.5

    def test_one_is_accepted(self):
        assert extract_probability("PROBABILITY: 1.0", 0.5) == 1.0


class TestLabelMatchesTheNarrative:
    def test_the_live_case_now_agrees_with_itself(self):
        """0.78 must read "Likely", not "Roughly Even Chance"."""
        text = "**PROBABILITY:** 0.78  \n**CONFIDENCE_LABEL:** Likely"
        value = extract_probability(text, 0.5)
        assert probability_to_label(value) == "Likely"
        assert probability_to_label(0.5) == "Roughly Even Chance"


class TestEmphasisAppearsAnywhere:
    """Both live forms, plus the arrangements between them.

    The first fix allowed one run of asterisks after the colon and still failed
    on "**PROBABILITY:** **0.70**", which puts emphasis on both sides of the
    number. Asterisks and whitespace are now one interchangeable run.
    """

    def test_the_second_live_form(self):
        text = "**PROBABILITY:** **0.70**  \n**CONFIDENCE_LABEL:** **Likely**"
        assert extract_probability(text, 0.5) == 0.70

    def test_every_arrangement(self):
        for text in (
            "PROBABILITY: 0.70",
            "**PROBABILITY:** 0.70",
            "**PROBABILITY**: 0.70",
            "**PROBABILITY:** **0.70**",
            "*PROBABILITY*: *0.70*",
            "__PROBABILITY__: __0.70__",
            "PROBABILITY  :   **0.70**",
        ):
            assert extract_probability(text, 0.5) == 0.70, text
