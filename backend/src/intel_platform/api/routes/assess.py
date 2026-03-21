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
