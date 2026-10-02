import asyncio
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.api.deps import get_graph_store, require_project_access, verify_api_key
from intel_platform.db.engine import get_db
from intel_platform.graph.store import GraphStore
from intel_platform.models.responses import (
    GraphRagQueryResponse,
)
from intel_platform.services.graph_rag import GraphRAGPipeline

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])

# Contract 6. When no model produced an answer, the response says so: `answer`
# is empty, `model` is "none", `llm_error` gives a reason fit for the client,
# and `context` is still returned. Returning the retrieval dump as `answer`
# rendered raw context as though the assistant had said it.
_NO_PROVIDER = "No LLM provider is configured."
_EMPTY_REPLY = "The model returned an empty answer."
_TIMED_OUT = "The model did not respond in time."
_FAILED = "The model could not be reached or failed to answer."


def _reason(exc: BaseException) -> str:
    """A client-safe reason: exception text can carry hosts, models and keys."""
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)) or "Timeout" in type(exc).__name__:
        return _TIMED_OUT
    return _FAILED


class QueryRequest(BaseModel):
    project_id: str
    query: str
    # Interpolated into a variable-length Cypher pattern: a negative value is a
    # syntax error, and a deep one enumerates every path through the shared
    # ATT&CK hubs. 1..4 matches the store's own clamp.
    max_hops: int = Field(default=2, ge=1, le=4)
    token_budget: int = 8000
    use_vector: bool = True


@router.post(
    "/query", response_model=GraphRagQueryResponse, response_model_exclude_unset=True,
    dependencies=[Depends(require_project_access("viewer"))],
)
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
        llm_error: str | None = None
        try:
            from intel_platform.api.routes.llm import _get_provider
            provider = await _get_provider()
            if not provider:
                llm_error = _NO_PROVIDER
            else:
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
                if (result.content or "").strip():
                    answer = result.content
                    model = result.model
                    tokens_used = result.total_tokens
                else:
                    llm_error = _EMPTY_REPLY
        except Exception as exc:
            logger.exception("LLM generation failed in hybrid query")
            llm_error = _reason(exc)

        return {
            "query": req.query,
            "answer": answer,
            "model": model,
            "tokens_used": tokens_used,
            "llm_error": llm_error,
            "context": hybrid["context"],
            "context_nodes": hybrid["node_count"],
            "context_edges": hybrid["edge_count"],
            "vector_results": len(hybrid["vector_results"]),
            "retrieval_mode": "hybrid",
        }

    # Graph-only mode. The pipeline leaves `model` at "none" when no model ran
    # and substitutes fallback text or the context itself for a missing answer;
    # neither is an answer.
    result = await pipeline.query(
        req.query, req.project_id,
        max_hops=req.max_hops, token_budget=req.token_budget,
    )
    answer = (result.get("answer") or "").strip()
    if result.get("model", "none") == "none" or not answer or answer == (result.get("context") or "").strip():
        result.update(answer="", model="none", tokens_used=0, llm_error=_FAILED)
    else:
        result["llm_error"] = None
    result["retrieval_mode"] = "graph"
    return result
