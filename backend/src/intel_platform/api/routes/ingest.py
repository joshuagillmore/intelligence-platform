import asyncio
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.config import settings
from intel_platform.graph.store import GraphStore
from intel_platform.models.responses import (
    BatchIngestResponse,
    IngestResponse,
)
from intel_platform.models.entities import Document
from intel_platform.services.ingestion import ingest_text, process_file
from intel_platform.services.extraction import extract_entities_nlp
from intel_platform.services.graph_builder import build_graph_from_extractions
from intel_platform.services.telemetry import record_degraded

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {'.pdf', '.txt', '.md', '.csv', '.json'}
# Name given to pasted text when the caller does not supply `source_name`.
DEFAULT_TEXT_SOURCE_NAME = "text_input"
MAX_SOURCE_NAME_CHARS = 256


def _text_source_name(source_name: str | None) -> str:
    """The analyst's name for pasted text: whitespace collapsed, bounded, or the default."""
    name = " ".join((source_name or "").split())[:MAX_SOURCE_NAME_CHARS].strip()
    return name or DEFAULT_TEXT_SOURCE_NAME

# Everything below that parses, runs spaCy or talks to Neo4j is synchronous, and
# these handlers run on the event loop that also serves /health and every other
# request, so each such call goes through asyncio.to_thread (contract 15).


async def _extract(text: str, doc_id: str, mode: str):
    """Run extraction based on configured mode."""
    if mode == "llm":
        from intel_platform.services.extraction import extract_entities_llm
        return await extract_entities_llm(text, doc_id)
    elif mode == "hybrid":
        from intel_platform.services.extraction import extract_entities_hybrid
        return await extract_entities_hybrid(text, doc_id)
    else:
        return await asyncio.to_thread(extract_entities_nlp, text, doc_id)


def _extension(filename: str | None) -> str:
    return '.' + (filename or '').rsplit('.', 1)[-1].lower() if '.' in (filename or '') else ''


async def _read_upload(file: UploadFile) -> tuple[str, bytes]:
    """Validate one upload and return its sanitised name and bytes.

    Reads at most one byte past the limit, so an oversized upload is refused
    without being held in memory whole.
    """
    ext = _extension(file.filename)
    if ext and ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type {ext} not supported. Allowed: {ALLOWED_EXTENSIONS}")
    file_bytes = await file.read(MAX_FILE_SIZE + 1)
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large: {file.filename}. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB",
        )
    return re.sub(r'[^\w\-.]', '_', file.filename or 'upload'), file_bytes


def _bound_chunks(chunks: list[dict], max_chars: int) -> tuple[list[dict], bool]:
    """Keep chunks, in order, until the stored document would exceed `max_chars`.

    The same bound collection applies (`agentic.py`), for the same reasons: it
    caps the sequential extraction calls one document can cost, and it keeps
    every extracted entity's evidence inside the document that is stored,
    because the document is built from exactly the chunks that are extracted.
    """
    kept: list[dict] = []
    used = 0
    for chunk in chunks:
        separator = 1 if kept else 0  # the "\n" the document is joined with
        room = max_chars - used - separator
        if room <= 0:
            break
        text = chunk["content"]
        if len(text) > room:
            kept.append({**chunk, "content": text[:room]})
            break
        kept.append(chunk)
        used += separator + len(text)
    truncated = len(kept) < len(chunks) or (bool(kept) and kept[-1]["content"] != chunks[len(kept) - 1]["content"])
    if truncated:
        kept = [{**c, "total_chunks": len(kept)} if "total_chunks" in c else c for c in kept]
    return kept, truncated


