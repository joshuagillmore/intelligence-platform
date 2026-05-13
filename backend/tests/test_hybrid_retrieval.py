"""Tests for hybrid retrieval — RRF merge of graph and vector results."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from intel_platform.services.hybrid_retrieval import HybridRetriever, _rrf_merge, _RRF_K


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# RRF merge unit tests
# ---------------------------------------------------------------------------

class TestRRFMerge:
    def test_graph_only_results(self):
        merged = _rrf_merge(["doc-1", "doc-2", "doc-3"], [], graph_weight=0.5)

        assert len(merged) == 3
        assert merged[0]["document_id"] == "doc-1"  # rank 1 has highest score
        assert merged[0]["graph_rank"] == 1
        assert merged[0]["vector_rank"] is None
        # Score should be weight * 1/(k+1)
        expected = 0.5 * (1.0 / (_RRF_K + 1))
        assert abs(merged[0]["rrf_score"] - expected) < 1e-10

    def test_vector_only_results(self):
        vec_results = [
            {"document_id": "doc-a", "similarity": 0.95, "chunk_text": "text a"},
            {"document_id": "doc-b", "similarity": 0.80, "chunk_text": "text b"},
        ]
        merged = _rrf_merge([], vec_results, graph_weight=0.5)

        assert len(merged) == 2
        assert merged[0]["document_id"] == "doc-a"
        assert merged[0]["graph_rank"] is None
        assert merged[0]["vector_rank"] == 1
        assert merged[0]["vector_similarity"] == 0.95

    def test_overlap_boosts_score(self):
        """Documents appearing in both graph and vector results should score higher."""
        graph_ids = ["doc-shared", "doc-graph-only"]
        vec_results = [
            {"document_id": "doc-shared", "similarity": 0.9, "chunk_text": "shared text"},
            {"document_id": "doc-vec-only", "similarity": 0.85, "chunk_text": "vec text"},
        ]

        merged = _rrf_merge(graph_ids, vec_results, graph_weight=0.5)
        scores = {m["document_id"]: m["rrf_score"] for m in merged}

        # doc-shared should have the highest combined score
        assert scores["doc-shared"] > scores["doc-graph-only"]
        assert scores["doc-shared"] > scores["doc-vec-only"]

        # It should have both ranks
        shared = next(m for m in merged if m["document_id"] == "doc-shared")
        assert shared["graph_rank"] == 1
        assert shared["vector_rank"] == 1

    def test_graph_weight_affects_ranking(self):
        """Higher graph_weight should favor graph results."""
        graph_ids = ["doc-graph"]
        vec_results = [
            {"document_id": "doc-vec", "similarity": 0.95, "chunk_text": "text"},
        ]

        # Graph-heavy
        merged_graph = _rrf_merge(graph_ids, vec_results, graph_weight=0.8)
        # Vector-heavy
        merged_vec = _rrf_merge(graph_ids, vec_results, graph_weight=0.2)

        graph_score_heavy = next(m for m in merged_graph if m["document_id"] == "doc-graph")["rrf_score"]
        graph_score_light = next(m for m in merged_vec if m["document_id"] == "doc-graph")["rrf_score"]

        assert graph_score_heavy > graph_score_light

    def test_empty_both_returns_empty(self):
        merged = _rrf_merge([], [])
        assert merged == []

    def test_deduplication_by_document_id(self):
        """Multiple vector results with same doc_id should be deduped to first occurrence."""
        vec_results = [
            {"document_id": "doc-1", "similarity": 0.95, "chunk_text": "chunk a"},
            {"document_id": "doc-1", "similarity": 0.80, "chunk_text": "chunk b"},
            {"document_id": "doc-2", "similarity": 0.70, "chunk_text": "chunk c"},
        ]
        merged = _rrf_merge([], vec_results, graph_weight=0.0)

        doc_ids = [m["document_id"] for m in merged]
        # doc-1 appears once (from rank 1), doc-1 rank 2 adds to its score
        assert doc_ids.count("doc-1") == 1
        assert doc_ids.count("doc-2") == 1

    def test_preserves_chunk_text(self):
        vec_results = [
            {"document_id": "doc-1", "similarity": 0.9, "chunk_text": "important text"},
        ]
        merged = _rrf_merge([], vec_results)
        assert merged[0]["chunk_text"] == "important text"


# ---------------------------------------------------------------------------
# HybridRetriever integration tests (mocked dependencies)
# ---------------------------------------------------------------------------

def _mock_graph_pipeline():
    pipeline = MagicMock()
    pipeline.understand_query.return_value = {
        "query": "test query",
        "target_entities": [
            {"id": "ent-1", "name": "APT29", "entity_type": "ThreatActor"},
        ],
    }
    pipeline.retrieve_context.return_value = {
        "nodes": [
            {"id": "ent-1", "name": "APT29", "entity_type": "ThreatActor", "source_doc_id": "doc-g1"},
            {"id": "ent-2", "name": "SUNBURST", "entity_type": "Malware", "source": "doc-g2"},
        ],
        "edges": [{"source_name": "APT29", "target_name": "SUNBURST", "rel_type": "USES"}],
        "node_count": 2,
        "edge_count": 1,
        "node_name_map": {"ent-1": "APT29", "ent-2": "SUNBURST"},
        "doc_texts": {},
    }
    pipeline.assemble_context.return_value = "## Graph Context\n- APT29 uses SUNBURST"
    return pipeline


class TestHybridRetriever:
    def test_retrieve_combines_graph_and_vector(self):
        pipeline = _mock_graph_pipeline()
        session = MagicMock()

        vec_results = [
            {"document_id": "doc-v1", "chunk_index": 0, "similarity": 0.92,
             "chunk_text": "APT29 deployed SUNBURST backdoor", "metadata": {}},
        ]

        with patch("intel_platform.services.hybrid_retrieval.vector_search", new_callable=AsyncMock) as mock_vs:
            mock_vs.return_value = vec_results
            retriever = HybridRetriever(pipeline, session)
            result = run(retriever.retrieve("APT29 malware", "proj-1"))

        assert result["node_count"] == 2
        assert result["edge_count"] == 1
        assert len(result["vector_results"]) == 1
        assert "Graph Context" in result["context"]
        assert "Semantically Similar" in result["context"]
        assert "APT29 deployed SUNBURST" in result["context"]
        assert len(result["merged_ranking"]) > 0

    def test_retrieve_graph_only_when_vector_fails(self):
        pipeline = _mock_graph_pipeline()
        session = MagicMock()

        with patch("intel_platform.services.hybrid_retrieval.vector_search", new_callable=AsyncMock) as mock_vs:
            mock_vs.side_effect = RuntimeError("DB down")
            retriever = HybridRetriever(pipeline, session)
            result = run(retriever.retrieve("test", "proj-1"))

        assert result["vector_results"] == []
        assert "Graph Context" in result["context"]
        assert "Semantically Similar" not in result["context"]

    def test_retrieve_with_no_graph_results(self):
        pipeline = MagicMock()
        pipeline.understand_query.return_value = {"query": "test", "target_entities": []}
        pipeline.retrieve_context.return_value = {
            "nodes": [], "edges": [],
            "node_count": 0, "edge_count": 0,
            "node_name_map": {}, "doc_texts": {},
        }
        pipeline.assemble_context.return_value = "## No graph results"

        session = MagicMock()
        vec_results = [
            {"document_id": "doc-1", "chunk_index": 0, "similarity": 0.88,
             "chunk_text": "Relevant text from vector search", "metadata": {}},
        ]

        with patch("intel_platform.services.hybrid_retrieval.vector_search", new_callable=AsyncMock) as mock_vs:
            mock_vs.return_value = vec_results
            retriever = HybridRetriever(pipeline, session)
            result = run(retriever.retrieve("obscure query", "proj-1"))

        assert len(result["vector_results"]) == 1
        assert result["node_count"] == 0
        assert "Relevant text from vector search" in result["context"]

    def test_merged_ranking_includes_both_sources(self):
        pipeline = _mock_graph_pipeline()
        session = MagicMock()

        vec_results = [
            {"document_id": "doc-g1", "chunk_index": 0, "similarity": 0.85,
             "chunk_text": "Overlap chunk", "metadata": {}},
            {"document_id": "doc-new", "chunk_index": 0, "similarity": 0.75,
             "chunk_text": "New chunk", "metadata": {}},
        ]

        with patch("intel_platform.services.hybrid_retrieval.vector_search", new_callable=AsyncMock) as mock_vs:
            mock_vs.return_value = vec_results
            retriever = HybridRetriever(pipeline, session)
            result = run(retriever.retrieve("test", "proj-1"))

        ranking = result["merged_ranking"]
        doc_ids = {r["document_id"] for r in ranking}
        assert "doc-g1" in doc_ids  # overlap doc
        assert "doc-g2" in doc_ids  # graph-only
        assert "doc-new" in doc_ids  # vector-only

        # Overlap doc should be ranked highest
        assert ranking[0]["document_id"] == "doc-g1"
        assert ranking[0]["graph_rank"] is not None
        assert ranking[0]["vector_rank"] is not None
