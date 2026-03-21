from fastapi import APIRouter, Depends
from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore
from intel_platform.services.topics import TopicTreeService

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/topics")
def get_topic_tree(project_id: str, store: GraphStore = Depends(get_graph_store)):
    svc = TopicTreeService(store)
    return svc.build_topic_tree(project_id)


@router.get("/topics/{entity_id}")
def get_topic_context(entity_id: str, project_id: str, store: GraphStore = Depends(get_graph_store)):
    svc = TopicTreeService(store)
    return svc.get_topic_context(entity_id, project_id)
