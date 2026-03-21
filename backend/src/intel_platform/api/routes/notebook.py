from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore
from intel_platform.models.entities import Entity, EntityType, Report
from intel_platform.models.relationships import Relationship

router = APIRouter(dependencies=[Depends(verify_api_key)])


class NoteRequest(BaseModel):
    project_id: str
    title: str
    content: str
    entity_ids: list[str] = []
    note_type: str = "observation"  # observation, hypothesis, question, conclusion


@router.post("/notebook")
def create_note(req: NoteRequest, store: GraphStore = Depends(get_graph_store)):
    note = Report(
        name=req.title,
        content=req.content,
        report_type="notebook_entry",
        project_id=req.project_id,
    )
    store.create_entity(note)

    # Link to referenced entities
    for eid in req.entity_ids:
        try:
            rel = Relationship(
                source_id=note.id,
                target_id=eid,
                rel_type="MENTIONS",
                confidence=1.0,
                source="notebook",
                method="analyst",
            )
            store.create_relationship(rel)
        except (ValueError, Exception):
            pass

    return {
        "note_id": note.id,
        "title": req.title,
        "note_type": req.note_type,
        "linked_entities": len(req.entity_ids),
    }


@router.get("/notebook")
def list_notes(project_id: str, store: GraphStore = Depends(get_graph_store)):
    notes = store.search_entities(
        project_id=project_id, entity_type="Report", limit=100
    )
    # Filter to notebook entries only
    notebook_entries = [n for n in notes if n.get("report_type") == "notebook_entry"]
    return notebook_entries


@router.get("/notebook/{note_id}")
def get_note(note_id: str, store: GraphStore = Depends(get_graph_store)):
    note = store.get_entity(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@router.delete("/notebook/{note_id}")
def delete_note(note_id: str, store: GraphStore = Depends(get_graph_store)):
    store.delete_entity(note_id)
    return {"status": "deleted"}
