from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore
from intel_platform.services.assessment import AssessmentService

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
