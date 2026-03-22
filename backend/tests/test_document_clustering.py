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


from intel_platform.services.document_clustering import kmeans


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
