from fastapi import APIRouter, Depends, HTTPException
from intel_platform.api.deps import get_graph_store, project_exists, verify_api_key
from intel_platform.graph.store import GraphStore

router = APIRouter(dependencies=[Depends(verify_api_key)])

# How many documents one list response carries. `total` says how many exist.
DOCUMENT_LIST_LIMIT = 500

# An entity belongs to the document it was extracted from. Ingestion records
# that as `source_doc_id` on the entity (and the store appends later documents
# to `source_doc_ids` when an entity is merged); it never creates an edge to the
# Document node, so counting edges read 0 entities for every document.
_EXTRACTED_FROM = "[x IN [e.source_doc_id] + coalesce(e.source_doc_ids, []) WHERE x IS NOT NULL AND x <> '']"


@router.get("/documents")
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
        doc_ids = [r["id"] for r in rows]
        counts = {
            r["doc_id"]: r["n"]
            for r in session.run(
                f"""
                MATCH (e) WHERE e.project_id = $pid AND NOT e:Document
                UNWIND {_EXTRACTED_FROM} AS doc_id
                WITH DISTINCT doc_id, e
                WHERE doc_id IN $doc_ids
                RETURN doc_id, count(e) AS n
                """,
                pid=project_id, doc_ids=doc_ids,
            )
        }
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


@router.get("/documents/{doc_id}")
def get_document(doc_id: str, store: GraphStore = Depends(get_graph_store)):
    """Get full document with content and extracted entities."""
    doc = store.get_entity(doc_id)
    if not doc or doc.get("entity_type") != "Document":
        raise HTTPException(status_code=404, detail="Document not found")

    # The entities extracted from this document, found the way ingestion links
    # them: by their source document id, within the document's project.
    with store._driver.session() as session:
        result = session.run(
            f"""
            MATCH (e) WHERE e.project_id = $pid AND NOT e:Document
              AND $doc_id IN {_EXTRACTED_FROM}
            RETURN e.id AS id, e.name AS name, e.entity_type AS entity_type
            ORDER BY e.name
            """,
            pid=doc.get("project_id", ""), doc_id=doc_id,
        )
        entities = [
            {
                "id": r["id"],
                "name": r["name"],
                "entity_type": r["entity_type"],
                "relationship": "EXTRACTED_FROM",
            }
            for r in result
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


@router.get("/documents/{doc_id}/evidence")
def get_evidence_for_entity(doc_id: str, entity_name: str, store: GraphStore = Depends(get_graph_store)):
    """Get text passages from a document that mention a specific entity."""
    doc = store.get_entity(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    content = doc.get("content", "") or ""
    passages = []

    # Find all occurrences and extract surrounding context (200 chars each side)
    start = 0
    while True:
        idx = content.find(entity_name, start)
        if idx == -1:
            break
        context_start = max(0, idx - 200)
        context_end = min(len(content), idx + len(entity_name) + 200)
        passage = content[context_start:context_end]
        if context_start > 0:
            passage = "..." + passage
        if context_end < len(content):
            passage = passage + "..."
        passages.append({
            "text": passage,
            "position": idx,
            "entity_name": entity_name,
        })
        start = idx + 1

    return {
        "document_id": doc_id,
        "document_name": doc.get("name"),
        "entity_name": entity_name,
        "passages": passages,
        "count": len(passages),
    }
