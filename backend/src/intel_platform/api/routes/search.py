from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.db.engine import get_db
from intel_platform.graph.store import GraphStore

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/search")
def global_search(
    q: str,
    project_id: str,
    limit: int = Query(50, ge=1, le=1000),
    store: GraphStore = Depends(get_graph_store),
):
    """Search entity names across all entity types, documents, and reports.

    Every search term must appear in the name. `count` is the rows on this
    page and `total` the true number of matches (the same filter, not capped
    by the page size); `total` used to be the page length, so a search capped
    at 50 always reported 50.
    """
    results = store.search_entities(project_id=project_id, query=q, limit=limit)
    total = store.count_entities(project_id=project_id, query=q)

    # Categorize results; `results` keeps the same rows as one list, in order.
    categorized = {
        "entities": [],
        "documents": [],
        "reports": [],
        "results": [],
        "count": len(results),
        "total": total,
        "truncated": total > len(results),
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
        categorized["results"].append(entry)

    return categorized


class SemanticSearchRequest(BaseModel):
    project_id: str
    query: str
    limit: int = 20
    # Cosine similarity is relative, not absolute: a short conceptual query scores
    # lower against long chunks than a specific one does, so a high floor returns
    # nothing for perfectly reasonable searches. ("command and control
    # infrastructure" scored under the old 0.3 default on a corpus that plainly
    # discusses C2 infrastructure.) Keep the floor low enough to be useful and
    # surface the score, so the caller can judge a weak match instead of being
    # shown an empty page.
    min_similarity: float = Field(default=0.15, ge=0.0, le=1.0)


@router.post("/search/semantic")
async def semantic_search(req: SemanticSearchRequest, session: AsyncSession = Depends(get_db)):
    """Semantic similarity search across document chunks using vector embeddings."""
    from intel_platform.services.vector_search import vector_search
    results = await vector_search(
        req.query,
        req.project_id,
        session,
        limit=req.limit,
        similarity_threshold=req.min_similarity,
    )
    return {"results": results, "total": len(results)}
