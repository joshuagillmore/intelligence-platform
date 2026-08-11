# Topic Mind Map — Document Clustering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace entity-grouping topic tree with TF-IDF document content clustering so the Data Sources mind map shows what documents are about, not how entities are categorized.

**Architecture:** New `document_clustering.py` module handles TF-IDF vectorization and recursive K-Means. `TopicTreeService` calls it to build the primary "Topics" branch. Module-level dicts cache cluster-to-document mappings for the context endpoint. Frontend adds keyword tags and topic-aware panel headers.

**Tech Stack:** Python (scipy.sparse, numpy), FastAPI, Neo4j, Next.js 14, D3.js

**Spec:** `docs/superpowers/specs/2026-03-22-topic-mindmap-document-clustering-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/src/intel_platform/services/document_clustering.py` | Create | TF-IDF vectorization, K-Means clustering, cluster labeling — pure algorithms, no Neo4j dependency |
| `backend/src/intel_platform/services/topics.py` | Modify | Add `_build_topic_branch()`, update `build_topic_tree()` to use it as primary branch, update `get_topic_context()` for `topic-*` nodes, add module-level cluster caches |
| `backend/src/intel_platform/api/routes/topics.py` | Modify | Increase cache TTL from 30s to 60s |
| `backend/tests/test_document_clustering.py` | Create | Unit tests for TF-IDF, K-Means, labeling |
| `backend/tests/test_topics_route.py` | Modify | Add integration test for topic-* nodes |
| `frontend/src/app/data-sources/page.tsx` | Modify | Keyword tags, topic-aware headers, context normalization |

---

## Task 1: TF-IDF Vectorization

**Files:**
- Create: `backend/src/intel_platform/services/document_clustering.py`
- Create: `backend/tests/test_document_clustering.py`

- [ ] **Step 1: Write failing test for TF-IDF**

In `backend/tests/test_document_clustering.py`:

```python
"""Tests for document clustering (TF-IDF + K-Means)."""
import numpy as np
from intel_platform.services.document_clustering import build_tfidf


def test_tfidf_basic():
    """Two docs with distinct terms produce non-zero vectors."""
    docs = [
        ("doc1", "cyber attack malware phishing credential theft"),
        ("doc2", "sanctions iran oil trade export revenue"),
    ]
    matrix, doc_ids, vocab = build_tfidf(docs)
    assert matrix.shape[0] == 2
    assert matrix.shape[1] > 0
    assert doc_ids == ["doc1", "doc2"]
    # Each row should be L2-normalized
    for i in range(matrix.shape[0]):
        row_norm = np.sqrt(matrix[i].multiply(matrix[i]).sum())
        assert abs(row_norm - 1.0) < 1e-6


def test_tfidf_stopwords_removed():
    """Common English stopwords should not appear in vocabulary."""
    docs = [
        ("d1", "the quick brown fox jumps over the lazy dog"),
        ("d2", "the lazy dog sleeps all day long"),
    ]
    _, _, vocab = build_tfidf(docs)
    for stopword in ["the", "over", "all"]:
        assert stopword not in vocab


def test_tfidf_empty_corpus():
    """Empty corpus returns empty matrix."""
    matrix, doc_ids, vocab = build_tfidf([])
    assert matrix.shape == (0, 0)
    assert doc_ids == []
    assert vocab == []


def test_tfidf_single_doc():
    """Single document produces valid matrix."""
    docs = [("d1", "intelligence analysis report summary findings")]
    matrix, doc_ids, vocab = build_tfidf(docs)
    assert matrix.shape[0] == 1
    assert len(vocab) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/Users/joshu/intelligence-platform/backend && uv run pytest tests/test_document_clustering.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'intel_platform.services.document_clustering'`

- [ ] **Step 3: Implement TF-IDF**

Create `backend/src/intel_platform/services/document_clustering.py`:

