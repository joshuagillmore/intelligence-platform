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
    assert edge["corroboration_count"] == 3
