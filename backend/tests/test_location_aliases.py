"""A country node keeps the government forms it was named by as aliases (contract 5).

The government/country rule (data/governments.yaml) folds "the Kremlin", "PRC
government" and a capital acting for its state into the country's node, but
the form the document actually used was lost: a later search for "Kremlin"
found nothing, and an analyst could not see why a document about the Kremlin
was linked to Russia. The form now lives in `Location.aliases`, written by
every extraction mode and by the graph build, added to (never replaced) when
a later document names the country another way, and matched by
`search_entities(query=...)` and by `resolve_entity_name`.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from intel_platform.graph.store import _clean_aliases
from intel_platform.llm.base import LLMResponse
from intel_platform.models.entities import Location, ThreatActor
from intel_platform.services import extraction
from intel_platform.services.graph_builder import build_graph_from_extractions, resolve_entity_name
from intel_platform.services.text_utils import country_key
from tests.ids import tp

KREMLIN_TEXT = "The Kremlin denied that Russia had supplied the drones to the militia."
KREMLIN_REPLY = {
    "entities": [{"name": "the Kremlin", "entity_type": "GovernmentAgency"},
                 {"name": "Russia", "entity_type": "Country"}],
    "relationships": [],
}
MOSCOW_ACTOR_TEXT = "Moscow insists the sanctions are illegal. Russia announced new countermeasures."
MOSCOW_PLACE_TEXT = "Officials met for talks in Moscow on Tuesday."


def _llm_returning(reply: dict):
    class _Reply:
        async def generate(self, **_kw):
            return LLMResponse(content=json.dumps(reply), model="fake")

    return patch("intel_platform.llm.providers._get_extraction_provider", new=AsyncMock(return_value=_Reply()))


async def _extract(mode: str, text: str, reply: dict | None = None) -> list[dict]:
    if mode == "nlp":
        entities, _ = extraction.extract_entities_nlp(text, "doc-aliases")
        return entities
    with _llm_returning(reply or {"entities": [], "relationships": []}):
        if mode == "llm":
            entities, _ = await extraction.extract_entities_llm(text, "doc-aliases")
        else:
            entities, _ = await extraction.extract_entities_hybrid(text, "doc-aliases")
    return entities


def _nodes(driver, project: str) -> list[dict]:
    with driver.session() as s:
        return [dict(r["n"]) for r in s.run("MATCH (n:Entity {project_id: $p}) RETURN n ORDER BY n.name", p=project)]


def _keys(aliases) -> set[str]:
    return {country_key(a) for a in aliases or []}


# ── Extraction to the graph, in every mode ────────────────────────────────────

@pytest.mark.parametrize("mode", ["nlp", "llm", "hybrid"])
async def test_the_kremlin_and_russia_are_one_node_carrying_the_form_as_an_alias(mode, graph_store, neo4j_driver):
    project = tp(f"aliases-kremlin-{mode}")
    entities = await _extract(mode, KREMLIN_TEXT, KREMLIN_REPLY)
    build_graph_from_extractions(graph_store, entities, [], project_id=project)

    states = [n for n in _nodes(neo4j_driver, project) if n["name"] in ("Russia", "Kremlin", "the Kremlin")]
    assert [(n["name"], n["entity_type"]) for n in states] == [("Russia", "Location")]
    # spaCy leaves the article off the span ("Kremlin"); the model writes it.
    assert "kremlin" in _keys(states[0]["aliases"])
    if mode == "llm":
        assert "the Kremlin" in states[0]["aliases"]


async def test_a_later_search_for_the_form_finds_the_country(graph_store):
    project = tp("aliases-search")
    entities = await _extract("llm", KREMLIN_TEXT, KREMLIN_REPLY)
    build_graph_from_extractions(graph_store, entities, [], project_id=project)

    for query in ("Kremlin", "kremlin", "the Kremlin"):
        found = graph_store.search_entities(project_id=project, query=query)
        assert [n["name"] for n in found] == ["Russia"], query
        assert graph_store.count_entities(project_id=project, query=query) == 1


async def test_a_second_document_extends_the_aliases_and_a_capital_used_as_a_place_stays_a_city(
    graph_store, neo4j_driver,
):
    project = tp("aliases-union")
    first = await _extract("llm", KREMLIN_TEXT, KREMLIN_REPLY)
    build_graph_from_extractions(graph_store, first, [], project_id=project)

    # "Moscow insists ...": the capital acting for the state.
    second = await _extract("nlp", MOSCOW_ACTOR_TEXT)
    assert "Moscow" in next(e for e in second if e["name"] == "Russia")["aliases"]
    result = build_graph_from_extractions(graph_store, second, [], project_id=project)
    assert result["entities_merged"] == 1 and result["entities_created"] == 0

    (russia,) = [n for n in _nodes(neo4j_driver, project) if n["name"] == "Russia"]
    assert russia["aliases"] == ["the Kremlin", "Moscow"]
    assert [n["name"] for n in graph_store.search_entities(project_id=project, query="Moscow")] == ["Russia"]

    # "talks in Moscow": the city. Russia carrying "Moscow" as an alias must
    # not pull it in; the governments table decides, not the alias.
    third = await _extract("nlp", MOSCOW_PLACE_TEXT)
    assert [e["name"] for e in third if e["entity_type"] == "Location"] == ["Moscow"]
    build_graph_from_extractions(graph_store, third, [], project_id=project)
    names = sorted(n["name"] for n in _nodes(neo4j_driver, project))
    assert names == ["Moscow", "Russia"]
    (russia,) = [n for n in _nodes(neo4j_driver, project) if n["name"] == "Russia"]
    assert russia["aliases"] == ["the Kremlin", "Moscow"]


def test_the_build_records_a_government_form_merging_into_an_existing_country(graph_store, neo4j_driver):
    project = tp("aliases-build-merge")
    build_graph_from_extractions(graph_store, [{"name": "China", "entity_type": "Location"}], [], project_id=project)
    build_graph_from_extractions(
        graph_store, [{"name": "PRC government", "entity_type": "GovernmentAgency"}], [], project_id=project,
    )
    build_graph_from_extractions(
        graph_store, [{"name": "the Chinese government", "entity_type": "Organization"},
                      {"name": "prc GOVERNMENT", "entity_type": "Organization"}], [], project_id=project,
    )
    (china,) = _nodes(neo4j_driver, project)
    assert china["name"] == "China"
    # In order, once each ignoring case; the canonical name is not its own alias.
    assert china["aliases"] == ["PRC government", "the Chinese government"]


def test_extraction_aliases_the_table_does_not_vouch_for_are_left_off(graph_store, neo4j_driver):
    project = tp("aliases-filtered")
    build_graph_from_extractions(
        graph_store,
        [{"name": "Russia", "entity_type": "Location", "aliases": ["Kremlin", "RF", "Kyiv", "Russia"]}],
        [], project_id=project,
    )
    (russia,) = _nodes(neo4j_driver, project)
    assert russia["aliases"] == ["Kremlin"]


# ── Resolution matches aliases ────────────────────────────────────────────────

class TestResolveEntityName:
    def test_a_name_equal_to_an_alias_resolves_to_its_entity(self):
        assert resolve_entity_name(
            "Fancy Bear", ["APT28", "Lazarus Group"], entity_type="ThreatActor",
            existing_types={"APT28": "ThreatActor", "Lazarus Group": "ThreatActor"},
            existing_aliases={"APT28": ["Sofacy", "fancy bear"]},
        ) == "APT28"

    def test_an_alias_is_matched_exactly_not_fuzzily(self):
        assert resolve_entity_name(
            "Fancy Bears United", ["APT28"], entity_type="ThreatActor",
            existing_types={"APT28": "ThreatActor"}, existing_aliases={"APT28": ["Fancy Bear"]},
        ) is None

    def test_an_exact_name_beats_another_entitys_alias(self):
        assert resolve_entity_name(
            "Sofacy", ["APT28", "Sofacy"], entity_type="ThreatActor",
            existing_types={"APT28": "ThreatActor", "Sofacy": "ThreatActor"},
            existing_aliases={"APT28": ["Sofacy"]},
        ) == "Sofacy"

    def test_the_type_gate_applies_to_aliases(self):
        assert resolve_entity_name(
            "Jordan", ["Jordan Kingdom"], entity_type="Person",
            existing_types={"Jordan Kingdom": "Location"}, existing_aliases={"Jordan Kingdom": ["Jordan"]},
        ) is None

    def test_indicators_never_match_an_alias(self):
        assert resolve_entity_name(
            "203.0.113.7", ["198.51.100.1"], entity_type="IPAddress",
            existing_types={"198.51.100.1": "IPAddress"}, existing_aliases={"198.51.100.1": ["203.0.113.7"]},
        ) is None

    def test_a_malformed_alias_list_is_ignored(self):
        assert resolve_entity_name(
            "F", ["APT28"], entity_type="ThreatActor",
            existing_types={"APT28": "ThreatActor"}, existing_aliases={"APT28": "Fancy Bear"},
        ) is None


def test_a_later_build_naming_an_entity_by_its_alias_merges_into_it(graph_store, neo4j_driver):
    project = tp("aliases-resolve-graph")
    graph_store.create_entity(ThreatActor(name="APT28", project_id=project, aliases=["Fancy Bear"]))
    # Decoys the name index ranks above APT28 for "Fancy Bear".
    graph_store.create_entity(ThreatActor(name="Fancy Panda", project_id=project))
    graph_store.create_entity(ThreatActor(name="Cozy Bear", project_id=project))

    result = build_graph_from_extractions(
        graph_store, [{"name": "fancy bear", "entity_type": "ThreatActor"}], [], project_id=project,
    )
    assert result["entities_merged"] == 1 and result["entities_created"] == 0
    assert sorted(n["name"] for n in _nodes(neo4j_driver, project)) == ["APT28", "Cozy Bear", "Fancy Panda"]


def test_name_candidates_come_first_and_alias_holders_follow(graph_store):
    project = tp("aliases-candidates")
    graph_store.create_entity(ThreatActor(name="APT28", project_id=project, aliases=["Fancy Bear"]))
    graph_store.create_entity(ThreatActor(name="Fancy Bear Fan Club", project_id=project))

    found = [c["name"] for c in graph_store.search_entity_by_name(project, "Fancy Bear")]
    assert found == ["Fancy Bear Fan Club", "APT28"]
    assert [c["name"] for c in graph_store.search_entity_by_name(project, "Fancy Bear", match_aliases=False)] == [
        "Fancy Bear Fan Club"]
    # Another project's alias is not a candidate.
    assert graph_store.search_entity_by_name(tp("aliases-candidates-other"), "Fancy Bear") == []


# ── The store adds aliases; it never replaces them ───────────────────────────

class TestStoreUnion:
    def test_add_aliases_keeps_what_the_node_had(self, graph_store, neo4j_driver):
        project = tp("aliases-store-add")
        node = graph_store.create_entity(Location(name="Iran", project_id=project, aliases=["Tehran"]))
        written = graph_store.add_aliases({node["id"]: ["Iranian government", "TEHRAN", "iran", " ", "Iranian regime"]})
        assert written == 1
        (iran,) = _nodes(neo4j_driver, project)
        assert iran["aliases"] == ["Tehran", "Iranian government", "Iranian regime"]

    def test_add_aliases_starts_a_list_on_a_node_without_one(self, graph_store, neo4j_driver):
        project = tp("aliases-store-new")
        with neo4j_driver.session() as s:
            s.run("CREATE (:Entity:Location {id: $id, name: 'Syria', project_id: $p})", id=tp("syria"), p=project)
        assert graph_store.add_aliases({tp("syria"): ["Damascus"], "": ["x"], tp("absent"): []}) == 1
        assert _nodes(neo4j_driver, project)[0]["aliases"] == ["Damascus"]

    def test_add_aliases_with_nothing_to_add_writes_nothing(self, graph_store):
        assert graph_store.add_aliases({}) == 0
        assert graph_store.add_aliases({tp("whatever"): ["", "  "]}) == 0

    def test_update_entity_merges_aliases_rather_than_overwriting_them(self, graph_store, neo4j_driver):
        project = tp("aliases-store-update")
        node = graph_store.create_entity(Location(name="Russia", project_id=project, aliases=["the Kremlin"]))
        updated = graph_store.update_entity(node["id"], {"aliases": ["Moscow", "the kremlin"], "location_type": "country"})
        assert updated["aliases"] == ["the Kremlin", "Moscow"]
        assert updated["location_type"] == "country"
        assert "_aliases_lock" not in updated

    def test_clean_aliases(self):
        assert _clean_aliases([" a ", "A", "", None, 3, "b"]) == ["a", "b"]
        assert _clean_aliases("not a list") == []
        assert _clean_aliases(None) == []
