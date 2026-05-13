from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.db.engine import get_db
from intel_platform.graph.store import GraphStore

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/search")
def global_search(q: str, project_id: str, limit: int = 50, store: GraphStore = Depends(get_graph_store)):
    """Search across all entity types, documents, and reports."""
    results = store.search_entities(project_id=project_id, query=q, limit=limit)

    # Categorize results
    categorized = {
        "entities": [],
        "documents": [],
        "reports": [],
        "total": len(results),
    }
    for r in results:
        etype = r.get("entity_type", "")
        entry = {
            "id": r.get("id"),
            "name": r.get("name"),
            "entity_type": etype,
        }
        if etype == "Document":
            entry["reliability"] = r.get("reliability_rating", "")
            entry["preview"] = (r.get("content", "") or "")[:200]
            categorized["documents"].append(entry)
        elif etype == "Report":
            entry["report_type"] = r.get("report_type", "")
            entry["preview"] = (r.get("content", "") or "")[:200]
            categorized["reports"].append(entry)
        else:
            categorized["entities"].append(entry)

    return categorized


class SemanticSearchRequest(BaseModel):
    project_id: str
    query: str
    limit: int = 20


@router.post("/search/semantic")
async def semantic_search(req: SemanticSearchRequest, session: AsyncSession = Depends(get_db)):
    """Semantic similarity search across document chunks using vector embeddings."""
    from intel_platform.services.vector_search import vector_search
    results = await vector_search(req.query, req.project_id, session, limit=req.limit)
    return {"results": results, "total": len(results)}
