from __future__ import annotations


def chunk_text(text: str, chunk_size: int = 2000, overlap: int = 50) -> list[str]:
    if not text.strip():
        return []
    if len(text) <= chunk_size:
        return [text]

    # Split by paragraphs first
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= chunk_size:
            current_chunk = f"{current_chunk}\n\n{para}" if current_chunk else para
        else:
            if current_chunk:
                chunks.append(current_chunk)
            # If single paragraph exceeds chunk_size, split it
            if len(para) > chunk_size:
                words = para.split()
                sub_chunk = ""
                for word in words:
                    if len(sub_chunk) + len(word) + 1 > chunk_size:
                        chunks.append(sub_chunk)
                        # Overlap: take last N chars
                        sub_chunk = sub_chunk[-overlap:] + " " + word if overlap else word
                    else:
                        sub_chunk = f"{sub_chunk} {word}" if sub_chunk else word
                current_chunk = sub_chunk
            else:
                current_chunk = para

    if current_chunk:
        chunks.append(current_chunk)

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


def process_file(filename: str, file_bytes: bytes, chunk_size: int = 2000, overlap: int = 50) -> list[dict]:
    """Auto-detect file type and process accordingly."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "pdf":
        return ingest_pdf_bytes(file_bytes, chunk_size=chunk_size, overlap=overlap)
    else:
        # txt, md, csv, and any other text format
        text = file_bytes.decode("utf-8", errors="replace")
        return ingest_text(text, chunk_size=chunk_size, overlap=overlap)
