from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.db.engine import get_db
from intel_platform.graph.store import GraphStore
from intel_platform.services.graph_rag import GraphRAGPipeline

router = APIRouter(dependencies=[Depends(verify_api_key)])


class QueryRequest(BaseModel):
    project_id: str
    query: str
    max_hops: int = 2
    token_budget: int = 8000
    use_vector: bool = True


@router.post("/query")
async def graph_rag_query(
    req: QueryRequest,
    store: GraphStore = Depends(get_graph_store),
    session: AsyncSession = Depends(get_db),
):
    pipeline = GraphRAGPipeline(store)

    if req.use_vector:
        from intel_platform.services.hybrid_retrieval import HybridRetriever
        retriever = HybridRetriever(pipeline, session)
        hybrid = await retriever.retrieve(
            req.query, req.project_id,
            max_hops=req.max_hops, token_budget=req.token_budget,
        )

        # Generate answer using the hybrid context
        answer = ""
        model = "none"
        tokens_used = 0
        try:
            from intel_platform.api.routes.llm import _get_provider
            provider = await _get_provider()
            if provider:
                from intel_platform.llm.skills.loader import SkillsLoader
                loader = SkillsLoader()
                system = loader.get_system_prompt("foundation", include_foundation=False) or ""
                system += "\n\nYou are answering intelligence analyst queries using knowledge graph and semantic search data. "
                system += "Base your answer ONLY on the provided context. Cite entities and relationships. "
                system += "If the context doesn't contain enough information, say so explicitly."

                prompt = f"**Question:** {req.query}\n\n{hybrid['context']}"
                result = await provider.generate(
                    messages=[{"role": "user", "content": prompt}],
                    system=system, temperature=0.3, max_tokens=4096,
                )
                answer = result.content
                model = result.model
                tokens_used = result.total_tokens
        except Exception:
            import logging
            logging.getLogger(__name__).exception("LLM generation failed in hybrid query")
            answer = hybrid["context"]

        return {
            "query": req.query,
            "answer": answer or hybrid["context"],
            "model": model,
            "tokens_used": tokens_used,
            "context": hybrid["context"],
            "context_nodes": hybrid["node_count"],
            "context_edges": hybrid["edge_count"],
            "vector_results": len(hybrid["vector_results"]),
            "retrieval_mode": "hybrid",
        }

    # Graph-only mode
    result = await pipeline.query(
        req.query, req.project_id,
        max_hops=req.max_hops, token_budget=req.token_budget,
    )
    result["retrieval_mode"] = "graph"
    return result
