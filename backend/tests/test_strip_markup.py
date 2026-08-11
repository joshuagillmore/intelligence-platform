"""Markdown stripped from text before it is chunked, embedded, or shown.

Collected pages arrive as markdown. Measured on eight chunks retrieved for a
real question: 31,060 characters, of which 11,424 (36%) were markup — 120
`[text](url)` constructs, 88 `[[27]](url)` citation markers and 12 `[edit]`
links. That is context budget spent on URLs, embeddings partly driven by URL
tokens, and evidence panels showing an analyst link syntax mid-sentence.

Conservative by design: link *text* survives, because "[NATO](url)" means NATO.
"""
from __future__ import annotations

import pytest

from intel_platform.services.text_utils import strip_markup


class TestWhatIsRemoved:
    def test_a_link_keeps_its_text_and_loses_its_url(self):
        got = strip_markup('[NATO](https://en.wikipedia.org/wiki/NATO "NATO") member states')
        assert got == "NATO member states"

    def test_a_citation_marker_goes_entirely(self):
        """The number refers to a reference list that is not in the chunk."""
        got = strip_markup("disruptions.[[27]](https://en.wikipedia.org/wiki/X#cite_note-eju-27)")
        assert got == "disruptions."

    def test_a_wrapped_edit_link_leaves_no_empty_brackets(self):
        got = strip_markup("[[edit](https://en.wikipedia.org/w/index.php?title=X&action=edit)]")
        assert got == ""

    def test_headings_lose_their_hashes_and_keep_their_words(self):
        assert strip_markup("## Suspicious ships") == "Suspicious ships"
        assert strip_markup("###### Deep heading") == "Deep heading"

    def test_blockquote_markers_go(self):
        assert strip_markup("> quoted claim") == "quoted claim"

    def test_emphasis_is_removed(self):
        assert strip_markup("came under **investigation**") == "came under investigation"
        assert strip_markup("the _Yi Peng 3_ vessel") == "the Yi Peng 3 vessel"

    def test_an_image_is_treated_like_a_link(self):
        assert strip_markup("![satellite view](https://x/y.png)") == "satellite view"

    def test_a_link_truncated_by_chunking_still_yields_its_text(self):
        """Chunk boundaries cut mid-link constantly at 1,200 characters."""
        assert strip_markup("A [truncated link](https://example.com/very/long") == "A truncated link"

    def test_a_chunk_that_begins_inside_a_url_drops_the_debris(self):
        got = strip_markup('://en.wikipedia.org/wiki/Baltic_Sea "Baltic Sea"). The incidents occurred')
        assert got == "The incidents occurred"


class TestWhatIsPreserved:
    @pytest.mark.parametrize("text", [
        "Plain prose with no markup at all.",
        "The Yi Peng 3 was investigated by Swedish authorities.",
        "Costs rose 20_30 percent",
    ])
    def test_prose_is_untouched(self, text):
        assert strip_markup(text) == text

    def test_snake_case_survives(self):
        """Italic stripping must not eat identifiers."""
        got = strip_markup("the chunk_text column and vector_search module")
        assert got == "the chunk_text column and vector_search module"

    def test_a_bare_url_in_prose_is_kept(self):
        """Only link *syntax* goes; a URL an author wrote out is content."""
        got = strip_markup("See https://example.com/report for detail")
        assert "https://example.com/report" in got

    def test_paragraph_breaks_survive(self):
        assert strip_markup("First para.\n\nSecond para.") == "First para.\n\nSecond para."

    def test_hash_inside_a_line_is_not_a_heading(self):
        assert strip_markup("issue #27 was raised") == "issue #27 was raised"


class TestEdges:
    @pytest.mark.parametrize("empty", ["", "   ", None])
    def test_empty_input_is_empty_output(self, empty):
        assert strip_markup(empty) == ""

    def test_stripping_is_idempotent(self):
        """It runs at ingestion and again on retrieval, so old chunks benefit
        without double-cleaning new ones into something different."""
        once = strip_markup('[NATO](https://x "NATO") said **no**.[[3]](https://y)')
        assert strip_markup(once) == once

    def test_a_chunk_of_pure_markup_becomes_empty_not_garbage(self):
        assert strip_markup("[[1]](https://a) [[2]](https://b)") == ""


class TestOnRealRetrievedText:
    """The shape that produced the 36% measurement."""

    SAMPLE = (
        '://en.wikipedia.org/wiki/Baltic_Sea "Baltic Sea"). The incidents involving both '
        'cables occurred in close proximity to each other and near-simultaneously, which '
        'prompted accusations from [European](https://en.wikipedia.org/wiki/European_Union '
        '"European Union") government officials and [NATO](https://en.wikipedia.org/wiki/NATO '
        '"NATO") member states of [hybrid warfare](https://en.wikipedia.org/wiki/Hybrid_warfare '
        '"Hybrid warfare").[[27]](https://en.wikipedia.org/wiki/X#cite_note-eju-27)'
    )

    def test_the_prose_survives_intact(self):
        got = strip_markup(self.SAMPLE)
        for phrase in ["European", "NATO", "hybrid warfare", "near-simultaneously"]:
            assert phrase in got

    def test_the_syntax_is_gone(self):
        got = strip_markup(self.SAMPLE)
        for junk in ["](", "https://", "[[27]]", "wikipedia.org"]:
            assert junk not in got

    def test_it_is_substantially_shorter(self):
        got = strip_markup(self.SAMPLE)
        assert len(got) < len(self.SAMPLE) * 0.5
