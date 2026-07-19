"""Tests for semantic clustering and mind map export."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np

from intel_platform.llm.embeddings import EmbeddingResult
from intel_platform.services.document_clustering import (
    GRANULARITY_PRESETS,
    _build_semantic_tree,
    _tokenize,
    build_tfidf,
    cluster_semantic,
)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Semantic clustering
# ---------------------------------------------------------------------------

def _mock_embedding_provider(dim: int = 384):
    """Create a mock embedding provider that returns deterministic vectors."""
    provider = MagicMock()
    provider.name.return_value = "mock:test-embed"
    provider.dimension.return_value = dim

    async def _embed(texts, *, input_type="search_document"):
        # Generate deterministic embeddings based on text hash
        vecs = []
        for t in texts:
            rng = np.random.RandomState(hash(t) % (2 ** 31))
            vecs.append(rng.randn(dim).tolist())
        return EmbeddingResult(embeddings=vecs, model="test-embed", total_tokens=len(texts) * 10)

    provider.embed = AsyncMock(side_effect=_embed)
    return provider


class TestClusterSemantic:
    def test_empty_documents(self):
        result = run(cluster_semantic([], "proj-1"))
        tree, doc_map, kw_map = result
        assert tree is None

    def test_single_document_falls_back_to_tfidf(self):
        """Single document should fall back to TF-IDF (which handles chunking)."""
        docs = [("doc-1", "This is a test document about machine learning and artificial intelligence.")]

        with patch("intel_platform.llm.embeddings.get_embedding_provider", return_value=_mock_embedding_provider()):
            tree, doc_map, kw_map = run(cluster_semantic(docs, "proj-1"))

        assert tree is not None
        assert "doc-1" in tree.get("doc_ids", [])

    def test_multiple_documents_produces_hierarchy(self):
        """Multiple documents should produce a hierarchical tree."""
        docs = [
            ("doc-1", "Machine learning algorithms for classification and regression tasks in data science."),
            ("doc-2", "Deep neural networks and convolutional architectures for image recognition."),
            ("doc-3", "Natural language processing with transformers and attention mechanisms."),
            ("doc-4", "Cybersecurity threats including malware, phishing, and ransomware attacks."),
            ("doc-5", "Network intrusion detection systems and firewall configuration."),
            ("doc-6", "Vulnerability scanning and penetration testing methodologies."),
        ]

        with patch("intel_platform.llm.embeddings.get_embedding_provider", return_value=_mock_embedding_provider()):
            tree, doc_map, kw_map = run(cluster_semantic(docs, "proj-1"))

        assert tree is not None
        assert tree["count"] == 6
        # Should have children (not a flat list)
        assert len(tree.get("children", [])) > 0
        # All doc IDs should be present
        all_doc_ids = set()
        def collect(node):
            all_doc_ids.update(node.get("doc_ids", []))
            for child in node.get("children", []):
                collect(child)
        collect(tree)
        assert all_doc_ids == {"doc-1", "doc-2", "doc-3", "doc-4", "doc-5", "doc-6"}

    def test_granularity_presets(self):
        """Different granularity levels should produce different tree depths."""
        assert "broad" in GRANULARITY_PRESETS
        assert "medium" in GRANULARITY_PRESETS
        assert "detailed" in GRANULARITY_PRESETS

        broad_k, broad_d = GRANULARITY_PRESETS["broad"]
        med_k, med_d = GRANULARITY_PRESETS["medium"]
        det_k, det_d = GRANULARITY_PRESETS["detailed"]

        assert broad_k < med_k < det_k
        assert broad_d < med_d < det_d

    def test_fallback_to_tfidf_when_no_provider(self):
        """Should fall back to TF-IDF when embedding provider unavailable."""
        docs = [
            ("doc-1", "Machine learning for classification."),
            ("doc-2", "Cybersecurity and network defense."),
        ]

        with patch("intel_platform.llm.embeddings.get_embedding_provider", side_effect=RuntimeError("no provider")):
            tree, doc_map, kw_map = run(cluster_semantic(docs, "proj-1"))

        assert tree is not None  # Should produce TF-IDF result, not crash

    def test_fallback_to_tfidf_when_embedding_fails(self):
        """Should fall back to TF-IDF when embedding API fails."""
        docs = [
            ("doc-1", "Machine learning for classification."),
            ("doc-2", "Cybersecurity and network defense."),
        ]

        provider = MagicMock()
        provider.embed = AsyncMock(side_effect=RuntimeError("API error"))

        with patch("intel_platform.llm.embeddings.get_embedding_provider", return_value=provider):
            tree, doc_map, kw_map = run(cluster_semantic(docs, "proj-1"))

        assert tree is not None

    def test_doc_map_populated(self):
        """doc_map should map node IDs to document IDs."""
        docs = [
            ("doc-1", "First document about topic A."),
            ("doc-2", "Second document about topic B."),
            ("doc-3", "Third document about topic C."),
        ]

        with patch("intel_platform.llm.embeddings.get_embedding_provider", return_value=_mock_embedding_provider()):
            tree, doc_map, kw_map = run(cluster_semantic(docs, "proj-1"))

        inner_map = doc_map.get("proj-1", {})
        assert len(inner_map) > 0
        # Every document should appear in at least one node
        all_mapped_docs = set()
        for doc_ids in inner_map.values():
            all_mapped_docs.update(doc_ids)
        assert all_mapped_docs == {"doc-1", "doc-2", "doc-3"}

    def test_keywords_populated(self):
        """kw_map should have keywords for each node."""
        docs = [
            ("doc-1", "Machine learning algorithms for classification."),
            ("doc-2", "Deep learning neural networks for recognition."),
            ("doc-3", "Cybersecurity threats and vulnerability scanning."),
        ]

        with patch("intel_platform.llm.embeddings.get_embedding_provider", return_value=_mock_embedding_provider()):
            tree, doc_map, kw_map = run(cluster_semantic(docs, "proj-1"))

        inner_kw = kw_map.get("proj-1", {})
        assert len(inner_kw) > 0


# ---------------------------------------------------------------------------
# Build semantic tree
# ---------------------------------------------------------------------------

class TestBuildSemanticTree:
    def test_basic_tree(self):
        """Build a simple two-level tree from level cuts."""
        doc_ids = ["d1", "d2", "d3", "d4"]
        level_cuts = [
            np.array([1, 1, 2, 2]),  # level 0: two clusters
            np.array([1, 2, 3, 4]),  # level 1: four clusters
        ]
        docs = [
            ("d1", "alpha beta"), ("d2", "alpha gamma"),
            ("d3", "delta epsilon"), ("d4", "delta zeta"),
        ]
        vectors, _, vocab = build_tfidf(docs)
        all_tokenized = [_tokenize(t) for _, t in docs]

        doc_map = {}
        kw_map = {}
        tree = _build_semantic_tree(
            doc_ids, level_cuts, vectors, vocab, all_tokenized,
            doc_map, kw_map,
        )

        assert tree["count"] == 4
        assert len(tree["children"]) == 2
        assert len(doc_map) > 0

    def test_single_cluster_skips_level(self):
        """If all docs in one cluster, should skip to next level."""
        doc_ids = ["d1", "d2"]
        level_cuts = [
            np.array([1, 1]),  # all same cluster
            np.array([1, 2]),  # split
        ]
        docs = [("d1", "alpha"), ("d2", "beta")]
        vectors, _, vocab = build_tfidf(docs)
        all_tokenized = [_tokenize(t) for _, t in docs]

        doc_map = {}
        kw_map = {}
        tree = _build_semantic_tree(
            doc_ids, level_cuts, vectors, vocab, all_tokenized,
            doc_map, kw_map,
        )

        # Should skip level 0 (single cluster) and use level 1
        assert tree["count"] == 2


# ---------------------------------------------------------------------------
# Mind map export formats
# ---------------------------------------------------------------------------

class TestMindMapExport:
    def test_markdown_export(self):
        from intel_platform.services.mindmap_export import tree_to_markdown

        tree = {
            "name": "Knowledge Base",
            "count": 10,
            "children": [
                {"name": "Cybersecurity", "count": 5, "keywords": ["malware", "threat"], "children": [
                    {"name": "Malware Analysis", "count": 3, "keywords": ["ransomware"], "children": []},
                    {"name": "Threat Intelligence", "count": 2, "keywords": ["apt"], "children": []},
                ]},
                {"name": "Geopolitics", "count": 5, "keywords": ["conflict", "diplomacy"], "children": []},
            ],
        }

        md = tree_to_markdown(tree)
        assert "# Knowledge Base" in md
        assert "## Cybersecurity" in md
        assert "### Malware Analysis" in md
        assert "### Threat Intelligence" in md
        assert "## Geopolitics" in md
        assert "Keywords: malware, threat" in md

    def test_mermaid_export(self):
        from intel_platform.services.mindmap_export import tree_to_mermaid

        tree = {
            "name": "Root",
            "children": [
                {"name": "Branch A", "children": [
                    {"name": "Leaf 1", "children": []},
                ]},
                {"name": "Branch B", "children": []},
            ],
        }

        mmd = tree_to_mermaid(tree)
        assert mmd.startswith("mindmap")
        assert "Root" in mmd
        assert "Branch A" in mmd
        assert "Leaf 1" in mmd
        assert "Branch B" in mmd
        # Leaf 1 should be indented more than Branch A
        lines = mmd.split("\n")
        branch_a_indent = len(lines[2]) - len(lines[2].lstrip())
        leaf_1_indent = len(lines[3]) - len(lines[3].lstrip())
        assert leaf_1_indent > branch_a_indent

    def test_markdown_empty_tree(self):
        from intel_platform.services.mindmap_export import tree_to_markdown

        tree = {"name": "Empty", "children": []}
        md = tree_to_markdown(tree)
        assert "Empty" in md

    def test_mermaid_special_characters(self):
        from intel_platform.services.mindmap_export import tree_to_mermaid

        tree = {"name": 'Topic with "quotes"', "children": []}
        mmd = tree_to_mermaid(tree)
        assert '"' not in mmd.split("\n")[1]  # quotes should be replaced


# ---------------------------------------------------------------------------
# TopicEdit model
# ---------------------------------------------------------------------------

class TestTopicEditModel:
    def test_model_instantiation(self):
        from intel_platform.db.models import TopicEdit
        edit = TopicEdit(
            node_id="topic-0-1",
            project_id="proj-1",
            edit_type="rename",
            name="New Label",
        )
        assert edit.node_id == "topic-0-1"
        assert edit.edit_type == "rename"
        assert edit.name == "New Label"
