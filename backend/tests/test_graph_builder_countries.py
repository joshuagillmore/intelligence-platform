"""The build resolves a government, and a capital typed as one, to its country's node.

Reporting names a state as the country ("China", "PRC"), its government ("the
PRC government", "the Kremlin") or its capital ("Tehran asserts ..."), and
each became a node of its own (openrep corpus eval). ``data/governments.yaml``
is the table both extraction and the build resolve against; here the build
has no text, so a capital resolves only when it arrives typed as an
organization (extraction has already judged how the text used it).
"""
from __future__ import annotations

from types import SimpleNamespace

from intel_platform.services.graph_builder import build_graph_from_extractions
from tests.ids import tp

PROJECT = tp("builder-countries")


def _store(aliased: list | None = None):
    created: list = []
    written: list = []
    aliased = aliased if aliased is not None else []
    return created, written, SimpleNamespace(
        create_entity=lambda e: created.append(e) or {"id": e.id},
        search_entity_by_name=lambda *a, **k: [],
        record_entity_source=lambda *a, **k: None,
        record_mentions=lambda *a, **k: 0,
        create_relationship=lambda rel: written.append(rel) or {},
        add_aliases=lambda by_id: aliased.append(by_id) or len(by_id),
    )


def test_a_government_form_and_its_country_are_one_node_and_its_edges_follow():
    created, written, store = _store()
    result = build_graph_from_extractions(
        store,
        [{"name": "PRC government", "entity_type": "Organization"},
         {"name": "China", "entity_type": "Location"},
         {"name": "ByteDance", "entity_type": "Organization"}],
        [{"source_name": "ByteDance", "target_name": "PRC government", "rel_type": "FUNDED_BY",
          "confidence": 0.8}],
        project_id=PROJECT,
    )
    assert [(e.name, e.entity_type.value) for e in created] == [("China", "Location"), ("ByteDance", "Organization")]
    assert result["entities_merged"] == 1
    assert len(written) == 1 and written[0].target_id == created[0].id
    assert result["relationships_dropped"] == 0


def test_the_kremlin_is_russia_and_a_country_name_is_its_canonical_name():
    aliased: list = []
    created, _, store = _store(aliased)
    build_graph_from_extractions(
        store,
        [{"name": "the Kremlin", "entity_type": "Organization"}, {"name": "Russian Federation", "entity_type": "Location"},
         {"name": "PRC", "entity_type": "Location"}],
        [], project_id=PROJECT,
    )
    assert [(e.name, e.entity_type.value) for e in created] == [("Russia", "Location"), ("China", "Location")]
    # The forms as written stay on the node: the first on the created node, a
    # later one merging into it in one write after the loop.
    russia, china = created
    assert russia.aliases == ["the Kremlin"] and china.aliases == ["PRC"]
    assert aliased == [{russia.id: ["Russian Federation"]}]


def test_a_country_named_as_itself_gets_no_alias_and_writes_none():
    aliased: list = []
    created, _, store = _store(aliased)
    build_graph_from_extractions(
        store, [{"name": "Iran", "entity_type": "Location"}, {"name": "iran", "entity_type": "Location"}], [],
        project_id=PROJECT,
    )
    assert [(e.name, e.aliases) for e in created] == [("Iran", [])]
    assert aliased == []


def test_a_capital_stays_a_place_unless_it_arrives_typed_as_a_government():
    created, _, store = _store()
    build_graph_from_extractions(store, [{"name": "Tehran", "entity_type": "Location"}], [], project_id=PROJECT)
    assert [(e.name, e.entity_type.value) for e in created] == [("Tehran", "Location")]
    created, _, store = _store()
    build_graph_from_extractions(store, [{"name": "Tehran", "entity_type": "GovernmentAgency"}], [],
                                 project_id=PROJECT)
    assert [(e.name, e.entity_type.value) for e in created] == [("Iran", "Location")]


def test_a_person_or_event_named_like_a_country_is_left_alone():
    created, _, store = _store()
    build_graph_from_extractions(
        store,
        [{"name": "US", "entity_type": "Person"}, {"name": "China", "entity_type": "Event"}], [], project_id=PROJECT,
    )
    assert [(e.name, e.entity_type.value) for e in created] == [("US", "Person"), ("China", "Event")]


def test_a_later_build_naming_the_government_merges_into_the_country_node(graph_store):
    project = tp("builder-countries-db")
    first = build_graph_from_extractions(
        graph_store, [{"name": "Iran", "entity_type": "Location"}], [], project_id=project)
    second = build_graph_from_extractions(
        graph_store, [{"name": "Iranian government", "entity_type": "Organization"},
                      {"name": "IAEA", "entity_type": "Organization"}],
        [{"source_name": "Iranian government", "target_name": "IAEA", "rel_type": "TARGETS", "confidence": 0.8}],
        project_id=project,
    )
    assert first["entities_created"] == 1
    assert second["entities_merged"] == 1 and second["entities_created"] == 1
    assert second["relationships_created"] == 1
    with graph_store._driver.session() as s:
        names = sorted(r["name"] for r in s.run("MATCH (n:Entity {project_id: $p}) RETURN n.name AS name",
                                                 p=project))
        aliases = s.run("MATCH (n:Entity {project_id: $p, name: 'Iran'}) RETURN n.aliases AS a", p=project).single()["a"]
    assert names == ["IAEA", "Iran"]
    assert aliases == ["Iranian government"]
