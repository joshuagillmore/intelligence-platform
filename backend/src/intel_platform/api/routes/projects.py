from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore
from intel_platform.models.requests import CreateProjectRequest
from intel_platform.models.responses import ProjectResponse

router = APIRouter(dependencies=[Depends(verify_api_key)])


class BatchDeleteRequest(BaseModel):
    project_ids: list[str]


@router.get("/projects")
def list_projects(store: GraphStore = Depends(get_graph_store)):
    projects = store.list_projects()
    result = []
    for p in projects:
        pid = p.get("id", "")
        try:
            stats = store.get_project_stats(pid)
        except Exception:
            stats = {"entity_count": 0, "relationship_count": 0, "document_count": 0}
        result.append({
            "id": pid,
            "name": p.get("name", ""),
            "description": p.get("description", ""),
            "classification_level": p.get("classification_level", "UNCLASSIFIED"),
            "priority": p.get("priority", "medium"),
            "status": p.get("status", "active"),
            **stats,
        })
    return result


@router.post("/projects", response_model=ProjectResponse)
def create_project(req: CreateProjectRequest, store: GraphStore = Depends(get_graph_store)):
    project = store.create_project(
        name=req.name, description=req.description,
        classification_level=req.classification_level, priority=req.priority,
    )
    stats = store.get_project_stats(project["id"])
    return ProjectResponse(
        id=project["id"], name=project["name"], description=project["description"],
        classification_level=project["classification_level"], priority=project["priority"],
        status=project["status"], **stats,
    )


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, store: GraphStore = Depends(get_graph_store)):
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    stats = store.get_project_stats(project_id)
    return ProjectResponse(
        id=project["id"], name=project["name"], description=project["description"],
        classification_level=project["classification_level"], priority=project["priority"],
        status=project["status"], **stats,
    )


@router.put("/projects/{project_id}", response_model=ProjectResponse)
def update_project(project_id: str, req: CreateProjectRequest, store: GraphStore = Depends(get_graph_store)):
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    store.update_project(project_id, name=req.name, description=req.description,
                         classification_level=req.classification_level, priority=req.priority)
    updated = store.get_project(project_id)
    stats = store.get_project_stats(project_id)
    return ProjectResponse(
        id=updated["id"], name=updated["name"], description=updated["description"],
        classification_level=updated["classification_level"], priority=updated["priority"],
        status=updated["status"], **stats,
    )


@router.post("/projects/batch-delete")
def batch_delete_projects(req: BatchDeleteRequest, store: GraphStore = Depends(get_graph_store)):
    deleted = 0
    for pid in req.project_ids:
        project = store.get_project(pid)
        if project:
            # Delete all entities in the project first
            entities = store.search_entities(project_id=pid, limit=10000)
            for e in entities:
                store.delete_entity(e.get("id", ""))
            store.delete_entity(pid)
            deleted += 1
    return {"deleted": deleted}


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, store: GraphStore = Depends(get_graph_store)):
    # Delete all entities in the project
    entities = store.search_entities(project_id=project_id, limit=10000)
    for e in entities:
        store.delete_entity(e.get("id", ""))
    # Delete the project itself
    store.delete_entity(project_id)
    return {"status": "deleted", "entities_removed": len(entities)}


@router.get("/projects/{project_id}/activity")
def get_project_activity(project_id: str, limit: int = 20, store: GraphStore = Depends(get_graph_store)):
    """Get recent activity for a project."""
    entities = store.search_entities(project_id=project_id, limit=limit)

    activity = []
    for e in entities:
        created = e.get("created_at", "")
        if isinstance(created, dict):
            dt = created.get("_DateTime__date", {})
            tm = created.get("_DateTime__time", {})
            year = dt.get("_Date__year", 2026)
            month = dt.get("_Date__month", 1)
            day = dt.get("_Date__day", 1)
            hour = tm.get("_Time__hour", 0)
            minute = tm.get("_Time__minute", 0)
            created = f"{year}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00Z"
        elif hasattr(created, "isoformat"):
            created = created.isoformat()
        else:
            created = str(created) if created else ""

        etype = e.get("entity_type", "")
        if etype == "Document":
            action = "Document ingested"
        elif etype == "Report":
            action = "Report generated"
        elif etype == "Assessment":
            action = "Assessment created"
        else:
            action = f"{etype} extracted"

        activity.append({
            "id": e.get("id", ""),
            "action": action,
            "entity_name": e.get("name", ""),
            "entity_type": etype,
            "timestamp": created,
        })

    activity.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return {"activity": activity[:limit], "count": len(activity)}
