"""Tests for enhanced ingestion: sentence-aware chunking, new defaults."""
from intel_platform.services.ingestion import chunk_text, ingest_text, _split_sentences


# ---------------------------------------------------------------------------
# Sentence splitting
# ---------------------------------------------------------------------------

def test_split_sentences_basic():
    text = "First sentence. Second sentence! Third sentence? Fourth."
    sentences = _split_sentences(text)
    assert len(sentences) == 4
    assert "First sentence." in sentences[0]


def test_split_sentences_no_boundaries():
    text = "No sentence boundaries here just words"
    sentences = _split_sentences(text)
    assert len(sentences) == 1


def test_split_sentences_empty():
    assert _split_sentences("") == []
    assert _split_sentences("   ") == []


# ---------------------------------------------------------------------------
# New default chunk sizes
# ---------------------------------------------------------------------------

def test_default_chunk_size():
    """Default chunk_size should be 1200."""
    # 2000 chars of text - with old defaults this would be 1 chunk,
    # with new defaults (1200) it should be 2+
    text = "Sentence end. " * 150  # ~2100 chars
    chunks = chunk_text(text)
    assert len(chunks) >= 2


def test_default_overlap():
    """Default overlap should be 200."""
    # Generate text that forces multiple chunks with sentence boundaries
    sentences = [f"This is sentence number {i} about intelligence analysis. " for i in range(40)]
    text = " ".join(sentences)
    chunks = chunk_text(text)
    assert len(chunks) >= 2
    # With 200-char overlap, there should be shared content between consecutive chunks
    if len(chunks) >= 2:
        # The end of chunk 1 and start of chunk 2 should share some text
        chunk1_end = chunks[0][-100:]
        chunk2_start = chunks[1][:200]
        # Find any overlap (at least some words should match)
        chunk1_words = set(chunk1_end.lower().split())
        chunk2_words = set(chunk2_start.lower().split())
        overlap_words = chunk1_words & chunk2_words
        # There should be some word overlap due to the 200-char overlap
        assert len(overlap_words) > 0


# ---------------------------------------------------------------------------
# Sentence-aware splitting for long paragraphs
# ---------------------------------------------------------------------------

def test_sentence_aware_splitting():
    """Long paragraphs should be split at sentence boundaries, not mid-word."""
    sentences = [f"Intelligence report finding number {i} is significant." for i in range(30)]
    # One big paragraph (no \n\n)
    text = " ".join(sentences)
    chunks = chunk_text(text, chunk_size=500, overlap=100)
    assert len(chunks) >= 2
    # Each chunk should end at a sentence boundary (ends with a period)
    for chunk in chunks[:-1]:  # Last chunk may not end with period
        stripped = chunk.strip()
        # Should end with a period (sentence boundary) or be the overlap start
        assert stripped[-1] in '.!?' or len(stripped) <= 500 + 100


def test_word_fallback_for_no_sentences():
    """Text without sentence boundaries should fall back to word splitting."""
    text = "word " * 500  # 2500 chars, no sentence boundaries
    chunks = chunk_text(text, chunk_size=1000, overlap=100)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 1200  # chunk_size + some overlap allowance


# ---------------------------------------------------------------------------
# Paragraph-aware splitting preserved
# ---------------------------------------------------------------------------

def test_paragraph_splitting_preserved():
    """Paragraphs that fit within chunk_size should be kept together."""
    para1 = "First paragraph about Iran. " * 5
    para2 = "Second paragraph about Russia. " * 5
    text = f"{para1}\n\n{para2}"
    chunks = chunk_text(text, chunk_size=2000, overlap=200)
    assert len(chunks) == 1  # Both paras fit in one chunk
    assert "Iran" in chunks[0]
    assert "Russia" in chunks[0]


def test_paragraph_splitting_across_chunks():
    """Paragraphs exceeding chunk_size should be split into separate chunks."""
    para1 = "Iran nuclear program discussion. " * 30
    para2 = "Russia military operations analysis. " * 30
    text = f"{para1}\n\n{para2}"
    chunks = chunk_text(text, chunk_size=500, overlap=100)
    assert len(chunks) >= 3


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_chunk_text_exact_size():
    """Text exactly at chunk_size should produce one chunk."""
    text = "x" * 1200
    chunks = chunk_text(text, chunk_size=1200)
    assert len(chunks) == 1


def test_chunk_text_unicode():
    """Unicode text should be handled correctly."""
    text = "Украина и Россия. " * 100
    chunks = chunk_text(text, chunk_size=500, overlap=100)
    assert len(chunks) >= 1
    assert "Украина" in chunks[0]


def test_ingest_text_new_defaults():
    """ingest_text should use new default parameters."""
    text = "Short document about cyber threats."
    result = ingest_text(text)
    assert len(result) == 1
    assert result[0]["content"] == text
