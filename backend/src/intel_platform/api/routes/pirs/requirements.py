"""Per-element (EEI) collection state for a PIR: ``GET /pirs/{pir_id}/requirements``."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.api.routes.collection_plans.plans import _parse_uuid
from intel_platform.db.engine import get_db
from intel_platform.db.models import Pir
from intel_platform.models.responses import PirRequirementsResponse

# Mounted by the package router, which carries the API-key dependency.
router = APIRouter()


@router.get("/pirs/{pir_id}/requirements", response_model=PirRequirementsResponse)
async def get_pir_requirements(pir_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Per-element collection state: what is answered, what was tried, what is missing.

    The assessor's reasoning was previously computed and discarded into a
    response payload nothing consumed. These rows are what the collection loop
    acts on, so exposing them is what lets an analyst see *why* a requirement is
    unfinished rather than only that it is.
    """
    from intel_platform.collection.requirement_loop import sync_requirements
    from intel_platform.db.models import PirRequirement

    pir = await db.get(Pir, _parse_uuid(pir_id, "pir_id"))
    if not pir:
        raise HTTPException(404, "PIR not found")

    # Materialise rows for a PIR whose elements predate this table, so an older
    # requirement reports its elements as pending rather than as absent.
    await sync_requirements(db, pir)
    await db.commit()

    rows = (await db.execute(
        select(PirRequirement)
        .where(PirRequirement.pir_id == pir.id)
        .order_by(PirRequirement.ordinal)
    )).scalars().all()

    elements = [
        {
            "ordinal": r.ordinal,
            "text": r.text,
            "status": r.status,
            "attempts": r.attempts,
            "queries_tried": list(r.next_queries or []),
            "missing": r.assessment_missing or "",
            "confidence": r.assessment_confidence or "",
        }
        for r in rows
    ]
    counts = {status: 0 for status in ("pending", "satisfied", "unmet")}
    for element in elements:
        counts[element["status"]] = counts.get(element["status"], 0) + 1

    return {
        "pir_id": str(pir.id),
        "project_id": pir.project_id,
        "total": len(elements),
        # "unmet" is tried-and-given-up-on; "pending" is still open. Collapsing
        # them would hide which elements collection actually attempted.
        "counts": counts,
        "elements": elements,
    }
