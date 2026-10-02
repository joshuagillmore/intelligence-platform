from fastapi import APIRouter, Depends, HTTPException
from intel_platform.api.deps import get_graph_store, project_exists, verify_api_key
from intel_platform.graph.evidence import find_passages
from intel_platform.graph.store import GraphStore
from intel_platform.models.responses import (
    DocumentDetailResponse,
    DocumentEvidenceResponse,
    DocumentListResponse,
)

router = APIRouter(dependencies=[Depends(verify_api_key)])

# How many documents one list response carries. `total` says how many exist.
DOCUMENT_LIST_LIMIT = 500
# How many passages one evidence response carries. `total` counts every mention.
MAX_EVIDENCE_PASSAGES = 50

# A document's entities are the ones it MENTIONS: graph_builder writes that
# edge for every entity it extracts or merges, and the startup backfill builds
# it from the older `source_doc_ids` property. Both reads below used to invert
# that property by scanning every entity in the project.


@router.get("/documents", response_model=DocumentListResponse)
def list_documents(project_id: str, store: GraphStore = Depends(get_graph_store)):
    """List a project's documents with metadata, and how many exist in all."""
    with store._driver.session() as session:
        total = session.run(
            "MATCH (d:Document {project_id: $pid}) RETURN count(d) AS n", pid=project_id,
        ).single()["n"]
        # `size(d.content)` rather than `properties(d)`: the list only needs the
        # length, and shipping every document's full text to measure it was the
        # bulk of this response's cost.
        rows = list(session.run(
            """
            MATCH (d:Document {project_id: $pid})
            RETURN d.id AS id, d.name AS name, d.reliability_rating AS reliability_rating,
                   size(coalesce(d.content, '')) AS content_length,
                   d.created_at AS created_at, d.summary_json AS summary_json
            ORDER BY d.name
            LIMIT $limit
            """,
            pid=project_id, limit=DOCUMENT_LIST_LIMIT,
        ))
    counts = store.count_entities_mentioned([r["id"] for r in rows], project_id)
    docs = [
        {
            "id": r["id"],
            "name": r["name"],
            "reliability_rating": r["reliability_rating"] or "",
            "content_length": r["content_length"],
            "entity_count": counts.get(r["id"], 0),
            "created_at": str(r["created_at"] or ""),
            "summary_json": r["summary_json"] or "",
        }
        for r in rows
    ]
    # Distinguishes "this project holds no documents" from "this is not a
    # project" — both otherwise return an empty list and a zero.
    return {
        "documents": docs,
        "count": len(docs),
        "total": total,
        "truncated": total > len(docs),
        "project_exists": project_exists(store, project_id),
    }


@router.get("/documents/{doc_id}", response_model=DocumentDetailResponse)
def get_document(doc_id: str, store: GraphStore = Depends(get_graph_store)):
    """Get full document with content and extracted entities."""
    doc = store.get_entity(doc_id)
    if not doc or doc.get("entity_type") != "Document":
        raise HTTPException(status_code=404, detail="Document not found")

    # The entities this document mentions, within its project.
    entities = [
        {
            "id": r["id"],
            "name": r["name"],
            "entity_type": r["entity_type"],
            "relationship": "EXTRACTED_FROM",
        }
        for r in store.entities_mentioned_in(doc_id, doc.get("project_id", ""))
    ]

    content = doc.get("content", "") or ""

    # Find entity positions in the text for highlighting
    highlights = []
    for entity in entities:
        name = entity.get("name", "")
        if name and name in content:
            start = 0
            while True:
                idx = content.find(name, start)
                if idx == -1:
                    break
                highlights.append({
                    "start": idx,
                    "end": idx + len(name),
                    "entity_id": entity.get("id"),
                    "entity_name": name,
                    "entity_type": entity.get("entity_type"),
                })
                start = idx + 1

    highlights.sort(key=lambda x: x["start"])

    return {
        "id": doc.get("id"),
        "name": doc.get("name"),
        "reliability_rating": doc.get("reliability_rating", ""),
        "content": content,
        "entities": entities,
        "highlights": highlights,
        "entity_count": len(entities),
        "summary_json": doc.get("summary_json", ""),
    }


@router.get("/documents/{doc_id}/evidence", response_model=DocumentEvidenceResponse)
def get_evidence_for_entity(doc_id: str, entity_name: str, store: GraphStore = Depends(get_graph_store)):
    """Get text passages from a document that mention a specific entity.

    At most MAX_EVIDENCE_PASSAGES are returned; `total` counts every mention.
    A blank name is refused: it matched at every index, so one request against
    a 10 MB document built about ten million passages.
    """
    if not entity_name.strip():
        raise HTTPException(status_code=422, detail="entity_name must not be blank")
    doc = store.get_entity(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    found, total = find_passages(doc.get("content", "") or "", entity_name, MAX_EVIDENCE_PASSAGES)
    passages = [
        {"text": p["text"], "position": p["offset"], "entity_name": entity_name}
        for p in found
    ]

    return {
        "document_id": doc_id,
        "document_name": doc.get("name"),
        "entity_name": entity_name,
        "passages": passages,
        "count": len(passages),
        "total": total,
        "truncated": total > len(passages),
    }
