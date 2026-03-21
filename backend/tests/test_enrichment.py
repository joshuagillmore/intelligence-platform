from intel_platform.services.enrichment import compute_degree_centrality, detect_communities
from intel_platform.models.entities import Person, Organization
from intel_platform.models.relationships import Relationship


def test_degree_centrality(graph_store):
    a = Person(name="Enrich A", project_id="test-proj-enrich")
    b = Person(name="Enrich B", project_id="test-proj-enrich")
    c = Organization(name="Enrich C", project_id="test-proj-enrich")
    graph_store.create_entity(a)
    graph_store.create_entity(b)
    graph_store.create_entity(c)
    graph_store.create_relationship(
        Relationship(source_id=a.id, target_id=b.id, rel_type="ASSOCIATED_WITH",
                     confidence=0.9, source="d", method="t")
    )
    graph_store.create_relationship(
        Relationship(source_id=b.id, target_id=c.id, rel_type="BELONGS_TO",
                     confidence=0.8, source="d", method="t")
    )
    result = compute_degree_centrality(graph_store, "test-proj-enrich")
    assert len(result) >= 3
    b_entry = next((r for r in result if r["name"] == "Enrich B"), None)
    assert b_entry is not None
    assert b_entry["degree"] == 2


def test_detect_communities(graph_store):
    # Create separate data for this test
    a = Person(name="Comm A", project_id="test-proj-comm")
    b = Person(name="Comm B", project_id="test-proj-comm")
    graph_store.create_entity(a)
    graph_store.create_entity(b)
    graph_store.create_relationship(
        Relationship(source_id=a.id, target_id=b.id, rel_type="ASSOCIATED_WITH",
                     confidence=0.9, source="d", method="t")
    )
    result = detect_communities(graph_store, "test-proj-comm")
    assert isinstance(result, list)
    assert len(result) >= 1
