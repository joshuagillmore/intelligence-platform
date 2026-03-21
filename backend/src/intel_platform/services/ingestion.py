from __future__ import annotations


def chunk_text(text: str, chunk_size: int = 2000, overlap: int = 50) -> list[str]:
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            space_idx = text.rfind(" ", start, end)
            if space_idx > start:
                end = space_idx + 1
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def ingest_text(text: str, chunk_size: int = 2000, overlap: int = 50, source_url: str = "") -> list[dict]:
    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    return [
        {"content": chunk, "chunk_index": i, "total_chunks": len(chunks), "source_url": source_url}
        for i, chunk in enumerate(chunks)
    ]


def ingest_pdf_bytes(pdf_bytes: bytes, chunk_size: int = 2000, overlap: int = 50, source_url: str = "") -> list[dict]:
    from pypdf import PdfReader
    from io import BytesIO
    reader = PdfReader(BytesIO(pdf_bytes))
    full_text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    return ingest_text(full_text, chunk_size=chunk_size, overlap=overlap, source_url=source_url)
