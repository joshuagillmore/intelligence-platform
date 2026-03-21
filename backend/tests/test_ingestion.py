from intel_platform.services.ingestion import chunk_text, ingest_text, process_file


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


def test_chunk_text_empty():
    chunks = chunk_text("", chunk_size=2000, overlap=50)
    assert chunks == []
    chunks2 = chunk_text("   ", chunk_size=2000, overlap=50)
    assert chunks2 == []


def test_chunk_text_paragraph_aware():
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    chunks = chunk_text(text, chunk_size=2000, overlap=50)
    assert len(chunks) == 1
    assert "First paragraph." in chunks[0]
    assert "Second paragraph." in chunks[0]


def test_chunk_text_paragraph_split():
    para1 = "A " * 600
    para2 = "B " * 600
    para3 = "C " * 600
    text = f"{para1}\n\n{para2}\n\n{para3}"
    chunks = chunk_text(text, chunk_size=1500, overlap=50)
    assert len(chunks) >= 2


def test_chunk_text_overlap():
    text = "word " * 1000
    chunks = chunk_text(text, chunk_size=200, overlap=50)
    assert len(chunks) > 1


def test_ingest_text():
    result = ingest_text("This is a test document about threat actors.", chunk_size=2000, overlap=50)
    assert len(result) >= 1
    assert result[0]["content"] == "This is a test document about threat actors."
    assert result[0]["chunk_index"] == 0


def test_ingest_text_with_metadata():
    result = ingest_text("Test content", chunk_size=2000, overlap=50, source_url="https://example.com")
    assert result[0]["source_url"] == "https://example.com"


def test_process_file_txt():
    content = b"Hello world. This is a test file."
    chunks = process_file("test.txt", content)
    assert len(chunks) >= 1
    assert "Hello world" in chunks[0]["content"]


def test_process_file_md():
    content = b"# Header\n\nSome markdown content.\n\n## Section 2\n\nMore content."
    chunks = process_file("readme.md", content)
    assert len(chunks) >= 1
    assert "Header" in chunks[0]["content"]
