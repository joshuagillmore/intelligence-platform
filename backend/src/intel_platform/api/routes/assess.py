import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from intel_platform.api.deps import get_graph_store, require_project_access, verify_api_key
from intel_platform.graph.store import GraphStore
from intel_platform.models.responses import (
    AssessmentCreatedResponse,
    GeneratedAssessmentResponse,
    MultiAssessmentResponse,
)
from intel_platform.services.assessment import AssessmentService
from intel_platform.services.llm_output import labelled_probability_parsed
from intel_platform.services.telemetry import record_degraded

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])

# The one message a client sees when no model produced the product. Fixed text:
# the reason is logged, never returned.
LLM_UNAVAILABLE = "LLM provider unavailable"


class CreateAssessmentRequest(BaseModel):
    """An analyst's own assessment. The judgment and probability are theirs."""

    entity_id: str
    project_id: str
    judgment: str
    probability: float
    analyst: str = "system"
    methodology: str = ""


class GenerateAssessmentRequest(BaseModel):
    """Ask the model to produce an assessment from the entity's graph context.

    Separate from `CreateAssessmentRequest`, which this endpoint used to reuse:
    that model requires `judgment` and `probability`, which are precisely what
    this endpoint exists to produce, so every caller had to invent the answer in
    order to ask the question. The handler already treated both as optional —
    `req.judgment if req.judgment else 'None provided'`, and `req.probability`
    only as a fallback when the model emits nothing parseable — so the two had
    simply drifted apart.
    """

    entity_id: str
    project_id: str
    # Optional steer for the model, not the answer.
    judgment: str = ""
    # Used only if the generated assessment carries no parseable probability.
    probability: float = 0.5
    analyst: str = "llm"
    methodology: str = ""


@router.post(
    "/entities/{entity_id}/assess", response_model=AssessmentCreatedResponse,
    dependencies=[Depends(require_project_access("editor"))],
)
def create_assessment(
    entity_id: str,
    req: CreateAssessmentRequest,
    store: GraphStore = Depends(get_graph_store),
):
    svc = AssessmentService(store)
    result = svc.create_assessment(
        entity_id=entity_id,
        project_id=req.project_id,
        judgment=req.judgment,
        probability=req.probability,
        analyst=req.analyst,
        methodology=req.methodology,
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


class MultiAssessmentRequest(BaseModel):
    entity_ids: list[str]
    project_id: str
    judgment: str = ""
    probability: float = 0.5
    analyst: str = "system"
    methodology: str = ""


@router.post(
    "/assess/generate", response_model=GeneratedAssessmentResponse, response_model_exclude_unset=True,
    dependencies=[Depends(require_project_access("editor"))],
)
async def generate_assessment(req: GenerateAssessmentRequest, store: GraphStore = Depends(get_graph_store)):
    """Use LLM to generate an assessment for an entity based on graph context."""
    from intel_platform.services.graph_rag import GraphRAGPipeline

    # Get entity and its context. The Neo4j driver is synchronous.
    entity = await asyncio.to_thread(store.get_entity, req.entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Build context using Graph RAG
    pipeline = GraphRAGPipeline(store)
    rag_result = await pipeline.query(f"What do we know about {entity.get('name', '')}?", req.project_id)
    context = rag_result.get("context", "")

    # Get LLM provider (centralized selection respecting runtime overrides)
    from intel_platform.api.routes.llm import _get_provider
    provider = await _get_provider()

    if not provider:
        # A 200 carrying an error string was rendered and saved as though it
        # were an assessment. Failure is a status, not content.
        record_degraded("llm", "assessment_no_provider")
        raise HTTPException(status_code=503, detail=LLM_UNAVAILABLE)

    # Load threat assessment skill
    from intel_platform.llm.skills.loader import SkillsLoader
    loader = SkillsLoader()
    system = loader.get_system_prompt("threat_assessment", include_foundation=True) or ""

    entity_name = entity.get("name", "Unknown")
    entity_type = entity.get("entity_type", "Unknown")

    prompt = f"""Generate a structured threat assessment for the following entity:

Entity: {entity_name}
Type: {entity_type}

Graph Context:
{context}

Additional analyst input: {req.judgment if req.judgment else 'None provided'}

Provide: Entity Overview, Key Relationships, Threat Profile, Assessment with probability rating, Gaps, and Recommendations.

At the end of your assessment, provide:
PROBABILITY: [0.01-0.99 numeric value]
CONFIDENCE_LABEL: [Almost No Chance | Very Unlikely | Unlikely | Roughly Even Chance | Likely | Very Likely | Almost Certain]"""

    try:
        result = await provider.generate(
            messages=[{"role": "user", "content": prompt}],
            system=system,
            temperature=0.3,
            max_tokens=4096,
        )
    except Exception as exc:
        logger.exception("Failed to generate assessment for entity %s", req.entity_id)
        record_degraded("llm", "assessment_call_failed", detail=type(exc).__name__)
        # SECURITY: don't leak internal error details to client
        raise HTTPException(status_code=503, detail=LLM_UNAVAILABLE)
    if not (result.content or "").strip():
        # An empty reply is a failure wearing a success shape; saving it would
        # store an assessment with no judgement in it.
        logger.warning("Empty assessment reply for entity %s", req.entity_id)
        record_degraded("llm", "assessment_empty_reply")
        raise HTTPException(status_code=503, detail=LLM_UNAVAILABLE)

    # `parsed` is False when the reply carried no readable probability and the
    # request's fallback was stored instead — the caller must be able to tell
    # a default from the model's judgement.
    probability, parsed = labelled_probability_parsed(result.content, req.probability)

    # Save the assessment
    svc = AssessmentService(store)
    saved = await asyncio.to_thread(
        svc.create_assessment,
        entity_id=req.entity_id,
        project_id=req.project_id,
        judgment=result.content,
        probability=probability,
        analyst=req.analyst or "llm",
        methodology="LLM-generated threat assessment with Graph RAG context",
    )

    return {
        "assessment": result.content,
        "model": result.model,
        "tokens_used": result.total_tokens,
        **saved,
        "probability_parsed": parsed,
    }


@router.post(
    "/assess/multi", response_model=MultiAssessmentResponse, response_model_exclude_unset=True,
    dependencies=[Depends(require_project_access("editor"))],
)
def assess_multiple_entities(req: MultiAssessmentRequest, store: GraphStore = Depends(get_graph_store)):
    """Assess multiple entities at once — gathers context for all and returns combined assessment data."""
    entities_data = []
    for eid in req.entity_ids:
        entity = store.get_entity(eid)
        if entity:
            rels = store.get_relationships(eid)
            entities_data.append({
                "entity": entity,
                "relationships": rels,
                "relationship_count": len(rels),
            })

    # If judgment provided, create assessment for each
    assessments = []
    if req.judgment:
        svc = AssessmentService(store)
        for eid in req.entity_ids:
            result = svc.create_assessment(
                entity_id=eid, project_id=req.project_id,
                judgment=req.judgment, probability=req.probability,
                analyst=req.analyst, methodology=req.methodology,
            )
            assessments.append(result)

    return {
        "entities": entities_data,
        "assessments": assessments,
        "entity_count": len(entities_data),
    }
