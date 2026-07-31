"""Collection plan management API routes.

Provides full CRUD for collection plans and sources, file upload ingestion
through the collection pipeline, acquisition logging, and a status dashboard.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.config import settings
from intel_platform.connectors.base import get_connector, CONNECTOR_REGISTRY
from intel_platform.connectors.flat_file import detect_format, SUPPORTED_FORMATS
from intel_platform.db.engine import get_db
from intel_platform.db.models import (
    AcquisitionLog,
    CollectionActivity,
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

# A plan silent for longer than this reports "stalled" rather than "running".
# Extraction now heartbeats every few chunks, so this is several times the
# expected gap — long enough not to cry wolf on a slow local model, short enough
# that a dead run surfaces within one analyst's attention span.
_STALL_AFTER_SECONDS = 600


def refinement_system_prompt() -> str:
    """System prompt for PIR refinement, framed by the active persona.

    The persona reaches the decomposition, not just the prose. Which elements a
    requirement is split into decides what is collected against it, so a cyber
    analyst and a maritime analyst should not break the same question into the
    same elements. Personas previously reached nothing here at all.

    Built as a function rather than inline so the framing is testable without
    driving the whole from-pir route.
    """
    from intel_platform.api.routes.personas import active_persona_brief

    brief = active_persona_brief()
    return (
        (brief + "\n\n" if brief else "")
        + "You are an intelligence analyst. Given a PIR:\n"
        "1. ASSESS specificity, measurability, and time-bounds\n"
        "2. IDENTIFY hidden assumptions\n"
        "3. BREAK DOWN into 3-5 Essential Elements of Information (EEIs).\n"
        "   Each EEI must be answerable independently and must not overlap "
        "another: two elements that ask the same thing in different words "
        "cannot be judged apart, and the second is then scored against "
        "whatever evidence the first did not use. Observed: 'types of "
        "anti-ship missiles employed' and 'weapon systems used, including "
        "capabilities and ranges' are one element, not two.\n"
        "4. PROPOSE a refined, more actionable PIR\n"
        "Return the refined PIR on the first line, then your analysis."
    )


def _split_refinement(content: str, fallback: str) -> tuple[str, str]:
    """Split an LLM refinement into (refined PIR, analysis).

    The prompt asks for the refined PIR on the first line, but models routinely
    emit a label first ("Refined PIR:", "**Refined PIR**") and put the text on
    the next line. Taking line 0 verbatim captured the label and pushed the real
    requirement into the description, leaving refined_pir 12 characters long.
    """
    text = (content or "").strip()
    if not text:
        return fallback, ""

    lines = text.split("\n")
    # Trailing markdown matters too — "**Refined PIR**" is as common as "Refined PIR:".
    label = re.compile(r'^\s*[*_#>\-\s]*refined\s*pir\s*[*_]*\s*[:\-–]?\s*[*_]*\s*$', re.IGNORECASE)
    inline = re.compile(
        r'^\s*[*_#>\-\s]*refined\s*pir\s*[*_]*\s*[:\-–]\s*(?P<body>.+)$', re.IGNORECASE
    )

    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        m = inline.match(line)
        if m:
            # "Refined PIR: <text>" on one line. Clean first, then check — for
            # "**Refined PIR:**" the capture is just the closing "**", which is
            # truthy but empty once stripped, and the real text is the next line.
            body = m.group("body").strip().strip('"').strip("*").strip()
            if body:
                return body, "\n".join(lines[i + 1:]).strip()
            for j in range(i + 1, len(lines)):
                nxt = lines[j].strip()
                if nxt:
                    return nxt.strip('"').strip("*").strip(), "\n".join(lines[j + 1:]).strip()
            return fallback, ""
        if label.match(line):
            # Label alone — the requirement is the next non-empty line.
            for j in range(i + 1, len(lines)):
                nxt = lines[j].strip()
                if nxt:
                    return (
                        nxt.strip('"').strip("*").strip(),
                        "\n".join(lines[j + 1:]).strip(),
                    )
            return fallback, ""
        # First substantive line, no label in sight.
        return line.strip('"').strip("*").strip(), "\n".join(lines[i + 1:]).strip()

    return fallback, ""


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
    # Link to a first-class PIR (see api/routes/pirs.py). When omitted but `pir`
    # text is supplied, the plan is anchored to a matching/new PIR so free-typed
    # requirements still land on the project's requirements spine.
    pir_id: str | None = None
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
    pir: str = ""
    # Run against an already-persisted requirement. Omit to have one created (or
    # an identical live one reused) from `pir` — either way the plan ends up
    # linked to a PIR the project hub can show.
    pir_id: str | None = None
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
        "pir_id": str(plan.pir_id) if plan.pir_id else None,
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
        # The live acquisition status (resolving/queued/collecting/succeeded/
        # failed). Was omitted here, so the UI defaulted every source to
        # "pending" even while the pipeline progressed.
        "collection_status": src.collection_status,
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
    # Local import: pirs.py imports this module's _parse_uuid.
    from intel_platform.api.routes.pirs import get_or_create_pir

    pir_record = await get_or_create_pir(
        db, req.project_id, req.pir, pir_id=req.pir_id, created_by=req.created_by,
    )

    plan = CollectionPlan(
        project_id=req.project_id,
        name=req.name,
        description=req.description,
        requirement=req.requirement,
        pir=req.pir or (pir_record.text if pir_record else ""),
        pir_id=pir_record.id if pir_record else None,
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

    The PIR itself is persisted first (or resolved from `pir_id`), so the plan is
    always anchored to a requirement the project hub can list and track.
    """
    # Local import: pirs.py imports this module's _parse_uuid.
    from intel_platform.api.routes.pirs import get_or_create_pir

    # Step 0: Anchor the run on a first-class PIR before any LLM work, so an
    # unknown pir_id fails fast and the requirement survives an LLM outage.
    pir_record = await get_or_create_pir(
        db, req.project_id, req.pir, pir_id=req.pir_id, created_by=req.created_by,
    )
    pir_text = (req.pir or "").strip() or (pir_record.text if pir_record else "")
    if not pir_text:
        raise HTTPException(400, "A PIR (text or pir_id) is required")

    # Step 1: Get the LLM provider
    provider = None
    llm_available = False
    llm_status = ""
    try:
        # Use the collection provider (local Ollama when configured) so autonomous
        # plan/source generation doesn't hit a rate-limited cloud key — matching the
        # execute path. Falls back to the default provider when no collection provider.
        from intel_platform.api.routes.llm import _get_collection_provider
        provider = await _get_collection_provider()
        if provider:
            llm_available = True
            llm_status = f"Using {provider.name()}"
    except Exception as e:
        logger.warning("Failed to get LLM provider for PIR plan generation: %s", e)
        llm_status = f"LLM unavailable: {e}"

    refined_pir = pir_text
    plan_description = ""
    # Why a plan came back thin, in the plan's own words rather than the UI's
    # guess. Without this the analyst was shown "The LLM may have been
    # rate-limited" for any failure at all, including ones that were nothing of
    # the sort.
    failures: list[str] = []

    if provider:
        # Step 2: Refine the PIR
        try:
            from intel_platform.llm.skills.loader import SkillsLoader
            loader = SkillsLoader()

            from intel_platform.api.routes.personas import active_persona_temperature

            refine_result = await provider.generate(
                messages=[{"role": "user", "content": f"Refine this Priority Intelligence Requirement (PIR):\n\n{pir_text}"}],
                system=refinement_system_prompt(),
                temperature=active_persona_temperature(0.3),
            )
            refined_pir, plan_description = _split_refinement(refine_result.content, pir_text)
        except Exception as e:
            # `%s` alone loses everything when the exception carries no message —
            # a timeout stringifies to "" and the log line read literally
            # "PIR refinement failed: ", which is undiagnosable. Record the type
            # and the traceback, and keep the reason for the response.
            logger.warning("PIR refinement failed: %s: %s", type(e).__name__, e, exc_info=True)
            failures.append(f"refinement failed ({type(e).__name__})")

        # Step 3: Generate collection plan with sources
        try:
            system = loader.get_system_prompt("collection_planning", include_foundation=True) or ""
            plan_result = await provider.generate(
                messages=[{"role": "user", "content": (
                    f"Create a collection plan for this PIR:\n\n{refined_pir}\n\n"
                    f"Original requirement, for domain context:\n{pir_text}\n\n"
                    "The sources MUST match the subject matter of that requirement. A maritime,"
                    " economic, political or humanitarian PIR needs maritime, economic, political"
                    " or humanitarian sources — do not default to cyber-threat sources unless the"
                    " requirement is actually about cyber.\n\n"
                    "For each source, output a numbered list item in EXACTLY this format:\n"
                    'N. [SOURCE_TYPE] Description of what to collect\n'
                    '   CONFIG: {"key": "value"}\n\n'
                    "Valid SOURCE_TYPE values and their CONFIG keys:\n"
                    '- web_scrape: CONFIG must include {"url": "https://..."}\n'
                    '- rss_feed: CONFIG must include {"feed_url": "https://..."}\n'
                    '- api_feed: CONFIG must include {"base_url": "https://..."}\n'
                    "- file_upload: no CONFIG needed (analyst uploads manually)\n\n"
                    "Include 3-7 concrete, actionable sources with REAL URLs.\n"
                    "Focus on publicly accessible sources relevant to the PIR.\n"
                    "Examples of the FORMAT only — pick sources for the actual subject, not these:\n"
                    '1. [web_scrape] UKMTO maritime incident advisories\n'
                    '   CONFIG: {"url": "https://www.ukmto.org/incidents"}\n'
                    '2. [rss_feed] Reuters world news feed\n'
                    '   CONFIG: {"feed_url": "https://feeds.reuters.com/reuters/worldNews"}'
                )}],
                system=system,
                temperature=0.4,
            )
            plan_text = plan_result.content
        except Exception as e:
            logger.warning("Plan generation failed: %s: %s", type(e).__name__, e, exc_info=True)
            failures.append(f"source generation failed ({type(e).__name__})")
            plan_text = ""
    else:
        plan_text = ""

    # Step 4: Create the plan, linked to the requirement it serves
    if pir_record and refined_pir and not pir_record.refined_text:
        # Carry the LLM's refinement back onto the requirement so the analyst
        # does not have to re-derive it on the next run.
        pir_record.refined_text = refined_pir

    if pir_record and not pir_record.eeis:
        # The refinement is asked to decompose the requirement into EEIs, and
        # capturing them is what makes satisfaction measurable later
        # (`/pirs/{id}/assess`) and what the collection loop re-tasks against.
        from intel_platform.api.routes.pirs import extract_eeis

        # Search the whole refinement, not just the analysis half: a model that
        # puts the EEI list above the split point would otherwise have it
        # discarded, and the requirement would look undecomposed.
        captured = extract_eeis(plan_description) or extract_eeis(refined_pir)
        if captured:
            pir_record.eeis = captured
        else:
            # Observed live: the model returned a refined PIR plus a "Why this
            # version works" critique and no EEI section at all, while still
            # referring to "the EEIs". Every downstream capability that needs
            # them — assessment, the requirement loop, the gap count — then does
            # nothing, and reported success while doing it.
            logger.warning(
                "No EEIs captured for PIR %s; the refinement produced no "
                "Essential Elements section", getattr(pir_record, "id", "?"),
            )
            failures.append("no essential elements were extracted from the refinement")

    plan = CollectionPlan(
        project_id=req.project_id,
        name=f"PIR: {pir_text[:80]}{'...' if len(pir_text) > 80 else ''}",
        description=plan_description,
        requirement=pir_text,
        pir=pir_text,
        pir_id=pir_record.id if pir_record else None,
        refined_pir=refined_pir,
        status=PlanStatus.DRAFT,
        routing_rules={
            "extract_entities": True,
            "store_documents": True,
            "extraction_mode": req.extraction_mode,
        },
        created_by=req.created_by,
    )
    db.add(plan)
    await db.flush()

    # Step 5: Parse LLM plan text into sources with configs
    sources_created = []
    if plan_text:
        parsed_sources = parse_plan_sources(plan_text)
        for ps in parsed_sources:
            source = CollectionSource(
                plan_id=plan.id,
                name=ps["name"],
                source_type=ps["source_type"],
                config=ps.get("config", {}),
                enabled=True,
            )
            db.add(source)
            sources_created.append(source)

    await db.commit()
    await db.refresh(plan)

    result = _plan_to_dict(plan)
    result["llm_plan_text"] = plan_text
    result["llm_available"] = llm_available
    result["llm_status"] = llm_status
    # What went wrong, if anything, in the plan's own words. A caller seeing a
    # plan with no sources previously had to guess why, and the UI guessed
    # "the LLM may have been rate-limited" for every cause including the ones
    # that were nothing of the sort.
    result["generation_failures"] = failures
    result["eeis_captured"] = len(getattr(pir_record, "eeis", None) or []) if pir_record else 0
    if not llm_available:
        result["llm_requirements"] = {
            "message": "An LLM provider is required for autonomous plan generation. "
                       "Without an LLM, plans must be created manually with sources and URLs.",
            "supported_providers": ["anthropic", "openai", "cohere", "ollama"],
            "configuration": "Set one of: ANTHROPIC_API_KEY, OPENAI_API_KEY, COHERE_API_KEY "
                             "in .env, or configure Ollama at OLLAMA_BASE_URL.",
            "minimum_capability": "The LLM must support structured output generation "
                                  "(tool calling or JSON mode). Recommended: Claude Sonnet 4, "
                                  "GPT-4o, Command A, or Qwen 3 30B+ via Ollama.",
        }
    return result


