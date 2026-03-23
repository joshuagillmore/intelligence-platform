from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore
from intel_platform.models.requests import CreateProjectRequest
from intel_platform.models.responses import ProjectResponse
from intel_platform.services.text_utils import normalize_datetime as _normalize_datetime

router = APIRouter(dependencies=[Depends(verify_api_key)])


class BatchDeleteRequest(BaseModel):
    project_ids: list[str]


@router.get("/projects")
def list_projects(store: GraphStore = Depends(get_graph_store)):
    # PERF: single Cypher query for all projects with stats, replacing N+1 pattern
    # (was: 3 separate DB calls per project for stats, latest_entity_time, collection_count)
    with store._driver.session() as session:
        result = session.run(
            """
            MATCH (p:Project)
            OPTIONAL MATCH (n {project_id: p.id}) WHERE NOT n:Project
            WITH p, count(n) as entity_count
            OPTIONAL MATCH (d:Document {project_id: p.id})
            WITH p, entity_count, count(d) as doc_count
            OPTIONAL MATCH (a {project_id: p.id})-[r]->(b {project_id: p.id})
            WITH p, entity_count, doc_count, count(r) as rel_count
            OPTIONAL MATCH (c:Collection {project_id: p.id})
            WITH p, entity_count, doc_count, rel_count, count(c) as coll_count
            RETURN properties(p) as props, entity_count, doc_count, rel_count, coll_count
            ORDER BY p.created_at DESC
            """
        )
        projects = []
        for record in result:
            p = record["props"]
            pid = p.get("id", "")
            created_at = _normalize_datetime(p.get("created_at", ""))
            updated_at = _normalize_datetime(p.get("updated_at", "")) or created_at

            projects.append({
                "id": pid,
                "name": p.get("name", ""),
                "description": p.get("description", ""),
                "classification_level": p.get("classification_level", "UNCLASSIFIED"),
                "priority": p.get("priority", "medium"),
                "status": p.get("status", "active"),
                "created_at": created_at or "",
                "updated_at": updated_at or "",
                "collection_count": record["coll_count"],
                "entity_count": record["entity_count"],
                "document_count": record["doc_count"],
                "relationship_count": record["rel_count"],
            })
    return projects


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
        status=project["status"],
        created_at=_normalize_datetime(project.get("created_at", "")),
        updated_at=_normalize_datetime(project.get("updated_at", "")),
        **stats,
    )


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, store: GraphStore = Depends(get_graph_store)):
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    stats = store.get_project_stats(project_id)
    try:
        from intel_platform.api.routes.collections import _get_collection_count
        coll_count = _get_collection_count(store, project_id)
    except Exception:
        coll_count = 0
    return ProjectResponse(
        id=project["id"], name=project["name"], description=project["description"],
        classification_level=project["classification_level"], priority=project["priority"],
        status=project["status"],
        created_at=_normalize_datetime(project.get("created_at", "")),
        updated_at=_normalize_datetime(project.get("updated_at", "")),
        collection_count=coll_count,
        **stats,
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
        status=updated["status"],
        created_at=_normalize_datetime(updated.get("created_at", "")),
        updated_at=_normalize_datetime(updated.get("updated_at", "")),
        **stats,
    )


@router.post("/projects/batch-delete")
def batch_delete_projects(req: BatchDeleteRequest, store: GraphStore = Depends(get_graph_store)):
    deleted = 0
    for pid in req.project_ids:
        with store._driver.session() as session:
            session.run("MATCH (n {project_id: $pid}) DETACH DELETE n", pid=pid)
            session.run("MATCH (p:Project {id: $pid}) DETACH DELETE p", pid=pid)
        deleted += 1
    return {"deleted": deleted}


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, store: GraphStore = Depends(get_graph_store)):
    # Delete all entities in project with single query
    with store._driver.session() as session:
        result = session.run(
            "MATCH (n {project_id: $pid}) DETACH DELETE n RETURN count(n) as deleted",
            pid=project_id,
        )
        record = result.single()
        entities_deleted = record["deleted"] if record else 0
    # Delete the project itself
    store.delete_entity(project_id)
    return {"status": "deleted", "entities_removed": entities_deleted}


@router.get("/projects/{project_id}/activity")
def get_project_activity(project_id: str, limit: int = 20, store: GraphStore = Depends(get_graph_store)):
    """Get recent activity for a project."""
    entities = store.search_entities(project_id=project_id, limit=limit)

    activity = []
    for e in entities:
        created = _normalize_datetime(e.get("created_at", ""))

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
