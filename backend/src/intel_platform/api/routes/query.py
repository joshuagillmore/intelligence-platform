from fastapi import APIRouter, Depends
from pydantic import BaseModel

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore
from intel_platform.services.graph_rag import GraphRAGPipeline

router = APIRouter(dependencies=[Depends(verify_api_key)])


class QueryRequest(BaseModel):
    project_id: str
    query: str
    max_hops: int = 2
    token_budget: int = 8000


@router.post("/query")
async def graph_rag_query(req: QueryRequest, store: GraphStore = Depends(get_graph_store)):
    pipeline = GraphRAGPipeline(store)
    result = await pipeline.query(req.query, req.project_id, max_hops=req.max_hops, token_budget=req.token_budget)
    return result
