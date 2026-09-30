"""Relationship endpoints are named the way entities were stored (review G-6).

Entity names were cleaned of markdown before being keyed, but relationship
endpoint names never were, so `**Yi Peng 3**` became a node named "Yi Peng 3"
while every edge naming `**Yi Peng 3**` was dropped as "never extracted".
"""
from __future__ import annotations

from intel_platform.services.graph_builder import build_graph_from_extractions

PROJECT = "test-builder-endpoints"

YI_PENG = {"name": "**Yi Peng 3**", "entity_type": "Ship"}
BALTIC = {"name": "Baltic Sea", "entity_type": "Location"}
AT_SEA = {"source_name": "**Yi Peng 3**", "target_name": "Baltic Sea", "rel_type": "LOCATED_AT", "confidence": 0.8}


def test_a_bolded_entity_keeps_its_bolded_edges(graph_store):
    result = build_graph_from_extractions(graph_store, [YI_PENG, BALTIC], [AT_SEA], project_id=PROJECT)
    assert result["relationships_dropped"] == 0
    assert result["relationships_created"] == 1


def test_a_bolded_endpoint_finds_a_plain_entity(graph_store):
    plain = {"name": "Yi Peng 3", "entity_type": "Ship"}
    result = build_graph_from_extractions(graph_store, [plain, BALTIC], [AT_SEA], project_id=PROJECT)
    assert result["relationships_created"] == 1


def test_the_edge_lands_on_the_cleaned_node(graph_store):
    build_graph_from_extractions(graph_store, [YI_PENG, BALTIC], [AT_SEA], project_id=PROJECT)
    ship = next(n for n in graph_store.search_entities(PROJECT, query="Yi Peng") if n["name"] == "Yi Peng 3")
    (edge,) = graph_store.get_relationships(ship["id"])
    assert edge["target_name"] == "Baltic Sea"


def test_a_bolded_absorbed_date_is_retired_not_dropped(graph_store):
    entities = [{"name": "Cable cut", "entity_type": "Event"},
                {"name": "**March 2026**", "entity_type": "Date", "attributes": {"_absorbed": True}}]
    rels = [{"source_name": "Cable cut", "target_name": "**March 2026**",
             "rel_type": "OCCURRED_ON", "confidence": 0.8}]
    result = build_graph_from_extractions(graph_store, entities, rels, project_id=PROJECT)
    assert result["relationships_retired"] == 1
    assert result["relationships_dropped"] == 0
