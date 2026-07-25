"""Structured analytic technique endpoints.

First-class, evidence-grounded workflows for the three tradecraft skills that
previously existed only as YAML prompts reachable through the LLM Hub:
source evaluation (Admiralty), Analysis of Competing Hypotheses, and gap
analysis. All three retrieve real project evidence before prompting and return
a deterministic result when no LLM provider is configured — see
``services/analytic_agents.py``.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.db.engine import get_db
from intel_platform.graph.store import GraphStore
from intel_platform.services.analytic_agents import AnalyticAgentService

router = APIRouter(dependencies=[Depends(verify_api_key)])
logger = logging.getLogger(__name__)


class SourceEvaluationRequest(BaseModel):
    project_id: str
    # Empty = every document in the project, highest entity-yield first.
    document_ids: list[str] = Field(default_factory=list)
    limit: int = Field(10, ge=1, le=25)
    # Opt-in: write the parsed Admiralty rating back onto the Document nodes so
    # Graph-RAG can caveat downstream claims by source quality. Off by default
    # so a model never silently overwrites an analyst's own rating.
    apply_ratings: bool = False


class HypothesesRequest(BaseModel):
    project_id: str
    question: str
    entity_ids: list[str] = Field(default_factory=list)
    max_hops: int = Field(2, ge=1, le=4)
    token_budget: int = Field(8000, ge=500, le=32000)
    use_vector: bool = True
    # Persists the leading hypothesis as an Assessment linked to the first
    # focus entity, exactly as /assess/generate does.
    save_assessment: bool = False
    analyst: str = "llm"


class GapAnalysisRequest(BaseModel):
    project_id: str
    entity_ids: list[str] = Field(default_factory=list)
    focus: str = ""
    max_hops: int = Field(2, ge=1, le=4)
    token_budget: int = Field(8000, ge=500, le=32000)


@router.post("/analysis/source-evaluation")
async def evaluate_sources(
    req: SourceEvaluationRequest,
    store: GraphStore = Depends(get_graph_store),
):
    """Grade the project's sources on the NATO Admiralty scale.

    Grounded in measured provenance: entity yield per document, corroboration
    against the project's other documents, content volume, origin URL, and any
    rating already on file.
    """
    svc = AnalyticAgentService(store)
    return await svc.evaluate_sources(
        project_id=req.project_id,
        document_ids=req.document_ids,
        limit=req.limit,
        apply_ratings=req.apply_ratings,
    )


@router.post("/analysis/hypotheses")
async def generate_hypotheses(
    req: HypothesesRequest,
    store: GraphStore = Depends(get_graph_store),
    session: AsyncSession = Depends(get_db),
):
    """Analysis of Competing Hypotheses over retrieved graph + document evidence."""
    svc = AnalyticAgentService(store)
    return await svc.generate_hypotheses(
        project_id=req.project_id,
        question=req.question,
        entity_ids=req.entity_ids,
        max_hops=req.max_hops,
        token_budget=req.token_budget,
        session=session,
        use_vector=req.use_vector,
        save_assessment=req.save_assessment,
        analyst=req.analyst,
    )


@router.post("/analysis/gaps")
async def analyze_gaps(
    req: GapAnalysisRequest,
    store: GraphStore = Depends(get_graph_store),
):
    """Intelligence gaps: measured graph-coverage holes, then a narrated read."""
    svc = AnalyticAgentService(store)
    return await svc.analyze_gaps(
        project_id=req.project_id,
        entity_ids=req.entity_ids,
        focus=req.focus,
        max_hops=req.max_hops,
        token_budget=req.token_budget,
    )
