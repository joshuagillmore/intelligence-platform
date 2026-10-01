"""One bad LLM attribute must not abort a document's graph build (review G-2, contract 17).

LLM `attributes` went straight into the Pydantic constructor. `"roles":
"General"` — a string where Person.roles is a list — raised ValidationError
after the entities before it were already written and before any relationship
was, so /ingest returned 500 with an orphaned Document and the agentic loop
marked the whole source failed.

The contract: attributes are validated field by field; an invalid one is
dropped and logged, the result counts it in `dropped_attributes`, and the build
never raises for an attribute.
"""
from __future__ import annotations

import logging

from intel_platform.services.graph_builder import build_graph_from_extractions
from tests.ids import tp

PROJECT = tp("attr-validation")

ORG = {"name": "Northern Fleet", "entity_type": "Organization"}
GERASIMOV = {"name": "Valery Gerasimov", "entity_type": "Person", "attributes": {"roles": "General"}}
MEMBER_OF = {"source_name": "Valery Gerasimov", "target_name": "Northern Fleet",
             "rel_type": "BELONGS_TO", "confidence": 0.8}


def _node(store, name):
    return next(n for n in store.search_entities(PROJECT, query=name) if n["name"] == name)


def test_a_string_where_a_list_belongs_is_dropped_not_fatal(graph_store):
    result = build_graph_from_extractions(graph_store, [ORG, GERASIMOV], [MEMBER_OF], project_id=PROJECT)
    assert result["entities_created"] == 2
    assert result["relationships_created"] == 1, "the build must reach the relationships"
    assert result["dropped_attributes"] == 1
    assert _node(graph_store, "Valery Gerasimov").get("roles") in (None, [])


def test_the_drop_is_logged_with_the_field_and_entity(graph_store, caplog):
    with caplog.at_level(logging.WARNING, logger="intel_platform.services.graph_builder"):
        build_graph_from_extractions(graph_store, [GERASIMOV], [], project_id=PROJECT)
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "roles" in messages and "Valery Gerasimov" in messages


def test_valid_attributes_beside_an_invalid_one_survive(graph_store):
    ent = {"name": "Valery Gerasimov", "entity_type": "Person",
           "attributes": {"roles": "General", "affiliations": ["Russian General Staff"]}}
    result = build_graph_from_extractions(graph_store, [ent], [], project_id=PROJECT)
    assert result["dropped_attributes"] == 1
    assert _node(graph_store, "Valery Gerasimov")["affiliations"] == ["Russian General Staff"]


def test_well_formed_attributes_are_kept_and_nothing_is_counted(graph_store):
    ent = {"name": "Valery Gerasimov", "entity_type": "Person", "attributes": {"roles": ["General"]}}
    result = build_graph_from_extractions(graph_store, [ent], [], project_id=PROJECT)
    assert result["dropped_attributes"] == 0
    assert _node(graph_store, "Valery Gerasimov")["roles"] == ["General"]


def test_a_value_the_model_would_accept_is_coerced_as_before(graph_store):
    ent = {"name": "CVE-2024-3400", "entity_type": "Vulnerability", "attributes": {"cvss_score": "10.0"}}
    result = build_graph_from_extractions(graph_store, [ent], [], project_id=PROJECT)
    assert result["dropped_attributes"] == 0
    assert _node(graph_store, "CVE-2024-3400")["cvss_score"] == 10.0


def test_attributes_that_are_not_a_mapping_are_dropped(graph_store):
    ent = {"name": "Valery Gerasimov", "entity_type": "Person", "attributes": "General"}
    result = build_graph_from_extractions(graph_store, [ent], [], project_id=PROJECT)
    assert result["entities_created"] == 1
    assert result["dropped_attributes"] == 1


def test_an_attribute_cannot_move_an_entity_to_another_project(graph_store):
    """`project_id`, `id`, `name` and `entity_type` are the build's to set, not
    the model's: an attribute named after one overwrote it."""
    ent = {"name": "Valery Gerasimov", "entity_type": "Person",
           "attributes": {"project_id": tp("attr-elsewhere"), "entity_type": "Organization"}}
    result = build_graph_from_extractions(graph_store, [ent], [], project_id=PROJECT)
    node = _node(graph_store, "Valery Gerasimov")
    assert node["project_id"] == PROJECT
    assert node["entity_type"] == "Person"
    assert result["dropped_attributes"] == 2
