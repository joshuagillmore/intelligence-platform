import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore

router = APIRouter(dependencies=[Depends(verify_api_key)])


class CreateSnapshotRequest(BaseModel):
    project_id: str
    name: str
    entity_ids: list[str]
    description: str = ""


@router.post("/snapshots")
def create_snapshot(req: CreateSnapshotRequest, store: GraphStore = Depends(get_graph_store)):
    """Save a subgraph snapshot (bin) for later analysis."""
    snapshot_id = str(uuid.uuid4())

    # Gather entity metadata
    entities = []
    for eid in req.entity_ids:
        entity = store.get_entity(eid)
        if entity:
            entities.append({
                "id": entity.get("id"),
                "name": entity.get("name"),
                "entity_type": entity.get("entity_type"),
            })

    created_at = datetime.now(timezone.utc).isoformat()

    with store._driver.session() as session:
        session.run(
            """
            CREATE (s:Snapshot {
                id: $id,
                project_id: $project_id,
                name: $name,
                description: $description,
                entity_ids: $entity_ids,
                entities_json: $entities_json,
                entity_count: $entity_count,
                created_at: $created_at
            })
            """,
            id=snapshot_id,
            project_id=req.project_id,
            name=req.name,
            description=req.description,
            entity_ids=req.entity_ids,
            entities_json=json.dumps(entities),
            entity_count=len(entities),
            created_at=created_at,
        )

    return {
        "id": snapshot_id,
        "project_id": req.project_id,
        "name": req.name,
        "description": req.description,
        "entity_ids": req.entity_ids,
        "entities": entities,
        "entity_count": len(entities),
        "created_at": created_at,
    }


@router.get("/snapshots")
def list_snapshots(project_id: str, store: GraphStore = Depends(get_graph_store)):
    """List all snapshots for a project."""
    with store._driver.session() as session:
        result = session.run(
            """
            MATCH (s:Snapshot {project_id: $pid})
            RETURN properties(s) as props
            ORDER BY s.created_at DESC
            """,
            pid=project_id,
        )
        snapshots = []
        for record in result:
            props = record["props"]
            props["entities"] = json.loads(props.pop("entities_json", "[]"))
            snapshots.append(props)

    return {"snapshots": snapshots, "count": len(snapshots)}


@router.get("/snapshots/{snapshot_id}")
def get_snapshot(snapshot_id: str, store: GraphStore = Depends(get_graph_store)):
    """Get a snapshot with full entity and relationship data."""
    with store._driver.session() as session:
        result = session.run(
            "MATCH (s:Snapshot {id: $id}) RETURN properties(s) as props",
            id=snapshot_id,
        )
        record = result.single()

    if not record:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    snapshot = record["props"]
    snapshot["entities"] = json.loads(snapshot.pop("entities_json", "[]"))

    # Get current relationships between snapshot entities
    entity_ids = set(snapshot.get("entity_ids", []))
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
def delete_snapshot(snapshot_id: str, store: GraphStore = Depends(get_graph_store)):
    with store._driver.session() as session:
        result = session.run(
            "MATCH (s:Snapshot {id: $id}) DELETE s RETURN count(*) as deleted",
            id=snapshot_id,
        )
        record = result.single()
        if not record or record["deleted"] == 0:
            raise HTTPException(status_code=404, detail="Snapshot not found")
    return {"status": "deleted"}
