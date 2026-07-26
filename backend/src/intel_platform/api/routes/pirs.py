"""Priority Intelligence Requirement (PIR) routes — the requirements spine.

A PIR is what a project is trying to answer. It is persisted per project and
carries the chain forward: every collection plan raised against it stores its
`pir_id`, so a PIR reports back the plans it drove and what they acquired.

Lives in Postgres alongside `collection_plans` (see `db/models.Pir`): the plan is
the thing a PIR drives, and keeping both in one store makes PIR → plan a join
rather than a cross-datastore lookup.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.api.deps import verify_api_key
from intel_platform.api.routes.collection_plans import _parse_uuid
from intel_platform.db.engine import get_db
from intel_platform.db.models import (
    PIR_PRIORITIES,
    PIR_STATUSES,
    CollectionPlan,
    Pir,
    PirStatus,
)
from intel_platform.models.requests import CreatePirRequest, UpdatePirRequest
from intel_platform.models.responses import PirPlanLink, PirResponse

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])

TITLE_MAX = 256


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_status(status: str) -> str:
    if status not in PIR_STATUSES:
        raise HTTPException(400, f"Invalid status: {status!r}. Expected one of {list(PIR_STATUSES)}")
    return status


def _validate_priority(priority: str) -> str:
    if priority not in PIR_PRIORITIES:
        raise HTTPException(400, f"Invalid priority: {priority!r}. Expected one of {list(PIR_PRIORITIES)}")
    return priority


def derive_title(text: str) -> str:
    """A short label for a PIR that the analyst did not title."""
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= 120:
        return cleaned
    return cleaned[:117].rstrip() + "..."


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _plan_link(plan: CollectionPlan) -> PirPlanLink:
    sources = plan.sources or []
    return PirPlanLink(
        id=str(plan.id),
        name=plan.name,
        status=plan.status,
        source_count=len(sources),
        records_acquired=sum(s.total_records_acquired or 0 for s in sources),
        created_at=plan.created_at.isoformat() if plan.created_at else "",
    )


def _pir_to_response(pir: Pir, plans: list[CollectionPlan] | None = None) -> PirResponse:
    links = [_plan_link(p) for p in (plans or [])]
    return PirResponse(
        id=str(pir.id),
        project_id=pir.project_id,
        title=pir.title or "",
        text=pir.text or "",
        refined_text=pir.refined_text or "",
        eeis=list(pir.eeis or []),
        priority=pir.priority or "medium",
        status=pir.status or PirStatus.OPEN,
        created_by=pir.created_by or "",
        created_at=pir.created_at.isoformat() if pir.created_at else "",
        updated_at=pir.updated_at.isoformat() if pir.updated_at else "",
        plan_count=len(links),
        plans=links,
    )


async def _plans_by_pir(db: AsyncSession, pir_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[CollectionPlan]]:
    """Load the collection plans raised against each PIR (one query, no N+1)."""
    if not pir_ids:
        return {}
    stmt = (
        select(CollectionPlan)
        .where(CollectionPlan.pir_id.in_(pir_ids))
        .order_by(CollectionPlan.created_at.desc())
    )
    result = await db.execute(stmt)
    grouped: dict[uuid.UUID, list[CollectionPlan]] = {}
    for plan in result.scalars().all():
        grouped.setdefault(plan.pir_id, []).append(plan)
    return grouped


# ---------------------------------------------------------------------------
# Shared helper — used by /collection-plans/from-pir so a plan generated from
# free text still lands on a persisted requirement instead of vanishing.
# ---------------------------------------------------------------------------

async def get_or_create_pir(
    db: AsyncSession,
    project_id: str,
    text: str,
    pir_id: str | None = None,
    created_by: str = "analyst",
) -> Pir | None:
    """Resolve the PIR a collection run belongs to.

    - `pir_id` given → that PIR (404 if unknown, 400 if it belongs elsewhere).
    - otherwise → reuse an existing live PIR in the project with the same text,
      or create one. Reuse keeps repeat runs of the same question on one
      requirement instead of spawning a duplicate per run.
    Returns None only when there is nothing to anchor (no id and no text).
    """
    if pir_id:
        pir = await db.get(Pir, _parse_uuid(pir_id, "pir_id"))
        if not pir:
            raise HTTPException(404, "PIR not found")
        if pir.project_id != project_id:
            raise HTTPException(400, "PIR belongs to a different project")
        return pir

    cleaned = (text or "").strip()
    if not cleaned:
        return None

    stmt = (
        select(Pir)
        .where(
            Pir.project_id == project_id,
            Pir.text == cleaned,
            Pir.status != PirStatus.ARCHIVED,
        )
        .order_by(Pir.created_at.desc())
        .limit(1)
    )
    existing = (await db.execute(stmt)).scalars().first()
    if existing:
        return existing

    pir = Pir(
        project_id=project_id,
        title=derive_title(cleaned),
        text=cleaned,
        status=PirStatus.OPEN,
        created_by=created_by,
    )
    db.add(pir)
    await db.flush()
    return pir


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.post("/pirs", response_model=PirResponse)
async def create_pir(req: CreatePirRequest, db: AsyncSession = Depends(get_db)) -> PirResponse:
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(400, "PIR text is required")

    pir = Pir(
        project_id=req.project_id,
        title=(req.title or "").strip()[:TITLE_MAX] or derive_title(text),
        text=text,
        refined_text=(req.refined_text or "").strip(),
        eeis=[e for e in (req.eeis or []) if e and e.strip()],
        priority=_validate_priority(req.priority),
        status=_validate_status(req.status),
        created_by=req.created_by,
    )
    db.add(pir)
    await db.commit()
    await db.refresh(pir)
    return _pir_to_response(pir)


@router.get("/pirs", response_model=list[PirResponse])
async def list_pirs(
    project_id: str,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[PirResponse]:
    """List a project's requirements, newest first, each with the plans it drove."""
    stmt = select(Pir).where(Pir.project_id == project_id).order_by(Pir.created_at.desc())
    if status:
        stmt = stmt.where(Pir.status == _validate_status(status))
    pirs = (await db.execute(stmt)).scalars().all()

    grouped = await _plans_by_pir(db, [p.id for p in pirs])
    return [_pir_to_response(p, grouped.get(p.id, [])) for p in pirs]


