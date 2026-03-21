from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from intel_platform.api.deps import verify_api_key
from intel_platform.collection.tasks import CollectionManager
from intel_platform.services.collection_planner import parse_collection_plan

router = APIRouter(dependencies=[Depends(verify_api_key)])

_manager = CollectionManager()


class CreateCollectionRequest(BaseModel):
    project_id: str
    pir: str = ""
    plan: list[dict] = []


class ApproveCollectionRequest(BaseModel):
    pass


@router.post("/collections")
def create_collection(req: CreateCollectionRequest):
    task = _manager.create_task(project_id=req.project_id, pir=req.pir, plan=req.plan)
    return task.model_dump()


@router.get("/collections/{task_id}")
def get_collection(task_id: str):
    task = _manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Collection task not found")
    return task.model_dump()


@router.get("/collections/{task_id}/status")
def get_collection_status(task_id: str):
    task = _manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Collection task not found")
    return {"status": task.status, "progress": task.progress, "documents_acquired": task.documents_acquired}


@router.post("/collections/{task_id}/approve")
async def approve_collection(task_id: str):
    from intel_platform.collection.executor import CollectionExecutor

    task = _manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Collection task not found")
    executor = CollectionExecutor(_manager)
    result = await executor.execute_plan(task_id)
    return result


@router.post("/collections/{task_id}/cancel")
def cancel_collection(task_id: str):
    if not _manager.cancel_task(task_id):
        raise HTTPException(status_code=400, detail="Cannot cancel this task")
    return {"status": "cancelled"}


@router.post("/collections/parse-plan")
def parse_plan(data: dict):
    """Parse an LLM-generated collection plan into structured items."""
    plan_text = data.get("plan_text", "")
    items = parse_collection_plan(plan_text)
    return {"items": items, "count": len(items)}


@router.get("/collections")
def list_collections(project_id: str | None = None):
    tasks = _manager.list_tasks(project_id=project_id)
    return [t.model_dump() for t in tasks]
