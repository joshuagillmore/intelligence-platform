from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import Optional

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
    content: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    reliability_rating: str = Form("C3"),
    extraction_mode: str = Form("nlp"),
    store: GraphStore = Depends(get_graph_store),
):
    if file:
        file_bytes = await file.read()
        chunks = process_file(file.filename or "upload", file_bytes, settings.chunk_size, settings.chunk_overlap)
        source_name = file.filename or "uploaded_file"
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

    result = build_graph_from_extractions(store, all_entities, all_relationships, project_id)
    return {"document_id": doc.id, "document_name": source_name, "chunks": len(chunks), **result}


@router.post("/ingest/batch")
async def ingest_batch(
    project_id: str = Form(...),
    files: list[UploadFile] = File(...),
    reliability_rating: str = Form("C3"),
    extraction_mode: str = Form("nlp"),
    store: GraphStore = Depends(get_graph_store),
):
    results = []
    total_entities = 0
    total_relationships = 0

    for file in files:
        file_bytes = await file.read()
        chunks = process_file(file.filename or "upload", file_bytes, settings.chunk_size, settings.chunk_overlap)
        source_name = file.filename or "uploaded_file"

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

        build_result = build_graph_from_extractions(store, all_entities, all_relationships, project_id)
        total_entities += build_result["entities_created"]
        total_relationships += build_result["relationships_created"]

        results.append({
            "document_id": doc.id,
            "document_name": source_name,
            "chunks": len(chunks),
            **build_result,
        })

    return {
        "documents_processed": len(results),
        "total_entities_created": total_entities,
        "total_relationships_created": total_relationships,
        "results": results,
    }
