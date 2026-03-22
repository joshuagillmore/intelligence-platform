# Topic Mind Map — Document-Centric Clustering Design

**Date:** 2026-03-22
**Status:** Approved
**Scope:** Data Sources page topic mind map — shift from entity groupings to TF-IDF document clustering, inspired by Overview Docs

---

## Problem

The current topic mind map on the Data Sources page organizes nodes by entity type, category, and graph community detection. This produces a data browser, not a topic explorer. An intelligence analyst exploring their corpus wants to see **what their documents are about** — thematic clusters derived from document content — not how entities are categorized.

## Design Goals

1. Primary tree branch built from **document content clustering** (TF-IDF + recursive K-Means)
2. Each internal node labeled with **distinctive keywords** from its document cluster
3. Selecting a node shows **documents in that cluster** and their associated entities
4. Summary generation is **user-initiated**, not automatic
5. Preserve the current **D3 horizontal mind map** rendering
6. Keep Network Analysis and entity-level interactions **completely separate**

## Non-Goals

- Replacing the Network Analysis page or entity graph
- Adding scikit-learn as a dependency (use scipy/numpy already present)
- Real-time clustering (acceptable to compute on tree load, cached)

---

## Architecture

### Backend — New `_build_topic_branch()` in `TopicTreeService`

#### Step 1: Document Vectorization (TF-IDF)

For each Document entity in the project:
1. Retrieve document content
2. Tokenize: lowercase, split on whitespace/punctuation, remove stopwords (English stopword list)
3. Build term frequency (TF) per document
4. Compute inverse document frequency (IDF) across corpus
5. Produce TF-IDF vector per document

Implementation: Pure Python using `scipy.sparse` for sparse vectors and basic math. No scikit-learn dependency.

#### Step 2: Recursive K-Means Clustering

```
function cluster(doc_ids, vectors, depth=0):
    if len(doc_ids) <= MIN_CLUSTER_SIZE (3) or depth >= MAX_DEPTH (6):
        return leaf_node(doc_ids)

    k = min(5, len(doc_ids) // 2)  # arity capped at 5
    assignments = kmeans(vectors, k, max_iter=20)

    children = []
    for each cluster_group:
        if len(cluster_group) == len(doc_ids):
            return leaf_node(doc_ids)  # no split possible
        child = cluster(cluster_group_ids, cluster_group_vectors, depth+1)
        children.append(child)

    return internal_node(doc_ids, children)
```

K-Means implementation: Use scipy for distance calculations. Initialize centroids with K-Means++ (pick first centroid randomly, subsequent centroids proportional to distance from nearest existing centroid).

#### Step 3: Node Labeling

For each internal node:
1. Sum TF-IDF vectors of all documents in the cluster
2. Extract top terms by weight
3. Filter terms by document frequency within the cluster:
   - **Primary terms**: appear in >=70% of cluster docs (up to 3 terms)
   - **Secondary terms**: next highest weight (up to 2 more terms)
4. Remove unigrams that are substrings of selected bigrams
5. Node label = comma-separated top terms (e.g., "Sanctions, Iran, Oil Exports")

#### Step 4: Tree Assembly

```
root
├── "Cyber Operations, APT Groups" (15 docs)
│   ├── "Phishing, Credential Theft" (7 docs)
│   │   ├── doc: "APT29_Report.pdf"
│   │   ├── doc: "Spearphishing_Analysis.txt"
│   │   └── ...
│   └── "Malware, C2 Infrastructure" (8 docs)
│       └── ...
├── "Sanctions, Trade, Iran" (12 docs)
│   └── ...
└── "Maritime, South China Sea" (6 docs)
    └── ...
```

Leaf nodes are individual documents. Internal nodes carry:
- `id`: unique cluster ID (e.g., `topic-0-2-1`)
- `name`: keyword label
- `entity_type`: `"topic"` for internal nodes, `"document_source"` for leaves
- `doc_ids`: list of all document IDs in this cluster (including children)
- `count`: number of documents
- `children`: child nodes

#### Existing Branches Kept as Secondary

