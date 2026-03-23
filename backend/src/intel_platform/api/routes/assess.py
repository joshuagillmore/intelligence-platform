import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore
from intel_platform.services.assessment import AssessmentService

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


class CreateAssessmentRequest(BaseModel):
    entity_id: str
    project_id: str
    judgment: str
    probability: float
    analyst: str = "system"
    methodology: str = ""


@router.post("/entities/{entity_id}/assess")
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


@router.post("/assess/generate")
async def generate_assessment(req: CreateAssessmentRequest, store: GraphStore = Depends(get_graph_store)):
    """Use LLM to generate an assessment for an entity based on graph context."""
    from intel_platform.services.graph_rag import GraphRAGPipeline

    # Get entity and its context
    entity = store.get_entity(req.entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Build context using Graph RAG
    pipeline = GraphRAGPipeline(store)
    rag_result = await pipeline.query(f"What do we know about {entity.get('name', '')}?", req.project_id)
    context = rag_result.get("context", "")

    # Get LLM provider (centralized selection respecting runtime overrides)
    from intel_platform.api.routes.llm import _get_provider
    provider = _get_provider()

    if not provider:
        return {"error": "No LLM provider configured", "entity_name": entity.get("name")}

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

        # Extract probability from LLM response
        prob_match = re.search(r'PROBABILITY:\s*(0\.\d+)', result.content)
        probability = float(prob_match.group(1)) if prob_match else req.probability

        # Save the assessment
        svc = AssessmentService(store)
        saved = svc.create_assessment(
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
        }
    except Exception:
        logger.exception("Failed to generate assessment for entity %s", req.entity_id)
        # SECURITY: don't leak internal error details to client
        return {"error": "Assessment generation failed", "entity_name": entity_name}


@router.post("/assess/multi")
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
