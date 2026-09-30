"""G-10: the semantic topic tree actually deepens, and says when it is TF-IDF.

The tree was built by cutting one dendrogram at ``k = min(max_k, n // level)``
for each level. Once ``n // level`` exceeds ``max_k`` every level is the same
cut, so every level below the first was skipped as "one cluster": every preset
produced depth 2, whatever its ``max_depth`` (reproduced for n = 20/60/200).
Also: the whole corpus went to the embedder in one call (Cohere caps a call
at 96 texts), a failure fell back to TF-IDF with nothing on the tree to say
so, and Ward linkage ran on the event loop.
"""
from __future__ import annotations

import threading
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from intel_platform.llm.embeddings import EmbeddingResult
from intel_platform.services import document_clustering as dc
from intel_platform.services.document_clustering import GRANULARITY_PRESETS, cluster_semantic


def _corpus(n_super: int = 3, n_sub: int = 4, per_sub: int = 5, dim: int = 32, seed: int = 7):
    """A corpus with real hierarchy: 3 themes x 4 sub-themes x 5 documents."""
    rng = np.random.RandomState(seed)
    docs: list[tuple[str, str]] = []
    vectors: dict[str, list[float]] = {}
    for s in range(n_super):
        theme = rng.randn(dim) * 10
        for b in range(n_sub):
            sub = theme + rng.randn(dim) * 3
            for d in range(per_sub):
                text = (f"theme{s} report on subject{s}x{b} covering item{d} with "
                        f"details about theme{s} and subject{s}x{b}")
                doc_id = f"doc-{s}-{b}-{d}"
                docs.append((doc_id, text))
                vectors[text[:2000]] = (sub + rng.randn(dim) * 0.5).tolist()
    return docs, vectors


def _provider(vectors: dict[str, list[float]]):
    p = MagicMock()
    p.name.return_value = "fake:embed"

    async def _embed(texts, *, input_type="search_document"):
        return EmbeddingResult(embeddings=[vectors[t] for t in texts], model="fake")

    p.embed = AsyncMock(side_effect=_embed)
    return p


def _depth(node: dict) -> int:
    return 1 + max((_depth(c) for c in node.get("children", [])), default=0)


def _leaves(node: dict) -> list[dict]:
    kids = node.get("children", [])
    return [node] if not kids else [leaf for c in kids for leaf in _leaves(c)]


async def _tree(granularity: str, n_super: int = 3, n_sub: int = 4, per_sub: int = 5):
    docs, vectors = _corpus(n_super, n_sub, per_sub)
    provider = _provider(vectors)
    with patch("intel_platform.llm.embeddings.get_embedding_provider", return_value=provider):
        tree, doc_map, kw_map = await cluster_semantic(docs, "proj-g10", granularity=granularity)
    return tree, docs, provider


async def test_the_medium_tree_is_deeper_than_two_levels():
    """The reproduction: n = 60 used to give depth 2 for every preset."""
    tree, docs, _ = await _tree("medium")
    assert len(docs) == 60
    assert _depth(tree) > 2, f"depth {_depth(tree)}"


@pytest.mark.parametrize("granularity", sorted(GRANULARITY_PRESETS))
async def test_every_preset_deepens_within_its_bound(granularity):
    max_k, max_depth = GRANULARITY_PRESETS[granularity]
    tree, docs, _ = await _tree(granularity)
    assert 2 < _depth(tree) <= max_depth + 1

    def _check(node: dict) -> None:
        assert len(node.get("children", [])) <= max_k
        for child in node.get("children", []):
            _check(child)

    _check(tree)


@pytest.mark.parametrize("granularity", sorted(GRANULARITY_PRESETS))
async def test_the_leaves_partition_the_corpus(granularity):
    tree, docs, _ = await _tree(granularity)
    leaf_docs = [d for leaf in _leaves(tree) for d in leaf["doc_ids"]]
    assert sorted(leaf_docs) == sorted(d for d, _ in docs)


async def test_broad_is_shallower_than_medium():
    broad, _, _ = await _tree("broad")
    medium, _, _ = await _tree("medium")
    assert _depth(broad) < _depth(medium)


