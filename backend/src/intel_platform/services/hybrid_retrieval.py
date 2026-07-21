"""Hybrid retrieval — merges graph-based and vector-based results using RRF.

Reciprocal Rank Fusion (RRF) combines ranked lists without requiring score
normalization. Each item gets score = 1/(k + rank), weighted by source.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.services.graph_rag import GraphRAGPipeline
from intel_platform.services.vector_search import vector_search

logger = logging.getLogger(__name__)

# RRF constant — standard value from the original paper
_RRF_K = 60


def _rrf_merge(
    graph_doc_ids: list[str],
    vector_results: list[dict],
    graph_weight: float = 0.4,
) -> list[dict]:
    """Merge graph and vector results using Reciprocal Rank Fusion.

    Returns sorted list of {document_id, rrf_score, graph_rank, vector_rank, vector_similarity, chunk_text}.
    """
    vector_weight = 1.0 - graph_weight
    scores: dict[str, dict] = {}

    # Score graph results
    for rank, doc_id in enumerate(graph_doc_ids):
        rrf = graph_weight * (1.0 / (_RRF_K + rank + 1))
        scores[doc_id] = {
            "document_id": doc_id,
            "rrf_score": rrf,
            "graph_rank": rank + 1,
            "vector_rank": None,
            "vector_similarity": None,
            "chunk_text": None,
        }

    # Score vector results (keyed by document_id for dedup)
    for rank, vr in enumerate(vector_results):
        doc_id = vr["document_id"]
        rrf = vector_weight * (1.0 / (_RRF_K + rank + 1))
        if doc_id in scores:
            # Document appears in both — boost
            scores[doc_id]["rrf_score"] += rrf
            scores[doc_id]["vector_rank"] = rank + 1
            scores[doc_id]["vector_similarity"] = vr["similarity"]
            scores[doc_id]["chunk_text"] = vr["chunk_text"]
        else:
            scores[doc_id] = {
                "document_id": doc_id,
                "rrf_score": rrf,
                "graph_rank": None,
                "vector_rank": rank + 1,
                "vector_similarity": vr["similarity"],
                "chunk_text": vr["chunk_text"],
            }

    # Sort by combined RRF score descending
    merged = sorted(scores.values(), key=lambda x: x["rrf_score"], reverse=True)
    return merged


class HybridRetriever:
    """Combines graph-based (Neo4j) and vector-based (pgvector) retrieval."""

    def __init__(self, graph_pipeline: GraphRAGPipeline, session: AsyncSession):
        self._graph = graph_pipeline
        self._session = session

    async def retrieve(
        self,
        query: str,
        project_id: str,
        max_hops: int = 2,
        vector_limit: int = 20,
        graph_weight: float = 0.4,
        token_budget: int = 8000,
    ) -> dict:
        """Run graph + vector retrieval, merge via RRF, return unified context.

        Returns dict with:
        - context: assembled text for LLM consumption
        - graph_context: raw graph retrieval result
        - vector_results: raw vector search results
        - merged_ranking: RRF-merged document ranking
        - node_count, edge_count: graph stats
        """
        # 1. Graph retrieval — the Neo4j driver is synchronous, so offload these
        # calls to a thread to keep the event loop free.
        understanding = await asyncio.to_thread(self._graph.understand_query, query, project_id)
        graph_context = await asyncio.to_thread(
            self._graph.retrieve_context, understanding, project_id, max_hops
        )

        # 2. Vector retrieval
        try:
            vec_results = await vector_search(
                query, project_id, self._session, limit=vector_limit,
            )
        except Exception:
            logger.warning("Vector search failed, using graph-only results", exc_info=True)
            vec_results = []

        # 3. Extract document IDs from graph results for RRF
        graph_doc_ids = []
        seen = set()
        for node in graph_context.get("nodes", []):
            src = node.get("source_doc_id", "") or node.get("source", "")
            if src and src not in seen:
                seen.add(src)
                graph_doc_ids.append(src)

        # 4. RRF merge
        merged = _rrf_merge(graph_doc_ids, vec_results, graph_weight)

        # 5. Assemble context — graph context + vector passages
        graph_text = self._graph.assemble_context(graph_context, token_budget=token_budget)

        # Append vector-matched passages
        vector_passages = []
        char_budget = token_budget * 2  # rough chars for vector section
        char_count = 0
        for vr in vec_results:
            chunk = vr.get("chunk_text", "")
            if not chunk:
                continue
            if char_count + len(chunk) > char_budget:
                break
            vector_passages.append(
                f"[similarity={vr['similarity']:.3f}, doc={vr['document_id']}]\n{chunk}"
            )
            char_count += len(chunk)

        if vector_passages:
            graph_text += "\n\n### Semantically Similar Document Passages\n"
            graph_text += "\n\n".join(vector_passages)

        return {
            "context": graph_text,
            "graph_context": graph_context,
            "vector_results": vec_results,
            "merged_ranking": merged,
            "node_count": graph_context.get("node_count", 0),
            "edge_count": graph_context.get("edge_count", 0),
        }