```python
"""Document clustering via TF-IDF + recursive K-Means.

Pure algorithms — no Neo4j or FastAPI dependency.
Uses scipy.sparse and numpy (already available via spaCy).
"""
from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np
from scipy.sparse import csr_matrix

# ~175 common English stopwords
STOPWORDS = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "also", "am",
    "an", "and", "any", "are", "as", "at", "be", "because", "been", "before",
    "being", "below", "between", "both", "but", "by", "can", "could", "did",
    "do", "does", "doing", "down", "during", "each", "even", "few", "for",
    "from", "further", "get", "got", "had", "has", "have", "having", "he",
    "her", "here", "hers", "herself", "him", "himself", "his", "how", "if",
    "in", "into", "is", "it", "its", "itself", "just", "know", "let", "like",
    "make", "may", "me", "might", "more", "most", "much", "must", "my",
    "myself", "no", "nor", "not", "now", "of", "off", "on", "once", "one",
    "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own",
    "per", "re", "same", "shall", "she", "should", "so", "some", "still",
    "such", "than", "that", "the", "their", "theirs", "them", "themselves",
    "then", "there", "therefore", "these", "they", "this", "those", "through",
    "to", "too", "under", "until", "up", "upon", "us", "use", "used", "using",
    "very", "was", "we", "well", "were", "what", "when", "where", "which",
    "while", "who", "whom", "why", "will", "with", "within", "without",
    "would", "yet", "you", "your", "yours", "yourself", "yourselves",
})

_TOKEN_RE = re.compile(r"\b[a-z]{2,}\b")


def _tokenize(text: str) -> list[str]:
    return [w for w in _TOKEN_RE.findall(text.lower()) if w not in STOPWORDS]


def build_tfidf(
    documents: list[tuple[str, str]],
) -> tuple[csr_matrix, list[str], list[str]]:
    """Build TF-IDF sparse matrix from (doc_id, text) pairs.

    Returns (tfidf_matrix, doc_ids, vocabulary_list).
    """
    if not documents:
        return csr_matrix((0, 0)), [], []

    n_docs = len(documents)
    tokenized = [_tokenize(text) for _, text in documents]

    # Build vocabulary + document frequency
    vocab: dict[str, int] = {}
    df: Counter[str] = Counter()
    for tokens in tokenized:
        unique = set(tokens)
        for t in unique:
            df[t] += 1
            if t not in vocab:
                vocab[t] = len(vocab)

    # Filter vocabulary
    if n_docs < 5:
        valid = {t for t in vocab if df[t] >= 1}
    else:
        valid = {t for t in vocab if 2 <= df[t] <= 0.9 * n_docs}

    if not valid:
        # Fallback: use all terms
        valid = set(vocab.keys())

    # Re-index to contiguous integers
    final_vocab: dict[str, int] = {}
    for t in sorted(valid):
        final_vocab[t] = len(final_vocab)

    if not final_vocab:
        return csr_matrix((n_docs, 0)), [d[0] for d in documents], []

    # Compute IDF
    idf = {t: math.log(n_docs / df[t]) for t in final_vocab}

    # Build sparse TF-IDF matrix
    rows, cols, data = [], [], []
    for i, tokens in enumerate(tokenized):
        if not tokens:
            continue
        tf = Counter(tokens)
        for t, count in tf.items():
            if t in final_vocab:
                rows.append(i)
                cols.append(final_vocab[t])
                data.append((count / len(tokens)) * idf[t])

    matrix = csr_matrix((data, (rows, cols)), shape=(n_docs, len(final_vocab)))

    # L2 normalize rows
    norms = np.sqrt(matrix.multiply(matrix).sum(axis=1)).A1
    norms[norms == 0] = 1
    matrix = matrix.multiply(1.0 / norms[:, np.newaxis])

    return matrix, [d[0] for d in documents], list(final_vocab.keys())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/Users/joshu/intelligence-platform/backend && uv run pytest tests/test_document_clustering.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
cd /c/Users/joshu/intelligence-platform
git add backend/src/intel_platform/services/document_clustering.py backend/tests/test_document_clustering.py
git commit -m "feat: add TF-IDF vectorization for document clustering"
```

---

## Task 2: K-Means Clustering

**Files:**
- Modify: `backend/src/intel_platform/services/document_clustering.py`
- Modify: `backend/tests/test_document_clustering.py`

- [ ] **Step 1: Write failing test for K-Means**

Append to `backend/tests/test_document_clustering.py`:

```python
from intel_platform.services.document_clustering import kmeans, build_tfidf


def test_kmeans_two_clusters():
    """Documents on clearly different topics should separate."""
    docs = [
        ("d1", "cyber attack malware phishing credential"),
        ("d2", "cyber threat exploit vulnerability malware"),
        ("d3", "cyber ransomware attack phishing email"),
        ("d4", "sanctions iran oil trade export"),
        ("d5", "sanctions embargo trade iran nuclear"),
        ("d6", "oil export revenue sanctions iran"),
    ]
    matrix, doc_ids, vocab = build_tfidf(docs)
    rng = np.random.RandomState(42)
    assignments = kmeans(matrix, k=2, max_iter=20, rng=rng)
    # Cyber docs (0-2) should be in same cluster, sanctions docs (3-5) in another
    assert assignments[0] == assignments[1] == assignments[2]
    assert assignments[3] == assignments[4] == assignments[5]
    assert assignments[0] != assignments[3]


def test_kmeans_single_cluster():
    """All identical docs should end up in one cluster."""
    docs = [("d1", "hello world"), ("d2", "hello world"), ("d3", "hello world")]
    matrix, _, _ = build_tfidf(docs)
    rng = np.random.RandomState(42)
    assignments = kmeans(matrix, k=2, max_iter=20, rng=rng)
    # All in same cluster
    assert len(set(assignments)) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/Users/joshu/intelligence-platform/backend && uv run pytest tests/test_document_clustering.py::test_kmeans_two_clusters -v`
