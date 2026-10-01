"""Collection plan management API routes.

Provides full CRUD for collection plans and sources, file upload ingestion
through the collection pipeline, acquisition logging, and a status dashboard.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.collection import job_runner
from intel_platform.config import settings
from intel_platform.connectors.base import (
    CONNECTOR_REGISTRY,
    describe_collection_capabilities,
    get_connector,
)
from intel_platform.connectors.flat_file import detect_format, SUPPORTED_FORMATS
from intel_platform.db import jobs
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
from intel_platform.services.llm_output import normalise_line

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])

# The two events a run writes last. Used to split the activity trail into runs
# for the progress counts; whether a run is in flight comes from the job table.
_TERMINAL_EVENTS = ("plan_completed", "plan_failed")


def current_run_events(events: list) -> list:
    """The events belonging to the most recent run only.

    Progress counts were summed over the whole activity trail, so a plan run
    twice reported the first run's successes and failures alongside the
    second's — "2 succeeded, 2 failed" for a run that collected one source.
    Harmless while a plan could only ever be executed once; now that a finished
    plan can be run again, the trail routinely holds several runs.
    """
    terminals = [i for i, e in enumerate(events) if e.event in _TERMINAL_EVENTS]
    if not terminals:
        return events
    if terminals[-1] == len(events) - 1:
        # The trail ends on a finished run: it began after the one before it.
        return events[(terminals[-2] + 1) if len(terminals) > 1 else 0:]
    return events[terminals[-1] + 1:]


async def _run_state_and_job(db: AsyncSession, plan_id: uuid.UUID):
    """(state, latest job, database now) — the one read behind the guard and the status endpoint."""
    job, now = await jobs.latest_job(db, plan_id)
    return job_runner.run_state(job, now), job, now


async def current_run_state(db: AsyncSession, plan_id: uuid.UUID) -> str:
    """``idle | running | stalled | completed | failed | cancelled`` for the plan's latest run.

    Read from the job table, which every run writes whichever process runs it
    (see collection/job_runner.run_state for the rules). The execute guard and
    ``/execution-status`` both go through here, so what the analyst is shown
    and what the API enforces cannot disagree. Only ``running`` blocks a run.
    """
    state, _job, _now = await _run_state_and_job(db, plan_id)
    return state


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


# The label the requirement hides behind. "Refined PIR" is the form the prompt
# asks for; models also answer "Priority Intelligence Requirement (PIR)",
# "Proposed PIR", "Revised requirement", "4. Proposed Refined PIR" as a numbered
# heading, or a table row. Lines are normalised first (`normalise_line`), so
# emphasis, blockquotes, headings and list numbering are already gone and the
# pattern only has to describe the words.
_PIR_NOUN = r"(?:priority\s+intelligence\s+requirement|pir)(?:\s*\(\s*pir\s*\))?"
_QUALIFIER = r"(?:proposed|revised|refined|improved|updated|final|rewritten|new)"
_PIR_LABEL = re.compile(
    rf"^(?:(?:{_QUALIFIER}[\s,]+)+(?:{_PIR_NOUN}|requirement|version)|{_PIR_NOUN})"
    r"\s*(?:[:\-–—|]\s*(?P<body>.*))?$",
    re.IGNORECASE,
)

# The prompt's own section names. A reply that opens on one of these is
# analysis, not a requirement: "### 1. Assessment" was once stored as the PIR
# and then drove source resolution and the judge. Matched against the whole
# normalised line, so a requirement that merely begins "Identify …" survives —
# only the prompt's step text ("IDENTIFY hidden assumptions") is a section.
_SECTION_HEADING = re.compile(
    r"^(?:step\s*\d+\s*[:.\-]?\s*)?(?:"
    r"assess(?:ment)?(?:\s+of\s+(?:the\s+)?(?:original\s+)?(?:pir|requirement))?"
    r"|assess\s+specificity\b.*"
    r"|specificity(?:\s*,?\s*(?:and\s+)?(?:measurability|time[-\s]?bound(?:s|edness)?))*"
    r"|(?:identify\s+)?hidden\s+assumptions?(?:\s*\.\.\.)?|identify\s+hidden\s+assumptions\b.*"
    r"|break\s*down\b.*|breakdown"
    r"|(?:\d+\s*[-–]\s*\d+\s+)?essential\s+elements(?:\s+of\s+information)?(?:\s*\(\s*eeis?\s*\))?"
    r"|eeis?|propose\s+a\s+refined\b.*"
    r"|analysis|critique|rationale|summary|overview|recommendations?|assumptions?"
    r")\s*[:.]?$",
    re.IGNORECASE,
)

# A line introducing what follows rather than stating it.
_PREAMBLE = re.compile(
    r"^(?:here(?:'s|\s+is|\s+are)|below\s+is|sure|certainly|of\s+course|okay|ok\b|great"
    r"|i(?:'ve|\s+have|'ll|\s+will)|let\s+me|the\s+following)\b",
    re.IGNORECASE,
)


def _clean_candidate(text: str) -> str:
    """A normalised line with the quoting a model puts round a requirement removed."""
    return (text or "").strip().strip('"“”').strip("*_ |").strip()


def _candidate_kind(text: str) -> str:
    """Whether a cleaned line is the requirement: "ok", "skip" or "stop".

    "skip" is a line that introduces what follows (a preamble, anything ending
    in a colon) — keep looking. "stop" is one of the prompt's own sections: the
    reply has moved on to analysis, and taking the next line would store the
    model's critique as the requirement.
    """
    if not re.search(r"[^\W\d_]{2,}", text):
        return "skip"   # markdown punctuation, a rule, a bare number
    if _SECTION_HEADING.match(text):
        return "stop"
    if text.endswith(":") or _PREAMBLE.match(text):
        return "skip"
    return "ok"


def _split_refinement_parsed(content: str, fallback: str) -> tuple[str, str, bool]:
    """Split an LLM refinement into (refined PIR, analysis, parsed).

    `parsed` is False when nothing in the reply could be taken as the
    requirement and `fallback` was returned in its place. The caller must not
    store that fallback as a refinement: it is the original text wearing the
    refinement's name, and once written it was never corrected.

    The prompt asks for the refined PIR on the first line. Replies routinely
    arrive as a markdown-only line, then a blockquoted label, then the
    requirement in italics, then a critique of the rewrite — so the label is
    searched for across the whole reply before falling back to the first line
    that is neither a preamble nor one of the prompt's section headings.
    """
    text = (content or "").strip()
    if not text:
        return fallback, "", False

    lines = text.split("\n")

    def _requirement_from(start: int) -> tuple[str, str, bool]:
        for j in range(start, len(lines)):
            cleaned = _clean_candidate(normalise_line(lines[j]))
            kind = _candidate_kind(cleaned)
            if kind == "ok":
                return cleaned, "\n".join(lines[j + 1:]).strip(), True
            if kind == "stop":
                break
        return fallback, "", False

    # Pass 1: the labelled requirement, wherever it sits in the reply.
    for i, raw in enumerate(lines):
        label = _PIR_LABEL.match(normalise_line(raw))
        if not label:
            continue
        body = _clean_candidate(label.group("body") or "")
        kind = _candidate_kind(body) if body else "skip"
        if kind == "ok":
            return body, "\n".join(lines[i + 1:]).strip(), True
        if kind == "stop":
            return fallback, "", False
        return _requirement_from(i + 1)

    # Pass 2: no label anywhere — the first line that states something.
    return _requirement_from(0)


def _split_refinement(content: str, fallback: str) -> tuple[str, str]:
    """(refined PIR, analysis) — `_split_refinement_parsed` without the flag."""
    refined, analysis, _parsed = _split_refinement_parsed(content, fallback)
    return refined, analysis


def _parse_uuid(value: str, label: str = "ID") -> uuid.UUID:
    """Safely parse a UUID string, raising 400 on invalid input."""
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(400, f"Invalid {label}: {value!r}")


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

# Lengths match the String(n) columns in db/models.CollectionPlan. Past them
# the insert failed in Postgres and the client got a 500; they are now a 422.
_NAME_MAX = 256
_SHORT_MAX = 128
_STATUS_MAX = 20

# Every status a plan may be given. FAILED is the terminal state of a run that
# failed (see plan_executor.PLAN_FAILED).
_PLAN_STATUSES = frozenset({
    PlanStatus.DRAFT, PlanStatus.ACTIVE, PlanStatus.PAUSED,
    PlanStatus.COMPLETED, PlanStatus.ARCHIVED, "FAILED",
})


def _validate_plan_status(status: str) -> str:
    if status not in _PLAN_STATUSES:
        raise HTTPException(400, f"Invalid status: {status!r}. Expected one of {sorted(_PLAN_STATUSES)}")
    return status


class CreatePlanRequest(BaseModel):
    project_id: str
    name: str = Field(max_length=_NAME_MAX)
    description: str = ""
    requirement: str = ""
    pir: str = ""
    # Link to a first-class PIR (see api/routes/pirs.py). When omitted but `pir`
    # text is supplied, the plan is anchored to a matching/new PIR so free-typed
    # requirements still land on the project's requirements spine.
    pir_id: str | None = None
    refined_pir: str = ""
    status: str = Field(default=PlanStatus.DRAFT, max_length=_STATUS_MAX)
    routing_rules: dict = Field(default_factory=lambda: {
        "extract_entities": True,
        "store_documents": True,
    })
    created_by: str = Field(default="analyst", max_length=_SHORT_MAX)
    assigned_to: str = Field(default="", max_length=_SHORT_MAX)
    schedule_cron: str = Field(default="", max_length=_SHORT_MAX)


class UpdatePlanRequest(BaseModel):
    name: str | None = Field(default=None, max_length=_NAME_MAX)
    description: str | None = None
    requirement: str | None = None
    pir: str | None = None
    refined_pir: str | None = None
    status: str | None = Field(default=None, max_length=_STATUS_MAX)
    routing_rules: dict | None = None
    assigned_to: str | None = Field(default=None, max_length=_SHORT_MAX)
    schedule_cron: str | None = Field(default=None, max_length=_SHORT_MAX)


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
        status=_validate_plan_status(req.status),
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
    if "status" in update_data:
        # Any string used to be stored, and an ARCHIVED plan could be revived
        # by writing a new status over it. Un-archiving is not an edit.
        new_status = _validate_plan_status(update_data["status"])
        if plan.status == PlanStatus.ARCHIVED and new_status != PlanStatus.ARCHIVED:
            raise HTTPException(409, "An archived plan's status cannot be changed")
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
    if plan.status == PlanStatus.ARCHIVED:
        # Completing an archived plan un-archived it.
        raise HTTPException(400, "Cannot complete an archived plan")
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
    refined_ok = False
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
            refined_pir, plan_description, refined_ok = _split_refinement_parsed(
                refine_result.content, pir_text,
            )
            if not refined_ok:
                failures.append("refinement returned no usable requirement")
                # No requirement could be read, but the reply is still the
                # model's analysis — keep it so the EEIs it lists are captured.
                plan_description = (refine_result.content or "").strip()
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
                    "These are the ONLY collection methods this system has. "
                    "Propose a source only if one of them can actually reach it:\n"
                    f"{describe_collection_capabilities()}\n\n"
                    "A plan is judged on what it collects, not on how complete it "
                    "looks. Every source you list that this system cannot reach is a "
                    "row the analyst has to work out is dead. Prefer four sources that "
                    "will return data to seven that read well.\n\n"
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
    stored = (pir_record.refined_text or "").strip() if pir_record else ""
    if pir_record and refined_ok and (not stored or stored == (pir_record.text or "").strip()):
        # Carry the LLM's refinement back onto the requirement so the analyst
        # does not have to re-derive it on the next run — only when there is a
        # refinement to carry. This used to run on failure too, storing the
        # original text as its own refinement, and the "already refined" guard
        # then meant no later success could ever correct it. A stored value
        # equal to the original text is exactly that fallback, so a success now
        # replaces it; any other stored wording is someone's refinement and is
        # kept.
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


@router.post("/collection-plans/{plan_id}/execute", status_code=202)
async def execute_plan_endpoint(
    plan_id: str,
    body: ExecuteRequest | None = None,
    db: AsyncSession = Depends(get_db),
    store: GraphStore = Depends(get_graph_store),
):
    """Approve and execute a collection plan: 202 with the ``job_id`` of the run.

    Inserts a ``collection_jobs`` row. In ``inline`` worker mode the API process
    runs it at once as a background task; in ``worker`` mode it is ``queued``
    for ``python -m intel_platform.worker``. The run resolves sources, acquires
    them through the registered connectors, extracts entities into the graph,
    then re-tasks against the requirement's open elements. File upload sources
    are skipped (they need a manual upload). With nothing to run the plan is
    still activated, and ``job_id`` is null.
    """
    pid = _parse_uuid(plan_id, "plan_id")
    # The plan row stays locked until this request commits, so a second
    # execute for the same plan, in this process or another, waits here and
    # then sees the first one's job. The job table's one-live-job index is the
    # backstop if anything ever skipped this lock.
    plan = await db.get(CollectionPlan, pid, with_for_update=True)
    if not plan:
        raise HTTPException(404, "Collection plan not found")
    try:
        return await _start_execution(plan, body, db, store)
    except BaseException:
        await db.rollback()
        raise


async def _start_execution(
    plan: CollectionPlan, body: ExecuteRequest | None, db: AsyncSession, store: GraphStore,
) -> dict:
    """The execute guard and launch. Runs with the plan row locked."""
    # Refuse only when a run is genuinely in flight, not because of a status
    # flag. The old guard allowed DRAFT and PAUSED only, which made "Activate" —
    # the button an analyst naturally presses before running something — set
    # ACTIVE and thereby make the plan unrunnable, recoverable only by pressing
    # Pause. It also stranded any plan whose run died: execution sets ACTIVE, so
    # a crashed run left the plan permanently unexecutable.
    if plan.status == PlanStatus.ARCHIVED:
        raise HTTPException(400, "Cannot execute an archived plan")

    state, previous, now = await _run_state_and_job(db, plan.id)
    if state == "running":
        # A stalled run is deliberately not blocking: past the silence
        # threshold the previous attempt is presumed dead, and refusing forever
        # is how the old guard stranded plans.
        raise HTTPException(409, "A collection run is already in flight for this plan")
    if state == "stalled":
        # Close it before the new one: it holds the plan's one live job, and if
        # its worker is in fact alive, the next heartbeat finds the job gone
        # and stops the run.
        silent = job_runner.seconds_since(
            previous.heartbeat_at or previous.started_at or previous.created_at, now)
        await jobs.close_unfinished(
            db, plan.id, f"Stalled: no heartbeat for {silent} s; superseded by a new run")

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

    all_auto = [s for s in sources if s.enabled and s.source_type != "file_upload"]
    source_limit = body.source_limit if body else None
    max_results = max(1, min(25, body.max_results_per_source if body else 10))
    # A plan raised against a PIR is collected against its open elements even
    # with no planned sources: the loop goes straight to re-tasking. It used to
    # be set ACTIVE and left there, with the requirement loop never run.
    requirement_only = not all_auto and plan.pir_id is not None
    launched = bool(all_auto) or requirement_only

    # Activate the plan, recording the collection budget it was given. The PIR
    # assessor reports "stopped on the source limit", which must rest on what
    # the run was actually allowed rather than on a number the caller re-supplies
    # at assessment time. The routing rules are also how the run's parameters
    # reach a worker in another process.
    plan.status = PlanStatus.ACTIVE
    # The budget belongs to this run only. It used to persist when a later run
    # was started without one, so that run was assessed against a limit it was
    # never given.
    rules = {k: v for k, v in (plan.routing_rules or {}).items() if k != "source_limit"}
    if body and body.source_limit:
        rules["source_limit"] = body.source_limit
    rules["max_results_per_source"] = max_results
    plan.routing_rules = rules
    plan.updated_at = datetime.now(timezone.utc)

    mode = job_runner.worker_mode()
    job_id = None
    if launched:
        job_id = await jobs.insert_job(
            db, plan_id=plan.id, project_id=plan.project_id,
            kind=jobs.KIND_AGENTIC if all_auto else jobs.KIND_REQUIREMENTS,
            # Inline: this process claims it now, so no worker can take it too.
            claimed_by=job_runner.process_worker_id("api") if mode == job_runner.INLINE else None,
        )
    await db.commit()
    await db.refresh(plan)

    if launched and mode == job_runner.INLINE:
        from intel_platform.db.engine import get_session_factory

        # Bulk resolution + summarization go to the collection provider (local
        # Ollama when configured), which run_agentic_loop selects itself.
        job_runner.start_inline(job_id, get_store=lambda: store, db_factory=get_session_factory())

    if all_auto:
        message = f"Agentic execution started with {len(all_auto)} source(s)."
    elif requirement_only:
        message = "No planned sources; collecting against the requirement's open elements."
    else:
        message = "Plan activated but no automated sources found."
    if launched and mode == job_runner.WORKER:
        message += " Queued for a collection worker."
    return {
        **_plan_to_dict(plan),
        "job_id": str(job_id) if job_id else None,
        "worker_mode": mode,
        "execution_status": (
            ("started" if mode == job_runner.INLINE else "queued") if launched else "no_executable_sources"
        ),
        "message": message,
        "sources_queued": min(len(all_auto), source_limit) if source_limit else len(all_auto),
        "sources_manual": len(file_only),
        "sources_missing_config": len(missing_config),
        "source_limit": source_limit,
        "sources_over_budget": max(0, len(all_auto) - source_limit) if source_limit else 0,
        "warnings": warnings,
    }


@router.get("/collection-plans/{plan_id}/execution-status")
async def get_execution_status(plan_id: str, db: AsyncSession = Depends(get_db)):
    """Poll the execution progress of a collection plan's latest run.

    ``status`` is the job table's answer (``current_run_state``), the same one
    the execute guard enforces; the activity trail supplies the message and the
    per-run counts. ``job_status``, ``seconds_since_heartbeat`` and ``error``
    come from the job row so a caller can see why a run reads as it does.
    """
    pid = _parse_uuid(plan_id, "plan_id")
    state, job, now = await _run_state_and_job(db, pid)
    job_fields = _job_fields(job, now)

    result = await db.execute(
        select(CollectionActivity)
        .where(CollectionActivity.plan_id == pid)
        .order_by(CollectionActivity.created_at.asc())
    )
    events = result.scalars().all()
    if not events:
        return {
            "plan_id": plan_id, "status": state, "message": _job_message(state, job),
            "sources_succeeded": 0, "sources_failed": 0, **job_fields,
        }

    latest = events[-1]
    # Counts are for the current run only — see current_run_events. A live run
    # whose trail still ends on the previous run's terminal event has not
    # written anything of its own yet.
    if state == "running" and latest.event in _TERMINAL_EVENTS:
        this_run = []
        message = _job_message(state, job)
    else:
        this_run = current_run_events(events)
        message = latest.message
    return {
        "plan_id": plan_id,
        "status": state,
        "message": message,
        "last_event": latest.event,
        "sources_succeeded": sum(1 for e in this_run if e.event == "source_succeeded"),
        "sources_failed": sum(1 for e in this_run if e.event == "source_failed"),
        "updated_at": latest.created_at.isoformat(),
        # How long the plan has been silent, so a caller can judge for itself
        # rather than inferring liveness from the status string alone.
        "seconds_since_last_event": int(
            (datetime.now(timezone.utc) - latest.created_at).total_seconds()
        ),
        **job_fields,
    }


def _job_fields(job, now) -> dict:
    """What the status endpoint says about the job row. ``worker_id`` (a host
    name and pid) stays server-side."""
    if job is None:
        return {"job_id": None, "job_status": None}
    return {
        "job_id": str(job.id),
        "job_status": job.status,
        "heartbeat_at": job.heartbeat_at.isoformat() if job.heartbeat_at else None,
        "seconds_since_heartbeat": job_runner.seconds_since(job.heartbeat_at, now),
        "error": job.error,
        # This run's degraded outcomes ({subsystem: {reason: count}}), which
        # /health cannot show when a worker process ran it.
        "degraded": job.degraded or {},
    }


def _job_message(state: str, job) -> str:
    if job is None:
        return "No active execution"
    if state == "running":
        if job.status == jobs.QUEUED:
            return "Queued; waiting for a collection worker"
        if job.status == jobs.CANCELLED:
            return "Cancelling; the run stops before its next source"
        return "Run starting"
    if state == "stalled":
        return "No heartbeat from the run's worker; it is presumed dead. Running again is safe."
    if state == "failed":
        return job.error or "The collection run ended with an error"
    if state == "cancelled":
        return "The collection run was cancelled"
    return "Collection run complete"


@router.post("/collection-plans/{plan_id}/cancel", status_code=202)
async def cancel_plan_run(plan_id: str, db: AsyncSession = Depends(get_db)):
    """Cancel the plan's live run (queued, running, or stalled).

    A running job is marked ``cancelled`` and stops before its next source
    (``plan_should_stop`` reads it); ``stopping`` says so, and the run state
    stays ``running`` until it has. A queued or stalled job has nothing left to
    stop and is finished at once. 409 when no run is live.
    """
    pid = _parse_uuid(plan_id, "plan_id")
    # Same lock as /execute, so a cancel and a new run cannot interleave.
    plan = await db.get(CollectionPlan, pid, with_for_update=True)
    if not plan:
        raise HTTPException(404, "Collection plan not found")
    state, job, _now = await _run_state_and_job(db, pid)
    if job is None or job.status not in jobs.LIVE_STATUSES:
        # Decided before the rollback, which expires `job`.
        stopping_already = job is not None and job.status == jobs.CANCELLED and state == "running"
        await db.rollback()
        if stopping_already:
            raise HTTPException(409, "The collection run is already stopping")
        raise HTTPException(409, "No collection run is in flight for this plan")

    # Read before the update: an ORM-enabled UPDATE also refreshes `job`.
    job_id, previous = job.id, job.status
    stopping = state == "running" and previous == jobs.RUNNING
    await jobs.cancel(db, job_id, still_running=stopping)
    if stopping:
        message = "Cancelled; the run stops before its next source"
    elif previous == jobs.QUEUED:
        message = "Cancelled before a worker picked it up"
    else:
        message = "Cancelled a stalled run"
    db.add(CollectionActivity(plan_id=pid, event="run_cancelled", message=message))
    await db.commit()
    return {
        "plan_id": plan_id,
        "job_id": str(job_id),
        "status": jobs.CANCELLED,
        "previous_status": previous,
        "stopping": stopping,
        "message": message,
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
async def get_activity(
    plan_id: str,
    since: str | None = None,
    limit: int = Query(500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
):
    """A page of a plan's activity log, oldest first.

    Without `since`, the most recent `limit` events. With `since` (an ISO-8601
    timestamp, normally the last event the caller holds), up to `limit` events
    after it — so a poller pages forward instead of reloading the trail. The UI
    polls every 3 s and every poll used to load the whole trail; a malformed
    `since` was silently ignored, which also meant "load all of it", and is now
    a 400.
    """
    stmt = select(CollectionActivity).where(
        CollectionActivity.plan_id == _parse_uuid(plan_id, "plan_id")
    )
    if since:
        # An unencoded "+00:00" offset arrives as " 00:00" once the query
        # string is decoded; restore it rather than refusing the poll.
        since = re.sub(r" (\d{2}:\d{2})$", r"+\1", since.strip())
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "since must be an ISO-8601 timestamp")
        if since_dt.tzinfo is None:
            since_dt = since_dt.replace(tzinfo=timezone.utc)
        stmt = (
            stmt.where(CollectionActivity.created_at > since_dt)
            .order_by(CollectionActivity.created_at.asc())
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()
    else:
        stmt = stmt.order_by(CollectionActivity.created_at.desc()).limit(limit)
        rows = list(reversed((await db.execute(stmt)).scalars().all()))
    return [
        {
            "id": str(a.id),
            "plan_id": str(a.plan_id),
            "source_id": str(a.source_id) if a.source_id else None,
            "event": a.event,
            "message": a.message,
            "created_at": a.created_at.isoformat(),
        }
        for a in rows
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
        # spaCy is synchronous and CPU-bound (contract 15).
        return await asyncio.to_thread(extract_entities_nlp, text, doc_id)
