"""Collection plans and their sources: CRUD and status transitions.

Also home to what the other collection-plan modules, and the PIR routes, share:
``_parse_uuid`` and the plan and source serialisers.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.api.access import visible_projects
from intel_platform.api.deps import ProjectAccess, require_project_access
from intel_platform.connectors.base import CONNECTOR_REGISTRY, get_connector
from intel_platform.db.engine import get_db
from intel_platform.db.models import CollectionPlan, CollectionSource, PlanStatus
from intel_platform.models.responses import (
    CollectionPlanResponse,
    CollectionSourceResponse,
    DeletedResponse,
)

# Mounted by the package router, which carries the API-key dependency.
router = APIRouter()


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
    # Link to a first-class PIR (see api/routes/pirs/). When omitted but `pir`
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


# ---------------------------------------------------------------------------
# Collection Plan CRUD
# ---------------------------------------------------------------------------

@router.post(
    "/collection-plans", response_model=CollectionPlanResponse,
    dependencies=[Depends(require_project_access("editor"))],
)
async def create_plan(req: CreatePlanRequest, db: AsyncSession = Depends(get_db)):
    # Local import: the PIR routes import this module's _parse_uuid.
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


@router.get("/collection-plans", response_model=list[CollectionPlanResponse])
async def list_plans(
    project_id: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    access: ProjectAccess = Depends(require_project_access("viewer")),
):
    stmt = select(CollectionPlan).order_by(CollectionPlan.updated_at.desc())
    if project_id:
        stmt = stmt.where(CollectionPlan.project_id == project_id)
    if status:
        stmt = stmt.where(CollectionPlan.status == status)
    result = await db.execute(stmt)
    plans = result.scalars().all()
    if not project_id and not access.is_admin:
        # Unscoped, this lists every project's plans: keep the readable ones.
        visible = await visible_projects(access.user, {p.project_id for p in plans})
        plans = [p for p in plans if p.project_id in visible]
    return [_plan_to_dict(p) for p in plans]


@router.get(
    "/collection-plans/{plan_id}", response_model=CollectionPlanResponse,
    dependencies=[Depends(require_project_access("viewer"))],
)
async def get_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    plan = await db.get(CollectionPlan, _parse_uuid(plan_id, "plan_id"))
    if not plan:
        raise HTTPException(404, "Collection plan not found")
    return _plan_to_dict(plan)


@router.put(
    "/collection-plans/{plan_id}", response_model=CollectionPlanResponse,
    dependencies=[Depends(require_project_access("editor"))],
)
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


@router.delete(
    "/collection-plans/{plan_id}", response_model=DeletedResponse,
    dependencies=[Depends(require_project_access("editor"))],
)
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

@router.post(
    "/collection-plans/{plan_id}/activate", response_model=CollectionPlanResponse,
    dependencies=[Depends(require_project_access("editor"))],
)
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


@router.post(
    "/collection-plans/{plan_id}/pause", response_model=CollectionPlanResponse,
    dependencies=[Depends(require_project_access("editor"))],
)
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


@router.post(
    "/collection-plans/{plan_id}/complete", response_model=CollectionPlanResponse,
    dependencies=[Depends(require_project_access("editor"))],
)
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


@router.post(
    "/collection-plans/{plan_id}/archive", response_model=CollectionPlanResponse,
    dependencies=[Depends(require_project_access("editor"))],
)
async def archive_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    plan = await db.get(CollectionPlan, _parse_uuid(plan_id, "plan_id"))
    if not plan:
        raise HTTPException(404, "Collection plan not found")
    plan.status = PlanStatus.ARCHIVED
    plan.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _plan_to_dict(plan)


# ---------------------------------------------------------------------------
# Source assignment
# ---------------------------------------------------------------------------

@router.post(
    "/collection-plans/{plan_id}/sources", response_model=CollectionSourceResponse,
    dependencies=[Depends(require_project_access("editor"))],
)
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


@router.get(
    "/collection-plans/{plan_id}/sources", response_model=list[CollectionSourceResponse],
    dependencies=[Depends(require_project_access("viewer"))],
)
async def list_sources(plan_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(CollectionSource).where(
        CollectionSource.plan_id == _parse_uuid(plan_id, "plan_id")
    ).order_by(CollectionSource.created_at)
    result = await db.execute(stmt)
    return [_source_to_dict(s) for s in result.scalars().all()]


@router.put(
    "/collection-plans/{plan_id}/sources/{source_id}", response_model=CollectionSourceResponse,
    dependencies=[Depends(require_project_access("editor"))],
)
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


@router.delete(
    "/collection-plans/{plan_id}/sources/{source_id}", response_model=DeletedResponse,
    dependencies=[Depends(require_project_access("editor"))],
)
async def delete_source(plan_id: str, source_id: str, db: AsyncSession = Depends(get_db)):
    source = await db.get(CollectionSource, _parse_uuid(source_id, "source_id"))
    if not source or str(source.plan_id) != plan_id:
        raise HTTPException(404, "Source not found")
    await db.delete(source)
    await db.commit()
    return {"deleted": True, "id": source_id}