Expected: FAIL — `ImportError: cannot import name 'kmeans'`

- [ ] **Step 3: Implement K-Means**

Append to `backend/src/intel_platform/services/document_clustering.py`:

```python
def kmeans(
    vectors: csr_matrix, k: int, max_iter: int = 20, rng: np.random.RandomState | None = None,
) -> np.ndarray:
    """K-Means on L2-normalized sparse vectors using cosine similarity.

    Returns array of cluster assignments (length = number of rows).
    """
    if rng is None:
        rng = np.random.RandomState(42)

    n = vectors.shape[0]
    if n == 0 or vectors.shape[1] == 0:
        return np.zeros(n, dtype=int)

    k = min(k, n)

    # K-Means++ initialization
    first_idx = rng.randint(n)
    centroids_list: list[np.ndarray] = [vectors[first_idx].toarray().flatten()]

    for _ in range(k - 1):
        centroid_matrix = np.array(centroids_list)
        sims = vectors.dot(centroid_matrix.T)
        if hasattr(sims, "A1"):
            max_sims = sims.max(axis=1).A1 if sims.shape[1] > 1 else sims.toarray().flatten()
        else:
            max_sims = sims.max(axis=1)
        min_dists = np.maximum(1.0 - max_sims, 0)
        total = min_dists.sum()
        if total < 1e-10:
            # All points identical to existing centroids
            idx = rng.randint(n)
        else:
            probs = min_dists / total
            idx = rng.choice(n, p=probs)
        centroids_list.append(vectors[idx].toarray().flatten())

    centroids = np.array(centroids_list)

    assignments = np.zeros(n, dtype=int)
    for _ in range(max_iter):
        # Assign each vector to nearest centroid (cosine = dot for L2-normed)
        sims = vectors.dot(centroids.T)
        if hasattr(sims, "A"):
            new_assignments = sims.A.argmax(axis=1)
        else:
            new_assignments = sims.argmax(axis=1)

        if np.array_equal(assignments, new_assignments):
            break
        assignments = new_assignments

        # Update centroids + L2 renormalize
        new_centroids = np.zeros_like(centroids)
        for j in range(k):
            mask = assignments == j
            if mask.any():
                mean_vec = vectors[mask].mean(axis=0)
                if hasattr(mean_vec, "A1"):
                    mean_vec = mean_vec.A1
                else:
                    mean_vec = np.asarray(mean_vec).flatten()
                norm = np.linalg.norm(mean_vec)
                new_centroids[j] = mean_vec / norm if norm > 0 else mean_vec
        centroids = new_centroids

    return assignments
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/Users/joshu/intelligence-platform/backend && uv run pytest tests/test_document_clustering.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
cd /c/Users/joshu/intelligence-platform
git add backend/src/intel_platform/services/document_clustering.py backend/tests/test_document_clustering.py
git commit -m "feat: add K-Means clustering with K-Means++ init"
```

---

## Task 3: Recursive Clustering + Node Labeling

**Files:**
- Modify: `backend/src/intel_platform/services/document_clustering.py`
- Modify: `backend/tests/test_document_clustering.py`

- [ ] **Step 1: Write failing test for recursive clustering and labeling**

Append to `backend/tests/test_document_clustering.py`:

