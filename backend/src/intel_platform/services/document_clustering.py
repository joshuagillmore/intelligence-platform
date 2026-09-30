"""Document clustering via TF-IDF + recursive K-Means, with optional semantic clustering.

Pure algorithms — no Neo4j or FastAPI dependency.
Uses scipy.sparse and numpy (already available via spaCy).
Semantic clustering uses the platform's embedding providers + scipy agglomerative.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
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

    # Filter vocabulary. Prefer terms shared by >= 2 docs and not in almost
    # every doc (pure stopword-like terms) — a term unique to a single
    # document (df=1) gets the maximum possible IDF weight and, if kept
    # unconditionally, can swamp a cluster's genuinely discriminating shared
    # terms with per-document noise (see test_kmeans_two_clusters).
    #
    # Only fall back to allowing df=1 terms when the stricter df>=2 filter
    # would leave some document with *no* surviving vocabulary at all (an
    # all-zero TF-IDF row) — that full collapse is the failure mode
    # test_cluster_documents_produces_multiple_topics guards against, and it
    # genuinely requires the unique per-document terms to have any signal.
    max_df = max(2, int(0.85 * n_docs))
    valid = {t for t in vocab if 2 <= df[t] <= max_df}
    docs_covered = all(any(t in valid for t in set(tokens)) for tokens in tokenized if tokens)
    if not valid or not docs_covered:
        valid = {t for t in vocab if df[t] <= max_df}

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

MIN_CLUSTER_SIZE = 2
MAX_DEPTH = 8


def _project_seed(project_id: str) -> int:
    """A k-means seed that is the same for a project in every process.

    ``hash(project_id)`` is salted per process (PYTHONHASHSEED), so a restart
    reshuffled a project's topic tree — different clusters, different node ids.
    """
    return int.from_bytes(hashlib.sha256(project_id.encode("utf-8")).digest()[:4], "big") % (2 ** 31)


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

    # Base cases: leaf topic node (no further splitting)
    if n <= MIN_CLUSTER_SIZE or depth >= MAX_DEPTH:
        node = {
            "id": node_id,
            "name": label,
            "entity_type": "topic",
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
            "entity_type": "topic",
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


_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+')


def _chunk_into_sections(text: str, min_chunks: int = 4, target_size: int = 800) -> list[str]:
    """Split a document into sections for sub-document topic clustering.

    Strategy: paragraph boundaries first, then sentence splitting for
    oversized chunks, then further splitting if we have too few chunks.
    """
    if len(text) < 500:
        return [text]

    # Step 1: Split on double-newlines (paragraph boundaries)
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]

    # Step 2: Merge small adjacent paragraphs to reach ~target_size
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if current and len(current) + len(para) > target_size:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        chunks.append(current)

    # Step 3: Split oversized chunks at sentence boundaries
    split_chunks: list[str] = []
    for chunk in chunks:
        if len(chunk) <= target_size * 1.5:
            split_chunks.append(chunk)
            continue
        sentences = _SENTENCE_RE.split(chunk)
        buf = ""
        for sent in sentences:
            if buf and len(buf) + len(sent) > target_size:
                split_chunks.append(buf)
                buf = sent
            else:
                buf = f"{buf} {sent}" if buf else sent
        if buf:
            split_chunks.append(buf)

    # Step 4: If too few chunks, split the longest ones further
    while len(split_chunks) < min_chunks:
        longest_idx = max(range(len(split_chunks)), key=lambda i: len(split_chunks[i]))
        longest = split_chunks[longest_idx]
        if len(longest) < 200:
            break  # too short to split further
        mid = len(longest) // 2
        # Find nearest sentence or newline boundary near the midpoint
        best_split = mid
        for offset in range(min(200, mid)):
            for pos in (mid + offset, mid - offset):
                if 0 < pos < len(longest) and longest[pos - 1] in '.!?\n':
                    best_split = pos
                    break
            else:
                continue
            break
        split_chunks[longest_idx:longest_idx + 1] = [
            longest[:best_split].strip(),
            longest[best_split:].strip(),
        ]
        split_chunks = [c for c in split_chunks if c]

    return split_chunks if len(split_chunks) >= 2 else [text]


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

    # Single document: chunk into sections and cluster those
    if len(documents) == 1:
        doc_id, text = documents[0]
        sections = _chunk_into_sections(text)

        if len(sections) < 2:
            # Too short to section — produce a single leaf node
            tokens = _tokenize(text)
            label = " / ".join(tokens[:3]) if tokens else doc_id
            node = {
                "id": "topic-root",
                "name": label,
                "entity_type": "topic",
                "doc_ids": [doc_id],
                "count": 1,
                "children": [],
                "keywords": tokens[:10],
            }
            doc_map_inner["topic-root"] = [doc_id]
            kw_map_inner["topic-root"] = tokens[:10]
            return node, doc_map, kw_map

        # Create synthetic section pairs for clustering
        section_pairs = [(f"{doc_id}__s{i}", sec) for i, sec in enumerate(sections)]

        vectors, sec_ids, vocab = build_tfidf(section_pairs)
        if not vocab:
            tokens = _tokenize(text)
            label = " / ".join(tokens[:3]) if tokens else doc_id
            node = {
                "id": "topic-root",
                "name": label,
                "entity_type": "topic",
                "doc_ids": [doc_id],
                "count": 1,
                "children": [],
                "keywords": tokens[:10],
            }
            doc_map_inner["topic-root"] = [doc_id]
            kw_map_inner["topic-root"] = tokens[:10]
            return node, doc_map, kw_map

        all_tokenized = [_tokenize(sec) for _, sec in section_pairs]
        rng = np.random.RandomState(_project_seed(project_id))

        tree = _recursive_cluster(
            vectors=vectors,
            doc_ids=sec_ids,
            vocab=vocab,
            all_tokenized=all_tokenized,
            doc_indices=list(range(len(sec_ids))),
            depth=0,
            path="root",
            rng=rng,
            doc_map=doc_map_inner,
            kw_map=kw_map_inner,
            project_id=project_id,
        )

        # Post-process: replace section chunk IDs with the real doc_id
        # so that get_topic_context() can resolve to the actual document.
        def _fix_doc_ids(node: dict) -> None:
            node["doc_ids"] = [doc_id]
            node["count"] = 1
            for child in node.get("children", []):
                _fix_doc_ids(child)

        _fix_doc_ids(tree)

        # Also fix the doc_map cache entries
        for node_id in list(doc_map_inner.keys()):
            doc_map_inner[node_id] = [doc_id]

        return tree, doc_map, kw_map

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

    rng = np.random.RandomState(_project_seed(project_id))

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


# ---------------------------------------------------------------------------
# Semantic (embedding-based) clustering
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# Granularity presets: (max_clusters_per_level, max_depth)
GRANULARITY_PRESETS = {
    "broad": (5, 2),
    "medium": (12, 4),
    "detailed": (30, 6),
}


# Texts per embedding call. Cohere caps a call at 96 texts; sending a whole
# corpus in one call failed there and dropped the tree to TF-IDF.
_EMBED_BATCH_SIZE = 96

# The group size a node aims to split into. Splitting into n // 2 groups leaves
# pairs at the first level with no room beneath them; aiming for ~4 members
# keeps a level to deepen into, capped by the preset's clusters-per-level.
_SEMANTIC_TARGET_GROUP = 4


async def _tfidf_fallback(
    documents: list[tuple[str, str]], project_id: str, reason: str,
) -> tuple[dict | None, dict, dict]:
    """The TF-IDF tree, marked as what it is.

    Without the marker a failed semantic build was indistinguishable from a
    successful one: same shape, keyword labels, no hint that the embedder never
    ran. ``fallback_reason`` names the failure without exception text.
    """
    logger.warning("Semantic clustering unavailable (%s) — falling back to TF-IDF", reason)
    tree, doc_map, kw_map = await asyncio.to_thread(cluster_documents, documents, project_id)
    if tree is not None:
        tree["fallback"] = "tfidf"
        tree["fallback_reason"] = reason
    return tree, doc_map, kw_map


async def cluster_semantic(
    documents: list[tuple[str, str]],
    project_id: str,
    granularity: str = "medium",
) -> tuple[dict | None, dict, dict]:
    """Cluster documents using dense embeddings + agglomerative hierarchy.

    Uses the platform's EmbeddingProvider to generate vectors (in batches of
    96), then recursive Ward linkage for a deterministic hierarchy whose depth
    follows the granularity preset. Linkage and TF-IDF run in a worker thread.
    Falls back to TF-IDF clustering if embedding fails, and marks the tree
    ``fallback: "tfidf"`` when it does.

    Returns (tree_node, doc_map, kw_map) — same interface as cluster_documents().
    """
    doc_map_inner: dict[str, list[str]] = {}
    kw_map_inner: dict[str, list[str]] = {}
    doc_map = {project_id: doc_map_inner}
    kw_map = {project_id: kw_map_inner}

    if not documents:
        return None, doc_map, kw_map

    # Get embedding provider
    try:
        from intel_platform.llm.embeddings import get_embedding_provider
        provider = get_embedding_provider()
    except Exception:
        logger.warning("No embedding provider for semantic clustering", exc_info=True)
        return await _tfidf_fallback(documents, project_id, "no embedding provider")

    # Embed all documents
    texts = [text for _, text in documents]
    doc_ids = [did for did, _ in documents]

    try:
        # Truncate texts to avoid token limits (embedding models typically cap at 512 tokens)
        truncated = [t[:2000] for t in texts]
        vectors: list[list[float]] = []
        for i in range(0, len(truncated), _EMBED_BATCH_SIZE):
            result = await provider.embed(truncated[i:i + _EMBED_BATCH_SIZE], input_type="search_document")
            vectors.extend(result.embeddings)
    except Exception:
        logger.warning("Embedding failed during semantic clustering", exc_info=True)
        return await _tfidf_fallback(documents, project_id, "embedding failed")

    if len(vectors) != len(documents) or len({len(v) for v in vectors}) > 1:
        return await _tfidf_fallback(
            documents, project_id,
            f"embedding returned {len(vectors)} usable vectors for {len(documents)} documents",
        )
    embeddings = np.array(vectors, dtype=float)

    if len(embeddings) < 2:
        # Single doc — delegate to TF-IDF which handles single-doc chunking.
        # By design, not a failure, so no fallback marker.
        return await asyncio.to_thread(cluster_documents, documents, project_id)

    max_k, max_depth = GRANULARITY_PRESETS.get(granularity, GRANULARITY_PRESETS["medium"])

    def _build() -> dict:
        # TF-IDF for keyword labeling (reuse existing infrastructure).
        tfidf_vectors, _, vocab = build_tfidf(documents)
        all_tokenized = [_tokenize(text) for _, text in documents]
        return _build_semantic_tree(
            embeddings=embeddings,
            doc_ids=doc_ids,
            tfidf_vectors=tfidf_vectors,
            vocab=vocab,
            all_tokenized=all_tokenized,
            doc_map=doc_map_inner,
            kw_map=kw_map_inner,
            max_k=max_k,
            max_depth=max_depth,
        )

    # Ward linkage is O(n^2) and TF-IDF tokenises the corpus; neither belongs
    # on the event loop that also serves /health and every agentic run.
    root = await asyncio.to_thread(_build)
    return root, doc_map, kw_map


def _ward_groups(embeddings: np.ndarray, indices: list[int], k: int) -> list[list[int]]:
    """Split ``indices`` into at most ``k`` groups by Ward linkage on their vectors."""
    from scipy.cluster.hierarchy import fcluster, linkage

    z = linkage(embeddings[indices], method="ward")
    assignments = fcluster(z, t=k, criterion="maxclust")
    groups: dict[int, list[int]] = {}
    for idx, cluster_id in zip(indices, assignments):
        groups.setdefault(int(cluster_id), []).append(idx)
    # In document order (each group's first member), not dendrogram order.
    return sorted(groups.values(), key=lambda g: g[0])


def _build_semantic_tree(
    embeddings: np.ndarray,
    doc_ids: list[str],
    tfidf_vectors,
    vocab: list[str],
    all_tokenized: list[list[str]],
    doc_map: dict,
    kw_map: dict,
    max_k: int,
    max_depth: int,
    depth: int = 0,
    indices: list[int] | None = None,
) -> dict:
    """Recursively build a topic tree by re-clustering each node's members.

    Each node's own documents are clustered again (Ward linkage on their
    embeddings) into up to ``max_k`` groups of about ``_SEMANTIC_TARGET_GROUP``,
    down to ``max_depth``. The previous approach cut one dendrogram at a fixed
    ``k`` per level; once ``n // level`` exceeded ``max_k`` every level was the
    same cut, so no preset ever produced a tree deeper than two levels.
    """
    if indices is None:
        indices = list(range(len(doc_ids)))

    node_id = f"topic-sem-{depth}-{'_'.join(str(i) for i in indices[:3])}"

    # Label this node using TF-IDF keywords
    label, keywords = _label_cluster(tfidf_vectors, vocab, indices, all_tokenized) if vocab else ("documents", [])
    current_doc_ids = [doc_ids[i] for i in indices]

    doc_map[node_id] = current_doc_ids
    kw_map[node_id] = keywords

    leaf = {
        "id": node_id,
        "name": label,
        "entity_type": "topic",
        "doc_ids": current_doc_ids,
        "count": len(indices),
        "children": [],
        "keywords": keywords,
    }

    # Base case: deep enough, or too few docs to split
    if depth >= max_depth or len(indices) <= MIN_CLUSTER_SIZE:
        return leaf

    k = max(2, min(max_k, math.ceil(len(indices) / _SEMANTIC_TARGET_GROUP)))
    groups = _ward_groups(embeddings, indices, k)
    # Indistinguishable members (identical vectors) do not split.
    if len(groups) <= 1:
        return leaf

    children = [
        _build_semantic_tree(
            embeddings, doc_ids, tfidf_vectors, vocab, all_tokenized,
            doc_map, kw_map, max_k, max_depth, depth + 1, group,
        )
        for group in groups
    ]

    return {
        "id": node_id,
        "name": label,
        "entity_type": "topic",
        "doc_ids": current_doc_ids,
        "count": len(indices),
        "children": children,
        "keywords": keywords,
    }


# ---------------------------------------------------------------------------
# LLM-based topic label refinement
# ---------------------------------------------------------------------------

def _is_rate_limited(exc: Exception) -> bool:
    """Whether a provider refused because of rate limiting.

    Kept provider-agnostic on purpose: each SDK raises its own class
    (cohere.TooManyRequestsError, anthropic.RateLimitError, openai.RateLimitError),
    and importing all of them to catch them would couple this module to every
    provider. The status code and the class name are what they agree on.
    """
    if getattr(exc, "status_code", None) == 429:
        return True
    name = type(exc).__name__.lower()
    if "toomanyrequests" in name or "ratelimit" in name:
        return True
    return "429" in str(exc)[:200]


async def refine_labels_with_llm(
    tree_node: dict,
    doc_pairs: list[tuple[str, str]],
) -> dict:
    """Walk the cluster tree and replace keyword labels with LLM-generated names.

    Falls back to existing keyword labels if no LLM provider is configured.
    Returns the tree with refined labels (mutated in place). Each node's
    refine only touches that node's own dict entries, so the per-node LLM
    calls run concurrently (Semaphore-gated) instead of one at a time.
    """
    # Shared provider selection: topics_llm_provider / the admin's runtime
    # choice, then a cloud key from the key store or env. Returns None when no
    # cloud key is configured, in which case we keep the existing keyword
    # labels rather than refine.
    from intel_platform.llm.providers import _get_topics_provider

    # Honours topics_llm_provider, so a deployment whose cloud key is
    # rate-limited can point refinement at local Ollama instead of silently
    # serving keyword labels. Returns None when neither is available.
    provider = await _get_topics_provider()
    if not provider:
        # Keyword labels are a legitimate result, but they must be
        # distinguishable from refined ones: an analyst reading "vessel cable
        # baltic" as a topic name should be able to tell that is what the
        # keywords say, not what a model concluded.
        logger.info("No topics provider configured; keeping keyword topic labels")
        tree_node["label_source"] = "keywords"
        return tree_node

    from intel_platform.llm.skills.loader import SkillsLoader
    loader = SkillsLoader()
    system = loader.get_system_prompt("topic_naming", include_foundation=True) or ""

    # Build a lookup of doc_id -> text for excerpt extraction
    doc_text_map = {doc_id: text for doc_id, text in doc_pairs}

    # Bound concurrent LLM round-trips so a "detailed" tree with dozens of
    # nodes doesn't fan out unbounded requests against a rate-limited provider.
    sem = asyncio.Semaphore(5)
    refined: list[str] = []
    failed: list[str] = []
    rate_limited = False

    async def _refine_node(node: dict) -> None:
        nonlocal rate_limited
        """Refine a single node's label via LLM. Only mutates this node."""
        if node.get("entity_type") != "topic":
            return

        keywords = node.get("keywords", [])
        doc_ids = node.get("doc_ids", [])

        if not keywords and not doc_ids:
            return

        # Build excerpts from up to 5 representative documents
        excerpts: list[str] = []
        for did in doc_ids[:5]:
            text = doc_text_map.get(did, "")
            if text:
                excerpts.append(text[:500])

        prompt_parts = []
        if keywords:
            prompt_parts.append(f"Keywords: {', '.join(keywords)}")
        if excerpts:
            prompt_parts.append("Document excerpts:\n" + "\n---\n".join(excerpts))

        user_msg = "\n\n".join(prompt_parts)

        try:
            async with sem:
                # Checked here, after acquiring the semaphore, rather than on
                # entry: asyncio.gather starts every coroutine at once, so they
                # would all pass an entry check before the first refusal came
                # back. Waiting for a slot is what puts them behind it — of 31
                # nodes, an entry check skipped 3 and this skips the rest.
                #
                # The provider has already refused; the remaining nodes will be
                # refused too. Measured on a Cohere trial key (20 calls/minute
                # against a 31-node tree): every call returned 429 and the
                # endpoint spent 19.3s of a 20.6s response failing.
                if rate_limited:
                    failed.append(node.get("id"))
                    return
                result = await provider.generate(
                    messages=[{"role": "user", "content": user_msg}],
                    system=system,
                    temperature=0.2,
                    max_tokens=256,
                )
            # The first JSON object in the reply, however it is presented
            # (fenced, after a sentence, behind a bold label). `{}` = none.
            from intel_platform.services.llm_output import json_object

            data = json_object(result.content or "")
            llm_name = data.get("topic_name") if data else None
            if not isinstance(llm_name, str) or not llm_name.strip():
                # No name is not a refinement. Counting it as one let a tree of
                # keyword labels report label_source "llm".
                logger.warning("Topic label refinement for node %s returned no topic_name", node.get("id"))
                failed.append(node.get("id"))
                return
            llm_name = llm_name.strip()
            node["llm_label"] = llm_name
            node["name"] = llm_name
            llm_summary = data.get("summary")
            if isinstance(llm_summary, str) and llm_summary.strip():
                node["summary"] = llm_summary.strip()
            refined.append(node.get("id"))
        except Exception as exc:
            # Keep the keyword label, but say so — a swallowed exception here
            # produced a tree indistinguishable from a successfully refined one.
            if _is_rate_limited(exc):
                if not rate_limited:
                    logger.warning(
                        "LLM provider rate-limited; abandoning topic label refinement "
                        "for the rest of the tree and keeping keyword labels"
                    )
                rate_limited = True
            else:
                logger.warning("Topic label refinement failed for node %s", node.get("id"), exc_info=True)
            failed.append(node.get("id"))

    def _flatten(node: dict) -> list[dict]:
        """Collect every node in the tree (pre-order) so refines can run as one batch.

        Mirrors the original sequential walk: a non-"topic" node is included
        (so its no-op refine still runs) but its children are not descended
        into, matching `_refine_node`'s early return for non-topic nodes.
        """
        nodes = [node]
        if node.get("entity_type") == "topic":
            for child in node.get("children", []):
                nodes.extend(_flatten(child))
        return nodes

    await asyncio.gather(*(_refine_node(n) for n in _flatten(tree_node)), return_exceptions=True)

    # What the labels actually are. "partial" is the case worth naming: some
    # nodes carry model labels and others carry keywords, and nothing in the
    # tree itself distinguishes them.
    if failed and refined:
        tree_node["label_source"] = "partial"
    elif failed:
        tree_node["label_source"] = "keywords"
    else:
        tree_node["label_source"] = "llm"
    tree_node["labels_refined"] = len(refined)
    tree_node["labels_failed"] = len(failed)
    if failed:
        logger.warning(
            "Topic labels: %d refined, %d fell back to keywords", len(refined), len(failed)
        )
    return tree_node
