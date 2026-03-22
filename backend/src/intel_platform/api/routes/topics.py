from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from intel_platform.api.cache import cached
from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore
from intel_platform.services.topics import TopicTreeService

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/topics")
@cached(ttl=60)
async def get_topic_tree(project_id: str, store: GraphStore = Depends(get_graph_store)):
    svc = TopicTreeService(store)
    return await svc.build_topic_tree(project_id)


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