```python
from intel_platform.services.document_clustering import cluster_documents


def test_cluster_documents_produces_tree():
    """Cluster documents should produce a tree with topic nodes."""
    docs = [
        ("d1", "cyber attack malware phishing credential theft"),
        ("d2", "cyber threat exploit vulnerability malware attack"),
        ("d3", "sanctions iran oil trade export revenue"),
        ("d4", "sanctions embargo trade iran nuclear deal"),
    ]
    tree, doc_map, kw_map = cluster_documents(docs, project_id="test-proj")
    assert tree["name"] != ""
    assert tree["id"].startswith("topic-")
    assert tree["entity_type"] == "topic"
    assert len(tree.get("doc_ids", [])) == 4
    # doc_map should have entries for the root node
    assert "test-proj" in doc_map or tree["id"] in doc_map.get("test-proj", {})


def test_cluster_documents_single_doc():
    """Single document returns leaf node."""
    docs = [("d1", "intelligence analysis report")]
    tree, _, _ = cluster_documents(docs, project_id="test-proj")
    assert tree["entity_type"] == "document_source"


def test_cluster_documents_empty():
    """Empty corpus returns None."""
    tree, _, _ = cluster_documents([], project_id="test-proj")
    assert tree is None


def test_cluster_labels_contain_terms():
    """Internal nodes should have keyword labels, not UUIDs."""
    docs = [
        ("d1", "cyber attack malware phishing credential theft"),
        ("d2", "cyber threat exploit vulnerability malware attack"),
        ("d3", "cyber ransomware attack phishing email spearphishing"),
        ("d4", "sanctions iran oil trade export revenue"),
        ("d5", "sanctions embargo trade iran nuclear deal"),
        ("d6", "oil export revenue sanctions iran economy"),
    ]
    tree, _, kw_map = cluster_documents(docs, project_id="test-proj")
    # Root should have children (the clusters)
    assert len(tree.get("children", [])) >= 2
    # Each child should have a name with actual words, not UUIDs
    for child in tree["children"]:
        assert len(child["name"]) > 0
        assert not child["name"].startswith("topic-")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/Users/joshu/intelligence-platform/backend && uv run pytest tests/test_document_clustering.py::test_cluster_documents_produces_tree -v`
Expected: FAIL — `ImportError: cannot import name 'cluster_documents'`

- [ ] **Step 3: Implement recursive clustering and labeling**

Append to `backend/src/intel_platform/services/document_clustering.py`:

