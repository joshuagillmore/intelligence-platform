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
