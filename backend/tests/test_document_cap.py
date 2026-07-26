"""One bound governs both what a crawled document stores and what is extracted.

A live crawl returned a 139,391-word page. Extraction chunked the whole thing —
hundreds of sequential LLM calls — and the collection stalled with a single
entity. Separately, the Document stored only the first 50k chars, so any entity
found past that mark referenced a document that no longer contained its
evidence and "Show Evidence" could never resolve it.
"""
from __future__ import annotations

from intel_platform.config import Settings
from intel_platform.services.ingestion import ingest_text


class TestSetting:
    def test_default_cap_is_present(self):
        assert Settings().max_document_chars == 50000

    def test_cap_is_configurable(self):
        assert Settings(max_document_chars=10000).max_document_chars == 10000


class TestChunkingUnderTheCap:
    """The cap is what keeps chunk count — and so LLM calls — bounded."""

    @staticmethod
    def _chunks(text: str, cap: int) -> int:
        return len(ingest_text(text[:cap], 1200, 200))

    def test_huge_page_is_bounded(self):
        huge = "Houthi forces struck a vessel in the Red Sea. " * 20000  # ~900k chars
        assert len(huge) > 500_000
        capped = self._chunks(huge, 50_000)
        uncapped = len(ingest_text(huge, 1200, 200))
        assert capped < uncapped
        # Each chunk is one extraction call, so this is the difference between a
        # collection that finishes and one that stalls.
        assert capped <= 60, f"{capped} chunks still too many"

    def test_small_document_is_untouched(self):
        small = "Houthi forces struck the MV Northern Star on 12 March 2026."
        assert self._chunks(small, 50_000) == len(ingest_text(small, 1200, 200))


class TestProvenanceHolds:
    """Everything extracted must sit inside what the document kept."""

    def test_extracted_text_is_within_stored_text(self):
        cap = 2000
        # "Alpha. " is 7 chars, so the marker lands at 3500 — comfortably past
        # the cap, which is the case this test exists to pin.
        content = ("Alpha. " * 500) + "SENTINEL_MARKER_BEYOND_CAP " + ("Beta. " * 500)
        assert content.index("SENTINEL_MARKER_BEYOND_CAP") > cap
        stored = content[:cap]
        chunks = ingest_text(stored, 1200, 200)
        joined = " ".join(c["content"] for c in chunks)
        # The marker sits past the cap, so it must be in neither.
        assert "SENTINEL_MARKER_BEYOND_CAP" not in stored
        assert "SENTINEL_MARKER_BEYOND_CAP" not in joined

    def test_every_chunk_is_a_substring_of_the_stored_document(self):
        stored = ("Houthi forces struck a vessel. " * 200)[:5000]
        for chunk in ingest_text(stored, 1200, 200):
            assert chunk["content"] in stored
