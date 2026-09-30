from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore
from intel_platform.models.entities import Report
from intel_platform.models.relationships import Relationship

router = APIRouter(dependencies=[Depends(verify_api_key)])


class NoteRequest(BaseModel):
    project_id: str
    title: str
    content: str
    entity_ids: list[str] = []
    note_type: Literal["observation", "hypothesis", "question", "conclusion"] = "observation"


@router.post("/notebook")
def create_note(req: NoteRequest, store: GraphStore = Depends(get_graph_store)):
    note = Report(
        name=req.title,
        content=req.content,
        report_type="notebook_entry",
        project_id=req.project_id,
    )
    store.create_entity(note)
    # Report has no note_type field, so it is written onto the node here; it
    # used to be echoed in the response and then lost.
    store.update_entity(note.id, {"note_type": req.note_type})

    # Link to referenced entities, counting only the links actually made.
    linked = 0
    unlinked: list[str] = []
    for eid in req.entity_ids:
        try:
            created = store.create_relationship(Relationship(
                source_id=note.id,
                target_id=eid,
                rel_type="MENTIONS",
                confidence=1.0,
                source="notebook",
                method="analyst",
                project_id=req.project_id,
            ))
        except ValueError:
            created = None
        if created:
            linked += 1
        else:
            unlinked.append(eid)

    return {
        "note_id": note.id,
        "title": req.title,
        "note_type": req.note_type,
        "linked_entities": linked,
        "unlinked_entity_ids": unlinked,
    }


@router.get("/notebook")
def list_notes(project_id: str, store: GraphStore = Depends(get_graph_store)):
    # Filtered in the query. Fetching the first 100 Reports of every kind by
    # name and filtering here showed an empty notebook to any project with
    # enough other reports ahead of its notes in the alphabet.
    with store._driver.session() as session:
        result = session.run(
            """
            MATCH (n:Report {project_id: $pid})
            WHERE n.report_type = 'notebook_entry'
            RETURN n ORDER BY n.created_at DESC
            """,
            pid=project_id,
        )
        return [dict(record["n"]) for record in result]


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