Below the primary Topics branch:
- **Source Documents** — flat list of documents with entity children
- **Geographic Regions** — location entities by region
- **Actors & Organizations** — people/orgs by connectivity

The removed branches (By Entity Type, By Category) stay removed.

### Backend — Updated `get_topic_context()` for Topic Nodes

When a topic cluster node is selected (ID starts with `topic-`):
1. Retrieve all `doc_ids` from that cluster
2. Fetch each Document entity (name, reliability_rating, content preview)
3. Collect entities that appear in those documents (via `source_doc_id` or text search)
4. Return: `{ documents: [...], connected_entities: [...], keywords: [...] }`

### API Changes

No new endpoints. Existing endpoints modified:

- `GET /api/topics?project_id=X` — tree now includes `topic-*` nodes with `doc_ids` field
- `GET /api/topics/{node_id}?project_id=X` — handles `topic-*` IDs by returning cluster documents

---

## Frontend — Data Sources Page

### Mind Map (Top Section)

Rendering unchanged — D3 horizontal collapsible tree.

Interaction changes:
- **Click toggle (+/-)**: expand/collapse only (already fixed)
- **Click node body**: select node, populate bottom panels
- Topic nodes display their keyword label + document count badge
- Document leaf nodes display filename

Color coding:
- Topic cluster nodes: purple (`#a855f7`) — matches current theme branch
- Document nodes: blue (`#3b82f6`) — matches current docs branch
- Geographic nodes: orange (`#f97316`)
- Actor nodes: red (`#ef4444`)

### Left Panel — "Source Documents" (on node selection)

When a **topic node** is selected:
- Header: "Documents in [Topic Keywords]" with count badge
- List of all documents in that cluster (including nested children)
- Each document card shows: name, reliability badge, 200-char content preview
- Clicking a doc navigates to `/documents/{id}`

When a **document leaf node** is selected:
- Header: "Document: [filename]"
- Single document card with full preview
- Connected entities section below (entities extracted from that document)

When a **grouping node** (Geographic, Actors branch header) is selected:
- Existing behavior: "Click a topic node above to view associated documents."

### Right Panel — "Intelligence Summary" (on node selection)

- **Cluster keywords** displayed as tags at the top of the panel
- **"Generate Summary" button** — user-initiated, never auto-triggered
- Summary output area with loading spinner when generating
- Suggested queries scoped to cluster themes
- Custom query input

### No Changes to Other Pages

Network Analysis, Geo-Intelligence, Cyber, etc. remain unchanged. Entity-level interactions (graph, subgraph, island method, watchlist) are unaffected.

---

## Data Flow

```
1. User navigates to Data Sources with active project
2. Frontend calls GET /api/topics?project_id=X
3. Backend TopicTreeService.build_topic_tree():
   a. Fetch all Document entities
   b. Run TF-IDF vectorization on document content
   c. Recursive K-Means clustering (k=5, depth<=6, min_size=3)
   d. Label nodes with top TF-IDF terms
   e. Append secondary branches (docs, geo, actors)
   f. Return tree (cached 60s)
4. Frontend renders D3 mind map
5. User expands topic branch, clicks a cluster node
6. Frontend calls GET /api/topics/topic-0-2?project_id=X
7. Backend returns documents in cluster + connected entities
8. Left panel shows document list, right panel shows keywords + Generate button
9. User clicks "Generate Summary"
10. Frontend calls POST /api/query (Graph RAG) scoped to topic
11. Right panel displays LLM-generated summary
```

---

## Implementation Notes

### TF-IDF Without scikit-learn

