"""Collection plan management API routes.

Provides full CRUD for collection plans and sources, file upload ingestion
through the collection pipeline, acquisition logging, and a status dashboard.
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.config import settings
from intel_platform.connectors.base import get_connector, CONNECTOR_REGISTRY
from intel_platform.connectors.flat_file import detect_format, SUPPORTED_FORMATS
from intel_platform.db.engine import get_db
from intel_platform.db.models import (
    AcquisitionLog,
    CollectionPlan,
    CollectionSource,
    DataCatalog,
    PlanStatus,
    SourceType,
)
from intel_platform.graph.store import GraphStore
from intel_platform.models.entities import Document
from intel_platform.services.collection_planner import parse_plan_sources
from intel_platform.services.extraction import extract_entities_nlp
from intel_platform.services.graph_builder import build_graph_from_extractions
from intel_platform.services.ingestion import ingest_text

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


def _parse_uuid(value: str, label: str = "ID") -> uuid.UUID:
    """Safely parse a UUID string, raising 400 on invalid input."""
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(400, f"Invalid {label}: {value!r}")


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class CreatePlanRequest(BaseModel):
    project_id: str
    name: str
    description: str = ""
    requirement: str = ""
    pir: str = ""
    refined_pir: str = ""
    status: str = PlanStatus.DRAFT
    routing_rules: dict = Field(default_factory=lambda: {
        "extract_entities": True,
        "store_documents": True,
    })
    created_by: str = "analyst"
    assigned_to: str = ""
    schedule_cron: str = ""


class UpdatePlanRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    requirement: str | None = None
    pir: str | None = None
    refined_pir: str | None = None
    status: str | None = None
    routing_rules: dict | None = None
    assigned_to: str | None = None
    schedule_cron: str | None = None


class AddSourceRequest(BaseModel):
    name: str
    source_type: str
    config: dict = Field(default_factory=dict)
    schedule_cron: str = ""
    enabled: bool = True


class UpdateSourceRequest(BaseModel):
    name: str | None = None
    config: dict | None = None
    schedule_cron: str | None = None
    enabled: bool | None = None


class SubmitPIRRequest(BaseModel):
    """Submit a PIR to create a full collection plan via LLM."""
    project_id: str
    pir: str
    extraction_mode: str = "hybrid"
    created_by: str = "analyst"


# ---------------------------------------------------------------------------
# Helper: serialize SQLAlchemy model to dict
# ---------------------------------------------------------------------------

def _plan_to_dict(plan: CollectionPlan) -> dict:
    return {
        "id": str(plan.id),
        "project_id": plan.project_id,
        "name": plan.name,
        "description": plan.description,
        "requirement": plan.requirement,
        "pir": plan.pir,
        "refined_pir": plan.refined_pir,
        "status": plan.status,
        "routing_rules": plan.routing_rules or {},
        "created_by": plan.created_by,
        "assigned_to": plan.assigned_to,
        "schedule_cron": plan.schedule_cron,
        "next_run_at": plan.next_run_at.isoformat() if plan.next_run_at else None,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
        "sources": [_source_to_dict(s) for s in (plan.sources or [])],
        "source_count": len(plan.sources or []),
    }


def _source_to_dict(src: CollectionSource) -> dict:
    return {
        "id": str(src.id),
        "plan_id": str(src.plan_id),
        "name": src.name,
        "source_type": src.source_type,
        "config": src.config or {},
        "schedule_cron": src.schedule_cron,
        "enabled": src.enabled,
        "last_success_at": src.last_success_at.isoformat() if src.last_success_at else None,
        "last_failure_at": src.last_failure_at.isoformat() if src.last_failure_at else None,
        "last_error": src.last_error,
        "total_records_acquired": src.total_records_acquired,
        "acquisition_count": src.acquisition_count,
        "next_run_at": src.next_run_at.isoformat() if src.next_run_at else None,
        "created_at": src.created_at.isoformat() if src.created_at else None,
    }


def _log_to_dict(log: AcquisitionLog) -> dict:
    return {
        "id": str(log.id),
        "source_id": str(log.source_id),
        "plan_id": str(log.plan_id),
        "result": log.result,
        "record_count": log.record_count,
        "error_message": log.error_message,
        "source_type": log.source_type,
        "entities_created": log.entities_created,
        "relationships_created": log.relationships_created,
        "document_id": log.document_id,
        "started_at": log.started_at.isoformat() if log.started_at else None,
        "completed_at": log.completed_at.isoformat() if log.completed_at else None,
        "duration_ms": log.duration_ms,
    }


def _catalog_to_dict(cat: DataCatalog) -> dict:
    return {
        "id": str(cat.id),
        "plan_id": str(cat.plan_id),
        "source_id": str(cat.source_id),
        "name": cat.name,
        "file_format": cat.file_format,
        "original_filename": cat.original_filename,
        "file_size_bytes": cat.file_size_bytes,
        "row_count": cat.row_count,
        "column_count": cat.column_count,
        "schema_info": cat.schema_info or {},
        "profiling": cat.profiling or {},
        "preview_rows": cat.preview_rows or [],
        "ingested_at": cat.ingested_at.isoformat() if cat.ingested_at else None,
    }


# ---------------------------------------------------------------------------
# Collection Plan CRUD
# ---------------------------------------------------------------------------

@router.post("/collection-plans")
async def create_plan(req: CreatePlanRequest, db: AsyncSession = Depends(get_db)):
    plan = CollectionPlan(
        project_id=req.project_id,
        name=req.name,
        description=req.description,
        requirement=req.requirement,
        pir=req.pir,
        refined_pir=req.refined_pir,
        status=req.status,
        routing_rules=req.routing_rules,
        created_by=req.created_by,
        assigned_to=req.assigned_to,
        schedule_cron=req.schedule_cron,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return _plan_to_dict(plan)


@router.get("/collection-plans")
async def list_plans(
    project_id: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CollectionPlan).order_by(CollectionPlan.updated_at.desc())
    if project_id:
        stmt = stmt.where(CollectionPlan.project_id == project_id)
    if status:
        stmt = stmt.where(CollectionPlan.status == status)
    result = await db.execute(stmt)
    plans = result.scalars().all()
    return [_plan_to_dict(p) for p in plans]


@router.get("/collection-plans/{plan_id}")
async def get_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    plan = await db.get(CollectionPlan, _parse_uuid(plan_id, "plan_id"))
    if not plan:
        raise HTTPException(404, "Collection plan not found")
    return _plan_to_dict(plan)


@router.put("/collection-plans/{plan_id}")
async def update_plan(plan_id: str, req: UpdatePlanRequest, db: AsyncSession = Depends(get_db)):
    plan = await db.get(CollectionPlan, _parse_uuid(plan_id, "plan_id"))
    if not plan:
        raise HTTPException(404, "Collection plan not found")

    update_data = req.model_dump(exclude_none=True)
    for key, value in update_data.items():
        setattr(plan, key, value)

    plan.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(plan)
    return _plan_to_dict(plan)


@router.delete("/collection-plans/{plan_id}")
async def delete_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    plan = await db.get(CollectionPlan, _parse_uuid(plan_id, "plan_id"))
    if not plan:
        raise HTTPException(404, "Collection plan not found")
    await db.delete(plan)
    await db.commit()
    return {"deleted": True, "id": plan_id}


# ---------------------------------------------------------------------------
# Plan status transitions
# ---------------------------------------------------------------------------

@router.post("/collection-plans/{plan_id}/activate")
async def activate_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    plan = await db.get(CollectionPlan, _parse_uuid(plan_id, "plan_id"))
    if not plan:
        raise HTTPException(404, "Collection plan not found")
    if plan.status not in (PlanStatus.DRAFT, PlanStatus.PAUSED):
        raise HTTPException(400, f"Cannot activate plan in {plan.status} status")
    plan.status = PlanStatus.ACTIVE
    plan.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _plan_to_dict(plan)


@router.post("/collection-plans/{plan_id}/pause")
async def pause_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    plan = await db.get(CollectionPlan, _parse_uuid(plan_id, "plan_id"))
    if not plan:
        raise HTTPException(404, "Collection plan not found")
    if plan.status != PlanStatus.ACTIVE:
        raise HTTPException(400, "Can only pause active plans")
    plan.status = PlanStatus.PAUSED
    plan.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _plan_to_dict(plan)


@router.post("/collection-plans/{plan_id}/complete")
async def complete_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    plan = await db.get(CollectionPlan, _parse_uuid(plan_id, "plan_id"))
    if not plan:
        raise HTTPException(404, "Collection plan not found")
    plan.status = PlanStatus.COMPLETED
    plan.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _plan_to_dict(plan)


@router.post("/collection-plans/{plan_id}/archive")
async def archive_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    plan = await db.get(CollectionPlan, _parse_uuid(plan_id, "plan_id"))
    if not plan:
        raise HTTPException(404, "Collection plan not found")
    plan.status = PlanStatus.ARCHIVED
    plan.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _plan_to_dict(plan)


# ---------------------------------------------------------------------------
# PIR → Plan (LLM-driven collection plan generation)
# ---------------------------------------------------------------------------

@router.post("/collection-plans/from-pir")
async def create_plan_from_pir(req: SubmitPIRRequest, db: AsyncSession = Depends(get_db)):
    """Submit a PIR → LLM refines it, generates a collection plan with sources.

    Flow: PIR → LLM refinement → LLM plan generation → create Plan + Sources → DRAFT
    Returns the plan ready for user approval.
    """
    # Step 1: Get the LLM provider
    provider = None
    try:
        from intel_platform.api.routes.llm import _get_provider
        provider = _get_provider()
    except Exception as e:
        logger.warning("Failed to get LLM provider for PIR plan generation: %s", e)

    refined_pir = req.pir
    plan_description = ""

    if provider:
        # Step 2: Refine the PIR
        try:
            from intel_platform.llm.skills.loader import SkillsLoader
            loader = SkillsLoader()

            refine_result = await provider.generate(
                messages=[{"role": "user", "content": f"Refine this Priority Intelligence Requirement (PIR):\n\n{req.pir}"}],
                system=(
                    "You are an intelligence analyst. Given a PIR:\n"
                    "1. ASSESS specificity, measurability, and time-bounds\n"
                    "2. IDENTIFY hidden assumptions\n"
                    "3. BREAK DOWN into 3-5 Essential Elements of Information (EEIs)\n"
                    "4. PROPOSE a refined, more actionable PIR\n"
                    "Return the refined PIR on the first line, then your analysis."
                ),
                temperature=0.3,
            )
            # First line is the refined PIR, rest is the analysis
            lines = refine_result.content.strip().split("\n", 1)
            refined_pir = lines[0].strip().strip('"').strip("*").strip()
            plan_description = lines[1].strip() if len(lines) > 1 else ""
        except Exception as e:
            logger.warning("PIR refinement failed: %s", e)

        # Step 3: Generate collection plan with sources
        try:
            system = loader.get_system_prompt("collection_planning", include_foundation=True) or ""
            plan_result = await provider.generate(
                messages=[{"role": "user", "content": (
                    f"Create a collection plan for this PIR:\n\n{refined_pir}\n\n"
                    "For each source, output a numbered list item in this format:\n"
                    "N. [SOURCE_TYPE] Description of what to collect\n\n"
                    "Valid SOURCE_TYPE values: file_upload, web_scrape, api_feed, database, rss_feed\n"
                    "Include 3-7 concrete, actionable sources."
                )}],
                system=system,
                temperature=0.4,
            )
            plan_text = plan_result.content
        except Exception as e:
            logger.warning("Plan generation failed: %s", e)
            plan_text = ""
    else:
        plan_text = ""

    # Step 4: Create the plan
    plan = CollectionPlan(
        project_id=req.project_id,
        name=f"PIR: {req.pir[:80]}{'...' if len(req.pir) > 80 else ''}",
        description=plan_description,
        requirement=req.pir,
        pir=req.pir,
        refined_pir=refined_pir,
        status=PlanStatus.DRAFT,
        routing_rules={"extract_entities": True, "store_documents": True},
        created_by=req.created_by,
    )
    db.add(plan)
    await db.flush()

    # Step 5: Parse LLM plan text into sources
    sources_created = []
    if plan_text:
        parsed_sources = parse_plan_sources(plan_text)
        for ps in parsed_sources:
            source = CollectionSource(
                plan_id=plan.id,
                name=ps["name"],
                source_type=ps["source_type"],
                config={},
                enabled=True,
            )
            db.add(source)
            sources_created.append(source)

    await db.commit()
    await db.refresh(plan)

    result = _plan_to_dict(plan)
    result["llm_plan_text"] = plan_text
    return result


@router.post("/collection-plans/{plan_id}/execute")
async def execute_plan(
    plan_id: str,
    db: AsyncSession = Depends(get_db),
    store: GraphStore = Depends(get_graph_store),
):
    """Approve and execute a collection plan — activates and triggers acquisition.

    For file_upload sources: marks as ready for upload.
    For all sources: activates the plan and logs the execution start.
    Entity extraction runs automatically on acquired data.
    """
    plan = await db.get(CollectionPlan, _parse_uuid(plan_id, "plan_id"))
    if not plan:
        raise HTTPException(404, "Collection plan not found")

    if plan.status not in (PlanStatus.DRAFT, PlanStatus.PAUSED):
        raise HTTPException(400, f"Cannot execute plan in {plan.status} status")

    # Activate the plan
    plan.status = PlanStatus.ACTIVE
    plan.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(plan)

    return {
        **_plan_to_dict(plan),
        "execution_status": "activated",
        "message": f"Plan activated with {len(plan.sources or [])} sources ready for acquisition.",
    }


# ---------------------------------------------------------------------------
# Source assignment
# ---------------------------------------------------------------------------

@router.post("/collection-plans/{plan_id}/sources")
async def add_source(plan_id: str, req: AddSourceRequest, db: AsyncSession = Depends(get_db)):
    plan = await db.get(CollectionPlan, _parse_uuid(plan_id, "plan_id"))
    if not plan:
        raise HTTPException(404, "Collection plan not found")

    # Validate source type
    if req.source_type not in CONNECTOR_REGISTRY:
        raise HTTPException(400,
            f"Unknown source type: {req.source_type}. Available: {list(CONNECTOR_REGISTRY.keys())}")

    # Validate config through the connector
    connector = get_connector(req.source_type)
    try:
        validated_config = connector.configure(req.config)
    except ValueError as e:
        raise HTTPException(400, f"Invalid source config: {e}")

    source = CollectionSource(
        plan_id=_parse_uuid(plan_id, "plan_id"),
        name=req.name,
        source_type=req.source_type,
        config=validated_config,
        schedule_cron=req.schedule_cron,
        enabled=req.enabled,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return _source_to_dict(source)


@router.get("/collection-plans/{plan_id}/sources")
async def list_sources(plan_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(CollectionSource).where(
        CollectionSource.plan_id == _parse_uuid(plan_id, "plan_id")
    ).order_by(CollectionSource.created_at)
    result = await db.execute(stmt)
    return [_source_to_dict(s) for s in result.scalars().all()]


@router.put("/collection-plans/{plan_id}/sources/{source_id}")
async def update_source(
    plan_id: str, source_id: str, req: UpdateSourceRequest, db: AsyncSession = Depends(get_db)
):
    source = await db.get(CollectionSource, _parse_uuid(source_id, "source_id"))
    if not source or str(source.plan_id) != plan_id:
        raise HTTPException(404, "Source not found")

    if req.config is not None:
        connector = get_connector(source.source_type)
        try:
            source.config = connector.configure(req.config)
        except ValueError as e:
            raise HTTPException(400, f"Invalid config: {e}")

    if req.name is not None:
        source.name = req.name
    if req.schedule_cron is not None:
        source.schedule_cron = req.schedule_cron
    if req.enabled is not None:
        source.enabled = req.enabled

    source.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(source)
    return _source_to_dict(source)


@router.delete("/collection-plans/{plan_id}/sources/{source_id}")
async def delete_source(plan_id: str, source_id: str, db: AsyncSession = Depends(get_db)):
    source = await db.get(CollectionSource, _parse_uuid(source_id, "source_id"))
    if not source or str(source.plan_id) != plan_id:
        raise HTTPException(404, "Source not found")
    await db.delete(source)
    await db.commit()
    return {"deleted": True, "id": source_id}


# ---------------------------------------------------------------------------
# File upload → ingest through collection plan
# ---------------------------------------------------------------------------

@router.post("/collection-plans/{plan_id}/sources/{source_id}/upload")
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

    # Read and validate file
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB for structured data
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(400, f"File too large. Max: {MAX_FILE_SIZE // (1024*1024)}MB")

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

    if routing.get("extract_entities", True) or routing.get("store_documents", True):
        # Convert structured records to text for entity extraction
        text_content = _records_to_text(result.records, safe_name)

        if routing.get("store_documents", True):
            doc = Document(
                name=f"[Collection] {safe_name}",
                content=text_content,
                reliability_rating=reliability_rating,
                project_id=plan.project_id,
            )
            store.create_entity(doc)
            document_id = doc.id

        if routing.get("extract_entities", True):
            chunks = ingest_text(text_content, settings.chunk_size, settings.chunk_overlap)
            all_entities = []
            all_rels = []
            for chunk in chunks:
                ents, rels = await _extract(chunk["content"], document_id or "inline", extraction_mode)
                all_entities.extend(ents)
                all_rels.extend(rels)

            if all_entities or all_rels:
                build_result = build_graph_from_extractions(
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
# Acquisition log
# ---------------------------------------------------------------------------

@router.get("/collection-plans/{plan_id}/acquisitions")
async def list_acquisitions(
    plan_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(AcquisitionLog)
        .where(AcquisitionLog.plan_id == _parse_uuid(plan_id, "plan_id"))
        .order_by(AcquisitionLog.started_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [_log_to_dict(log) for log in result.scalars().all()]


@router.get("/collection-plans/{plan_id}/sources/{source_id}/acquisitions")
async def list_source_acquisitions(
    plan_id: str,
    source_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(AcquisitionLog)
        .where(AcquisitionLog.source_id == _parse_uuid(source_id, "source_id"))
        .order_by(AcquisitionLog.started_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [_log_to_dict(log) for log in result.scalars().all()]


# ---------------------------------------------------------------------------
# Data catalog
# ---------------------------------------------------------------------------

@router.get("/collection-plans/{plan_id}/catalog")
async def list_catalog(plan_id: str, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(DataCatalog)
        .where(DataCatalog.plan_id == _parse_uuid(plan_id, "plan_id"))
        .order_by(DataCatalog.ingested_at.desc())
    )
    result = await db.execute(stmt)
    return [_catalog_to_dict(c) for c in result.scalars().all()]


@router.get("/data-catalog/{catalog_id}")
async def get_catalog_entry(catalog_id: str, db: AsyncSession = Depends(get_db)):
    entry = await db.get(DataCatalog, _parse_uuid(catalog_id, "catalog_id"))
    if not entry:
        raise HTTPException(404, "Catalog entry not found")
    return _catalog_to_dict(entry)


@router.get("/data-catalog/{catalog_id}/preview")
async def get_catalog_preview(
    catalog_id: str,
    offset: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    entry = await db.get(DataCatalog, _parse_uuid(catalog_id, "catalog_id"))
    if not entry:
        raise HTTPException(404, "Catalog entry not found")
    rows = entry.preview_rows or []
    return {
        "rows": rows[offset:offset + limit],
        "total": len(rows),
        "offset": offset,
        "schema": entry.schema_info,
    }


# ---------------------------------------------------------------------------
# Collection dashboard — summary stats across all plans for a project
# ---------------------------------------------------------------------------

@router.get("/collection-dashboard")
async def collection_dashboard(project_id: str, db: AsyncSession = Depends(get_db)):
    """Dashboard summary: plan counts, recent acquisitions, source health."""
    # Plan counts by status
    plan_counts_stmt = (
        select(CollectionPlan.status, func.count())
        .where(CollectionPlan.project_id == project_id)
        .group_by(CollectionPlan.status)
    )
    plan_counts_result = await db.execute(plan_counts_stmt)
    plan_counts = {row[0]: row[1] for row in plan_counts_result}

    # Total sources and their health
    sources_stmt = (
        select(CollectionSource)
        .join(CollectionPlan)
        .where(CollectionPlan.project_id == project_id)
    )
    sources_result = await db.execute(sources_stmt)
    sources = sources_result.scalars().all()

    healthy_sources = sum(1 for s in sources if s.enabled and not s.last_error)
    unhealthy_sources = sum(1 for s in sources if s.enabled and s.last_error)
    disabled_sources = sum(1 for s in sources if not s.enabled)

    # Recent acquisitions (last 10)
    recent_acq_stmt = (
        select(AcquisitionLog)
        .join(CollectionPlan, AcquisitionLog.plan_id == CollectionPlan.id)
        .where(CollectionPlan.project_id == project_id)
        .order_by(AcquisitionLog.started_at.desc())
        .limit(10)
    )
    recent_acq_result = await db.execute(recent_acq_stmt)
    recent_acquisitions = [_log_to_dict(a) for a in recent_acq_result.scalars().all()]

    # Total records acquired
    total_records_stmt = (
        select(func.sum(CollectionSource.total_records_acquired))
        .join(CollectionPlan)
        .where(CollectionPlan.project_id == project_id)
    )
    total_records_result = await db.execute(total_records_stmt)
    total_records = total_records_result.scalar() or 0

    return {
        "project_id": project_id,
        "plan_counts": plan_counts,
        "total_plans": sum(plan_counts.values()),
        "source_health": {
            "healthy": healthy_sources,
            "unhealthy": unhealthy_sources,
            "disabled": disabled_sources,
            "total": len(sources),
        },
        "total_records_acquired": total_records,
        "recent_acquisitions": recent_acquisitions,
    }


# ---------------------------------------------------------------------------
# Connector info
# ---------------------------------------------------------------------------

@router.get("/connector-types")
async def list_connector_types():
    """List available connector types and their capabilities."""
    result = []
    for type_name, cls in CONNECTOR_REGISTRY.items():
        connector = cls()
        result.append({
            "source_type": type_name,
            "description": cls.__doc__ or "",
        })
    return result


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
        return extract_entities_nlp(text, doc_id)
