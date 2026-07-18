from fastapi import APIRouter, Depends, HTTPException
from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/documents")
def list_documents(project_id: str, store: GraphStore = Depends(get_graph_store)):
    """List all documents in a project with metadata."""
    # PERF: single query with relationship count instead of N+1 pattern
    with store._driver.session() as session:
        result = session.run(
            """
            MATCH (d:Document {project_id: $pid})
            OPTIONAL MATCH (d)-[r]->(m) WHERE type(r) <> 'MENTIONS'
            WITH d, properties(d) as props, count(r) as entity_count
            RETURN props, entity_count
            ORDER BY d.name
            LIMIT 500
            """,
            pid=project_id,
        )
        docs = []
        for record in result:
            props = record["props"]
            docs.append({
                "id": props.get("id"),
                "name": props.get("name"),
                "reliability_rating": props.get("reliability_rating", ""),
                "content_length": len(props.get("content", "") or ""),
                "entity_count": record["entity_count"],
                "created_at": str(props.get("created_at", "")),
                "summary_json": props.get("summary_json", ""),
            })
    return {"documents": docs, "count": len(docs)}


@router.get("/documents/{doc_id}")
def get_document(doc_id: str, store: GraphStore = Depends(get_graph_store)):
    """Get full document with content and extracted entities."""
    doc = store.get_entity(doc_id)
    if not doc or doc.get("entity_type") != "Document":
        raise HTTPException(status_code=404, detail="Document not found")

    # Get entities extracted from this document
    rels = store.get_relationships(doc_id)
    entities = []
    for rel in rels:
        target = store.get_entity(rel.get("target_id", ""))
        if target and target.get("entity_type") != "Document":
            entities.append({
                "id": target.get("id"),
                "name": target.get("name"),
                "entity_type": target.get("entity_type"),
                "relationship": rel.get("rel_type"),
            })

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
