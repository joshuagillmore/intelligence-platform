"""Corroboration and contradiction on relationship merge.

Exercises GraphStore.create_relationship against the live Neo4j the suite
already requires, since the behaviour lives in Cypher.
"""
import uuid

import pytest

from intel_platform.models.entities import Organization
from intel_platform.models.relationships import Relationship


@pytest.fixture
def pair(graph_store):
    pid = f"test-conflict-{uuid.uuid4().hex[:8]}"
    a = Organization(name="Actor A", project_id=pid)
    b = Organization(name="Vessel B", project_id=pid)
    graph_store.create_entity(a)
    graph_store.create_entity(b)
    yield pid, a, b


def _edge(store, a, b):
    rels = store.get_relationships(a.id)
    return next((r for r in rels if r.get("target_id") == b.id), None)


def test_second_source_corroborates_rather_than_duplicating(graph_store, pair):
    _pid, a, b = pair
    for doc in ("doc-1", "doc-2"):
        graph_store.create_relationship(Relationship(
            source_id=a.id, target_id=b.id, rel_type="TARGETS",
            confidence=0.8, evidence="claimed responsibility", source_doc_id=doc,
        ))
    rels = [r for r in graph_store.get_relationships(a.id) if r.get("target_id") == b.id]
    assert len(rels) == 1, "the same claim from two documents must be one edge"
    assert rels[0]["corroboration_count"] == 2
    assert len(rels[0]["corroboration_sources"]) == 2


def test_same_document_twice_is_still_one_source(graph_store, pair):
    _pid, a, b = pair
    for _ in range(2):
        graph_store.create_relationship(Relationship(
            source_id=a.id, target_id=b.id, rel_type="TARGETS",
            confidence=0.8, source_doc_id="doc-1",
        ))
    edge = _edge(graph_store, a, b)
    assert edge["corroboration_count"] == 1, "two mentions in one document is one source"


def test_a_denial_sets_conflict(graph_store, pair):
    _pid, a, b = pair
    graph_store.create_relationship(Relationship(
        source_id=a.id, target_id=b.id, rel_type="TARGETS",
        confidence=0.9, source_doc_id="doc-1", polarity="asserts",
    ))
    graph_store.create_relationship(Relationship(
        source_id=a.id, target_id=b.id, rel_type="TARGETS",
        confidence=0.7, source_doc_id="doc-2", polarity="denies",
    ))
    edge = _edge(graph_store, a, b)
    assert edge["corroboration_agreement"] == "CONFLICT"
    # Disputed reporting must not inherit the stronger confidence.
    assert edge["confidence"] == pytest.approx(0.7)


def test_conflict_is_sticky_once_disputed(graph_store, pair):
    _pid, a, b = pair
    for doc, pol in (("d1", "asserts"), ("d2", "denies"), ("d3", "asserts")):
        graph_store.create_relationship(Relationship(
            source_id=a.id, target_id=b.id, rel_type="TARGETS",
            confidence=0.8, source_doc_id=doc, polarity=pol,
        ))
    edge = _edge(graph_store, a, b)
    assert edge["corroboration_agreement"] == "CONFLICT", "a later agreeing source must not erase the dispute"
    # Two sources agree, one contradicts. This asserted 3 — the denial counted
    # as corroboration — which was the defect itself (review G-13).
    assert edge["corroboration_count"] == 2
    assert edge["contradicting_sources"] == ["d2"]


# ── Review G-13: a denial is not corroboration, and later evidence is kept ──

def test_a_denial_is_not_counted_as_corroboration(graph_store, pair):
    _pid, a, b = pair
    graph_store.create_relationship(Relationship(
        source_id=a.id, target_id=b.id, rel_type="TARGETS",
        confidence=0.9, source_doc_id="doc-1", polarity="asserts",
    ))
    graph_store.create_relationship(Relationship(
        source_id=a.id, target_id=b.id, rel_type="TARGETS",
        confidence=0.7, source_doc_id="doc-2", polarity="denies",
    ))
    edge = _edge(graph_store, a, b)
    assert edge["corroboration_count"] == 1
    assert edge["corroboration_sources"] == ["doc-1"]
    assert edge["contradicting_sources"] == ["doc-2"]


def test_a_second_denial_from_the_same_source_is_recorded_once(graph_store, pair):
    _pid, a, b = pair
    graph_store.create_relationship(Relationship(
        source_id=a.id, target_id=b.id, rel_type="TARGETS", source_doc_id="doc-1",
    ))
    for _ in range(2):
        graph_store.create_relationship(Relationship(
            source_id=a.id, target_id=b.id, rel_type="TARGETS", source_doc_id="doc-2", polarity="denies",
        ))
    assert _edge(graph_store, a, b)["contradicting_sources"] == ["doc-2"]


def test_every_distinct_evidence_sentence_is_kept(graph_store, pair):
    """Only the first sentence survived a merge; a second source's own wording
    — often the more specific one — was discarded."""
    _pid, a, b = pair
    for doc, sentence in (("doc-1", "Actor A struck Vessel B."),
                          ("doc-2", "Vessel B was boarded by Actor A's unit off Gotland."),
                          ("doc-3", "Actor A struck Vessel B.")):
        graph_store.create_relationship(Relationship(
            source_id=a.id, target_id=b.id, rel_type="TARGETS", source_doc_id=doc, evidence=sentence,
        ))
    edge = _edge(graph_store, a, b)
    assert edge["evidence"] == "Actor A struck Vessel B.", "the first sentence stays the primary reference"
    assert edge["evidence_all"] == [
        "Actor A struck Vessel B.",
        "Vessel B was boarded by Actor A's unit off Gotland.",
    ]
