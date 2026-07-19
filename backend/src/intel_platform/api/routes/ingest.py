from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.config import settings
from intel_platform.graph.store import GraphStore
from intel_platform.models.entities import Document
from intel_platform.services.ingestion import ingest_text, process_file
from intel_platform.services.extraction import extract_entities_nlp
from intel_platform.services.graph_builder import build_graph_from_extractions

router = APIRouter(dependencies=[Depends(verify_api_key)])


async def _extract(text: str, doc_id: str, mode: str):
    """Run extraction based on configured mode."""
    if mode == "llm":
        from intel_platform.services.extraction import extract_entities_llm
        return await extract_entities_llm(text, doc_id)
    elif mode == "hybrid":
        from intel_platform.services.extraction import extract_entities_hybrid
        return await extract_entities_hybrid(text, doc_id)
    else:
        return extract_entities_nlp(text, doc_id)


@router.post("/ingest")
async def ingest_document(
    project_id: str = Form(...),
    content: str | None = Form(None),
    file: UploadFile | None = File(None),
    reliability_rating: str = Form("C3"),
    extraction_mode: str | None = Form(None),
    store: GraphStore = Depends(get_graph_store),
):
    # None -> the configured default (hybrid). Explicit value still honored.
    extraction_mode = extraction_mode or settings.extraction_mode
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS = {'.pdf', '.txt', '.md', '.csv', '.json'}

    if file:
        # Check extension
        ext = '.' + (file.filename or '').rsplit('.', 1)[-1].lower() if '.' in (file.filename or '') else ''
        if ext and ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"File type {ext} not supported. Allowed: {ALLOWED_EXTENSIONS}")

        file_bytes = await file.read()

        # Check size
        if len(file_bytes) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB")

        # Sanitize filename
        import re
        safe_name = re.sub(r'[^\w\-.]', '_', file.filename or 'upload')

        chunks = process_file(safe_name, file_bytes, settings.chunk_size, settings.chunk_overlap)
        source_name = safe_name
    elif content:
        chunks = ingest_text(content, settings.chunk_size, settings.chunk_overlap)
        source_name = "text_input"
    else:
        raise HTTPException(status_code=400, detail="Provide either content or file")

    doc = Document(
        name=source_name,
        content="\n".join(c["content"] for c in chunks),
        reliability_rating=reliability_rating,
        project_id=project_id,
    )
    store.create_entity(doc)

    all_entities = []
    all_relationships = []
    for chunk in chunks:
        entities, relationships = await _extract(chunk["content"], doc.id, extraction_mode)
        all_entities.extend(entities)
        all_relationships.extend(relationships)

    result = build_graph_from_extractions(store, all_entities, all_relationships, project_id, source_doc_id=doc.id)

    # Embed chunks for vector search (non-fatal if it fails)
    embeddings_stored = 0
    try:
        from intel_platform.db.engine import get_session_factory
        from intel_platform.services.vector_search import embed_and_store_chunks
        async with get_session_factory()() as db_session:
            embeddings_stored = await embed_and_store_chunks(chunks, doc.id, project_id, db_session)
            await db_session.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).warning("Embedding failed for %s — document still ingested", doc.id, exc_info=True)

    return {"document_id": doc.id, "document_name": source_name, "chunks": len(chunks), "embeddings_stored": embeddings_stored, **result}


@router.post("/ingest/batch")
async def ingest_batch(
    project_id: str = Form(...),
    files: list[UploadFile] = File(...),
    reliability_rating: str = Form("C3"),
    extraction_mode: str | None = Form(None),
    store: GraphStore = Depends(get_graph_store),
):
    extraction_mode = extraction_mode or settings.extraction_mode
    import re
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS = {'.pdf', '.txt', '.md', '.csv', '.json'}

    results = []
    total_entities = 0
    total_relationships = 0

    for file in files:
        # Check extension
        ext = '.' + (file.filename or '').rsplit('.', 1)[-1].lower() if '.' in (file.filename or '') else ''
        if ext and ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"File type {ext} not supported. Allowed: {ALLOWED_EXTENSIONS}")

        file_bytes = await file.read()

        # Check size
        if len(file_bytes) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"File too large: {file.filename}. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB")

        # Sanitize filename
        safe_name = re.sub(r'[^\w\-.]', '_', file.filename or 'upload')

        chunks = process_file(safe_name, file_bytes, settings.chunk_size, settings.chunk_overlap)
        source_name = safe_name

        doc = Document(
            name=source_name,
            content="\n".join(c["content"] for c in chunks),
            reliability_rating=reliability_rating,
            project_id=project_id,
        )
        store.create_entity(doc)

        all_entities = []
        all_relationships = []
        for chunk in chunks:
            entities, relationships = await _extract(chunk["content"], doc.id, extraction_mode)
            all_entities.extend(entities)
            all_relationships.extend(relationships)

        build_result = build_graph_from_extractions(store, all_entities, all_relationships, project_id, source_doc_id=doc.id)
        total_entities += build_result["entities_created"]
        total_relationships += build_result["relationships_created"]

        # Embed chunks for vector search (non-fatal)
        embeddings_stored = 0
        try:
            from intel_platform.db.engine import get_session_factory
            from intel_platform.services.vector_search import embed_and_store_chunks
            async with get_session_factory()() as db_session:
                embeddings_stored = await embed_and_store_chunks(chunks, doc.id, project_id, db_session)
                await db_session.commit()
        except Exception:
            pass

        results.append({
            "document_id": doc.id,
            "document_name": source_name,
            "chunks": len(chunks),
            "embeddings_stored": embeddings_stored,
            **build_result,
        })

    return {
        "documents_processed": len(results),
        "total_entities_created": total_entities,
        "total_relationships_created": total_relationships,
        "results": results,
    }
