"""Legacy collections API — redirects to the unified collection plans system.

The old Collections system stored PIR/plan data in Neo4j as pseudo-entities.
This has been replaced by the PostgreSQL-backed collection plans system which
provides proper relational storage, source management, acquisition logging,
and LLM-driven PIR→Plan→Execute flow.

Kept for backwards compatibility — new code should use /collection-plans.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.collection.runner import CollectionRunner
from intel_platform.graph.store import GraphStore
from intel_platform.services.collection_planner import parse_collection_plan

router = APIRouter(dependencies=[Depends(verify_api_key)])

logger = logging.getLogger(__name__)


class CreateCollectionRequest(BaseModel):
    project_id: str
    pir: str = ""
    plan: list[dict] = []
    refined_pir: str = ""
    refinement: str = ""


class UpdateCollectionRequest(BaseModel):
    refined_pir: str = ""
    refinement: str = ""
    plan: list[dict] = []
    status: str = ""


# ---------------------------------------------------------------------------
# Neo4j helpers (kept for reading legacy data)
# ---------------------------------------------------------------------------

def _save_collection_to_neo4j(store: GraphStore, collection: dict) -> None:
    props = {
        "id": collection["id"],
        "project_id": collection["project_id"],
        "pir": collection.get("pir", ""),
        "refined_pir": collection.get("refined_pir", ""),
        "refinement": collection.get("refinement", ""),
        "plan_json": json.dumps(collection.get("plan", [])),
        "status": collection.get("status", "PENDING"),
        "documents_acquired": collection.get("documents_acquired", 0),
        "created_at": collection.get("created_at", datetime.now(timezone.utc).isoformat()),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "entity_type": "Collection",
    }
    with store._driver.session() as session:
        session.run(
            "MERGE (c:Collection {id: $id}) SET c += $props",
            id=props["id"], props=props,
        )


def _load_collections_from_neo4j(store: GraphStore, project_id: str | None = None) -> list[dict]:
    with store._driver.session() as session:
        if project_id:
            result = session.run(
                "MATCH (c:Collection {project_id: $pid}) RETURN properties(c) as props ORDER BY c.created_at DESC",
                pid=project_id,
            )
        else:
            result = session.run(
                "MATCH (c:Collection) RETURN properties(c) as props ORDER BY c.created_at DESC"
            )
        collections = []
        for record in result:
            props = dict(record["props"])
            try:
                props["plan"] = json.loads(props.get("plan_json", "[]"))
            except (json.JSONDecodeError, TypeError):
                props["plan"] = []
            props.pop("plan_json", None)
            collections.append(props)
        return collections


def _get_collection_count(store: GraphStore, project_id: str) -> int:
    with store._driver.session() as session:
        result = session.run(
            "MATCH (c:Collection {project_id: $pid}) RETURN count(c) as cnt",
            pid=project_id,
        )
        record = result.single()
        return record["cnt"] if record else 0


# ---------------------------------------------------------------------------
# Legacy endpoints (backwards-compatible)
# ---------------------------------------------------------------------------

@router.post("/collections")
def create_collection(req: CreateCollectionRequest, store: GraphStore = Depends(get_graph_store)):
    """Legacy: create a collection. New code should use POST /collection-plans/from-pir."""
    collection = {
        "id": str(uuid.uuid4()),
        "project_id": req.project_id,
        "pir": req.pir,
        "refined_pir": req.refined_pir,
        "refinement": req.refinement,
        "plan": req.plan,
        "status": "PENDING",
        "documents_acquired": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_collection_to_neo4j(store, collection)
    return collection


@router.get("/collections/{task_id}")
def get_collection(task_id: str, store: GraphStore = Depends(get_graph_store)):
    with store._driver.session() as session:
        result = session.run("MATCH (c:Collection {id: $id}) RETURN properties(c) as props", id=task_id)
        record = result.single()
        if not record:
            raise HTTPException(status_code=404, detail="Collection task not found")
        props = dict(record["props"])
        try:
            props["plan"] = json.loads(props.get("plan_json", "[]"))
        except (json.JSONDecodeError, TypeError):
            props["plan"] = []
        props.pop("plan_json", None)
        return props


@router.put("/collections/{task_id}")
def update_collection(task_id: str, req: UpdateCollectionRequest, store: GraphStore = Depends(get_graph_store)):
    with store._driver.session() as session:
        updates = {}
        if req.refined_pir:
            updates["refined_pir"] = req.refined_pir
        if req.refinement:
            updates["refinement"] = req.refinement
        if req.plan:
            updates["plan_json"] = json.dumps(req.plan)
        if req.status:
            updates["status"] = req.status
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        if updates:
            set_clauses = ", ".join(f"c.{k} = ${k}" for k in updates)
            session.run(f"MATCH (c:Collection {{id: $id}}) SET {set_clauses}", id=task_id, **updates)
    return get_collection(task_id, store)


@router.get("/collections/{task_id}/status")
def get_collection_status(task_id: str, store: GraphStore = Depends(get_graph_store)):
    coll = get_collection(task_id, store)
    return {"status": coll.get("status"), "progress": coll.get("progress", 0), "documents_acquired": coll.get("documents_acquired", 0)}


@router.post("/collections/{task_id}/cancel")
def cancel_collection(task_id: str, store: GraphStore = Depends(get_graph_store)):
    with store._driver.session() as session:
        session.run(
            "MATCH (c:Collection {id: $id}) SET c.status = 'REVOKED', c.updated_at = $now",
            id=task_id, now=datetime.now(timezone.utc).isoformat(),
        )
    return {"status": "cancelled"}


@router.post("/collections/parse-plan")
def parse_plan(data: dict):
    plan_text = data.get("plan_text", "")
    items = parse_collection_plan(plan_text)
    return {"items": items, "count": len(items)}


@router.post("/collections/{task_id}/execute", status_code=202)
async def execute_collection(
    task_id: str,
    background_tasks: BackgroundTasks,
    extraction_mode: str = "nlp",
    store: GraphStore = Depends(get_graph_store),
):
    """Execute an approved collection plan: search -> crawl -> ingest -> extract."""
    coll = get_collection(task_id, store)
    if coll["status"] in ("STARTED", "PROGRESS"):
        raise HTTPException(status_code=409, detail="Collection is already running")

    plan = coll.get("plan", [])
    if not any(item.get("approved") for item in plan):
        raise HTTPException(status_code=400, detail="No approved plan items to execute")

    async def _run():
        try:
            runner = CollectionRunner(store)
            await runner.execute(
                collection_id=task_id,
                project_id=coll["project_id"],
                plan=plan,
                extraction_mode=extraction_mode,
            )
        except Exception:
            logger.exception("Collection execution failed: %s", task_id)
            now = datetime.now(timezone.utc).isoformat()
            with store._driver.session() as session:
                session.run(
                    "MATCH (c:Collection {id: $id}) SET c.status = 'FAILURE', c.updated_at = $now",
                    id=task_id, now=now,
                )

    background_tasks.add_task(_run)

    return {"collection_id": task_id, "status": "STARTED"}


@router.get("/collections/{task_id}/progress")
def get_collection_progress(task_id: str, store: GraphStore = Depends(get_graph_store)):
    """Get detailed collection execution progress."""
    coll = get_collection(task_id, store)
    # Count documents linked to this collection
    with store._driver.session() as session:
        result = session.run(
            "MATCH (d:Document {source_doc_id: $cid, project_id: $pid}) RETURN count(d) as cnt",
            cid=task_id, pid=coll["project_id"],
        )
        record = result.single()
        doc_count = record["cnt"] if record else 0

    return {
        "collection_id": task_id,
        "status": coll.get("status", "PENDING"),
        "progress": coll.get("progress", 0),
        "documents_acquired": coll.get("documents_acquired", 0),
        "documents_in_graph": doc_count,
    }


@router.get("/collections")
def list_collections(project_id: str | None = None, store: GraphStore = Depends(get_graph_store)):
    return _load_collections_from_neo4j(store, project_id)


@router.get("/collections/count/{project_id}")
def get_collection_count_for_project(project_id: str, store: GraphStore = Depends(get_graph_store)):
    return {"project_id": project_id, "count": _get_collection_count(store, project_id)}
