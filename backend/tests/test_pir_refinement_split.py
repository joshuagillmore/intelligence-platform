"""The refinement splitter — models label their output in several ways."""
from intel_platform.api.routes.collection_plans import _split_refinement

FALLBACK = "original pir"


def test_label_on_its_own_line():
    """The observed failure: line 0 was the label, so refined_pir was 12 chars."""
    content = "Refined PIR:\nDetermine the identities of actors attacking shipping.\n\n### Analysis:\n1. Specificity..."
    refined, analysis = _split_refinement(content, FALLBACK)
    assert refined == "Determine the identities of actors attacking shipping."
    assert "Analysis" in analysis


def test_label_inline_with_the_text():
    content = "Refined PIR: Identify the actors and their methods.\nRest of analysis here."
    refined, analysis = _split_refinement(content, FALLBACK)
    assert refined == "Identify the actors and their methods."
    assert analysis == "Rest of analysis here."


def test_markdown_bold_label():
    content = "**Refined PIR**\nWho is targeting the grid operators?\nAnalysis follows."
    refined, _ = _split_refinement(content, FALLBACK)
    assert refined == "Who is targeting the grid operators?"


def test_no_label_first_line_is_the_pir():
    content = "Identify actors attacking commercial shipping.\nThen some analysis."
    refined, analysis = _split_refinement(content, FALLBACK)
    assert refined == "Identify actors attacking commercial shipping."
    assert analysis == "Then some analysis."


def test_quotes_and_stars_stripped():
    content = '"Determine the threat actor\'s infrastructure."\nAnalysis.'
    refined, _ = _split_refinement(content, FALLBACK)
    assert refined == "Determine the threat actor's infrastructure."


def test_empty_content_falls_back_to_the_original_pir():
    assert _split_refinement("", FALLBACK) == (FALLBACK, "")
    assert _split_refinement("   \n  ", FALLBACK) == (FALLBACK, "")


def test_label_with_nothing_after_falls_back():
    refined, _ = _split_refinement("Refined PIR:", FALLBACK)
    assert refined == FALLBACK


def test_bold_label_with_colon_inside_the_markers():
    """`**Refined PIR:**` — the capture group grabs the closing `**`, which is
    truthy but empty once stripped. The text is on the next line."""
    content = "**Refined PIR:**\nDetermine the identities of actors attacking shipping.\n### Analysis:\nmore"
    refined, analysis = _split_refinement(content, FALLBACK)
    assert refined == "Determine the identities of actors attacking shipping."
    assert analysis.startswith("### Analysis:")


def test_bold_label_inline_with_real_text():
    content = "**Refined PIR:** Identify the actors and their methods.\nAnalysis."
    refined, _ = _split_refinement(content, FALLBACK)
    assert refined == "Identify the actors and their methods."


# ---------------------------------------------------------------------------
# R-7: the fallback took the first wordy line — a preamble or a section heading —
# and that line then drove source resolution and the judge.
# ---------------------------------------------------------------------------

import pytest  # noqa: E402

from intel_platform.api.routes.collection_plans import _split_refinement_parsed  # noqa: E402

REQ = "Identify the state actors responsible for Baltic Sea cable damage between 2023 and 2025."


class TestLabelForms:
    @pytest.mark.parametrize("content", [
        f"**4. Refined PIR:** {REQ}\nAnalysis.",                        # numbered, bold, inline
        f"4. Proposed PIR:\n{REQ}\nAnalysis.",                          # numbered, label-only
        f"### 4. Proposed Refined PIR\n{REQ}\n### Rationale",           # numbered heading
        f"Revised PIR: {REQ}\nAnalysis.",
        f"**Proposed Priority Intelligence Requirement:**\n\n*{REQ}*\n",
        f"| Refined PIR | {REQ} |\n",                                    # table row
        f"Improved requirement: {REQ}\n",
    ])
    def test_the_requirement_is_read_from_every_label_form(self, content):
        refined, _, parsed = _split_refinement_parsed(content, FALLBACK)
        assert refined == REQ
        assert parsed is True

    def test_a_label_on_a_later_line_beats_a_preamble(self):
        content = f"Here is a refined version of your PIR:\n\nRefined PIR: {REQ}\n"
        assert _split_refinement_parsed(content, FALLBACK)[0] == REQ


class TestLinesThatAreNotTheRequirement:
    def test_a_preamble_is_skipped(self):
        """The observed failure: "Here is a refined version…" became the PIR."""
        content = f"Here is a refined version of your PIR:\n\n{REQ}\n\nWhy it works: …"
        refined, _, parsed = _split_refinement_parsed(content, FALLBACK)
        assert refined == REQ and parsed

    def test_a_line_ending_in_a_colon_after_the_label_is_skipped(self):
        content = f"Refined PIR:\nThe refined requirement reads as follows:\n{REQ}\n"
        assert _split_refinement_parsed(content, FALLBACK)[0] == REQ

    @pytest.mark.parametrize("content", [
        "### 1. Assessment\nThe PIR lacks a time bound and a geographic focus.\n### 2. Hidden Assumptions\n…",
        "1. ASSESS specificity, measurability, and time-bounds\nThe PIR is vague.\n",
        "**Essential Elements of Information (EEIs)**\n1. Which vessels?\n2. Which dates?\n",
        "Analysis:\nThe requirement is too broad.\n",
    ])
    def test_a_reply_that_opens_on_a_section_falls_back_unparsed(self, content):
        """No label, and the first line is the prompt's own section: the reply
        did not return a requirement, so none is invented from its analysis."""
        refined, _, parsed = _split_refinement_parsed(content, FALLBACK)
        assert (refined, parsed) == (FALLBACK, False)

    def test_a_label_followed_only_by_a_section_falls_back(self):
        content = "Refined PIR:\n### Analysis\nThe original is fine.\n"
        assert _split_refinement_parsed(content, FALLBACK) == (FALLBACK, "", False)

    def test_a_requirement_starting_with_a_step_verb_survives(self):
        """"Identify …" is how many PIRs begin; only the prompt's own step text
        ("IDENTIFY hidden assumptions") is a section."""
        content = "Identify which vessels loitered over the cable before each break.\nAnalysis."
        refined, _, parsed = _split_refinement_parsed(content, FALLBACK)
        assert refined.startswith("Identify which vessels") and parsed