```python
from collections import Counter
import math
from scipy.sparse import csr_matrix
import numpy as np

def build_tfidf(documents: list[tuple[str, str]]) -> tuple[csr_matrix, list[str], list[str]]:
    """Build TF-IDF sparse matrix from (doc_id, text) pairs.
    Returns (tfidf_matrix, doc_ids, vocabulary).
    """
    # Tokenize
    STOPWORDS = {"the", "a", "an", "is", "are", "was", ...}  # ~150 English stopwords
    tokenized = []
    for doc_id, text in documents:
        tokens = [w for w in re.findall(r'\b[a-z]{2,}\b', text.lower()) if w not in STOPWORDS]
        tokenized.append(tokens)

    # Build vocabulary
    vocab = {}
    df = Counter()  # document frequency
    for tokens in tokenized:
        unique = set(tokens)
        for t in unique:
            df[t] += 1
            if t not in vocab:
                vocab[t] = len(vocab)

    # Filter: keep terms in 2+ docs but <90% of docs
    n_docs = len(documents)
    valid_terms = {t: i for t, i in vocab.items() if 2 <= df[t] <= 0.9 * n_docs}
    # Re-index
    final_vocab = {}
    for t in sorted(valid_terms.keys()):
        final_vocab[t] = len(final_vocab)

    # Build sparse TF-IDF matrix
    idf = {t: math.log(n_docs / df[t]) for t in final_vocab}
    rows, cols, data = [], [], []
    for i, tokens in enumerate(tokenized):
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
    matrix = matrix.multiply(1 / norms[:, np.newaxis])

    return matrix, [d[0] for d in documents], list(final_vocab.keys())
```

### K-Means With K-Means++ Init

```python
def kmeans(vectors: csr_matrix, k: int, max_iter: int = 20):
    """Simple K-Means on sparse TF-IDF vectors."""
    n = vectors.shape[0]
    # K-Means++ initialization
    centroids = [vectors[np.random.randint(n)].toarray().flatten()]
    for _ in range(k - 1):
        dists = np.array([min(cosine_dist(vectors[i], c) for c in centroids) for i in range(n)])
        probs = dists / dists.sum()
        next_idx = np.random.choice(n, p=probs)
        centroids.append(vectors[next_idx].toarray().flatten())
    centroids = np.array(centroids)

    for _ in range(max_iter):
        # Assign
        sims = vectors.dot(centroids.T)  # cosine similarity (vectors are L2-normed)
        assignments = sims.argmax(axis=1).A1
        # Update
        new_centroids = np.zeros_like(centroids)
        for j in range(k):
            mask = assignments == j
            if mask.any():
                new_centroids[j] = vectors[mask].mean(axis=0).A1
        if np.allclose(centroids, new_centroids, atol=1e-6):
            break
        centroids = new_centroids

    return assignments
```

### Caching

The topic tree involves TF-IDF computation across all documents. Cache the tree response for 60 seconds (increase the existing 30s cache). Invalidation happens naturally as the cache expires.

### Performance Budget

- Documents: up to 100 documents per project (typical)
- TF-IDF: O(n * v) where v = vocabulary size (~5000 terms) — sub-second
- K-Means: O(n * k * v * iterations) — sub-second for n<100
- Total tree build: <3 seconds for 100 documents

---

## Files Modified

### Backend
- `backend/src/intel_platform/services/topics.py` — add `_build_topic_branch()`, `_tfidf_vectorize()`, `_recursive_kmeans()`, `_label_cluster()` methods; update `build_topic_tree()` to use topic branch as primary; update `get_topic_context()` for topic-* nodes
- `backend/src/intel_platform/services/graph_rag.py` — no changes needed (already fixed)

### Frontend
- `frontend/src/app/data-sources/page.tsx` — handle `topic-*` node selection, display cluster keywords as tags, no other structural changes needed (Generate Summary button already added)
- `frontend/src/components/TopicMindMap.tsx` — no changes needed (expand/select separation already fixed)

### No New Files
All changes fit within existing files.

---

## Testing

- Unit test: TF-IDF vectorization with known documents produces expected term weights
- Unit test: K-Means on 2 clearly separable clusters produces correct assignments
- Unit test: Cluster labeling picks the most distinctive terms
- Integration test: `/api/topics` returns tree with `topic-*` nodes containing `doc_ids`
- Integration test: `/api/topics/topic-0` returns documents from that cluster
- Manual test: Ingest 3+ documents on different topics, verify tree shows meaningful clusters
