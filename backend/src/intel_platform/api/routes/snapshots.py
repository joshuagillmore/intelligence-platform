from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore
import uuid
from datetime import datetime, timezone

router = APIRouter(dependencies=[Depends(verify_api_key)])

# In-memory snapshot storage
_snapshots: dict[str, dict] = {}


class CreateSnapshotRequest(BaseModel):
    project_id: str
    name: str
    entity_ids: list[str]
    description: str = ""


@router.post("/snapshots")
def create_snapshot(req: CreateSnapshotRequest, store: GraphStore = Depends(get_graph_store)):
    """Save a subgraph snapshot (bin) for later analysis."""
    snapshot_id = str(uuid.uuid4())

    # Gather entity data
    entities = []
    for eid in req.entity_ids:
        entity = store.get_entity(eid)
        if entity:
            entities.append({
                "id": entity.get("id"),
                "name": entity.get("name"),
                "entity_type": entity.get("entity_type"),
            })

    _snapshots[snapshot_id] = {
        "id": snapshot_id,
        "project_id": req.project_id,
        "name": req.name,
        "description": req.description,
        "entity_ids": req.entity_ids,
        "entities": entities,
        "entity_count": len(entities),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    return _snapshots[snapshot_id]


@router.get("/snapshots")
def list_snapshots(project_id: str):
    """List all snapshots for a project."""
    return {
        "snapshots": [s for s in _snapshots.values() if s["project_id"] == project_id],
        "count": sum(1 for s in _snapshots.values() if s["project_id"] == project_id),
    }


@router.get("/snapshots/{snapshot_id}")
def get_snapshot(snapshot_id: str, store: GraphStore = Depends(get_graph_store)):
    """Get a snapshot with full entity and relationship data."""
    snapshot = _snapshots.get(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    # Get current relationships between snapshot entities
    entity_ids = set(snapshot["entity_ids"])
    edges = []
    for eid in entity_ids:
        rels = store.get_relationships(eid)
        for rel in rels:
            target_id = rel.get("target_id", "")
            if target_id in entity_ids:
                edges.append({
                    "source_id": eid,
                    "target_id": target_id,
                    "rel_type": rel.get("rel_type"),
                    "confidence": rel.get("confidence", rel.get("props", {}).get("confidence")),
                })

    return {
        **snapshot,
        "edges": edges,
        "edge_count": len(edges),
    }


@router.delete("/snapshots/{snapshot_id}")
def delete_snapshot(snapshot_id: str):
    if snapshot_id not in _snapshots:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    del _snapshots[snapshot_id]
    return {"status": "deleted"}