@router.get("/pirs/{pir_id}", response_model=PirResponse)
async def get_pir(pir_id: str, db: AsyncSession = Depends(get_db)) -> PirResponse:
    pir = await db.get(Pir, _parse_uuid(pir_id, "pir_id"))
    if not pir:
        raise HTTPException(404, "PIR not found")
    grouped = await _plans_by_pir(db, [pir.id])
    return _pir_to_response(pir, grouped.get(pir.id, []))


@router.put("/pirs/{pir_id}", response_model=PirResponse)
async def update_pir(
    pir_id: str, req: UpdatePirRequest, db: AsyncSession = Depends(get_db)
) -> PirResponse:
    pir = await db.get(Pir, _parse_uuid(pir_id, "pir_id"))
    if not pir:
        raise HTTPException(404, "PIR not found")

    if req.status is not None:
        pir.status = _validate_status(req.status)
    if req.priority is not None:
        pir.priority = _validate_priority(req.priority)
    if req.title is not None:
        pir.title = req.title.strip()[:TITLE_MAX]
    if req.text is not None:
        text = req.text.strip()
        if not text:
            raise HTTPException(400, "PIR text cannot be empty")
        pir.text = text
        if not pir.title:
            pir.title = derive_title(text)
    if req.refined_text is not None:
        pir.refined_text = req.refined_text.strip()
    if req.eeis is not None:
        pir.eeis = [e for e in req.eeis if e and e.strip()]

    pir.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(pir)
    grouped = await _plans_by_pir(db, [pir.id])
    return _pir_to_response(pir, grouped.get(pir.id, []))


@router.delete("/pirs/{pir_id}")
async def delete_pir(pir_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a PIR. Plans raised against it survive, unlinked — the collected
    intelligence outlives the question that prompted it."""
    parsed = _parse_uuid(pir_id, "pir_id")
    pir = await db.get(Pir, parsed)
    if not pir:
        raise HTTPException(404, "PIR not found")

    await db.execute(
        update(CollectionPlan).where(CollectionPlan.pir_id == parsed).values(pir_id=None)
    )
    await db.delete(pir)
    await db.commit()
    return {"deleted": True, "id": pir_id}
