"""The graph build writes each edge's evidence span: its text and its offset.

`evidence` was already carried onto the edge; `evidence_offset` says where in
the chunk the span starts, so chunk[offset:offset + len(evidence)] is the
sentence that states the relationship. -1 means unknown: no evidence, or an
extraction that could not place it.
"""
from __future__ import annotations

from intel_platform.graph.store import GraphStore
from intel_platform.services.graph_builder import build_graph_from_extractions
from tests.ids import tp

CHUNK = "Weekly summary.\n\nIran transferred missiles to Russia in May 2024."
SENTENCE = "Iran transferred missiles to Russia in May 2024."
ENTITIES = [
    {"name": "Iran", "entity_type": "Location"},
    {"name": "Russia", "entity_type": "Location"},
    {"name": "Kalvik Coast Guard", "entity_type": "Organization"},
]


def _edges(driver, project_id: str) -> list[dict]:
    with driver.session() as s:
        return [dict(r["props"]) | {"type": r["type"]} for r in s.run(
            "MATCH (a:Entity {project_id: $p})-[r]->(b:Entity {project_id: $p}) "
            "RETURN type(r) AS type, properties(r) AS props", p=project_id)]


def test_the_build_writes_the_evidence_offset_onto_the_edge(neo4j_driver):
    project = tp("evidence-offset")
    rels = [{"source_name": "Russia", "target_name": "Iran", "rel_type": "SUPPLIED_BY", "confidence": 0.9,
             "method": "llm", "evidence": SENTENCE, "evidence_offset": CHUNK.index(SENTENCE)}]
    result = build_graph_from_extractions(GraphStore(neo4j_driver), ENTITIES, rels, project_id=project,
                                          source_doc_id="doc-1")
    assert result["relationships_created"] == 1
    (edge,) = _edges(neo4j_driver, project)
    assert edge["type"] == "SUPPLIED_BY"
    assert edge["evidence"] == SENTENCE
    assert edge["evidence_offset"] == CHUNK.index(SENTENCE)
    off = edge["evidence_offset"]
    assert CHUNK[off:off + len(edge["evidence"])] == edge["evidence"]


def test_an_edge_without_an_offset_is_written_as_unknown(neo4j_driver):
    project = tp("evidence-offset-unknown")
    rels = [{"source_name": "Kalvik Coast Guard", "target_name": "Russia", "rel_type": "SUPPLIED_BY",
             "confidence": 0.9, "evidence": "some sentence"}]
    build_graph_from_extractions(GraphStore(neo4j_driver), ENTITIES, rels, project_id=project)
    (edge,) = _edges(neo4j_driver, project)
    assert edge["evidence_offset"] == -1


def test_an_offset_that_is_not_a_number_is_unknown(neo4j_driver):
    project = tp("evidence-offset-bad")
    rels = [{"source_name": "Kalvik Coast Guard", "target_name": "Russia", "rel_type": "SUPPLIED_BY",
             "confidence": 0.9, "evidence": "some sentence", "evidence_offset": "twelve"}]
    build_graph_from_extractions(GraphStore(neo4j_driver), ENTITIES, rels, project_id=project)
    (edge,) = _edges(neo4j_driver, project)
    assert edge["evidence_offset"] == -1


def test_corroboration_keeps_the_offset_of_the_primary_evidence(neo4j_driver):
    """A second document asserting the same edge adds to `evidence_all`; the
    primary `evidence` and its offset stay the first document's."""
    project = tp("evidence-offset-corroborated")
    store = GraphStore(neo4j_driver)
    first = [{"source_name": "Russia", "target_name": "Iran", "rel_type": "SUPPLIED_BY", "confidence": 0.9,
              "evidence": SENTENCE, "evidence_offset": 17}]
    second = [{"source_name": "Russia", "target_name": "Iran", "rel_type": "SUPPLIED_BY", "confidence": 0.9,
               "evidence": "Russia received Iranian missiles.", "evidence_offset": 3}]
    build_graph_from_extractions(store, ENTITIES, first, project_id=project, source_doc_id="doc-1")
    build_graph_from_extractions(store, ENTITIES, second, project_id=project, source_doc_id="doc-2")
    (edge,) = _edges(neo4j_driver, project)
    assert edge["evidence"] == SENTENCE
    assert edge["evidence_offset"] == 17
    assert edge["corroboration_count"] == 2


def test_an_edge_that_gains_its_first_evidence_gains_its_offset():
    current = {"evidence": "", "source_doc_id": "doc-1", "polarity": "asserts", "confidence": 0.5}
    update = GraphStore._merge_assertion(current, {
        "evidence": SENTENCE, "evidence_offset": 17, "source_doc_id": "doc-2", "polarity": "asserts",
        "confidence": 0.9,
    })
    assert update["evidence"] == SENTENCE
    assert update["evidence_offset"] == 17


def test_a_legacy_edge_with_evidence_and_no_offset_reports_it_unknown():
    current = {"evidence": "old sentence", "source_doc_id": "doc-1", "polarity": "asserts", "confidence": 0.5}
    update = GraphStore._merge_assertion(current, {
        "evidence": SENTENCE, "evidence_offset": 17, "source_doc_id": "doc-2", "polarity": "asserts",
        "confidence": 0.9,
    })
    assert update["evidence"] == "old sentence"
    assert update["evidence_offset"] == -1
