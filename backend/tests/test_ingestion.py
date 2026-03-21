from intel_platform.services.ingestion import chunk_text, ingest_text


def test_chunk_text_basic():
    text = "word " * 1000
    chunks = chunk_text(text, chunk_size=2000, overlap=50)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 2100


def test_chunk_text_small():
    text = "Short text."
    chunks = chunk_text(text, chunk_size=2000, overlap=50)
    assert len(chunks) == 1
    assert chunks[0] == "Short text."


def test_chunk_text_overlap():
    text = "word " * 1000
    chunks = chunk_text(text, chunk_size=200, overlap=50)
    if len(chunks) > 1:
        end_of_first = chunks[0][-50:]
        assert end_of_first in chunks[1]


def test_ingest_text():
    result = ingest_text("This is a test document about threat actors.", chunk_size=2000, overlap=50)
    assert len(result) >= 1
    assert result[0]["content"] == "This is a test document about threat actors."
    assert result[0]["chunk_index"] == 0


def test_ingest_text_with_metadata():
    result = ingest_text("Test content", chunk_size=2000, overlap=50, source_url="https://example.com")
    assert result[0]["source_url"] == "https://example.com"
