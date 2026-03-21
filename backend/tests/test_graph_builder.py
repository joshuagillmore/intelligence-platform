from intel_platform.services.graph_builder import resolve_entity_name, build_graph_from_extractions


def test_resolve_exact_match():
    existing = ["John Smith", "Jane Doe", "Microsoft"]
    match = resolve_entity_name("John Smith", existing, threshold=0.85)
    assert match == "John Smith"


def test_resolve_fuzzy_match():
    existing = ["John Smith", "Jane Doe"]
    match = resolve_entity_name("Jon Smith", existing, threshold=0.85)
    assert match == "John Smith"


def test_resolve_no_match():
    existing = ["John Smith", "Jane Doe"]
    match = resolve_entity_name("Totally Different", existing, threshold=0.85)
    assert match is None


def test_resolve_empty_existing():
    match = resolve_entity_name("John Smith", [], threshold=0.85)
    assert match is None


def test_build_graph_creates_entities(graph_store):
    entities = [
        {"name": "Test Actor", "entity_type": "ThreatActor", "source": "doc-1", "method": "nlp", "confidence": 0.8},
        {"name": "Test Org", "entity_type": "Organization", "source": "doc-1", "method": "nlp", "confidence": 0.7},
    ]
    relationships = [
        {"source_name": "Test Actor", "target_name": "Test Org", "rel_type": "TARGETS",
         "confidence": 0.6, "source": "doc-1", "method": "nlp"},
    ]
    result = build_graph_from_extractions(graph_store, entities, relationships, project_id="test-proj-build")
    assert result["entities_created"] == 2
    assert result["relationships_created"] == 1


def test_build_graph_deduplicates(graph_store):
    entities = [
        {"name": "Dedup Actor", "entity_type": "ThreatActor", "source": "doc-1", "method": "nlp", "confidence": 0.8},
    ]
    build_graph_from_extractions(graph_store, entities, [], project_id="test-proj-dedup")
    result = build_graph_from_extractions(graph_store, entities, [], project_id="test-proj-dedup")
    assert result["entities_created"] == 0
    assert result["entities_merged"] == 1
