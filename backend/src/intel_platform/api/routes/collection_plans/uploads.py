"""File upload through a collection plan's ``file_upload`` source: parse,
profile, catalogue, then route to the document store and the graph.
"""
from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.api.deps import get_graph_store
from intel_platform.api.routes.collection_plans.plans import _parse_uuid
from intel_platform.config import settings
from intel_platform.connectors.base import get_connector
from intel_platform.connectors.flat_file import detect_format, SUPPORTED_FORMATS
from intel_platform.db.engine import get_db
from intel_platform.db.models import (
    AcquisitionLog,
    CollectionPlan,
    CollectionSource,
    DataCatalog,
    SourceType,
)
from intel_platform.graph.store import GraphStore
from intel_platform.models.entities import Document
from intel_platform.models.responses import FileUploadResponse
from intel_platform.services.extraction import extract_entities_nlp
from intel_platform.services.graph_builder import build_graph_from_extractions
from intel_platform.services.ingestion import ingest_text

# Mounted by the package router, which carries the API-key dependency.
router = APIRouter()


# ---------------------------------------------------------------------------
# File upload → ingest through collection plan
# ---------------------------------------------------------------------------

_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB for structured data
_UPLOAD_CHUNK_BYTES = 1024 * 1024


async def _read_upload_capped(file: UploadFile, cap: int) -> bytes:
    """The upload's bytes, refused with 400 as soon as they pass `cap`.

    `await file.read()` read the whole upload into memory before comparing it
    with the cap, so the cap bounded nothing. Starlette has already spooled the
    request body to a temporary file; this reads it back a chunk at a time and
    stops at the cap, so memory is bounded by the cap rather than by whatever a
    client chose to send. A declared size over the cap is refused without
    reading at all. The whole file is still returned as bytes because the
    file_upload connector parses from bytes.
    """
    too_large = HTTPException(400, f"File too large. Max: {cap // (1024 * 1024)}MB")
    if file.size is not None and file.size > cap:
        raise too_large
    buf = bytearray()
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            return bytes(buf)
        if len(buf) + len(chunk) > cap:
            raise too_large
        buf.extend(chunk)


