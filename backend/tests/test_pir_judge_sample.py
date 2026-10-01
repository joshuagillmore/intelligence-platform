"""R-11: the PIR judge samples the entities the collection says most about.

`search_entities` orders by name, and the judge took its first 600. On a large
project that is crawl furniture and names starting with digits; the
ThreatActors and Campaigns sat past the cut and the requirement read as
unanswered. The sample is now ranked substantive-first, then by degree.

Runs against the suite's Neo4j, since the ranking lives in Cypher.
"""
from __future__ import annotations

import uuid

import pytest

from intel_platform.services.pir_judge.evidence import _ranked_entities
from intel_platform.models.entities import URL, Document, Organization, Person, ThreatActor
from intel_platform.models.relationships import Relationship
from tests.ids import tp


@pytest.fixture
def project(graph_store):
    pid = tp(f"judge-{uuid.uuid4().hex[:8]}")
    # Alphabetically first, and worth nothing to a judge.
    url = URL(name="000-cdn.example/asset.js", project_id=pid)
    doc = Document(name="AAA crawled page", content="x" * 5000, project_id=pid)
    # Substantive, alphabetically last, and the most connected.
    actor = ThreatActor(name="Zeta Group", project_id=pid)
    org = Organization(name="Beta Utility", project_id=pid)
    person = Person(name="Alpha Person", project_id=pid)
    for e in (url, doc, actor, org, person):
        graph_store.create_entity(e)
    for target in (org, person):
        graph_store.create_relationship(Relationship(
            source_id=actor.id, target_id=target.id, rel_type="TARGETS", confidence=0.8,
        ))
    # The URL is well connected too; being furniture must outweigh degree.
    # Degrees: Zeta 3, Beta 2, Alpha 1, URL 2, Document 0.
    for target in (actor, org):
        graph_store.create_relationship(Relationship(
            source_id=url.id, target_id=target.id, rel_type="MENTIONS", confidence=0.5,
        ))
    return pid


def test_substantive_entities_come_first_by_degree(graph_store, project):
    ranked, total = _ranked_entities(graph_store, project, 3)
    assert [e["name"] for e in ranked] == ["Zeta Group", "Beta Utility", "Alpha Person"]
    assert total == 5


def test_furniture_is_ranked_last_not_dropped(graph_store, project):
    ranked, _ = _ranked_entities(graph_store, project, 10)
    assert {e["entity_type"] for e in ranked[-2:]} == {"URL", "Document"}


def test_no_document_content_is_carried(graph_store, project):
    ranked, _ = _ranked_entities(graph_store, project, 10)
    assert all("content" not in e for e in ranked)
    assert {"id", "name", "entity_type", "date_text", "date_precision"} <= set(ranked[0])


def test_an_empty_project_is_empty_with_zero_total(graph_store):
    assert _ranked_entities(graph_store, tp(f"judge-empty-{uuid.uuid4().hex[:6]}"), 10) == ([], 0)