class TestFallbackIsReported:
    @pytest.mark.parametrize("content", ["", "   ", "**\n\n>\n---", "Refined PIR:"])
    def test_nothing_usable_is_unparsed(self, content):
        refined, _, parsed = _split_refinement_parsed(content, FALLBACK)
        assert (refined, parsed) == (FALLBACK, False)

    def test_the_two_tuple_wrapper_agrees(self):
        content = f"Revised PIR: {REQ}\nMore."
        assert _split_refinement(content, FALLBACK) == _split_refinement_parsed(content, FALLBACK)[:2]


# ---------------------------------------------------------------------------
# R-7: `refined_text` was written once, including the fallback, and never
# corrected. It is now written only on success, and a later success replaces
# a stored fallback.
# ---------------------------------------------------------------------------

class _Provider:
    def __init__(self, *replies):
        self._replies = list(replies)

    def name(self):
        return "fake"

    async def generate(self, messages, system="", temperature=0.3, max_tokens=4096):
        from types import SimpleNamespace

        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(content=reply, model="fake")


def _run_from_pir(monkeypatch, pir, provider):
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from intel_platform.api.routes import collection_plans as cp
    from intel_platform.api.routes import llm as llm_routes
    from intel_platform.api.routes import pirs as pirs_routes

    monkeypatch.setattr(pirs_routes, "get_or_create_pir", AsyncMock(return_value=pir))
    monkeypatch.setattr(llm_routes, "_get_collection_provider", AsyncMock(return_value=provider))
    db = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    req = cp.SubmitPIRRequest(project_id="p1", pir=pir.text)
    return asyncio.run(cp.create_plan_from_pir(req, db=db))


def _pir(refined_text=""):
    from types import SimpleNamespace
    import uuid

    return SimpleNamespace(
        id=uuid.uuid4(), text="Who is cutting the Baltic cables?",
        refined_text=refined_text, eeis=["already decomposed"],
    )


class TestRefinedTextIsWrittenOnSuccessOnly:
    PLAN = "1. [web_scrape] Something\n   CONFIG: {\"url\": \"https://example.com\"}"

    def test_a_failed_refinement_writes_nothing(self, monkeypatch):
        pir = _pir()
        _run_from_pir(monkeypatch, pir, _Provider(TimeoutError(), self.PLAN))
        assert pir.refined_text == "", "the original text must not be stored as its own refinement"

    def test_an_unusable_refinement_writes_nothing(self, monkeypatch):
        pir = _pir()
        _run_from_pir(monkeypatch, pir, _Provider("### 1. Assessment\nToo broad.\n", self.PLAN))
        assert pir.refined_text == ""

    def test_a_success_replaces_a_stored_fallback(self, monkeypatch):
        pir = _pir(refined_text="Who is cutting the Baltic cables?")   # the old fallback
        _run_from_pir(monkeypatch, pir, _Provider(f"Refined PIR: {REQ}\nAnalysis.", self.PLAN))
        assert pir.refined_text == REQ

    def test_a_success_fills_an_empty_one(self, monkeypatch):
        pir = _pir()
        _run_from_pir(monkeypatch, pir, _Provider(f"Refined PIR: {REQ}\nAnalysis.", self.PLAN))
        assert pir.refined_text == REQ

    def test_an_existing_real_refinement_is_kept(self, monkeypatch):
        pir = _pir(refined_text="An analyst's own wording of the requirement.")
        _run_from_pir(monkeypatch, pir, _Provider(f"Refined PIR: {REQ}\nAnalysis.", self.PLAN))
        assert pir.refined_text == "An analyst's own wording of the requirement."

    def test_elements_in_an_unlabelled_reply_are_still_captured(self, monkeypatch):
        """No requirement could be read, but the decomposition is still there."""
        pir = _pir()
        pir.eeis = []
        reply = (
            "### 1. Assessment\nToo broad.\n\n"
            "### 3. Essential Elements of Information\n"
            "1. Which vessels loitered over the cable before each break?\n"
            "2. Which states have claimed or denied responsibility?\n"
        )
        _run_from_pir(monkeypatch, pir, _Provider(reply, self.PLAN))
        assert pir.refined_text == ""
        assert len(pir.eeis) == 2

    def test_a_failed_refinement_is_reported(self, monkeypatch):
        body = _run_from_pir(monkeypatch, _pir(), _Provider("### 1. Assessment\nToo broad.\n", self.PLAN))
        assert any("refinement" in f for f in body["generation_failures"])