async def test_a_sub_theme_stays_together_under_its_theme():
    """The deeper levels are real structure: no top-level topic mixes themes."""
    tree, _, _ = await _tree("broad")
    for child in tree["children"]:
        themes = {d.split("-")[1] for d in child["doc_ids"]}
        assert len(themes) == 1, themes


async def test_the_same_corpus_gives_the_same_tree():
    a, _, _ = await _tree("medium")
    b, _, _ = await _tree("medium")

    def _shape(node: dict):
        return (node["id"], tuple(node["doc_ids"]), tuple(_shape(c) for c in node.get("children", [])))

    assert _shape(a) == _shape(b)


async def test_node_ids_are_unique():
    tree, _, _ = await _tree("detailed")
    ids: list[str] = []

    def _walk(node: dict) -> None:
        ids.append(node["id"])
        for c in node.get("children", []):
            _walk(c)

    _walk(tree)
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Batching, fallback marker, and the event loop
# ---------------------------------------------------------------------------

async def test_the_corpus_is_embedded_in_batches_of_96():
    tree, docs, provider = await _tree("medium", n_super=4, n_sub=5, per_sub=10)  # 200 docs
    sizes = [len(call.args[0]) for call in provider.embed.call_args_list]
    assert sum(sizes) == 200
    assert max(sizes) <= 96
    assert tree["count"] == 200


async def test_a_failed_embedding_marks_the_tree_as_tfidf():
    docs, _ = _corpus()
    p = MagicMock()
    p.embed = AsyncMock(side_effect=RuntimeError("429"))
    with patch("intel_platform.llm.embeddings.get_embedding_provider", return_value=p):
        tree, _, _ = await cluster_semantic(docs, "proj-g10")
    assert tree["fallback"] == "tfidf"
    assert tree["fallback_reason"]


async def test_no_provider_marks_the_tree_as_tfidf():
    docs, _ = _corpus()
    with patch("intel_platform.llm.embeddings.get_embedding_provider", side_effect=RuntimeError("no key")):
        tree, _, _ = await cluster_semantic(docs, "proj-g10")
    assert tree["fallback"] == "tfidf"


async def test_a_short_embedding_reply_marks_the_tree_as_tfidf():
    """A provider that returns fewer vectors than texts must not be zipped
    against the documents it did not embed."""
    docs, vectors = _corpus()
    p = MagicMock()

    async def _short(texts, *, input_type="search_document"):
        return EmbeddingResult(embeddings=[vectors[t] for t in texts][:-1], model="fake")

    p.embed = AsyncMock(side_effect=_short)
    with patch("intel_platform.llm.embeddings.get_embedding_provider", return_value=p):
        tree, _, _ = await cluster_semantic(docs, "proj-g10")
    assert tree["fallback"] == "tfidf"


async def test_a_semantic_tree_carries_no_fallback_marker():
    tree, _, _ = await _tree("medium")
    assert "fallback" not in tree


async def test_clustering_runs_off_the_event_loop(monkeypatch):
    loop_thread = threading.current_thread()
    seen: dict[str, threading.Thread] = {}
    real_build = dc._build_semantic_tree

    def _spy(*args, **kwargs):
        seen["semantic"] = threading.current_thread()
        return real_build(*args, **kwargs)

    monkeypatch.setattr(dc, "_build_semantic_tree", _spy)
    await _tree("medium")
    assert seen["semantic"] is not loop_thread


async def test_the_tfidf_fallback_runs_off_the_event_loop(monkeypatch):
    loop_thread = threading.current_thread()
    seen: dict[str, threading.Thread] = {}
    real = dc.cluster_documents

    def _spy(*args, **kwargs):
        seen["tfidf"] = threading.current_thread()
        return real(*args, **kwargs)

    monkeypatch.setattr(dc, "cluster_documents", _spy)
    docs, _ = _corpus()
    with patch("intel_platform.llm.embeddings.get_embedding_provider", side_effect=RuntimeError("no key")):
        await cluster_semantic(docs, "proj-g10")
    assert seen["tfidf"] is not loop_thread