```python
MIN_CLUSTER_SIZE = 3
MAX_DEPTH = 6


def _label_cluster(
    vectors: csr_matrix, vocab: list[str], doc_indices: list[int],
    all_tokenized: list[list[str]],
) -> tuple[str, list[str]]:
    """Generate keyword label for a cluster from TF-IDF weights.

    Returns (label_string, keyword_list).
    """
    if not doc_indices or not vocab:
        return "Documents", ["documents"]

    # Sum TF-IDF vectors across cluster
    cluster_vectors = vectors[doc_indices]
    summed = np.asarray(cluster_vectors.sum(axis=0)).flatten()

    # Count document frequency within this cluster
    n_cluster = len(doc_indices)
    cluster_df: Counter[str] = Counter()
    for idx in doc_indices:
        unique_terms = set(all_tokenized[idx])
        for t in unique_terms:
            if t in vocab:
                cluster_df[t] += 1

    # Score terms: weight * cluster_df_ratio
    scored: list[tuple[float, str]] = []
    vocab_set = {v: i for i, v in enumerate(vocab)}
    for term, col_idx in vocab_set.items():
        weight = summed[col_idx]
        if weight > 0:
            df_ratio = cluster_df.get(term, 0) / n_cluster
            scored.append((weight * (1 + df_ratio), term))

    scored.sort(key=lambda x: -x[0])

    # Pick primary terms (in >=70% of cluster docs, up to 3)
    primary = []
    secondary = []
    for _, term in scored:
        df_ratio = cluster_df.get(term, 0) / n_cluster
        if df_ratio >= 0.7 and len(primary) < 3:
            primary.append(term)
        elif len(secondary) < 2:
            secondary.append(term)
        if len(primary) >= 3 and len(secondary) >= 2:
            break

    keywords = primary + secondary
    if not keywords:
        keywords = [t for _, t in scored[:3]]

    # Generate bigrams from top docs and promote if they score higher
    bigrams: Counter[str] = Counter()
    for idx in doc_indices[:10]:  # sample top docs
        tokens = all_tokenized[idx]
        for i in range(len(tokens) - 1):
            bg = f"{tokens[i]} {tokens[i+1]}"
            if tokens[i] in vocab_set and tokens[i+1] in vocab_set:
                bigrams[bg] += 1

    # Replace unigrams with bigrams where appropriate
    for bg, count in bigrams.most_common(3):
        if count >= max(2, n_cluster * 0.3):
            parts = bg.split()
            if parts[0] in keywords or parts[1] in keywords:
                keywords = [k for k in keywords if k not in parts]
                keywords.insert(0, bg)

    # Capitalize for display
    keywords = [k.title() for k in keywords[:5]]
    label = ", ".join(keywords[:4])
    return label, keywords


def _recursive_cluster(
    vectors: csr_matrix,
    doc_ids: list[str],
    vocab: list[str],
    all_tokenized: list[list[str]],
    doc_indices: list[int],
    depth: int,
    path: str,
    rng: np.random.RandomState,
    doc_map: dict[str, list[str]],
    kw_map: dict[str, list[str]],
) -> dict:
    """Recursively cluster documents and build tree nodes."""
    n = len(doc_indices)

    # Base case: leaf cluster or single doc
    if n <= MIN_CLUSTER_SIZE or depth >= MAX_DEPTH:
        if n == 1:
            return {
                "id": doc_ids[doc_indices[0]],
                "name": doc_ids[doc_indices[0]],  # will be replaced with doc name by caller
                "entity_type": "document_source",
                "doc_ids": [doc_ids[doc_indices[0]]],
                "count": 1,
            }
        # Small cluster — make leaf topic node with doc children
        label, keywords = _label_cluster(vectors, vocab, doc_indices, all_tokenized)
        node_id = f"topic-{path}" if path else "topic-root"
        children = []
        for idx in doc_indices:
            children.append({
                "id": doc_ids[idx],
                "name": doc_ids[idx],
                "entity_type": "document_source",
                "doc_ids": [doc_ids[idx]],
                "count": 1,
            })
        cluster_doc_ids = [doc_ids[i] for i in doc_indices]
        doc_map[node_id] = cluster_doc_ids
        kw_map[node_id] = keywords
        return {
            "id": node_id,
            "name": label,
            "entity_type": "topic",
            "doc_ids": cluster_doc_ids,
            "count": n,
            "children": children,
            "keywords": keywords,
        }

    # Cluster
    sub_vectors = vectors[doc_indices]
    k = max(2, min(5, n // 2))
    assignments = kmeans(sub_vectors, k=k, max_iter=20, rng=rng)

    # Group by assignment
    groups: dict[int, list[int]] = {}
    for local_idx, cluster_id in enumerate(assignments):
        groups.setdefault(int(cluster_id), []).append(doc_indices[local_idx])

    # Check for degenerate split (all in one cluster)
    if len(groups) <= 1:
        label, keywords = _label_cluster(vectors, vocab, doc_indices, all_tokenized)
        node_id = f"topic-{path}" if path else "topic-root"
        children = []
        for idx in doc_indices:
            children.append({
                "id": doc_ids[idx],
                "name": doc_ids[idx],
                "entity_type": "document_source",
                "doc_ids": [doc_ids[idx]],
                "count": 1,
            })
        cluster_doc_ids = [doc_ids[i] for i in doc_indices]
        doc_map[node_id] = cluster_doc_ids
        kw_map[node_id] = keywords
        return {
            "id": node_id,
            "name": label,
            "entity_type": "topic",
            "doc_ids": cluster_doc_ids,
            "count": n,
            "children": children,
            "keywords": keywords,
        }

    # Recurse into each group
    children = []
    for group_idx, group_doc_indices in sorted(groups.items(), key=lambda x: -len(x[1])):
        child_path = f"{path}-{group_idx}" if path else str(group_idx)
        child = _recursive_cluster(
            vectors, doc_ids, vocab, all_tokenized, group_doc_indices,
            depth + 1, child_path, rng, doc_map, kw_map,
        )
        children.append(child)

    # Label this internal node
    label, keywords = _label_cluster(vectors, vocab, doc_indices, all_tokenized)
    node_id = f"topic-{path}" if path else "topic-root"
    cluster_doc_ids = [doc_ids[i] for i in doc_indices]
    doc_map[node_id] = cluster_doc_ids
    kw_map[node_id] = keywords

    return {
        "id": node_id,
        "name": label,
        "entity_type": "topic",
        "doc_ids": cluster_doc_ids,
        "count": n,
        "children": children,
        "keywords": keywords,
    }


def cluster_documents(
    documents: list[tuple[str, str]],
    project_id: str,
) -> tuple[dict | None, dict[str, dict[str, list[str]]], dict[str, dict[str, list[str]]]]:
    """Cluster documents by content and return tree + lookup maps.

    Args:
        documents: list of (doc_id, text) pairs
        project_id: for cache keying

    Returns:
        (tree_node, {project_id: {node_id: [doc_ids]}}, {project_id: {node_id: [keywords]}})
    """
    doc_map: dict[str, dict[str, list[str]]] = {project_id: {}}
    kw_map: dict[str, dict[str, list[str]]] = {project_id: {}}

    if not documents:
        return None, doc_map, kw_map

    if len(documents) == 1:
        doc_id, _ = documents[0]
        node = {
            "id": doc_id,
            "name": doc_id,
            "entity_type": "document_source",
            "doc_ids": [doc_id],
            "count": 1,
        }
        return node, doc_map, kw_map

    matrix, doc_ids, vocab = build_tfidf(documents)

    if matrix.shape[1] == 0:
        # No usable vocabulary — return flat list
        children = [
            {"id": did, "name": did, "entity_type": "document_source", "doc_ids": [did], "count": 1}
            for did in doc_ids
        ]
        root = {
            "id": "topic-root",
            "name": "All Documents",
            "entity_type": "topic",
            "doc_ids": doc_ids,
            "count": len(doc_ids),
            "children": children,
            "keywords": [],
        }
        doc_map[project_id]["topic-root"] = doc_ids
        kw_map[project_id]["topic-root"] = []
        return root, doc_map, kw_map

    # Tokenize all docs for labeling
    all_tokenized = [_tokenize(text) for _, text in documents]
    all_indices = list(range(len(documents)))

    rng = np.random.RandomState(hash(project_id) % (2**31))

    tree = _recursive_cluster(
        matrix, doc_ids, vocab, all_tokenized, all_indices,
        depth=0, path="", rng=rng,
        doc_map=doc_map[project_id], kw_map=kw_map[project_id],
    )

    return tree, doc_map, kw_map
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/Users/joshu/intelligence-platform/backend && uv run pytest tests/test_document_clustering.py -v`
Expected: 10 PASSED

