from __future__ import annotations

import re

from intel_platform.services.text_utils import strip_markup

_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, preserving the delimiter at the end of each."""
    parts = _SENTENCE_END_RE.split(text)
    return [s.strip() for s in parts if s.strip()]


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> list[str]:
    if not text.strip():
        return []
    if len(text) <= chunk_size:
        return [text]

    # Split by paragraphs first
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks: list[str] = []
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= chunk_size:
            current_chunk = f"{current_chunk}\n\n{para}" if current_chunk else para
        else:
            if current_chunk:
                chunks.append(current_chunk)
            # If single paragraph exceeds chunk_size, split at sentence
            # boundaries first; fall back to word-level splitting
            if len(para) > chunk_size:
                sentences = _split_sentences(para)
                # If sentence splitting didn't help (no boundaries found),
                # fall back to word-level splitting
                if len(sentences) <= 1:
                    words = para.split()
                    sub_chunk = ""
                    for word in words:
                        if len(sub_chunk) + len(word) + 1 > chunk_size:
                            if sub_chunk:
                                chunks.append(sub_chunk)
                            sub_chunk = sub_chunk[-overlap:] + " " + word if overlap and sub_chunk else word
                        else:
                            sub_chunk = f"{sub_chunk} {word}" if sub_chunk else word
                    current_chunk = sub_chunk
                else:
                    sub_chunk = ""
                    for sentence in sentences:
                        if len(sub_chunk) + len(sentence) + 1 > chunk_size:
                            if sub_chunk:
                                chunks.append(sub_chunk)
                            # Overlap: carry the last N chars into the next chunk
                            if overlap and sub_chunk:
                                sub_chunk = sub_chunk[-overlap:] + " " + sentence
                            else:
                                sub_chunk = sentence
                        else:
                            sub_chunk = f"{sub_chunk} {sentence}" if sub_chunk else sentence
                    current_chunk = sub_chunk
            else:
                current_chunk = para

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def ingest_text(text: str, chunk_size: int = 1200, overlap: int = 200, source_url: str = "") -> list[dict]:
    """Chunk text for storage and embedding.

    Markup is stripped before chunking, not after: the chunk boundaries, the
    embeddings and the stored text all then describe prose rather than link
    syntax. Collected pages arrive as markdown, and 36% of the characters in a
    retrieved chunk were `[text](url)` and `[[27]](url)` machinery — context
    budget spent on URLs, and embeddings partly driven by URL tokens.
    """
    chunks = chunk_text(strip_markup(text), chunk_size=chunk_size, overlap=overlap)
    return [
        {"content": chunk, "chunk_index": i, "total_chunks": len(chunks), "source_url": source_url}
        for i, chunk in enumerate(chunks)
    ]


def ingest_pdf_bytes(pdf_bytes: bytes, chunk_size: int = 1200, overlap: int = 200, source_url: str = "") -> list[dict]:
    from pypdf import PdfReader
    from io import BytesIO
    reader = PdfReader(BytesIO(pdf_bytes))
    full_text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    return ingest_text(full_text, chunk_size=chunk_size, overlap=overlap, source_url=source_url)


def process_file(filename: str, file_bytes: bytes, chunk_size: int = 1200, overlap: int = 200) -> list[dict]:
    """Auto-detect file type and process accordingly."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "pdf":
        return ingest_pdf_bytes(file_bytes, chunk_size=chunk_size, overlap=overlap)
    else:
        # txt, md, csv, and any other text format
        text = file_bytes.decode("utf-8", errors="replace")
        return ingest_text(text, chunk_size=chunk_size, overlap=overlap)
