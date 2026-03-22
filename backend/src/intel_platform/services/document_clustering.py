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
    matrix = csr_matrix(matrix.multiply(1.0 / norms[:, np.newaxis]))

    return matrix, [d[0] for d in documents], list(final_vocab.keys())


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
        if hasattr(sims, "A"):
            sims_dense = sims.A
        else:
            sims_dense = np.asarray(sims)
        max_sims = sims_dense.max(axis=1)
        min_dists = np.maximum(1.0 - max_sims, 0)
        total = min_dists.sum()
        if total < 1e-10:
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
            new_assignments = np.asarray(sims).argmax(axis=1)

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


# ---------------------------------------------------------------------------
# Recursive clustering + keyword labeling
# ---------------------------------------------------------------------------

MIN_CLUSTER_SIZE = 3
MAX_DEPTH = 6


def _label_cluster(
    vectors: csr_matrix,
    vocab: list[str],
    doc_indices: list[int],
    all_tokenized: list[list[str]],
) -> tuple[str, list[str]]:
    """Generate a human-readable keyword label for a cluster.

    Returns (label_string, keyword_list).
    """
    if not doc_indices or not vocab:
        return "cluster", []

    n = len(doc_indices)
    sub_matrix = vectors[doc_indices]

    # Sum TF-IDF weights across cluster docs
    summed = np.asarray(sub_matrix.sum(axis=0)).flatten()

    # Count how many docs contain each term (document frequency within cluster)
    doc_freq = np.zeros(len(vocab), dtype=int)
    for idx in doc_indices:
        row = vectors[idx]
        nonzero_cols = row.nonzero()[1]
        doc_freq[nonzero_cols] += 1

    # Sort terms by total weight
    ranked_indices = np.argsort(summed)[::-1]

    # Primary: terms present in >= 70% of cluster docs
    threshold = max(1, int(0.70 * n))
    primary_terms = []
    secondary_terms = []

    for idx in ranked_indices:
        if summed[idx] < 1e-10:
            break
        term = vocab[idx]
        if doc_freq[idx] >= threshold:
            if len(primary_terms) < 3:
                primary_terms.append(term)
        else:
            if len(secondary_terms) < 2:
                secondary_terms.append(term)

        if len(primary_terms) >= 3 and len(secondary_terms) >= 2:
            break

    # Try to build bigrams from top docs
    top_doc_count = min(3, n)
    top_doc_indices = doc_indices[:top_doc_count]
    bigram_counter: Counter[str] = Counter()
    for di in top_doc_indices:
        tokens = all_tokenized[di]
        for i in range(len(tokens) - 1):
            bigram = f"{tokens[i]} {tokens[i+1]}"
            bigram_counter[bigram] += 1

    # Promote bigrams that appear in >= 50% of the top docs sampled
    promoted_bigrams = [
        bg for bg, cnt in bigram_counter.most_common(3)
        if cnt >= max(1, top_doc_count // 2)
    ]

    # Build keyword list: primary first, then bigrams, then secondary
    keywords = primary_terms + promoted_bigrams + secondary_terms
    # Deduplicate preserving order
    seen: set[str] = set()
    unique_keywords: list[str] = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique_keywords.append(kw)

    # Label: prefer primary terms; fall back to any available terms
    label_parts = primary_terms if primary_terms else secondary_terms
    if not label_parts and unique_keywords:
        label_parts = unique_keywords[:3]

    label = " / ".join(label_parts[:3]) if label_parts else "cluster"
    return label, unique_keywords[:10]


def _recursive_cluster(
    vectors: csr_matrix,
    doc_ids: list[str],
    vocab: list[str],
    all_tokenized: list[list[str]],
    doc_indices: list[int],
    depth: int,
    path: str,
    rng: np.random.RandomState,
    doc_map: dict,
    kw_map: dict,
    project_id: str,
) -> dict:
    """Recursively partition doc_indices into a tree of topic nodes."""
    n = len(doc_indices)
    node_id = f"topic-{path}"

    label, keywords = _label_cluster(vectors, vocab, doc_indices, all_tokenized)
    all_doc_ids = [doc_ids[i] for i in doc_indices]

    # Base cases: leaf node
    if n <= MIN_CLUSTER_SIZE or depth >= MAX_DEPTH:
        node = {
            "id": node_id,
            "name": label,
            "entity_type": "document_source",
            "doc_ids": all_doc_ids,
            "count": n,
            "children": [],
            "keywords": keywords,
        }
        doc_map[node_id] = all_doc_ids
        kw_map[node_id] = keywords
        return node

    # Determine k
    k = max(2, min(5, n // 2))
    sub_matrix = vectors[doc_indices]
    assignments = kmeans(sub_matrix, k=k, rng=rng)

    # Check for degenerate split (all docs in one cluster)
    unique_clusters = set(assignments)
    if len(unique_clusters) <= 1:
        node = {
            "id": node_id,
            "name": label,
            "entity_type": "document_source",
            "doc_ids": all_doc_ids,
            "count": n,
            "children": [],
            "keywords": keywords,
        }
        doc_map[node_id] = all_doc_ids
        kw_map[node_id] = keywords
        return node

    # Build children recursively
    children = []
    for cluster_label_idx, cluster_id in enumerate(sorted(unique_clusters)):
        mask = assignments == cluster_id
        child_local_indices = np.where(mask)[0].tolist()
        child_global_indices = [doc_indices[i] for i in child_local_indices]
        if not child_global_indices:
            continue
        child_path = f"{path}-{cluster_label_idx}" if path != "root" else str(cluster_label_idx)
        child_node = _recursive_cluster(
            vectors=vectors,
            doc_ids=doc_ids,
            vocab=vocab,
            all_tokenized=all_tokenized,
            doc_indices=child_global_indices,
            depth=depth + 1,
            path=child_path,
            rng=rng,
            doc_map=doc_map,
            kw_map=kw_map,
            project_id=project_id,
        )
        children.append(child_node)

    node = {
        "id": node_id,
        "name": label,
        "entity_type": "topic",
        "doc_ids": all_doc_ids,
        "count": n,
        "children": children,
        "keywords": keywords,
    }
    doc_map[node_id] = all_doc_ids
    kw_map[node_id] = keywords
    return node


def cluster_documents(
    documents: list[tuple[str, str]],
    project_id: str,
) -> tuple[dict | None, dict, dict]:
    """Entry point for recursive document clustering.

    Returns (tree_node, doc_map, kw_map).
    doc_map = {project_id: {node_id: [doc_ids]}}
    kw_map  = {project_id: {node_id: [keywords]}}
    """
    doc_map_inner: dict[str, list[str]] = {}
    kw_map_inner: dict[str, list[str]] = {}
    doc_map = {project_id: doc_map_inner}
    kw_map = {project_id: kw_map_inner}

    # Edge case: empty
    if not documents:
        return None, doc_map, kw_map

    # Edge case: single document
    if len(documents) == 1:
        doc_id, text = documents[0]
        tokens = _tokenize(text)
        label = " / ".join(tokens[:3]) if tokens else doc_id
        node = {
            "id": "topic-root",
            "name": label,
            "entity_type": "document_source",
            "doc_ids": [doc_id],
            "count": 1,
            "children": [],
            "keywords": tokens[:10],
        }
        doc_map_inner["topic-root"] = [doc_id]
        kw_map_inner["topic-root"] = tokens[:10]
        return node, doc_map, kw_map

    # Build TF-IDF
    vectors, doc_ids, vocab = build_tfidf(documents)

    # Edge case: no vocabulary
    if not vocab:
        all_doc_ids = [d[0] for d in documents]
        node = {
            "id": "topic-root",
            "name": "documents",
            "entity_type": "topic",
            "doc_ids": all_doc_ids,
            "count": len(all_doc_ids),
            "children": [],
            "keywords": [],
        }
        doc_map_inner["topic-root"] = all_doc_ids
        kw_map_inner["topic-root"] = []
        return node, doc_map, kw_map

    all_tokenized = [_tokenize(text) for _, text in documents]
    doc_indices = list(range(len(doc_ids)))

    rng = np.random.RandomState(hash(project_id) % (2 ** 31))

    tree = _recursive_cluster(
        vectors=vectors,
        doc_ids=doc_ids,
        vocab=vocab,
        all_tokenized=all_tokenized,
        doc_indices=doc_indices,
        depth=0,
        path="root",
        rng=rng,
        doc_map=doc_map_inner,
        kw_map=kw_map_inner,
        project_id=project_id,
    )

    return tree, doc_map, kw_map
