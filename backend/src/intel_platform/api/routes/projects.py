import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore
from intel_platform.models.requests import CreateProjectRequest
from intel_platform.models.responses import (
    ProjectActivityResponse,
    ProjectBatchDeleteResponse,
    ProjectDeleteResponse,
    ProjectResponse,
)
from intel_platform.services.text_utils import normalize_datetime as _normalize_datetime

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


class BatchDeleteRequest(BaseModel):
    project_ids: list[str]


# Counts for every project at once, keyed by project_id. Each is a single pass
# the planner can serve from a label or property index.
#
# One statement per count reads worse than the one query this replaced, and is
# 28x faster on a real graph (5.44s -> 0.19s for 178 projects). The old query
# was already de-N+1'd in Cypher, but `OPTIONAL MATCH (n {project_id: p.id})`
# is unlabeled, so there is no index to use and Neo4j scanned every node once
# per project — the N+1 moved into the planner instead of going away. Cost grew
# with projects x graph size, and this is the landing page: every session paid
# it before seeing anything.
_COUNT_QUERIES = {
    "entity_count": """
        MATCH (n) WHERE n.project_id IS NOT NULL AND NOT n:Project
        RETURN n.project_id AS pid, count(*) AS c
    """,
    "document_count": """
        MATCH (d:Document) WHERE d.project_id IS NOT NULL
        RETURN d.project_id AS pid, count(*) AS c
    """,
    # Both endpoints in the same project, so a cross-project edge counts for
    # neither — as before.
    "relationship_count": """
        MATCH (a)-[r]->(b)
        WHERE a.project_id IS NOT NULL AND a.project_id = b.project_id
          AND NOT (type(r) = 'MENTIONS' AND a:Document)
        RETURN a.project_id AS pid, count(r) AS c
    """,
    "collection_count": """
        MATCH (c:Collection) WHERE c.project_id IS NOT NULL
        RETURN c.project_id AS pid, count(*) AS c
    """,
}


@router.get("/projects", response_model=list[ProjectResponse])
def list_projects(store: GraphStore = Depends(get_graph_store)):
    with store._driver.session() as session:
        counts = {
            field: {r["pid"]: r["c"] for r in session.run(query)}
            for field, query in _COUNT_QUERIES.items()
        }
        result = session.run(
            "MATCH (p:Project) RETURN properties(p) AS props ORDER BY p.created_at DESC"
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
                # A project with nothing in it is absent from the count maps,
                # which is a zero, not a missing value.
                "collection_count": counts["collection_count"].get(pid, 0),
                "entity_count": counts["entity_count"].get(pid, 0),
                "document_count": counts["document_count"].get(pid, 0),
                "relationship_count": counts["relationship_count"].get(pid, 0),
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


async def _delete_relational_rows(project_ids: list[str]) -> dict[str, int]:
    """Delete every Postgres row belonging to these projects, in one transaction.

    Children go before parents, explicitly: the plan tables declare ON DELETE
    CASCADE, but a table created before a constraint existed would not have it,
    and a delete that half-works is the failure this replaces.
    """
    from sqlalchemy import delete, select

    from intel_platform.db.engine import get_session_factory
    from intel_platform.db.models import (
        AcquisitionLog, ChunkEmbedding, CollectionActivity, CollectionPlan, CollectionSource,
        DataCatalog, Pir, PirRequirement, TopicEdit,
    )

    plan_ids = select(CollectionPlan.id).where(CollectionPlan.project_id.in_(project_ids))
    statements = [
        delete(AcquisitionLog).where(AcquisitionLog.plan_id.in_(plan_ids)),
        delete(CollectionActivity).where(CollectionActivity.plan_id.in_(plan_ids)),
        delete(DataCatalog).where(DataCatalog.plan_id.in_(plan_ids)),
        delete(CollectionSource).where(CollectionSource.plan_id.in_(plan_ids)),
        delete(CollectionPlan).where(CollectionPlan.project_id.in_(project_ids)),
        delete(PirRequirement).where(PirRequirement.project_id.in_(project_ids)),
        delete(Pir).where(Pir.project_id.in_(project_ids)),
        delete(ChunkEmbedding).where(ChunkEmbedding.project_id.in_(project_ids)),
        delete(TopicEdit).where(TopicEdit.project_id.in_(project_ids)),
    ]
    removed: dict[str, int] = {}
    async with get_session_factory()() as session:
        for statement in statements:
            result = await session.execute(statement)
            removed[statement.table.name] = result.rowcount or 0
        await session.commit()
    return removed


async def _delete_projects(store: GraphStore, project_ids: list[str]) -> tuple[dict[str, int], dict[str, int]]:
    """Delete projects from Postgres, then Neo4j. Postgres first: if it cannot be
    cleared, nothing has been deleted and the request can simply be retried.

    Returns (Neo4j nodes removed per project, Postgres rows removed per table).
    Raises 503 when Postgres fails; the detail carries no internal error text.
    """
    try:
        rows = await _delete_relational_rows(project_ids)
    except Exception:
        logger.exception("Project delete: Postgres cleanup failed for %s; nothing deleted", project_ids)
        raise HTTPException(
            status_code=503,
            detail="The project's stored documents and plans could not be removed; nothing was deleted. Try again.",
        )

    def delete_graph() -> dict[str, int]:
        nodes: dict[str, int] = {}
        with store._driver.session() as session:
            for pid in project_ids:
                record = session.run(
                    "MATCH (n {project_id: $pid}) DETACH DELETE n RETURN count(n) AS deleted", pid=pid,
                ).single()
                # A Project node written without its own project_id property.
                extra = session.run(
                    "MATCH (p:Project {id: $pid}) DETACH DELETE p RETURN count(p) AS deleted", pid=pid,
                ).single()
                nodes[pid] = (record["deleted"] if record else 0) + (extra["deleted"] if extra else 0)
        return nodes

    nodes = await asyncio.to_thread(delete_graph)
    from intel_platform.services.graph_cache import graph_cache
    for pid in project_ids:
        graph_cache.invalidate(pid)
    return nodes, rows


@router.post("/projects/batch-delete", response_model=ProjectBatchDeleteResponse)
async def batch_delete_projects(req: BatchDeleteRequest, store: GraphStore = Depends(get_graph_store)):
    project_ids = list(dict.fromkeys(req.project_ids))
    nodes, rows = await _delete_projects(store, project_ids)
    # Only ids that held anything count; an id that never existed was not deleted.
    return {"deleted": sum(1 for n in nodes.values() if n), "relational_rows_removed": rows}


@router.delete("/projects/{project_id}", response_model=ProjectDeleteResponse)
async def delete_project(project_id: str, store: GraphStore = Depends(get_graph_store)):
    nodes, rows = await _delete_projects(store, [project_id])
    return {"status": "deleted", "entities_removed": nodes[project_id], "relational_rows_removed": rows}


@router.get("/projects/{project_id}/activity", response_model=ProjectActivityResponse)
def get_project_activity(
    project_id: str, limit: int = Query(20, ge=1, le=500), store: GraphStore = Depends(get_graph_store),
):
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