async def _ingest_chunks(
    store: GraphStore, chunks: list[dict], source_name: str, project_id: str,
    reliability_rating: str, extraction_mode: str,
) -> dict:
    """Store one document built from its chunks, extract, build the graph, embed."""
    chunks, content_truncated = _bound_chunks(chunks, settings.max_document_chars)
    if content_truncated:
        logger.info("Truncated %s to %d chars for storage and extraction", source_name, settings.max_document_chars)

    doc = Document(
        name=source_name,
        content="\n".join(c["content"] for c in chunks),
        reliability_rating=reliability_rating,
        project_id=project_id,
    )
    await asyncio.to_thread(store.create_entity, doc)

    all_entities = []
    all_relationships = []
    for chunk in chunks:
        extraction = await _extract(chunk["content"], doc.id, extraction_mode)
        entities, relationships = extraction
        # ExtractionResult says when the requested method failed and this chunk
        # is the NLP fallback; a plain tuple (older callers, tests) never is.
        if getattr(extraction, "degraded", False):
            record_degraded("extraction", getattr(extraction, "reason", "") or "degraded", detail=doc.id)
        all_entities.extend(entities)
        all_relationships.extend(relationships)

    result = await asyncio.to_thread(
        build_graph_from_extractions, store, all_entities, all_relationships, project_id, source_doc_id=doc.id,
    )

    # Embed chunks for vector search (non-fatal, but never silent — a document
    # in the graph and not the index is findable by name and invisible to
    # meaning, and `embeddings_stored: 0` alone cannot be told apart from a
    # document that had nothing to embed).
    embeddings_stored = 0
    indexed = True
    try:
        from intel_platform.db.engine import get_session_factory
        from intel_platform.services.vector_search import embed_and_store_chunks
        async with get_session_factory()() as db_session:
            embeddings_stored = await embed_and_store_chunks(chunks, doc.id, project_id, db_session)
            await db_session.commit()
        indexed = bool(embeddings_stored) or not chunks
    except Exception as exc:
        indexed = False
        logger.warning(
            "Embedding failed for %s — document is in the graph but will not be "
            "findable by semantic search", source_name, exc_info=True,
        )
        record_degraded("embeddings", "store_unavailable", detail=type(exc).__name__)

    return {
        "document_id": doc.id,
        "document_name": source_name,
        "chunks": len(chunks),
        "content_truncated": content_truncated,
        "embeddings_stored": embeddings_stored,
        "indexed_for_search": indexed,
        **result,
    }


@router.post("/ingest", response_model=IngestResponse, response_model_exclude_unset=True)
async def ingest_document(
    project_id: str = Form(...),
    content: str | None = Form(None),
    file: UploadFile | None = File(None),
    reliability_rating: str = Form("C3"),
    extraction_mode: str | None = Form(None),
    # The document's name when `content` is pasted text (default "text_input").
    # An uploaded file is always named by its filename.
    source_name: str | None = Form(None),
    store: GraphStore = Depends(get_graph_store),
):
    # None -> the configured default (hybrid). Explicit value still honored.
    extraction_mode = extraction_mode or settings.extraction_mode

    if file:
        source_name, file_bytes = await _read_upload(file)
        chunks = await asyncio.to_thread(
            process_file, source_name, file_bytes, settings.chunk_size, settings.chunk_overlap,
        )
    elif content:
        chunks = await asyncio.to_thread(ingest_text, content, settings.chunk_size, settings.chunk_overlap)
        source_name = _text_source_name(source_name)
    else:
        raise HTTPException(status_code=400, detail="Provide either content or file")

    return await _ingest_chunks(store, chunks, source_name, project_id, reliability_rating, extraction_mode)


@router.post("/ingest/batch", response_model=BatchIngestResponse, response_model_exclude_unset=True)
async def ingest_batch(
    project_id: str = Form(...),
    files: list[UploadFile] = File(...),
    reliability_rating: str = Form("C3"),
    extraction_mode: str | None = Form(None),
    store: GraphStore = Depends(get_graph_store),
):
    extraction_mode = extraction_mode or settings.extraction_mode

    # Every file is validated before any is written. Checking inside the write
    # loop stored files 1-2 and then refused file 3, so the obvious retry
    # duplicated the first two.
    uploads = [await _read_upload(file) for file in files]

    results = []
    total_entities = 0
    total_relationships = 0
    for source_name, file_bytes in uploads:
        chunks = await asyncio.to_thread(
            process_file, source_name, file_bytes, settings.chunk_size, settings.chunk_overlap,
        )
        result = await _ingest_chunks(store, chunks, source_name, project_id, reliability_rating, extraction_mode)
        total_entities += result["entities_created"]
        total_relationships += result["relationships_created"]
        results.append(result)

    return {
        "documents_processed": len(results),
        "total_entities_created": total_entities,
        "total_relationships_created": total_relationships,
        "results": results,
    }
