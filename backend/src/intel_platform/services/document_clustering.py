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