class ExecuteRequest(BaseModel):
    # How many results to pull per source: URLs/pages for web_scrape/database/
    # api_feed, items for rss_feed. Clamped to 1..25.
    max_results_per_source: int = 10
    # Collection budget: stop after this many sources even if the plan proposes
    # more. Pairs with `POST /pirs/{id}/assess`, which reports whether the
    # requirement was answered or the budget ran out first.
    source_limit: int | None = Field(default=None, ge=1)


@router.post("/collection-plans/{plan_id}/execute")
async def execute_plan_endpoint(
    plan_id: str,
    body: ExecuteRequest | None = None,
    db: AsyncSession = Depends(get_db),
    store: GraphStore = Depends(get_graph_store),
):
    """Approve and execute a collection plan — activates and triggers autonomous acquisition.

    Launches a background task that iterates over all sources, acquires data
    via registered connectors, runs entity extraction, and builds the knowledge graph.
    File upload sources are skipped (require manual upload).
    """
    plan = await db.get(CollectionPlan, _parse_uuid(plan_id, "plan_id"))
    if not plan:
        raise HTTPException(404, "Collection plan not found")

    if plan.status not in (PlanStatus.DRAFT, PlanStatus.PAUSED):
        raise HTTPException(400, f"Cannot execute plan in {plan.status} status")

    # Check source readiness
    sources = plan.sources or []
    from intel_platform.services.plan_executor import _has_valid_config
    executable = [s for s in sources if s.enabled and s.source_type != "file_upload" and _has_valid_config(s.source_type, s.config or {})]
    file_only = [s for s in sources if s.enabled and s.source_type == "file_upload"]
    missing_config = [s for s in sources if s.enabled and s.source_type != "file_upload" and not _has_valid_config(s.source_type, s.config or {})]

    warnings = []
    if missing_config:
        names = [s.name for s in missing_config]
        warnings.append(f"{len(missing_config)} source(s) missing required config (url/feed_url/base_url) and will be skipped: {', '.join(names[:5])}")
    if file_only:
        warnings.append(f"{len(file_only)} file_upload source(s) require manual upload")
    if not executable and not file_only:
        warnings.append("No sources are ready for autonomous execution. Add URLs to source configs or upload files manually.")

    # Activate the plan, recording the collection budget it was given. The PIR
    # assessor reports "stopped on the source limit", which must rest on what
    # the run was actually allowed rather than on a number the caller re-supplies
    # at assessment time.
    plan.status = PlanStatus.ACTIVE
    if body and body.source_limit:
        plan.routing_rules = {**(plan.routing_rules or {}), "source_limit": body.source_limit}
    plan.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(plan)

    # Launch agentic execution as background task
    # Phase 1: LLM resolves configs for sources missing URLs
    # Phase 2: Connectors acquire content and run ingestion pipeline
    # Phase 3: LLM evaluates results and follows up on leads
    import asyncio
    from intel_platform.db.engine import get_session_factory
    from intel_platform.collection.agentic import run_agentic_loop
    from intel_platform.api.routes.llm import _get_collection_provider

    all_auto = [s for s in sources if s.enabled and s.source_type != "file_upload"]
    source_limit = body.source_limit if body else None
    if all_auto:
        session_factory = get_session_factory()
        max_results = max(1, min(25, body.max_results_per_source if body else 10))
        asyncio.create_task(
            run_agentic_loop(
                plan_id=plan.id,
                db_factory=session_factory,
                get_store=lambda: store,
                # Bulk resolution + summarization → collection provider (local
                # Ollama when configured), keeping the cloud key for products.
                get_provider=_get_collection_provider,
                max_results_per_source=max_results,
                source_limit=source_limit,
            )
        )

    return {
        **_plan_to_dict(plan),
        "execution_status": "started" if all_auto else "no_executable_sources",
        "message": f"Agentic execution started with {len(all_auto)} source(s)." if all_auto
                   else "Plan activated but no automated sources found.",
        "sources_queued": min(len(all_auto), source_limit) if source_limit else len(all_auto),
        "sources_manual": len(file_only),
        "sources_missing_config": len(missing_config),
        "source_limit": source_limit,
        "sources_over_budget": max(0, len(all_auto) - source_limit) if source_limit else 0,
        "warnings": warnings,
    }


