"""Satisfaction assessment — does the collected intelligence answer the PIR?

``POST /pirs/{pir_id}/assess``. The judging itself (budget, graph sample,
context, the model exchange, the verdicts) is ``services/pir_judge``; this
route loads the requirement, runs the steps in order, persists the status and
shapes the response.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.api.deps import get_graph_store
from intel_platform.api.routes.collection_plans.plans import _parse_uuid
from intel_platform.db.engine import get_db
from intel_platform.db.models import CollectionPlan, Pir, PirStatus
from intel_platform.models.responses import PirAssessmentResponse
from intel_platform.services import pir_judge

logger = logging.getLogger(__name__)

# Mounted by the package router, which carries the API-key dependency.
router = APIRouter()


class AssessPirRequest(BaseModel):
    """Optional inputs for a satisfaction assessment."""

    # The collection budget this PIR was given. Reported back so a PARTIAL
    # result can distinguish "we answered it" from "we ran out of sources".
    source_limit: int | None = Field(default=None, ge=1)


@router.post("/pirs/{pir_id}/assess", response_model=PirAssessmentResponse)
async def assess_pir(
    pir_id: str,
    req: AssessPirRequest | None = None,
    db: AsyncSession = Depends(get_db),
    store=Depends(get_graph_store),
):
    """Judge whether what has been collected answers the PIR.

    Either the requirement is satisfied or collection stopped at its source
    limit — and in that case the analyst needs to know *which* elements are
    still unanswered, rather than being handed a pile of documents and left to
    infer it. Each EEI is judged against the project's own graph, never against
    the model's background knowledge.
    """
    parsed = _parse_uuid(pir_id, "pir_id")
    pir = await db.get(Pir, parsed)
    if not pir:
        raise HTTPException(404, "PIR not found")

    plans = (
        await db.execute(select(CollectionPlan).where(CollectionPlan.pir_id == parsed))
    ).scalars().all()
    budget = pir_judge.source_budget(plans, req.source_limit if req else None)

    eeis = pir_judge.criteria(pir)

    # Read off the ORM instance here, not inside the worker: touching an expired
    # attribute from another thread would surface as a MissingGreenlet.
    project_id = pir.project_id

    sample = await asyncio.to_thread(pir_judge.gather_graph, store, project_id)
    logger.info(
        "PIR %s judge input: sampled=%d total=%d substantive=%d relationship_lines=%d",
        pir_id, len(sample.entities), sample.total, len(sample.ranked), len(sample.facts),
    )

    context, dated, evidence = await pir_judge.build_context(sample, eeis, project_id, db)
    reply = await pir_judge.run_judge(pir, eeis, context, pir_id)
    settled = pir_judge.settle(reply.assessments, eeis)
    status = settled.status

    # Only move the stored status when there was a real judgement behind it —
    # a failed LLM call must not silently reopen a satisfied requirement. An
    # ARCHIVED requirement is retired by an analyst; judging it is allowed, but
    # the verdict is reported as `assessed_status` rather than reviving it.
    if settled.any_verdict and pir.status != PirStatus.ARCHIVED:
        pir.status = status
        pir.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(pir)

    exhausted = pir_judge.stopped_on_budget(budget, settled.any_verdict)
    recommendation = pir_judge.recommendation(
        settled, budget, exhausted=exhausted, judge_failed=reply.failed, eeis_total=len(eeis),
    )

    return {
        "pir_id": str(pir.id),
        "status": pir.status,
        # What this assessment concluded, which differs from `status` only when
        # the requirement is ARCHIVED (not revived) or nothing was judged (None).
        "assessed_status": status if settled.any_verdict else None,
        "eeis_total": len(eeis),
        "eeis_satisfied": len(settled.satisfied),
        "assessments": settled.assessments,
        "unmet_criteria": [
            {"eei": a["eei"], "verdict": a["verdict"], "why": a["justification"]} for a in settled.unmet
        ],
        "entities_considered": len(sample.entities),
        # How many the project holds. The judge sees a ranked sample, and the
        # size of the sample only means something beside the size of the whole.
        "entities_total": sample.total,
        # What the verdicts were actually judged from. A caller comparing two
        # assessments needs to know whether one saw the documents and the other
        # only the graph — otherwise a UNMET caused by a missing chunk index
        # reads identically to a UNMET caused by uncollected intelligence.
        "evidence": {
            "substrate": evidence.substrate,
            "dated_entities": dated,
            "passages_retrieved": evidence.retrieved,
            "elements_with_passages": evidence.elements_with_passages,
            "elements_without_passages": evidence.elements_without_passages,
            "retrieval_failed_for": evidence.failed_elements,
            "budget_starved_elements": evidence.budget_starved_elements,
            "embedding_fallback": evidence.embedding_fallback,
            "embedding_failed": evidence.embedding_failed,
            "embedding_dim_mismatch": evidence.embedding_dim_mismatch,
            # True when retrieval could not run at all. Without this a caller
            # sees retrieval_degraded with no attributable reason, which is the
            # complaint the degraded flag exists to answer.
            "retrieval_unavailable": evidence.unavailable,
            "retrieval_degraded": evidence.degraded,
        },
        # Succeeded sources in the most recently run plan — the run `source_limit`
        # belongs to. `sources_used_all_plans` is the requirement's lifetime total.
        "sources_used": budget.sources_used,
        "sources_used_all_plans": budget.sources_used_all_plans,
        "sources_configured": budget.sources_configured,
        "source_limit": budget.limit,
        "stopped_on_source_limit": exhausted and status != PirStatus.SATISFIED,
        "recommendation": recommendation,
        "model": reply.model,
        "narrative": reply.narrative,
    }
