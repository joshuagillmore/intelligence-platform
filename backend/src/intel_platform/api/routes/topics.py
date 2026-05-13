from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.api.cache import cached
from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.db.engine import get_db
from intel_platform.graph.store import GraphStore
from intel_platform.services.topics import TopicTreeService

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/topics")
@cached(ttl=60)
async def get_topic_tree(
    project_id: str,
    method: str = "tfidf",
    granularity: str = "medium",
    store: GraphStore = Depends(get_graph_store),
):
    """Build hierarchical topic tree.

    method: tfidf (keyword-based), semantic (embedding-based), or hybrid
    granularity: broad (3-5 clusters), medium (10-15), detailed (30+)
    """
    svc = TopicTreeService(store)
    return await svc.build_topic_tree(project_id, method=method, granularity=granularity)


@router.get("/topics/{entity_id}")
def get_topic_context(entity_id: str, project_id: str, store: GraphStore = Depends(get_graph_store)):
    svc = TopicTreeService(store)
    return svc.get_topic_context(entity_id, project_id)


class SummarizeRequest(BaseModel):
    project_id: str
    level: str = "topic"  # "topic", "document", or "corpus"
    conversation_history: list[dict] | None = None


@router.post("/topics/{entity_id}/summarize")
async def summarize_topic(
    entity_id: str,
    body: SummarizeRequest,
    store: GraphStore = Depends(get_graph_store),
):
    """Stream an LLM-generated intelligence summary for a topic node."""
    svc = TopicTreeService(store)
    generator = svc.stream_summary(
        entity_id=entity_id,
        project_id=body.project_id,
        level=body.level,
        conversation_history=body.conversation_history,
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Topic node editing (persisted overlay on algorithmic tree)
# ---------------------------------------------------------------------------

class TopicEditRequest(BaseModel):
    project_id: str
    name: str | None = None
    description: str | None = None
    parent_id: str | None = None


class TopicCreateRequest(BaseModel):
    project_id: str
    name: str
    description: str = ""


@router.put("/topics/{node_id}")
async def update_topic_node(node_id: str, req: TopicEditRequest, db: AsyncSession = Depends(get_db)):
    """Rename or update a topic node."""
    from intel_platform.db.models import TopicEdit
    from sqlalchemy import select

    stmt = select(TopicEdit).where(
        TopicEdit.node_id == node_id, TopicEdit.project_id == req.project_id
    )
    result = await db.execute(stmt)
    edit = result.scalar_one_or_none()

    if edit:
        if req.name is not None:
            edit.name = req.name
        if req.description is not None:
            edit.description = req.description
        if req.parent_id is not None:
            edit.parent_id = req.parent_id
    else:
        edit = TopicEdit(
            node_id=node_id,
            project_id=req.project_id,
            name=req.name or "",
            description=req.description or "",
            parent_id=req.parent_id or "",
            edit_type="rename",
        )
        db.add(edit)

    await db.commit()
    return {"node_id": node_id, "updated": True}


@router.post("/topics/{node_id}/children")
async def add_topic_child(node_id: str, req: TopicCreateRequest, db: AsyncSession = Depends(get_db)):
    """Add a user-created child node to a topic."""
    import uuid
    from intel_platform.db.models import TopicEdit

    child_id = f"topic-user-{uuid.uuid4().hex[:8]}"
    edit = TopicEdit(
        node_id=child_id,
        project_id=req.project_id,
        name=req.name,
        description=req.description,
        parent_id=node_id,
        edit_type="add",
    )
    db.add(edit)
    await db.commit()
    return {"node_id": child_id, "parent_id": node_id, "name": req.name}


@router.delete("/topics/{node_id}")
async def delete_topic_node(node_id: str, project_id: str, db: AsyncSession = Depends(get_db)):
    """Mark a topic node as deleted (hidden from view)."""
    from intel_platform.db.models import TopicEdit
    from sqlalchemy import select

    # Check if edit exists
    stmt = select(TopicEdit).where(
        TopicEdit.node_id == node_id, TopicEdit.project_id == project_id
    )
    result = await db.execute(stmt)
    edit = result.scalar_one_or_none()

    if edit:
        edit.edit_type = "delete"
    else:
        edit = TopicEdit(
            node_id=node_id,
            project_id=project_id,
            name="",
            edit_type="delete",
        )
        db.add(edit)

    await db.commit()
    return {"node_id": node_id, "deleted": True}