@router.get("/collection-plans/{plan_id}/execution-status")
async def get_execution_status(plan_id: str, db: AsyncSession = Depends(get_db)):
    """Poll the execution progress of a running collection plan.

    The in-memory plan_executor tracker only covers the synchronous plan_executor
    path; the agentic loop (run_agentic_loop) records progress to CollectionActivity
    instead. Fall back to that trail so the endpoint reflects a real agentic run
    (previously it always reported "idle" while a crawl was in flight).
    """
    from intel_platform.services.plan_executor import get_execution_status as _mem_status
    pid = _parse_uuid(plan_id, "plan_id")

    mem = _mem_status(plan_id)
    if mem:
        return {"plan_id": plan_id, **mem}

    result = await db.execute(
        select(CollectionActivity)
        .where(CollectionActivity.plan_id == pid)
        .order_by(CollectionActivity.created_at.asc())
    )
    events = result.scalars().all()
    if not events:
        return {"plan_id": plan_id, "status": "idle", "message": "No active execution"}

    latest = events[-1]
    terminal = next((e for e in reversed(events) if e.event in ("plan_completed", "plan_failed")), None)
    if terminal:
        state = "completed" if terminal.event == "plan_completed" else "failed"
    else:
        # "running" was derived purely from the absence of a terminal event, so
        # a process killed mid-collection reported running forever — confirmed
        # by restarting the backend and watching a dead plan keep claiming it.
        # Now that extraction emits a heartbeat, silence past the threshold is
        # itself information: the work is not merely slow.
        age = (datetime.now(timezone.utc) - latest.created_at).total_seconds()
        state = "stalled" if age > _STALL_AFTER_SECONDS else "running"
    return {
        "plan_id": plan_id,
        "status": state,
        "message": latest.message,
        "last_event": latest.event,
        "sources_succeeded": sum(1 for e in events if e.event == "source_succeeded"),
        "sources_failed": sum(1 for e in events if e.event == "source_failed"),
        "updated_at": latest.created_at.isoformat(),
        # How long the plan has been silent, so a caller can judge for itself
        # rather than inferring liveness from the status string alone.
        "seconds_since_last_event": int(
            (datetime.now(timezone.utc) - latest.created_at).total_seconds()
        ),
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
# Activity log
# ---------------------------------------------------------------------------

@router.get("/collection-plans/{plan_id}/activity")
async def get_activity(plan_id: str, since: str | None = None, db: AsyncSession = Depends(get_db)):
    """Get the activity log for a collection plan, optionally filtered by timestamp."""
    stmt = (
        select(CollectionActivity)
        .where(CollectionActivity.plan_id == _parse_uuid(plan_id, "plan_id"))
        .order_by(CollectionActivity.created_at.asc())
    )
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            stmt = stmt.where(CollectionActivity.created_at > since_dt)
        except ValueError:
            pass
    result = await db.execute(stmt)
    return [
        {
            "id": str(a.id),
            "plan_id": str(a.plan_id),
            "source_id": str(a.source_id) if a.source_id else None,
            "event": a.event,
            "message": a.message,
            "created_at": a.created_at.isoformat(),
        }
        for a in result.scalars().all()
    ]


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
