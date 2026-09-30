"""A relationship knows its project (contract 16).

`create_relationship` looked both endpoints up by id alone, with no label and
no project, so nothing stopped an edge joining two projects, and the cache
invalidation needed another lookup to find out which project it touched.
`Relationship.project_id` lets the store match both endpoints inside the
project and stamp the edge with it.
"""
from __future__ import annotations

from intel_platform.models.entities import Organization, Person
from intel_platform.models.relationships import Relationship
from intel_platform.services.graph_builder import build_graph_from_extractions

P1 = "test-relproj-1"
P2 = "test-relproj-2"


def test_the_model_carries_a_project_defaulting_to_empty():
    rel = Relationship(source_id="a", target_id="b", rel_type="TARGETS")
    assert rel.project_id == ""
    assert Relationship(source_id="a", target_id="b", rel_type="TARGETS", project_id=P1).project_id == P1


def test_an_edge_inside_the_project_is_created_and_stamped(graph_store):
    a = Person(name="Ilse Varga", project_id=P1)
    b = Organization(name="Norrholm Logistics", project_id=P1)
    graph_store.create_entity(a)
    graph_store.create_entity(b)
    created = graph_store.create_relationship(Relationship(
        source_id=a.id, target_id=b.id, rel_type="BELONGS_TO", project_id=P1,
    ))
    assert created, "the edge was not created"
    (rel,) = graph_store.get_relationships(a.id)
    assert rel["project_id"] == P1


def test_an_endpoint_in_another_project_is_refused(graph_store):
    mine = Person(name="Ilse Varga", project_id=P1)
    theirs = Organization(name="Norrholm Logistics", project_id=P2)
    graph_store.create_entity(mine)
    graph_store.create_entity(theirs)
    created = graph_store.create_relationship(Relationship(
        source_id=mine.id, target_id=theirs.id, rel_type="BELONGS_TO", project_id=P1,
    ))
    assert created == {}
    assert graph_store.get_relationships(mine.id) == []


def test_without_a_project_the_edge_is_not_stamped(graph_store):
    """Callers that have not been updated keep working exactly as before."""
    a = Person(name="Ilse Varga", project_id=P1)
    b = Organization(name="Norrholm Logistics", project_id=P1)
    graph_store.create_entity(a)
    graph_store.create_entity(b)
    assert graph_store.create_relationship(Relationship(source_id=a.id, target_id=b.id, rel_type="BELONGS_TO"))
    (rel,) = graph_store.get_relationships(a.id)
    assert "project_id" not in rel


def test_the_graph_builder_passes_its_project(graph_store):
    build_graph_from_extractions(
        graph_store,
        [{"name": "Ilse Varga", "entity_type": "Person"},
         {"name": "Norrholm Logistics", "entity_type": "Organization"}],
        [{"source_name": "Ilse Varga", "target_name": "Norrholm Logistics", "rel_type": "BELONGS_TO",
          "confidence": 0.8}],
        project_id=P1,
    )
    person = graph_store.search_entities(P1, query="Ilse Varga")[0]
    (rel,) = graph_store.get_relationships(person["id"])
    assert rel["project_id"] == P1
