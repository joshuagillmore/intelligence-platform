from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.config import settings
from intel_platform.graph.store import GraphStore
from intel_platform.models.entities import Document
from intel_platform.services.ingestion import ingest_text, ingest_pdf_bytes
from intel_platform.services.extraction import extract_entities_nlp
from intel_platform.services.graph_builder import build_graph_from_extractions

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.post("/ingest")
async def ingest_document(
    project_id: str = Form(...),
    content: str | None = Form(None),
    file: UploadFile | None = File(None),
    reliability_rating: str = Form("C3"),
    store: GraphStore = Depends(get_graph_store),
):
    if file:
        file_bytes = await file.read()
        if file.filename and file.filename.lower().endswith(".pdf"):
            chunks = ingest_pdf_bytes(file_bytes, settings.chunk_size, settings.chunk_overlap)
        else:
            text = file_bytes.decode("utf-8")
            chunks = ingest_text(text, settings.chunk_size, settings.chunk_overlap)
        source_name = file.filename or "uploaded_file"
    elif content:
        chunks = ingest_text(content, settings.chunk_size, settings.chunk_overlap)
        source_name = "text_input"
    else:
        raise HTTPException(status_code=400, detail="Provide either content or file")

    doc = Document(
        name=source_name, content="\n".join(c["content"] for c in chunks),
        reliability_rating=reliability_rating, project_id=project_id,
    )
    store.create_entity(doc)

    all_entities = []
    all_relationships = []
    for chunk in chunks:
        entities, relationships = extract_entities_nlp(chunk["content"], doc_id=doc.id)
        all_entities.extend(entities)
        all_relationships.extend(relationships)

    result = build_graph_from_extractions(store, all_entities, all_relationships, project_id)
    return {"document_id": doc.id, "chunks": len(chunks), **result}
