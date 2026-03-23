"""Tests for document clustering and LLM label refinement."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from intel_platform.services.document_clustering import (
    cluster_documents,
    _label_cluster,
    _tokenize,
    build_tfidf,
    refine_labels_with_llm,
)


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------

def test_tokenize_basic():
    tokens = _tokenize("Iran is expanding naval operations in the Caspian Sea")
    assert "iran" in tokens
    assert "expanding" in tokens
    assert "naval" in tokens
    assert "caspian" in tokens
    # Stopwords should be removed
    assert "is" not in tokens
    assert "in" not in tokens
    assert "the" not in tokens


def test_tokenize_empty():
    assert _tokenize("") == []
    assert _tokenize("   ") == []


def test_tokenize_single_char_words():
    # Single-char words should be filtered (regex requires 2+ chars)
    tokens = _tokenize("I a x go run")
    assert "i" not in tokens
    assert "a" not in tokens
    assert "x" not in tokens
    assert "go" in tokens
    assert "run" in tokens


# ---------------------------------------------------------------------------
# TF-IDF
# ---------------------------------------------------------------------------

def test_build_tfidf_empty():
    matrix, doc_ids, vocab = build_tfidf([])
    assert matrix.shape == (0, 0)
    assert doc_ids == []
    assert vocab == []


def test_build_tfidf_single_doc():
    docs = [("doc1", "Iran nuclear program sanctions")]
    matrix, doc_ids, vocab = build_tfidf(docs)
    assert len(doc_ids) == 1
    assert doc_ids[0] == "doc1"
    assert matrix.shape[0] == 1


def test_build_tfidf_multiple_docs():
    docs = [
        ("doc1", "Iran nuclear program sanctions enforcement"),
        ("doc2", "Russia military buildup Ukraine border tensions"),
        ("doc3", "Iran sanctions enforcement nuclear proliferation"),
    ]
    matrix, doc_ids, vocab = build_tfidf(docs)
    assert matrix.shape[0] == 3
    assert len(doc_ids) == 3
    assert len(vocab) > 0


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------

def test_cluster_documents_empty():
    tree, doc_map, kw_map = cluster_documents([], "test-project")
    assert tree is None


def test_cluster_documents_single():
    docs = [("doc1", "Iran nuclear sanctions enforcement program")]
    tree, doc_map, kw_map = cluster_documents(docs, "test-project")
    assert tree is not None
    assert tree["entity_type"] == "topic"
    assert tree["count"] == 1
    assert "test-project" in doc_map


def test_cluster_documents_multiple():
    docs = [
        ("doc1", "Iran nuclear program sanctions enforcement international pressure"),
        ("doc2", "Russia military operations Ukraine border buildup tensions escalation"),
        ("doc3", "Iran sanctions enforcement nuclear proliferation concerns diplomatic"),
        ("doc4", "Russia Ukraine conflict military operations eastern front combat"),
    ]
    tree, doc_map, kw_map = cluster_documents(docs, "test-project")
    assert tree is not None
    assert tree["count"] == 4
    assert tree["entity_type"] == "topic"
    assert len(tree.get("keywords", [])) > 0


def test_cluster_documents_deterministic():
    """Clustering with same project_id should produce same results."""
    docs = [
        ("doc1", "Iran nuclear program sanctions enforcement"),
        ("doc2", "Russia military operations Ukraine border"),
        ("doc3", "Iran sanctions enforcement nuclear proliferation"),
    ]
    tree1, _, _ = cluster_documents(docs, "test-project")
    tree2, _, _ = cluster_documents(docs, "test-project")
    assert tree1["name"] == tree2["name"]
    assert tree1["count"] == tree2["count"]


def test_cluster_documents_doc_map_populated():
    docs = [
        ("doc1", "Iran nuclear program sanctions enforcement"),
        ("doc2", "Russia military operations Ukraine border"),
    ]
    tree, doc_map, kw_map = cluster_documents(docs, "test-proj")
    assert "test-proj" in doc_map
    all_mapped_ids = set()
    for ids in doc_map["test-proj"].values():
        all_mapped_ids.update(ids)
    assert "doc1" in all_mapped_ids
    assert "doc2" in all_mapped_ids


def test_cluster_documents_produces_multiple_topics():
    """Regression: documents on distinct topics MUST produce multiple clusters,
    not a single degenerate topic node.  Previously the TF-IDF vocabulary
    filter (df >= 2) was too aggressive and dropped most discriminating terms,
    collapsing everything into one cluster."""
    docs = [
        ("doc1", "Iran is developing nuclear weapons capabilities. International sanctions imposed on Iran nuclear program."),
        ("doc2", "Russia has deployed military forces near the Ukraine border. Moscow denies invasion plans. NATO increases readiness."),
        ("doc3", "APT29 conducted cyber espionage against government targets. The malware uses zero-day exploits."),
        ("doc4", "China expands naval operations in the South China Sea. Beijing asserts territorial claims."),
        ("doc5", "Iran sanctions enforcement involves financial institutions. Treasury department designates new entities."),
    ]
    tree, doc_map, kw_map = cluster_documents(docs, "test-multi-topic")
    assert tree is not None
    assert tree["count"] == 5
    # Must have children — a single root with no children means degenerate clustering
    assert len(tree.get("children", [])) >= 2, (
        f"Expected multiple topic clusters but got {len(tree.get('children', []))} children"
    )


# ---------------------------------------------------------------------------
# LLM Label Refinement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refine_labels_no_provider():
    """Without any LLM provider configured, labels should stay unchanged."""
    tree_node = {
        "id": "topic-root",
        "name": "iran / nuclear / sanctions",
        "entity_type": "topic",
        "keywords": ["iran", "nuclear", "sanctions"],
        "doc_ids": ["doc1"],
        "children": [],
    }
    doc_pairs = [("doc1", "Iran nuclear sanctions text")]

    # Ensure no API keys are set
    env_patch = {
        "COHERE_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "OPENAI_API_KEY": "",
    }
    with patch.dict(os.environ, env_patch, clear=False):
        result = await refine_labels_with_llm(tree_node, doc_pairs)

    # Name should be unchanged (no provider available)
    assert result["name"] == "iran / nuclear / sanctions"


@pytest.mark.asyncio
async def test_refine_labels_with_mocked_provider():
    """With a mocked LLM provider, labels should be refined."""
    tree_node = {
        "id": "topic-root",
        "name": "iran / nuclear / sanctions",
        "entity_type": "topic",
        "keywords": ["iran", "nuclear", "sanctions"],
        "doc_ids": ["doc1"],
        "children": [],
    }
    doc_pairs = [("doc1", "Iran nuclear sanctions enforcement measures")]

    mock_response = MagicMock()
    mock_response.content = '{"topic_name": "Iranian Nuclear Sanctions", "summary": "Documents covering nuclear-related sanctions against Iran."}'

    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(return_value=mock_response)

    mock_settings = MagicMock()
    mock_settings.anthropic_api_key = "test-key"
    mock_settings.cohere_api_key = ""
    mock_settings.openai_api_key = ""

    with patch("intel_platform.config.settings", mock_settings):
        with patch("intel_platform.llm.anthropic.AnthropicProvider", return_value=mock_provider):
            result = await refine_labels_with_llm(tree_node, doc_pairs)

    assert result["name"] == "Iranian Nuclear Sanctions"
    assert result["llm_label"] == "Iranian Nuclear Sanctions"
    assert result["summary"] == "Documents covering nuclear-related sanctions against Iran."


@pytest.mark.asyncio
async def test_refine_labels_llm_failure_keeps_original():
    """If LLM call fails, original keyword label should be preserved."""
    tree_node = {
        "id": "topic-root",
        "name": "iran / nuclear / sanctions",
        "entity_type": "topic",
        "keywords": ["iran", "nuclear", "sanctions"],
        "doc_ids": ["doc1"],
        "children": [],
    }
    doc_pairs = [("doc1", "Iran nuclear sanctions text")]

    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(side_effect=Exception("API error"))

    mock_settings = MagicMock()
    mock_settings.anthropic_api_key = "test-key"
    mock_settings.cohere_api_key = ""
    mock_settings.openai_api_key = ""

    with patch("intel_platform.config.settings", mock_settings):
        with patch("intel_platform.llm.anthropic.AnthropicProvider", return_value=mock_provider):
            result = await refine_labels_with_llm(tree_node, doc_pairs)

    assert result["name"] == "iran / nuclear / sanctions"


@pytest.mark.asyncio
async def test_refine_labels_recursive():
    """LLM refinement should recurse into children."""
    tree_node = {
        "id": "topic-root",
        "name": "root topic",
        "entity_type": "topic",
        "keywords": ["root"],
        "doc_ids": ["doc1"],
        "children": [
            {
                "id": "topic-0",
                "name": "child / topic",
                "entity_type": "topic",
                "keywords": ["child"],
                "doc_ids": ["doc2"],
                "children": [],
            }
        ],
    }
    doc_pairs = [("doc1", "Root content"), ("doc2", "Child content")]

    call_count = 0

    async def mock_generate(**kwargs):
        nonlocal call_count
        call_count += 1
        resp = MagicMock()
        resp.content = f'{{"topic_name": "Refined Topic {call_count}", "summary": "Summary {call_count}"}}'
        return resp

    mock_provider = AsyncMock()
    mock_provider.generate = mock_generate

    mock_settings = MagicMock()
    mock_settings.anthropic_api_key = "test-key"
    mock_settings.cohere_api_key = ""
    mock_settings.openai_api_key = ""

    with patch("intel_platform.config.settings", mock_settings):
        with patch("intel_platform.llm.anthropic.AnthropicProvider", return_value=mock_provider):
            result = await refine_labels_with_llm(tree_node, doc_pairs)

    assert call_count == 2
    assert "Refined Topic" in result["name"]
    assert "Refined Topic" in result["children"][0]["name"]


@pytest.mark.asyncio
async def test_refine_labels_skips_non_topic_nodes():
    """Non-topic nodes should not be sent to the LLM."""
    tree_node = {
        "id": "branch-docs",
        "name": "Source Documents",
        "entity_type": "branch",
        "children": [],
    }
    doc_pairs = []

    # Even with a provider, non-topic nodes should be skipped
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "", "COHERE_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False):
        result = await refine_labels_with_llm(tree_node, doc_pairs)

    assert result["name"] == "Source Documents"
