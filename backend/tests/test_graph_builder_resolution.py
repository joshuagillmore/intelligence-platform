"""The substring fallback respects entity types (review G-7).

resolve_entity_name refuses to fuzzy-merge incompatible types in its
Jaro-Winkler pass, but the substring fallback below it ignored types, so a
Person "Wagner" resolved into the Organization "Wagner Group".
"""
from __future__ import annotations

from intel_platform.services.graph_builder import build_graph_from_extractions, resolve_entity_name

PROJECT = "test-builder-resolution"


def test_a_person_is_not_merged_into_an_organization():
    match = resolve_entity_name(
        "Wagner", ["Wagner Group"], threshold=0.92,
        entity_type="Person", existing_types={"Wagner Group": "Organization"},
    )
    assert match is None


def test_a_partial_name_of_the_same_type_still_merges():
    match = resolve_entity_name(
        "Putin", ["Vladimir Putin"], threshold=0.92,
        entity_type="Person", existing_types={"Vladimir Putin": "Person"},
    )
    assert match == "Vladimir Putin"


def test_an_untyped_name_keeps_the_permissive_fallback():
    assert resolve_entity_name("Putin", ["Vladimir Putin"], threshold=0.92) == "Vladimir Putin"


def test_the_build_keeps_them_apart(graph_store):
    build_graph_from_extractions(
        graph_store, [{"name": "Wagner Group", "entity_type": "Organization"}], [], project_id=PROJECT,
    )
    result = build_graph_from_extractions(
        graph_store, [{"name": "Wagner", "entity_type": "Person"}], [], project_id=PROJECT,
    )
    assert result["entities_created"] == 1
    assert result["entities_merged"] == 0
