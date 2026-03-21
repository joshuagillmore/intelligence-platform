import pytest
from intel_platform.graph.store import GraphStore
from intel_platform.models.entities import Person, Organization, ThreatActor
from intel_platform.models.relationships import Relationship


def test_create_and_get_entity(graph_store):
    person = Person(name="John Doe", project_id="test-proj-1", roles=["analyst"])
    graph_store.create_entity(person)
    result = graph_store.get_entity(person.id)
    assert result is not None
    assert result["name"] == "John Doe"
    assert result["entity_type"] == "Person"


def test_search_entities(graph_store):
    p1 = Person(name="Alice Smith", project_id="test-proj-2")
    p2 = Organization(name="Acme Corp", project_id="test-proj-2")
    graph_store.create_entity(p1)
    graph_store.create_entity(p2)
    results = graph_store.search_entities(project_id="test-proj-2", query="Alice")
    assert len(results) >= 1
    assert any(r["name"] == "Alice Smith" for r in results)


def test_search_entities_by_type(graph_store):
    p = Person(name="Bob Jones", project_id="test-proj-3")
    o = Organization(name="Evil Corp", project_id="test-proj-3")
    graph_store.create_entity(p)
    graph_store.create_entity(o)
    results = graph_store.search_entities(project_id="test-proj-3", entity_type="Person")
    assert all(r["entity_type"] == "Person" for r in results)


def test_create_and_get_relationship(graph_store):
    p = Person(name="Jane Doe", project_id="test-proj-4")
    o = Organization(name="Target Org", project_id="test-proj-4")
    graph_store.create_entity(p)
    graph_store.create_entity(o)
    rel = Relationship(
        source_id=p.id, target_id=o.id, rel_type="BELONGS_TO",
        confidence=0.9, source="doc-1", method="llm",
    )
    graph_store.create_relationship(rel)
    rels = graph_store.get_relationships(p.id)
    assert len(rels) >= 1
    assert any(r["rel_type"] == "BELONGS_TO" for r in rels)


def test_get_subgraph(graph_store):
    a = ThreatActor(name="APT-99", project_id="test-proj-5")
    b = Organization(name="Victim Org", project_id="test-proj-5")
    graph_store.create_entity(a)
    graph_store.create_entity(b)
    rel = Relationship(
        source_id=a.id, target_id=b.id, rel_type="TARGETS",
        confidence=0.8, source="doc-2", method="nlp",
    )
    graph_store.create_relationship(rel)
    subgraph = graph_store.get_subgraph(a.id, hops=1)
    assert subgraph["node_count"] >= 2
    assert subgraph["edge_count"] >= 1


def test_get_full_graph(graph_store):
    p = Person(name="Graph Test", project_id="test-proj-6")
    graph_store.create_entity(p)
    graph = graph_store.get_full_graph(project_id="test-proj-6")
    assert graph["node_count"] >= 1


def test_delete_entity(graph_store):
    p = Person(name="To Delete", project_id="test-proj-7")
    graph_store.create_entity(p)
    graph_store.delete_entity(p.id)
    result = graph_store.get_entity(p.id)
    assert result is None


def test_create_project(graph_store):
    project = graph_store.create_project(
        name="Test Project", description="A test project",
        classification_level="UNCLASSIFIED", priority="medium",
    )
    assert project["name"] == "Test Project"
    assert project["status"] == "active"
    graph_store.delete_entity(project["id"])


def test_list_projects(graph_store):
    graph_store.create_project(name="Proj A", description="", classification_level="UNCLASSIFIED", priority="low")
    projects = graph_store.list_projects()
    assert len(projects) >= 1