- [ ] **Step 5: Commit**

```bash
cd /c/Users/joshu/intelligence-platform
git add backend/src/intel_platform/services/document_clustering.py backend/tests/test_document_clustering.py
git commit -m "feat: add recursive document clustering with keyword labeling"
```

---

## Task 4: Integrate Clustering into TopicTreeService

**Files:**
- Modify: `backend/src/intel_platform/services/topics.py`
- Modify: `backend/src/intel_platform/api/routes/topics.py`

- [ ] **Step 1: Add module-level cluster caches and update `build_topic_tree()`**

At the top of `backend/src/intel_platform/services/topics.py`, after the imports, add:

```python
from intel_platform.services.document_clustering import cluster_documents

# Module-level caches for cluster membership (survives across per-request service instances)
_cluster_doc_map: dict[str, dict[str, list[str]]] = {}
_cluster_keywords: dict[str, dict[str, list[str]]] = {}
```

Replace the `build_topic_tree` method body to use `_build_topic_branch()` as primary:

In the `build_topic_tree` method, replace the tree assembly section (after `entity_map` is built) so it:
1. Calls the new `_build_topic_branch(documents, project_id)` method as the first branch
2. Keeps Source Documents, Geographic, Actors as secondary branches
3. Removes Thematic Clusters (community detection) — replaced by document clustering

Add the new `_build_topic_branch` method:

```python
def _build_topic_branch(self, documents: list, project_id: str) -> dict | None:
    """Build primary topic branch from document content clustering."""
    global _cluster_doc_map, _cluster_keywords

    # Fetch full document content (search_entities returns content field)
    doc_pairs: list[tuple[str, str]] = []
    doc_name_map: dict[str, str] = {}  # doc_id -> display name
    for doc in documents:
        doc_id = doc.get("id", "")
        content = doc.get("content", "")
        name = doc.get("name", doc_id)
        doc_name_map[doc_id] = name
        if content and doc_id:
            doc_pairs.append((doc_id, content))

    if not doc_pairs:
        return None

    tree, doc_map, kw_map = cluster_documents(doc_pairs, project_id)
    if tree is None:
        return None

    # Update module-level caches
    _cluster_doc_map.update(doc_map)
    _cluster_keywords.update(kw_map)

    # Replace doc IDs with display names in leaf nodes
    def _set_doc_names(node: dict) -> None:
        if node.get("entity_type") == "document_source":
            node["name"] = doc_name_map.get(node["id"], node["id"])
        for child in node.get("children", []):
            _set_doc_names(child)

    _set_doc_names(tree)

    # Wrap in a branch node
    branch = {
        "name": "Topics",
        "id": "branch-themes",
        "entity_type": "branch",
        "children": tree.get("children", [tree]) if tree.get("children") else [tree],
        "count": tree.get("count", len(doc_pairs)),
    }
    return branch
```

- [ ] **Step 2: Update `build_topic_tree()` to use topic branch as primary**

Replace the tree children assembly in `build_topic_tree()`:

```python
tree["children"] = []

# Branch 1: Topics (document content clustering) — PRIMARY
topic_branch = self._build_topic_branch(documents, project_id)
if topic_branch:
    tree["children"].append(topic_branch)

# Branch 2: By Source Document (with entity drilldown)
doc_branch = self._build_document_branch(documents)
if doc_branch["children"]:
    tree["children"].append(doc_branch)

# Branch 3: Geographic Themes (locations grouped by region)
geo_branch = self._build_geo_branch(non_docs)
if geo_branch["children"]:
    tree["children"].append(geo_branch)

# Branch 4: Actors & Organizations
actor_branch = self._build_actor_branch(non_docs, G)
if actor_branch["children"]:
    tree["children"].append(actor_branch)
```

- [ ] **Step 3: Update `get_topic_context()` to handle `topic-*` IDs**

At the top of `get_topic_context()`, add handling for topic nodes:

```python
def get_topic_context(self, entity_id: str, project_id: str) -> dict:
    """Get full context for an entity or topic cluster."""
    global _cluster_doc_map, _cluster_keywords

    # Handle topic cluster nodes
    if entity_id.startswith("topic-"):
        project_clusters = _cluster_doc_map.get(project_id, {})
        doc_ids = project_clusters.get(entity_id, [])

        # If cache expired, rebuild tree to repopulate
        if not doc_ids:
            self.build_topic_tree(project_id)
            project_clusters = _cluster_doc_map.get(project_id, {})
            doc_ids = project_clusters.get(entity_id, [])

        keywords = _cluster_keywords.get(project_id, {}).get(entity_id, [])

        documents = []
        connected_entities = []
        seen_entity_ids: set[str] = set()

        for doc_id in doc_ids:
            doc = self._store.get_entity(doc_id)
            if doc and doc.get("entity_type") == "Document":
                documents.append({
                    "id": doc.get("id"),
                    "name": doc.get("name"),
                    "reliability_rating": doc.get("reliability_rating", ""),
                    "content_preview": (doc.get("content", "") or "")[:500],
                })
                # Find entities from this document
                rels = self._store.get_relationships(doc_id)
                for rel in rels:
                    target = self._store.get_entity(rel.get("target_id", ""))
                    if target and target.get("entity_type") != "Document":
                        eid = target.get("id", "")
                        if eid not in seen_entity_ids:
                            seen_entity_ids.add(eid)
                            connected_entities.append({
                                "id": eid,
                                "name": target.get("name"),
                                "entity_type": target.get("entity_type"),
                                "rel_type": rel.get("rel_type", "ASSOCIATED_WITH"),
                                "confidence": rel.get("confidence"),
                            })

        return {
            "entity": {"id": entity_id, "name": ", ".join(keywords) or "Topic Cluster", "entity_type": "topic"},
            "documents": documents,
            "source_documents": documents,
            "connected_entities": connected_entities,
            "keywords": keywords,
            "document_count": len(documents),
        }

    # Original entity handling below...
```

- [ ] **Step 4: Increase cache TTL**

In `backend/src/intel_platform/api/routes/topics.py`, change `@cached(ttl=30)` to `@cached(ttl=60)`.

- [ ] **Step 5: Add integration test for topic-* context endpoint**

Append to `backend/tests/test_topics_route.py`:

```python
def test_topic_context_returns_documents(graph_store):
    """Selecting a topic-* cluster node should return its documents."""
    from intel_platform.models.entities import Document
    from intel_platform.services.topics import TopicTreeService

    project_id = "test-topic-ctx"

    # Create test documents
    doc1 = Document(name="cyber_report.pdf", content="cyber attack malware phishing credential theft", project_id=project_id)
    doc2 = Document(name="sanctions_brief.pdf", content="sanctions iran oil trade export revenue", project_id=project_id)
    graph_store.create_entity(doc1)
    graph_store.create_entity(doc2)

    svc = TopicTreeService(graph_store)
    tree = svc.build_topic_tree(project_id)

    # Find first topic-* node in tree
    def find_topic_node(node):
        if node.get("id", "").startswith("topic-"):
            return node
        for child in node.get("children", []):
            found = find_topic_node(child)
            if found:
                return found
        return None

    topic_node = find_topic_node(tree)
    if topic_node:
        ctx = svc.get_topic_context(topic_node["id"], project_id)
        assert "documents" in ctx or "source_documents" in ctx
        assert ctx.get("keywords") is not None
```

- [ ] **Step 6: Run all topic tests**