@router.post("/collection-plans/{plan_id}/sources/{source_id}/upload", response_model=FileUploadResponse)
async def upload_file_to_source(
    plan_id: str,
    source_id: str,
    file: UploadFile = File(...),
    extraction_mode: str = Form("nlp"),
    reliability_rating: str = Form("C3"),
    db: AsyncSession = Depends(get_db),
    store: GraphStore = Depends(get_graph_store),
):
    """Upload a file through a collection plan source → parse → profile → ingest → route to graph."""
    start_time = time.time()

    # Validate plan and source exist
    plan = await db.get(CollectionPlan, _parse_uuid(plan_id, "plan_id"))
    if not plan:
        raise HTTPException(404, "Collection plan not found")

    source = await db.get(CollectionSource, _parse_uuid(source_id, "source_id"))
    if not source or str(source.plan_id) != plan_id:
        raise HTTPException(404, "Source not found")

    if source.source_type != SourceType.FILE_UPLOAD:
        raise HTTPException(400, "Source is not a file_upload type")

    # Read and validate file, refusing an oversized one while reading it.
    file_bytes = await _read_upload_capped(file, _MAX_UPLOAD_BYTES)

    safe_name = re.sub(r'[^\w\-.]', '_', file.filename or 'upload')
    file_format = detect_format(safe_name)

    if file_format not in SUPPORTED_FORMATS:
        raise HTTPException(400, f"Unsupported format: {file_format}. Supported: {SUPPORTED_FORMATS}")

    # Acquire: parse and profile through the connector
    connector = get_connector("file_upload")
    acquire_config = {
        **source.config,
        "file_bytes": file_bytes,
        "filename": safe_name,
        "file_format": file_format,
    }
    result = await connector.acquire(acquire_config)

    if not result.success:
        # Log failed acquisition
        acq_log = AcquisitionLog(
            source_id=_parse_uuid(source_id, "source_id"),
            plan_id=_parse_uuid(plan_id, "plan_id"),
            result="FAILURE",
            error_message=result.error,
            source_type=source.source_type,
            source_config_snapshot=source.config or {},
            started_at=datetime.fromtimestamp(start_time, tz=timezone.utc),
            completed_at=datetime.now(timezone.utc),
            duration_ms=int((time.time() - start_time) * 1000),
        )
        db.add(acq_log)
        source.last_failure_at = datetime.now(timezone.utc)
        source.last_error = result.error
        source.acquisition_count += 1
        await db.commit()
        raise HTTPException(400, f"Parse failed: {result.error}")

    # Store in data catalog
    catalog = DataCatalog(
        plan_id=_parse_uuid(plan_id, "plan_id"),
        source_id=_parse_uuid(source_id, "source_id"),
        name=safe_name,
        file_format=file_format,
        original_filename=re.sub(r'[^\w\-. ]', '_', file.filename or ""),
        file_size_bytes=len(file_bytes),
        row_count=result.record_count,
        column_count=len(result.schema_info.get("columns", [])),
        schema_info=result.schema_info,
        profiling=result.profiling,
        preview_rows=result.preview_rows,
    )
    db.add(catalog)
    await db.flush()

    # Route to downstream modules based on plan routing rules
    routing = plan.routing_rules or {}
    entities_created = 0
    relationships_created = 0
    document_id = ""

    # The Neo4j driver, spaCy and the graph build are synchronous. Each runs in
    # a worker thread (contract 15): on the event loop, one 10 MB upload stalled
    # every other request, the health check included, for its whole length.
    if routing.get("extract_entities", True) or routing.get("store_documents", True):
        # Convert structured records to text for entity extraction
        text_content = await asyncio.to_thread(_records_to_text, result.records, safe_name)

        if routing.get("store_documents", True):
            doc = Document(
                name=f"[Collection] {safe_name}",
                content=text_content,
                reliability_rating=reliability_rating,
                project_id=plan.project_id,
            )
            await asyncio.to_thread(store.create_entity, doc)
            document_id = doc.id

        if routing.get("extract_entities", True):
            chunks = await asyncio.to_thread(
                ingest_text, text_content, settings.chunk_size, settings.chunk_overlap,
            )
            all_entities = []
            all_rels = []
            for chunk in chunks:
                ents, rels = await _extract(chunk["content"], document_id or "inline", extraction_mode)
                all_entities.extend(ents)
                all_rels.extend(rels)

            if all_entities or all_rels:
                build_result = await asyncio.to_thread(
                    build_graph_from_extractions,
                    store, all_entities, all_rels, plan.project_id,
                    source_doc_id=document_id or None,
                )
                entities_created = build_result.get("entities_created", 0)
                relationships_created = build_result.get("relationships_created", 0)

    # Log successful acquisition
    acq_log = AcquisitionLog(
        source_id=_parse_uuid(source_id, "source_id"),
        plan_id=_parse_uuid(plan_id, "plan_id"),
        result="SUCCESS",
        record_count=result.record_count,
        source_type=source.source_type,
        source_config_snapshot=source.config or {},
        data_catalog_id=catalog.id,
        entities_created=entities_created,
        relationships_created=relationships_created,
        document_id=document_id,
        started_at=datetime.fromtimestamp(start_time, tz=timezone.utc),
        completed_at=datetime.now(timezone.utc),
        duration_ms=int((time.time() - start_time) * 1000),
    )
    db.add(acq_log)

    # Update source coverage tracking
    source.last_success_at = datetime.now(timezone.utc)
    source.last_error = ""
    source.total_records_acquired += result.record_count
    source.acquisition_count += 1

    await db.commit()

    return {
        "catalog_id": str(catalog.id),
        "plan_id": plan_id,
        "source_id": source_id,
        "filename": safe_name,
        "file_format": file_format,
        "record_count": result.record_count,
        "column_count": len(result.schema_info.get("columns", [])),
        "schema_info": result.schema_info,
        "profiling": result.profiling,
        "preview_rows": result.preview_rows[:20],
        "routing_results": {
            "document_id": document_id,
            "entities_created": entities_created,
            "relationships_created": relationships_created,
        },
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _records_to_text(records: list[dict], source_name: str) -> str:
    """Convert structured records to text for entity extraction.

    Creates a readable text representation that entity extraction can process.
    """
    if not records:
        return ""

    lines = [f"Data from {source_name}:"]
    headers = [k for k in records[0].keys() if k != "_row_number"]

    for record in records[:5000]:  # Cap at 5000 rows for extraction
        parts = []
        for h in headers:
            val = record.get(h)
            if val is not None and str(val).strip():
                parts.append(f"{h}: {val}")
        if parts:
            lines.append(". ".join(parts) + ".")

    return "\n".join(lines)


async def _extract(text: str, doc_id: str, mode: str):
    """Run extraction based on configured mode."""
    if mode == "llm":
        from intel_platform.services.extraction import extract_entities_llm
        return await extract_entities_llm(text, doc_id)
    elif mode == "hybrid":
        from intel_platform.services.extraction import extract_entities_hybrid
        return await extract_entities_hybrid(text, doc_id)
    else:
        # spaCy is synchronous and CPU-bound (contract 15).
        return await asyncio.to_thread(extract_entities_nlp, text, doc_id)