Run: `cd /c/Users/joshu/intelligence-platform/backend && uv run pytest tests/test_topics_route.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
cd /c/Users/joshu/intelligence-platform
git add backend/src/intel_platform/services/topics.py backend/src/intel_platform/api/routes/topics.py backend/tests/test_topics_route.py
git commit -m "feat: integrate document clustering as primary topic tree branch"
```

---

## Task 5: Frontend — Keyword Tags and Topic-Aware Panels

**Files:**
- Modify: `frontend/src/app/data-sources/page.tsx`

- [ ] **Step 1: Update TypeScript interface, add keywords state**

In the `EntityContext` interface, add the `keywords` field:

```typescript
interface EntityContext {
  entity: { id: string; name: string; entity_type: string; properties?: Record<string, unknown> };
  connected_entities?: ConnectedEntity[];
  source_documents?: SourceDocument[];
  keywords?: string[];
}
```

In the state declarations section, add:

```typescript
const [keywords, setKeywords] = useState<string[]>([]);
```

In `handleTopicClick`, after setting `entityContext`, extract keywords:

```typescript
// After: setEntityContext(data);
setKeywords(data.keywords || []);
```

Also clear keywords when resetting:

```typescript
// In the reset block at top of handleTopicClick:
setKeywords([]);
```

- [ ] **Step 2: Update left panel header for topic vs document nodes**

Replace the static header `Documents for "{selectedNodeName}"` with:

```tsx
<h3 className="font-bold text-[10px] uppercase tracking-widest text-gray-500">
  {selectedNodeId?.startsWith('topic-')
    ? `Documents in "${selectedNodeName}"`
    : `Document: "${selectedNodeName}"`
  }
</h3>
```

- [ ] **Step 3: Add keyword tags above the summary section**

In the right panel, above the "Intelligence Summary" section, add:

```tsx
{keywords.length > 0 && (
  <div className="flex flex-wrap gap-1.5 mb-3">
    {keywords.map((kw, i) => (
      <span
        key={i}
        className="bg-purple-900/30 text-purple-300 border border-purple-700/30 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider"
      >
        {kw}
      </span>
    ))}
  </div>
)}
```

- [ ] **Step 4: Add topic node purple coloring to TopicMindMap**

In `frontend/src/components/TopicMindMap.tsx`, add a color entry for `topic` entity_type nodes. In the `getBranchColor` function, add a check before the parent walk:

```typescript
function getBranchColor(node: any): string {
  // Topic cluster nodes get purple
  if (node.data?.entity_type === 'topic') return '#a855f7';
  let current = node;
  while (current) {
    const id = current.data?.id || '';
    if (BRANCH_COLORS[id]) return BRANCH_COLORS[id];
    current = current.parent;
  }
  return '#6b7280';
}
```

- [ ] **Step 5: Verify build succeeds**

Run: `cd /c/Users/joshu/intelligence-platform/frontend && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 6: Commit**

```bash
cd /c/Users/joshu/intelligence-platform
git add frontend/src/app/data-sources/page.tsx frontend/src/components/TopicMindMap.tsx
git commit -m "feat: add keyword tags, topic-aware panels, topic node coloring"
```

---

## Task 6: Docker Rebuild + Manual Verification

**Files:** None (deployment task)

- [ ] **Step 1: Rebuild and start local Docker containers**

```bash
cd /c/Users/joshu/intelligence-platform
docker compose down && docker compose up --build -d
```

Wait for health check: `curl -s http://localhost:8000/health`

- [ ] **Step 2: Verify topic tree endpoint returns topic-* nodes**

Login and get token:
```bash
TOKEN=$(curl -s http://localhost:8000/api/auth/login -X POST -H "Content-Type: application/json" -d '{"username":"admin","password":"admin"}' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

Test topics endpoint (requires a project with ingested documents):
```bash
curl -s http://localhost:8000/api/topics?project_id=<PROJECT_ID> -H "Authorization: Bearer $TOKEN" | python -m json.tool | head -40
```

Expected: Tree with `"id": "branch-themes"` containing children with `"id": "topic-..."` and `"keywords": [...]`

- [ ] **Step 3: Verify topic context endpoint**

```bash
curl -s "http://localhost:8000/api/topics/topic-0?project_id=<PROJECT_ID>" -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

Expected: Response with `documents`, `keywords`, `connected_entities`

- [ ] **Step 4: Push to GitHub for Railway deployment**

```bash
cd /c/Users/joshu/intelligence-platform
git push origin main
```

- [ ] **Step 5: Commit any final fixes**

If any issues found during manual testing, fix and commit.
