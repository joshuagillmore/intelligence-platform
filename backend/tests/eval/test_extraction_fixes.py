"""Extraction fixes driven by the corpus eval, each pinned to the sentence that showed it.

The sentences are the three documents ingested in the 2026-09-30 end-to-end
run (``tests/fixtures/extraction_corpus_cyber``) and the exercise corpus. Runs
in the default suite: NLP only, no model, no database.
"""

from __future__ import annotations

from intel_platform.services.extraction import extract_entities_nlp

DOC_2 = (
    "CISA Advisory AA23-144a: The People's Republic of China state-sponsored cyber actor known as Volt Typhoon "
    "has compromised critical infrastructure networks in Guam and elsewhere in the United States. The actor relies "
    "on living-off-the-land techniques including netsh, ntdsutil and wmic. Fortinet FortiGuard devices exposed to "
    "CVE-2023-27997 were an initial access vector. Traffic was proxied through compromised small-office routers "
    "made by ASUS, Cisco and Netgear."
)
DOC_3 = (
    "The NSA assessed that Volt Typhoon pre-positioned on Guam networks to disrupt communications between the "
    "United States and Asia in a crisis. Analysts at Microsoft linked the campaign to earlier intrusions against "
    "Naval Base Guam. The group avoided malware, instead abusing built-in Windows tools, and used hop points in "
    "Kaohsiung, Taiwan and Manila. A Netgear ProSAFE router at 45.83.12.7 served as an exit node."
)


DOC_1 = (
    "Volt Typhoon, a state-sponsored threat actor attributed to China, targeted Guam telecommunications providers "
    "in 2023. Microsoft reported the group used living-off-the-land techniques and the Fortinet vulnerability "
    "CVE-2023-27997. Command and control traffic was routed through 185.220.101.42 and the domain evil-c2[.]com. "
    "CISA and the NSA published a joint advisory on 24 May 2023."
)


def _types(text: str) -> dict[str, str]:
    entities, _ = extract_entities_nlp(text, "doc-fix")
    return {e["name"]: e["entity_type"] for e in entities}


# ── Software and hardware are not places or companies ─────────────────────────

def test_windows_in_built_in_windows_tools_is_software_not_a_location():
    types = _types(DOC_3)
    assert types["Windows"] == "Software"
    assert types["Kaohsiung"] == "Location"


def test_a_vendor_product_line_named_as_a_router_is_hardware():
    assert _types(DOC_3)["Netgear ProSAFE"] == "Hardware"


def test_a_vendor_product_line_named_as_devices_is_hardware_and_the_vendors_stay_organizations():
    types = _types(DOC_2)
    assert types["Fortinet FortiGuard"] == "Hardware"
    assert types["Netgear"] == "Organization"
    assert types["Cisco"] == "Organization"


def test_living_off_the_land_binaries_are_extracted_as_software():
    types = _types(DOC_2)
    assert {types.get("netsh"), types.get("ntdsutil"), types.get("wmic")} == {"Software"}


def test_a_tool_name_inside_a_longer_word_is_not_software():
    types = _types("The operators renamed the netshell helper before the network shellcode ran.")
    assert "netsh" not in types


def test_a_system_binary_the_model_typed_as_a_technique_is_software():
    from intel_platform.services.extraction import _apply_type_hints

    # Cohere's reply for DOC_2 typed all three tools TTP.
    ents = _apply_type_hints([
        {"name": "netsh", "entity_type": "TTP"}, {"name": "wmic.exe", "entity_type": "Technology"},
        {"name": "T1059.001", "entity_type": "TTP"},
    ])
    assert [e["entity_type"] for e in ents] == ["Software", "Software", "TTP"]


# ── Threat actors under the current naming schemes ────────────────────────────

def test_volt_typhoon_is_a_threat_actor_not_an_organization():
    assert _types(DOC_1)["Volt Typhoon"] == "ThreatActor"


def test_weather_and_cluster_names_are_threat_actors_but_weather_is_not():
    from intel_platform.services.extraction import _THREAT_ACTOR_RE

    for name in ("Volt Typhoon", "Midnight Blizzard", "Mint Sandstorm", "Storm-0558", "UNC2452", "FIN7", "APT29"):
        assert _THREAT_ACTOR_RE.match(name), name
    for name in ("Super Typhoon", "Tropical Storm", "Eurofighter Typhoon", "Typhoon", "Storm"):
        assert not _THREAT_ACTOR_RE.match(name), name


# ── Relationships the sentence states ─────────────────────────────────────────
# The live run built one edge from DOC_1 (Volt Typhoon TARGETS Guam) and
# dropped five: all ASSOCIATED_WITH, all to a Date, which is never a node.

def _rels(text: str) -> set[tuple[str, str, str]]:
    _, rels = extract_entities_nlp(text, "doc-fix")
    return {(r["source_name"], r["rel_type"], r["target_name"]) for r in rels}


def test_doc_1_states_attribution_exploitation_and_targeting():
    rels = _rels(DOC_1)
    assert ("Volt Typhoon", "ATTRIBUTED_TO", "China") in rels
    # "Microsoft reported the group used ... the Fortinet vulnerability
    # CVE-2023-27997": "the group" is Volt Typhoon, and using a vulnerability
    # is exploiting it.
    assert ("Volt Typhoon", "EXPLOITS", "CVE-2023-27997") in rels
    assert ("Volt Typhoon", "TARGETS", "Guam") in rels


def test_no_generic_edge_is_emitted_to_a_date():
    entities, rels = extract_entities_nlp(DOC_1, "doc-fix")
    dates = {e["name"] for e in entities if e["entity_type"] == "Date"}
    assert dates, "the dates are still extracted"
    assert not [r for r in rels if r["rel_type"] != "OCCURRED_ON"
                and (r["source_name"] in dates or r["target_name"] in dates)]


def test_the_actor_relies_on_each_listed_tool():
    rels = _rels(DOC_2)
    for tool in ("netsh", "ntdsutil", "wmic"):
        assert ("Volt Typhoon", "USES", tool) in rels
    assert ("Volt Typhoon", "TARGETS", "Guam") in rels


def test_abusing_built_in_tools_is_using_them_not_exploiting_them():
    rels = _rels(DOC_3)
    assert ("Volt Typhoon", "USES", "Windows") in rels
    assert ("Volt Typhoon", "EXPLOITS", "Windows") not in rels


def test_a_place_the_target_sits_in_is_targeted_when_the_object_names_nothing():
    rels = _rels("Volt Typhoon has compromised critical infrastructure networks in Guam.")
    assert ("Volt Typhoon", "TARGETS", "Guam") in rels


def test_linking_a_campaign_to_intrusions_is_not_the_analysts_attribution():
    rels = _rels(DOC_3)
    assert not {r for r in rels if r[1] == "ATTRIBUTED_TO" and r[0] == "Microsoft"}


def test_a_model_synonym_keeps_its_type_and_an_unknown_type_is_not_stored_as_an_association():
    from intel_platform.services.extraction import _normalize_rel_type

    # From Cohere's replies on the corpus: "ostravik (A-411) berth at quay 4".
    assert _normalize_rel_type("BERTHS_AT") == "LOCATED_AT"
    assert _normalize_rel_type("located in") == "LOCATED_AT"
    assert _normalize_rel_type("occurred-in") == "LOCATED_AT"
    assert _normalize_rel_type("TARGETED") == "TARGETS"
    assert _normalize_rel_type("member_of") == "BELONGS_TO"
    assert _normalize_rel_type("uses") == "USES"
    assert _normalize_rel_type("ASSOCIATED_WITH") == "ASSOCIATED_WITH"
    # "Source REPORTED Ostravik", "Imagery DOES_NOT_ESTABLISH Intent": a
    # statement about the reporting, not a relationship between the entities,
    # and calling it an association asserts what the model did not.
    for reporting in ("REPORTED", "OBSERVED", "IDENTIFIED", "DOES_NOT_ESTABLISH", "UNABLE_TO_ESTABLISH_DESTINATION",
                      "CANNOT_BE_EXCLUDED", "CORROBORATES", "INDICATES", "PUBLISHED", "BASED_ON"):
        assert _normalize_rel_type(reporting) is None, reporting
    # A relationship between the entities that the vocabulary has no word for
    # is still one: it stays the generic association it always was.
    assert _normalize_rel_type("PARTNERS_WITH") == "ASSOCIATED_WITH"
    assert _normalize_rel_type("") == "ASSOCIATED_WITH"


async def test_the_llm_path_keeps_the_synonym_and_drops_the_off_vocabulary_edge():
    import json
    from unittest.mock import AsyncMock, patch

    from intel_platform.llm.base import LLMResponse
    from intel_platform.services import extraction

    reply = {
        "entities": [
            {"name": "Ostravik", "entity_type": "Ship", "confidence": 0.9},
            {"name": "Torvik", "entity_type": "Location", "confidence": 0.9},
            {"name": "Source", "entity_type": "Person", "confidence": 0.7},
        ],
        "relationships": [
            {"source_entity": "Ostravik", "target_entity": "Torvik", "relationship_type": "BERTHS_AT",
             "confidence": 0.9},
            {"source_entity": "Source", "target_entity": "Ostravik", "relationship_type": "REPORTED",
             "confidence": 0.8},
        ],
    }

    class _Reply:
        async def generate(self, **_kw):
            return LLMResponse(content=json.dumps(reply), model="fake")

    with patch("intel_platform.llm.providers._get_extraction_provider", new=AsyncMock(return_value=_Reply())):
        result = await extraction.extract_entities_llm("Ostravik berths at Torvik.", "doc-fix")
    assert result.degraded is False
    assert [(r["source_name"], r["rel_type"], r["target_name"]) for r in result[1]] == [
        ("Ostravik", "LOCATED_AT", "Torvik"),
    ]
    assert result.skipped_items == 0, "an off-vocabulary type is not a malformed item"


# ── Vessels ───────────────────────────────────────────────────────────────────
# Forty of the corpus's gold entities are vessels; NLP typed none of them a
# Ship (Person 21, Organization 16) and missed some entirely.

KES_0008 = (
    "1. Imagery of Torvik collected during the period shows that hallgrim (A-425) arrives Torvik from Nyhavn, "
    "berths quay 5.\n\n2. Entities identified in this reporting: Hallgrim (A-425), 3rd Naval Auxiliary Group."
)


def test_a_name_with_a_hull_number_is_a_ship():
    types = _types(KES_0008)
    assert types.get("Hallgrim") == "Ship"
    assert "A-425" not in types


def test_a_vessel_arriving_at_a_port_is_located_there():
    assert ("Hallgrim", "LOCATED_AT", "Torvik") in _rels(KES_0008)


def test_a_name_after_a_vessel_noun_is_a_ship():
    types = _types(
        "1. Source reported on own initiative that commercial bulk carrier Mirenda loads aggregate at quay 1.\n\n"
        "2. Entities identified in this reporting: Mirenda, Torvik Harbour Authority."
    )
    assert types["Mirenda"] == "Ship"
    assert types["Torvik Harbour Authority"] == "Organization"
    types = _types(
        "1. Liaison reporting received during the period states that escort tasking was passed to patrol "
        "vessels Brenna and Sarn for a movement not yet timed."
    )
    assert types.get("Brenna") == "Ship" and types.get("Sarn") == "Ship"


def test_a_ship_of_a_unit_belongs_to_it():
    rels = _rels(
        "1. Partner service reporting passed by liaison indicates that torvald (A-430) of 2nd Naval Auxiliary "
        "Group loads at Nyhavn.\n\n2. Entities identified in this reporting: Torvald (A-430), 2nd Naval "
        "Auxiliary Group."
    )
    assert ("Torvald", "BELONGS_TO", "2nd Naval Auxiliary Group") in rels


def test_carriers_and_annexes_that_are_not_ships_stay_what_they_were():
    types = _types("The telecommunications carrier Verizon restored service. See Annex (A-12) for the order.")
    assert types.get("Verizon") != "Ship"
    assert types.get("Annex") != "Ship"


def test_a_unit_written_with_its_designator_in_brackets_is_not_a_ship():
    from intel_platform.services.extraction import _hull_numbers

    text = "Combined Task Force (CTF-150) and the Harbour Authority (HA-12) met Ostravik (A-411)."
    assert _hull_numbers(text) == [("Ostravik", "A-411")]


def test_the_vessel_evidence_retypes_what_the_model_called_a_person():
    from intel_platform.services.extraction import _apply_vessel_hints

    text = "Commercial and press reporting states that commercial bulk carrier Mirenda loads aggregate at quay 1."
    ents = _apply_vessel_hints([
        {"name": "Mirenda", "entity_type": "Person"}, {"name": "quay 1", "entity_type": "Location"},
    ], text)
    assert [e["entity_type"] for e in ents] == ["Ship", "Location"]


async def test_hybrid_does_not_add_the_hull_numbered_vessel_twice():
    import json
    from unittest.mock import AsyncMock, patch

    from intel_platform.llm.base import LLMResponse
    from intel_platform.services import extraction

    reply = {"entities": [{"name": "Hallgrim (A-425)", "entity_type": "Ship", "confidence": 0.9},
                          {"name": "Torvik", "entity_type": "Location", "confidence": 0.9}],
             "relationships": []}

    class _Reply:
        async def generate(self, **_kw):
            return LLMResponse(content=json.dumps(reply), model="fake")

    with patch("intel_platform.llm.providers._get_extraction_provider", new=AsyncMock(return_value=_Reply())):
        ents, _ = await extraction.extract_entities_hybrid(KES_0008, "doc-fix")
    names = [e["name"] for e in ents]
    assert "Hallgrim (A-425)" in names
    assert "Hallgrim" not in names, names


async def test_hybrid_points_an_nlp_edge_at_the_entity_its_endpoint_merged_into():
    import json
    from unittest.mock import AsyncMock, patch

    from intel_platform.llm.base import LLMResponse
    from intel_platform.services import extraction

    reply = {"entities": [{"name": "Hallgrim (A-425)", "entity_type": "Ship", "confidence": 0.9},
                          {"name": "Torvik", "entity_type": "Location", "confidence": 0.9}],
             "relationships": []}

    class _Reply:
        async def generate(self, **_kw):
            return LLMResponse(content=json.dumps(reply), model="fake")

    with patch("intel_platform.llm.providers._get_extraction_provider", new=AsyncMock(return_value=_Reply())):
        ents, rels = await extraction.extract_entities_hybrid(KES_0008, "doc-fix")
    names = {e["name"] for e in ents}
    # The NLP edge named "Hallgrim", which is no longer an entity: the graph
    # build would have dropped it as naming something never extracted.
    assert ("Hallgrim (A-425)", "LOCATED_AT", "Torvik") in {
        (r["source_name"], r["rel_type"], r["target_name"]) for r in rels
    }
    assert all(r["source_name"] in names and r["target_name"] in names for r in rels)


# ── Dates that date nothing ───────────────────────────────────────────────────
# NLP returned 25 Dates on the corpus against 3 in the gold: durations and
# relative spans ("6 months", "3 days earlier", "quarterly"). None can date an
# event, and every one becomes an orphan the graph build discards.

def test_durations_and_relative_spans_are_not_dates():
    entities, _ = extract_entities_nlp(
        "Source assessed approximately 20 personnel involved, which source described as without precedent in "
        "6 months of access. Comparison against imagery of 3 days earlier shows 20 additional objects. "
        "The routine quarterly maintenance period ended the same day.",
        "doc-fix",
    )
    assert not [e for e in entities if e["entity_type"] == "Date"]


def test_a_day_month_year_date_is_not_also_extracted_as_its_month_and_year():
    entities, _ = extract_entities_nlp(DOC_1, "doc-fix")
    assert {e["name"] for e in entities if e["entity_type"] == "Date"} == {"2023", "24 May 2023"}


def test_the_model_dates_that_date_nothing_go_with_their_edges():
    from intel_platform.services.extraction import _drop_undatable_dates

    entities = [{"name": n, "entity_type": "Date"} for n in ("1742Z", "Period", "Second Night",
                                                             "15-18 August", "Q1 2026", "24 May 2023")]
    entities.append({"name": "activity passed at 1742Z", "entity_type": "Event"})
    rels = [{"source_name": "activity passed at 1742Z", "target_name": "1742Z", "rel_type": "OCCURRED_ON"},
            {"source_name": "activity passed at 1742Z", "target_name": "Q1 2026", "rel_type": "OCCURRED_ON"}]
    entities, rels = _drop_undatable_dates(entities, rels)
    assert {e["name"] for e in entities if e["entity_type"] == "Date"} == {"15-18 August", "Q1 2026", "24 May 2023"}
    assert [r["target_name"] for r in rels] == ["Q1 2026"]


# ── Words that are not names ──────────────────────────────────────────────────

def test_an_adjectival_nationality_is_not_an_organization():
    types = _types("Valdorian naval liaison passed that liaison partner reporting corroborates the airframe type.")
    assert "Valdorian" not in types
    types = _types(
        "Communications passed in the clear establish that interference ceases for 36 hours, coinciding with "
        "a Ravenskan hydrographic survey transit.\n\nEntities identified in this reporting: RVK Hydrographic "
        "Service, Lysgard."
    )
    assert "Ravenskan" not in types
    assert types.get("RVK Hydrographic Service") == "Organization"


def test_a_group_named_in_front_of_its_fighters_is_still_extracted():
    types = _types("Taliban fighters attacked the post while the Taliban seized Kabul.")
    assert "Taliban" in types


def test_a_lower_case_common_noun_is_not_a_person():
    assert "liaison" not in _types("Valdorian naval liaison passed that liaison partner reporting corroborates it.")


def test_signal_and_navigation_acronyms_are_not_organizations():
    types = _types(
        "Publicly available shipping data indicate that product tanker Stellar Vane ceases AIS transmission "
        "for 14 hours, and merchant traffic reports GNSS position jumps and VHF interference in the approaches."
    )
    assert not {"AIS", "GNSS", "VHF"} & set(types)
    assert types.get("Stellar Vane") == "Ship"


# ── What the model is asked for ───────────────────────────────────────────────
# On the corpus the model returned 384 entities for 132 gold: "Source",
# "Partner", "Quay 4", "gap in collection", "Imagery collection of Torvik".
# The prompt told it to "err on the side of inclusion".

def _extraction_prompt() -> str:
    from intel_platform.llm.skills.loader import SkillsLoader

    return SkillsLoader().get_system_prompt("entity_extraction") or ""


def test_the_prompt_asks_for_named_entities_not_everything():
    prompt = _extraction_prompt()
    assert "err on the side of inclusion" not in prompt
    for excluded in ("the source", "berth 7", "0930Z", "12 vehicles", "unloading activity"):
        assert excluded in prompt, excluded


def test_the_prompt_types_vessels_and_tools_and_forbids_invented_relationship_types():
    prompt = _extraction_prompt()
    assert "(F-231)" in prompt and "`Ship`" in prompt
    assert "certutil" in prompt and "`Software`, not `TTP`" in prompt
    assert '"REPORTED"' in prompt  # named as a type not to invent


def test_the_prompt_examples_are_not_taken_from_the_eval_corpus():
    """Examples lifted from the documents being scored would score the prompt,
    not the extractor."""
    import json
    from pathlib import Path

    prompt = _extraction_prompt()
    fixtures = Path(__file__).resolve().parents[1] / "fixtures"
    names = set()
    for d in ("extraction_corpus", "extraction_corpus_cyber", "extraction_corpus_openrep"):
        for f in (fixtures / d).glob("*_expected.json"):
            for e in json.loads(f.read_text(encoding="utf-8"))["entities"]:
                names.update(n for n in [e["name"], *e.get("aliases", [])] if len(n) > 4)
    # Names the prompt already used before the corpus existed (its cyber
    # example's C2 address is also the one the live-run documents reused; its
    # polarity and coreference examples name the Houthis and Putin, and its
    # geopolitical example a March 2026 date, before openrep was a set).
    names -= {"China", "NATO", "Brussels", "T1059.001", "185.220.101.42",
              "Ansar Allah", "Houthi", "Putin", "Vladimir Putin", "Russia", "March 2026", "February 2026"}
    leaked = sorted(n for n in names if n in prompt)
    assert not leaked, leaked


async def test_a_defanged_indicator_from_the_model_leaves_extraction_refanged():
    """Cohere returned "evil-c2[.]com" as written; graph_builder's host check
    raises on the bracket, and the whole build failed."""
    import json
    from unittest.mock import AsyncMock, patch

    from intel_platform.llm.base import LLMResponse
    from intel_platform.services import extraction

    reply = {
        "entities": [{"name": "Volt Typhoon", "entity_type": "ThreatActor", "confidence": 0.9},
                     {"name": "evil-c2[.]com", "entity_type": "Domain", "confidence": 0.9}],
        "relationships": [{"source_entity": "Volt Typhoon", "target_entity": "evil-c2[.]com",
                           "relationship_type": "COMMUNICATES_WITH", "confidence": 0.8}],
    }

    class _Reply:
        async def generate(self, **_kw):
            return LLMResponse(content=json.dumps(reply), model="fake")

    with patch("intel_platform.llm.providers._get_extraction_provider", new=AsyncMock(return_value=_Reply())):
        ents, rels = await extraction.extract_entities_llm(DOC_1, "doc-fix")
    domain = next(e for e in ents if e["entity_type"] == "Domain")
    assert domain["name"] == "evil-c2.com"
    assert "evil-c2[.]com" in domain["aliases"]
    assert [(r["source_name"], r["target_name"]) for r in rels] == [("Volt Typhoon", "evil-c2.com")]


def test_place_subtypes_the_model_invents_are_locations():
    from intel_platform.services.extraction import _normalize_llm_entity_type

    # "Kirvo airfield" came back typed "Airfield": no such graph type, so it
    # would land as Custom.
    for raw in ("Airfield", "airport", "Harbour", "Naval Base", "Strait", "Peninsula", "Coast"):
        assert _normalize_llm_entity_type(raw) == "Location", raw


# ── Replies that parse to nothing ─────────────────────────────────────────────
# openrep-deep: Cohere's reply for the Burkina Faso chunk ended
# `..."relationships": [], "entities": []}` after the full lists, and json.loads
# kept the last of each duplicate key — 17 entities scored as none extracted.
# Its reply for the Navy-lasers chunk ran past the token limit, so nothing
# parsed and the chunk degraded to NLP.

async def _llm_reply(content: str, text: str = "Russia supplied weapons to Burkina Faso."):
    from unittest.mock import AsyncMock, patch

    from intel_platform.llm.base import LLMResponse
    from intel_platform.services import extraction

    class _Reply:
        async def generate(self, **_kw):
            return LLMResponse(content=content, model="fake")

    with patch("intel_platform.llm.providers._get_extraction_provider", new=AsyncMock(return_value=_Reply())):
        return await extraction.extract_entities_llm(text, "doc-fix")


async def test_a_reply_that_repeats_its_keys_keeps_what_it_extracted():
    content = (
        '{"entities": [{"name": "Burkina Faso", "entity_type": "Country"}, {"name": "Russia", "entity_type": '
        '"Country"}], "relationships": [{"source_entity": "Burkina Faso", "target_entity": "Russia", '
        '"relationship_type": "SUPPLIED_BY"}], "relationships": [], "entities": []}'
    )
    result = await _llm_reply(content)
    assert result.degraded is False
    assert {e["name"] for e in result[0]} >= {"Burkina Faso", "Russia"}
    assert [(r["source_name"], r["rel_type"]) for r in result[1]] == [("Burkina Faso", "SUPPLIED_BY")]


async def test_a_reply_cut_off_at_the_token_limit_keeps_its_complete_items():
    content = (
        '```json\n{\n  "entities": [\n    {"name": "Northrop Grumman", "entity_type": "Organization"},\n'
        '    {"name": "Portland", "entity_type": "Ship", "aliases": ["LPD-27"]},\n'
        '    {"name": "LWSD", "entity_type": "Wea'
    )
    result = await _llm_reply(content, "Northrop Grumman built the LWSD installed on Portland (LPD-27).")
    assert result.degraded is False and result.method == "llm"
    assert {e["name"] for e in result[0] if e.get("method") == "llm"} == {"Northrop Grumman", "Portland"}


def test_llm_output_merges_repeated_list_keys_only_when_asked():
    from intel_platform.services.llm_output import json_object

    reply = '{"entities": [1, 2], "note": "a", "entities": [], "note": ""}'
    assert json_object(reply) == {"entities": [], "note": ""}
    assert json_object(reply, merge_duplicate_lists=True) == {"entities": [1, 2], "note": "a"}


def test_llm_output_reads_the_complete_items_of_a_cut_off_array():
    from intel_platform.services.llm_output import json_array_items

    cut = '{"relationships": [ {"a": "{x}"} , {"b": 2},\n {"c": [1, {"d": 3}]}, {"e": "unterminated'
    assert json_array_items(cut, "relationships") == [{"a": "{x}"}, {"b": 2}, {"c": [1, {"d": 3}]}]
    assert json_array_items('{"entities": []}', "entities") == []
    assert json_array_items("no array here", "entities") == []


async def test_a_list_reply_with_no_keys_still_degrades():
    result = await _llm_reply('[{"name": "Russia", "entity_type": "Country"}]')
    assert result.degraded is True


# ── Relationships analytic prose states without a verb ────────────────────────
# NLP found 1 of the 73 openrep gold edges. Most are written as a possessive,
# a title, or an action noun rather than a subject-verb-object clause.

def test_a_possessive_body_belongs_to_its_possessor():
    rels = _rels("In April 2025, Poland's Internal Security Agency reported that the agency had detained 44 people.")
    assert ("Internal Security Agency", "BELONGS_TO", "Poland") in rels
    rels = _rels("Officials from DOJ's National Security Division and the FBI testified.")
    assert ("National Security Division", "BELONGS_TO", "DOJ") in rels


def test_a_title_ties_a_person_to_the_country_or_body_it_names():
    rels = _rels("There, he held talks with Russian President Vladimir Putin and voiced support for Russia's war.")
    assert ("Vladimir Putin", "BELONGS_TO", "Russia") in rels
    rels = _rels(
        "In November 2025, for example, Kaja Kallas, High Representative of the European Union (EU) for Foreign "
        "Affairs and Security Policy, stated that Russia is committing state-sponsored terrorism. In an October "
        "2025 speech, European Commission President Ursula von der Leyen stated that it is hybrid warfare."
    )
    assert ("Kaja Kallas", "BELONGS_TO", "European Union") in rels
    # en_core_web_sm cuts the name at "der"; the relation still binds.
    assert {r for r in rels if r[0].startswith("Ursula von der") and r[1:] == ("BELONGS_TO", "European Commission")}


def test_a_commander_title_is_the_command_relationship_the_right_way_round():
    rels = _rels(
        "According to congressional testimony in March 2026 by General Alexus G. Grynkewich, Commander of U.S. "
        "European Command and NATO Supreme Allied Commander Europe, the Russian activity is robust."
    )
    assert ("U.S. European Command", "COMMANDED_BY", "Alexus G. Grynkewich") in rels


def test_an_invasion_of_a_country_targets_it():
    rels = _rels("The Russian Federation (Russia) launched a full-scale invasion of Ukraine in February 2022.")
    assert ("Russia", "TARGETS", "Ukraine") in rels or ("Russian Federation", "TARGETS", "Ukraine") in rels
    rels = _rels(
        "In April and October 2024, Iran used ballistic missiles to directly attack Israel. Subsequent Israeli "
        "strikes on Iran destroyed Iran's ability to produce ballistic missiles for a year."
    )
    assert ("Israel", "TARGETS", "Iran") in rels


def test_supplying_points_from_recipient_to_supplier():
    rels = _rels("Iran has transferred close-range ballistic missiles to Russia, according to U.S. officials.")
    assert ("Russia", "SUPPLIED_BY", "Iran") in rels
    assert ("Iran", "SUPPLIED_BY", "Russia") not in rels
    rels = _rels("Iran has also provided the Houthis with components and technical knowledge to construct missiles.")
    assert ("Houthis", "SUPPLIED_BY", "Iran") in rels


def test_a_backed_group_is_funded_by_its_backer():
    rels = _rels("Iran-backed Houthi movement has attacked Saudi Arabia-linked vessels and energy targets.")
    assert ("Houthi", "FUNDED_BY", "Iran") in rels
    # The subject is the movement the phrase names, not the backer inside it.
    assert ("Houthi", "TARGETS", "Saudi Arabia") in rels
    assert ("Iran", "TARGETS", "Saudi Arabia") not in rels


def test_a_military_presence_in_a_place_is_deployment_there():
    rels = _rels("Highly likely that NATO is significantly increasing its military presence in the Arctic.")
    assert ("NATO", "DEPLOYED_AT", "Arctic") in rels


# ── Acronym bodies and named documents ────────────────────────────────────────

def test_a_single_word_acronym_organization_is_kept_and_a_heading_is_not():
    types = _types("Meanwhile, in October 2024, NORTHCOM conducted the Falcon Peak exercise. BACKGROUND")
    assert types.get("NORTHCOM") == "Organization"
    assert "BACKGROUND" not in types
    types = _types("BOTTOM LINE UP FRONT: Highly likely that NATO is increasing its presence.")
    assert not [n for n in types if n.isupper() and " " in n]


def test_executive_orders_and_acts_are_documents():
    types = _types(
        "President Donald J. Trump introduced the initiative in Executive Order (E.O.) 14186, dated January 27, "
        "2025. E.O. 13871 (May 8, 2019), blocking transactions and trade related to Iran's iron sectors."
    )
    assert types.get("Executive Order (E.O.) 14186") == "Document"
    assert types.get("E.O. 13871") == "Document"
    assert "14186" not in types
    types = _types(
        "Congress granted SLTT law enforcement and correctional agencies authority through the FY2026 NDAA to "
        "engage in actions. The 2025 Worldwide Threat Assessment stated that Iran has fielded missiles."
    )
    assert types.get("FY2026 NDAA") == "Document"
    assert types.get("Worldwide Threat Assessment") == "Document"


# ── Designators, named exercises, and place names spaCy cuts in two ───────────

def test_ship_class_designators_are_ships_and_missile_designators_weapons():
    types = _types(
        "The Navy's current amphibious ship force includes the so-called big-deck amphibious assault ships, "
        "designated LHA and LHD, and the smaller amphibious ships, designated LPD or LSD."
    )
    assert {types.get("LHA"), types.get("LHD"), types.get("LPD")} == {"Ship"}
    types = _types(
        "DIA stated that missiles fielded by Yemen's Houthis were likely based on Iranian designs, including "
        "Iran's Qiam-1, Fateh-110, and Shahab-3 missiles."
    )
    assert types.get("Qiam-1") == "Weapon"


def test_the_models_equipment_typed_ship_class_is_a_ship():
    from intel_platform.services.extraction import _apply_type_hints

    ents = _apply_type_hints([{"name": "LHD", "entity_type": "Equipment"}, {"name": "Covid-19", "entity_type": ""},
                              {"name": "Shahed-136", "entity_type": "Drone"}])
    assert [e["entity_type"] for e in ents] == ["Ship", "", "Drone"]


def test_a_name_before_exercise_is_an_event():
    types = _types("Meanwhile, in October 2024, NORTHCOM conducted the Falcon Peak exercise that sought to evaluate "
                   "counter-UAS solutions.")
    assert types.get("Falcon Peak") == "Event"


def test_a_known_waterway_is_one_location_not_two_fragments():
    types = _types(
        "Iran's disruption of commercial shipping has reduced transit through the Strait of Hormuz, a crucial "
        "conduit for energy resources and other commodities to reach global markets."
    )
    assert types.get("Strait of Hormuz") == "Location"
    assert "Hormuz" not in types and "Strait of" not in types


# ── Types the model invents ───────────────────────────────────────────────────

def test_abstract_types_outside_the_vocabulary_are_not_entities():
    from intel_platform.services.extraction import _drop_abstract_types

    # From Cohere's openrep replies.
    ents = [
        {"name": "uranium enrichment program", "entity_type": "Program"},
        {"name": "B2", "entity_type": "Indicator"}, {"name": "fissile material", "entity_type": "Material"},
        {"name": "European security", "entity_type": "Concept"},
        {"name": "Commercial reporting", "entity_type": "DataSource"},
        {"name": "Iran", "entity_type": "Location"},
    ]
    rels = [{"source_name": "Iran", "target_name": "uranium enrichment program", "rel_type": "USES"}]
    ents, rels = _drop_abstract_types(ents, rels)
    assert [e["name"] for e in ents] == ["Iran"]
    assert rels == []


def test_a_ship_class_the_model_calls_equipment_is_a_ship():
    from intel_platform.services.extraction import _apply_type_hints

    ents = _apply_type_hints([
        {"name": "Constellation-class frigate", "entity_type": "Equipment"},
        {"name": "Medium Landing Ship (LSM) program", "entity_type": "Equipment"},
        {"name": "Cargo", "entity_type": "Equipment"},
        {"name": "Class Action Group", "entity_type": "Organization"},
    ])
    assert [e["entity_type"] for e in ents] == ["Ship", "Ship", "Equipment", "Organization"]


# ── The head word decides ─────────────────────────────────────────────────────

def test_a_name_ending_in_a_weapon_noun_is_a_weapon():
    types = _types(
        "Finally, Japan is developing the Hypersonic Cruise Missile (HCM) and the Hyper Velocity Gliding "
        "Projectile (HVGP). Japan is procuring the Tomahawk Weapon System for an estimated $2.9 billion."
    )
    assert types.get("Hypersonic Cruise Missile") == "Weapon"
    assert types.get("Hyper Velocity Gliding Projectile") == "Weapon"
    assert types.get("Tomahawk Weapon System") == "Weapon"


def test_a_company_or_council_named_after_the_gulf_is_an_organization():
    types = _types(
        "In September 2025, the Khafji Joint Operations Company, a joint company of Saudi Aramco Gulf Operations "
        "Company and Kuwait Gulf Oil Company, issued tenders. Gulf Cooperation Council and Yemen. Ships crossed "
        "the Persian Gulf."
    )
    assert types.get("Kuwait Gulf Oil Company") == "Organization"
    assert types.get("Saudi Aramco Gulf Operations Company") == "Organization"
    assert types.get("Persian Gulf") == "Location"


# ── An acronym defined in brackets is the same entity ─────────────────────────

def test_an_acronym_defined_in_brackets_is_an_alias_not_a_second_entity():
    text = (
        "The Department of the Treasury's Office of Foreign Assets Control (OFAC) issued a new set of Frequently "
        "Asked Questions. On June 27, 2018, OFAC began a wind-down of the importation of Iranian-origin carpets."
    )
    entities, rels = extract_entities_nlp(text, "doc-fix")
    by_name = {e["name"]: e for e in entities}
    assert "OFAC" not in by_name
    assert "OFAC" in by_name["Office of Foreign Assets Control"].get("aliases", [])
    assert ("Office of Foreign Assets Control", "BELONGS_TO", "Department of the Treasury") in {
        (r["source_name"], r["rel_type"], r["target_name"]) for r in rels
    }


def test_a_bracketed_aside_that_is_not_an_acronym_is_left_alone():
    entities, _ = extract_entities_nlp("Iran launched a missile at Israel (Tel Aviv) in April 2024.", "doc-fix")
    names = {e["name"] for e in entities}
    assert "Tel Aviv" in names and "Israel" in names


def test_the_group_is_not_resolved_without_an_actor_to_resolve_to():
    rels = _rels("The group used the Fortinet vulnerability CVE-2023-27997.")
    assert not {r for r in rels if r[1] == "EXPLOITS"}


# ── Hybrid keeps one node for a name the model already gave as an alias ───────
# openrep: the model returned "U.S. Navy" (alias "Navy"), "Department of
# Defense" (alias "DOD") and "Executive Order 14347" (alias "E.O. 14347"); NLP
# found "Navy", "DOD" and "E.O. 14347", and hybrid kept both of each pair.

CRS_IF13264 = (
    "The Golden Dome for America refers to an integrated homeland air and missile defense system being developed "
    "by the Department of Defense (DOD), which is \"using a secondary Department of War designation\" under "
    "Executive Order (E.O.) 14347, dated September 5, 2025. Guetlein reports directly to the Deputy Secretary of "
    "Defense (who is using \"Deputy Secretary of War\" as a \"secondary title\" under E.O. 14347). The Navy's "
    "current amphibious ship force consists of larger amphibious ships."
)


def test_an_executive_order_written_two_ways_is_one_document_carrying_both():
    entities, _ = extract_entities_nlp(CRS_IF13264, "doc-fix")
    orders = [e for e in entities if "14347" in e["name"]]
    assert [e["name"] for e in orders] == ["Executive Order (E.O.) 14347"]
    assert orders[0]["entity_type"] == "Document"
    assert {"E.O. 14347", "Executive Order 14347"} <= set(orders[0].get("aliases") or [])


async def test_hybrid_merges_an_nlp_entity_named_by_one_of_the_models_aliases():
    import json
    from unittest.mock import AsyncMock, patch

    from intel_platform.llm.base import LLMResponse
    from intel_platform.services import extraction

    reply = {"entities": [
        {"name": "U.S. Navy", "entity_type": "Organization", "aliases": ["Navy"], "confidence": 0.95},
        {"name": "Department of Defense", "entity_type": "Organization", "aliases": ["DOD"], "confidence": 0.95},
        {"name": "Executive Order 14347", "entity_type": "Document", "aliases": ["E.O. 14347"], "confidence": 0.95},
    ], "relationships": []}

    class _Reply:
        async def generate(self, **_kw):
            return LLMResponse(content=json.dumps(reply), model="fake")

    with patch("intel_platform.llm.providers._get_extraction_provider", new=AsyncMock(return_value=_Reply())):
        ents, _ = await extraction.extract_entities_hybrid(CRS_IF13264, "doc-fix")
    names = [e["name"] for e in ents]
    for duplicate in ("Navy", "DOD", "E.O. 14347", "Executive Order (E.O.) 14347"):
        assert duplicate not in names, names
    assert {"U.S. Navy", "Department of Defense", "Executive Order 14347"} <= set(names)


async def test_hybrid_keeps_the_nlp_entity_a_kept_nlp_edge_names():
    # openrep crs-IF13264: the model listed Guetlein but not the U.S. Space
    # Force. Hybrid kept NLP's BELONGS_TO edge and not its endpoint, so the
    # graph build dropped the edge as naming something never extracted.
    import json
    from unittest.mock import AsyncMock, patch

    from intel_platform.llm.base import LLMResponse
    from intel_platform.services import extraction

    text = (
        "Golden Dome's development is managed by DOD's Office of Golden Dome for America, led by Senate-confirmed "
        "U.S. Space Force General Michael A. Guetlein, who reports directly to the Deputy Secretary of Defense."
    )
    reply = {"entities": [
        {"name": "Michael A. Guetlein", "entity_type": "Person", "confidence": 0.95},
        {"name": "Office of Golden Dome for America", "entity_type": "Organization", "confidence": 0.95},
    ], "relationships": []}

    class _Reply:
        async def generate(self, **_kw):
            return LLMResponse(content=json.dumps(reply), model="fake")

    with patch("intel_platform.llm.providers._get_extraction_provider", new=AsyncMock(return_value=_Reply())):
        ents, rels = await extraction.extract_entities_hybrid(text, "doc-fix")
    names = {e["name"] for e in ents}
    assert ("Michael A. Guetlein", "BELONGS_TO", "U.S. Space Force") in {
        (r["source_name"], r["rel_type"], r["target_name"]) for r in rels
    }
    assert "U.S. Space Force" in names
    assert all(r["source_name"] in names and r["target_name"] in names for r in rels)


# ── Generic associations: a shared sentence and nothing typed between them ────
# openrep: NLP emitted ASSOCIATED_WITH between entities spaCy's sentence joined
# across a heading ("China" + "In addition, South Korea ..."), and on pairs a
# typed relation linked later in the text; the model emitted it on pairs it
# also related by type.

KES_0173 = (
    "1. Partner service reporting passed by liaison indicates that torvald (A-430) of 2nd Naval Auxiliary Group "
    "loads at Nyhavn.\n\n2. Entities identified in this reporting: Torvald (A-430), 2nd Naval Auxiliary Group."
)


def _generic(rels) -> set[frozenset[str]]:
    return {frozenset((r["source_name"], r["target_name"])) for r in rels if r["rel_type"] == "ASSOCIATED_WITH"}


def test_no_generic_edge_on_a_pair_a_typed_relation_links_anywhere_in_the_text():
    _, rels = extract_entities_nlp(KES_0173, "doc-fix")
    assert ("Torvald", "BELONGS_TO", "2nd Naval Auxiliary Group") in {
        (r["source_name"], r["rel_type"], r["target_name"]) for r in rels}
    # The entity line in paragraph 2 co-mentions the pair; the typed edge is
    # read from paragraph 1 after every sentence has been seen.
    assert frozenset(("Torvald", "2nd Naval Auxiliary Group")) not in _generic(rels)


def test_a_heading_line_does_not_share_a_sentence_with_the_text_below_it():
    # openrep crs-R45811_29: spaCy reads the heading "China" and the first
    # sentence under it as one sentence.
    text = (
        "China\n\nIn addition, South Korea reportedly has been developing a ground-launched Mach 6+ hypersonic "
        "cruise missile, Hycore, since 2018."
    )
    _, rels = extract_entities_nlp(text, "doc-fix")
    assert frozenset(("China", "South Korea")) not in _generic(rels)


def test_entities_in_one_sentence_with_nothing_typed_between_them_keep_the_generic_edge():
    _, rels = extract_entities_nlp(
        "In addition, South Korea reportedly has been developing a ground-launched Mach 6+ hypersonic cruise "
        "missile, Hycore, since 2018, and Japan is procuring the Tomahawk Weapon System.", "doc-fix")
    assert _generic(rels), "co-occurrence still links what one sentence names together"


async def test_the_models_generic_edge_on_a_pair_nlp_reads_as_typed_is_dropped():
    # openrep OPENREP-SUPINTREP-0010: the model returned Russia ASSOCIATED_WITH
    # Ukraine for "Russia's 2022 invasion of Ukraine", which NLP reads as
    # TARGETS; hybrid kept both.
    import json
    from unittest.mock import AsyncMock, patch

    from intel_platform.llm.base import LLMResponse
    from intel_platform.services import extraction

    text = ("Some of these operations have been hampered by the expulsion of Russian diplomats from Europe and the "
            "United States following Russia's 2022 invasion of Ukraine.")
    reply = {
        "entities": [{"name": "Russia", "entity_type": "Country"}, {"name": "Ukraine", "entity_type": "Country"},
                     {"name": "Europe", "entity_type": "Region"}],
        "relationships": [{"source_entity": "Russia", "target_entity": "Ukraine",
                           "relationship_type": "ASSOCIATED_WITH", "evidence": "Russia's 2022 invasion of Ukraine"}],
    }

    class _Reply:
        async def generate(self, **_kw):
            return LLMResponse(content=json.dumps(reply), model="fake")

    with patch("intel_platform.llm.providers._get_extraction_provider", new=AsyncMock(return_value=_Reply())):
        _, rels = await extraction.extract_entities_hybrid(text, "doc-fix")
    triples = {(r["source_name"], r["rel_type"], r["target_name"]) for r in rels}
    assert ("Russia", "TARGETS", "Ukraine") in triples
    assert frozenset(("Russia", "Ukraine")) not in _generic(rels)


async def test_the_models_generic_edge_beside_its_own_typed_edge_is_dropped():
    # openrep OPENREP-SUPINTREP-0042: Iran TARGETS, USES and ASSOCIATED_WITH
    # the Strait of Hormuz, all from the model.
    reply = (
        '{"entities": [{"name": "Iran", "entity_type": "Country"}, {"name": "Strait of Hormuz", "entity_type": '
        '"Strait"}], "relationships": [{"source_entity": "Iran", "target_entity": "Strait of Hormuz", '
        '"relationship_type": "TARGETS"}, {"source_entity": "Strait of Hormuz", "target_entity": "Iran", '
        '"relationship_type": "ASSOCIATED_WITH"}]}'
    )
    result = await _llm_reply(reply, "Iran has sought to formalise its de facto control over the Strait of Hormuz.")
    assert [(r["source_name"], r["rel_type"]) for r in result[1]] == [("Iran", "TARGETS")]


# ── Relationship endpoints must be listed entities ────────────────────────────
# openrep: 66 of hybrid's 882 edges named something the model never listed
# ("Ukrainian forces", "31 larger amphibious ships"); the graph build dropped
# them as unknown endpoints. The parser now resolves an endpoint to a listed
# entity by name or alias, and drops and counts the rest.

CRS_IN12534 = (
    "In 2026, Ukrainian forces have limited—and in some cases reversed—Russian gains and markedly expanded a "
    "campaign of long-range attacks against Russian oil facilities and logistics infrastructure."
)


async def test_an_edge_naming_an_unlisted_endpoint_is_dropped_and_counted():
    reply = (
        '{"entities": [{"name": "Russia", "entity_type": "Country"}, {"name": "2026", "entity_type": "Date"}], '
        '"relationships": [{"source_entity": "Ukrainian forces", "target_entity": "Russian oil facilities", '
        '"relationship_type": "TARGETS"}, {"source_entity": "Ukrainian forces", "target_entity": "Russia", '
        '"relationship_type": "TARGETS"}]}'
    )
    result = await _llm_reply(reply, CRS_IN12534)
    assert result[1] == []
    assert result.relationships_dropped_by_reason["unlisted_endpoint"] == 2
    assert result.meta["relationships_dropped_by_reason"]["unlisted_endpoint"] == 2


async def test_an_endpoint_named_by_an_alias_resolves_to_the_listed_entity():
    # openrep crs-R47390_22: the model listed "Dorra/Arash gas field" and named
    # it "Dorra Gas field" in an edge; the build dropped the edge.
    text = (
        "In September 2025, the Khafji Joint Operations Company, a joint company of Saudi Aramco Gulf Operations "
        "Company and Kuwait Gulf Oil Company, issued tenders related to project management for the development of "
        "the Dorra Gas field."
    )
    reply = (
        '{"entities": [{"name": "Khafji Joint Operations Company", "entity_type": "Company"}, '
        '{"name": "Dorra/Arash gas field", "entity_type": "Facility", "aliases": ["Dorra Gas field"]}], '
        '"relationships": [{"source_entity": "khafji joint operations company", "target_entity": "Dorra Gas field", '
        '"relationship_type": "LOCATED_AT"}]}'
    )
    result = await _llm_reply(reply, text)
    assert [(r["source_name"], r["target_name"]) for r in result[1]] == [
        ("Khafji Joint Operations Company", "Dorra/Arash gas field")]
    assert result.relationships_dropped_by_reason["unlisted_endpoint"] == 0


async def test_an_event_named_only_in_its_date_link_is_still_recovered():
    # The timeline depends on it: the event is minted from the OCCURRED_ON edge
    # (see _link_event_dates), so its edge has a listed endpoint.
    reply = (
        '{"entities": [{"name": "July 2025", "entity_type": "Date"}], "relationships": [{"source_entity": '
        '"Copper tariff", "target_entity": "July 2025", "relationship_type": "OCCURRED_ON"}]}'
    )
    result = await _llm_reply(reply, "The copper tariff took effect in July 2025.")
    assert [(r["source_name"], r["rel_type"]) for r in result[1]] == [("Copper tariff", "OCCURRED_ON")]
    assert {e["name"] for e in result[0]} >= {"Copper tariff", "July 2025"}


async def test_hybrid_resolves_a_model_endpoint_to_the_entity_nlp_extracted():
    # openrep OPENREP-SUPINTREP-0021: the model's NATO DEPLOYED_AT Europe (a gold
    # edge) named Europe without listing it; NLP extracted Europe.
    import json
    from unittest.mock import AsyncMock, patch

    from intel_platform.llm.base import LLMResponse
    from intel_platform.services import extraction

    text = ("NATO has responded by reorienting its strategic focus and defense posture, increasing its military "
            "presence in Europe, and institutionalizing long-term support for Ukraine.")
    reply = {"entities": [{"name": "NATO", "entity_type": "Organization"}, {"name": "Ukraine", "entity_type": "Country"}],
             "relationships": [{"source_entity": "NATO", "target_entity": "Europe", "relationship_type": "DEPLOYED_AT"},
                               {"source_entity": "NATO", "target_entity": "Allied capitals",
                                "relationship_type": "LOCATED_AT"}]}

    class _Reply:
        async def generate(self, **_kw):
            return LLMResponse(content=json.dumps(reply), model="fake")

    with patch("intel_platform.llm.providers._get_extraction_provider", new=AsyncMock(return_value=_Reply())):
        result = await extraction.extract_entities_hybrid(text, "doc-fix")
    ents, rels = result
    names = {e["name"] for e in ents}
    assert ("NATO", "DEPLOYED_AT", "Europe") in {(r["source_name"], r["rel_type"], r["target_name"]) for r in rels}
    assert "Europe" in names
    assert all(r["source_name"] in names and r["target_name"] in names for r in rels)
    assert result.relationships_dropped_by_reason["unlisted_endpoint"] == 1


# ── A country and its government are one entity ───────────────────────────────
# openrep: the model named "PRC government" and NLP "China" and "PRC"; a
# capital standing for the state ("Tehran asserts ...") was a city node. The
# gold makes one node per state with the other names as aliases.

def _llm_returning(reply: dict):
    import json
    from unittest.mock import AsyncMock, patch

    from intel_platform.llm.base import LLMResponse

    class _Reply:
        async def generate(self, **_kw):
            return LLMResponse(content=json.dumps(reply), model="fake")

    return patch("intel_platform.llm.providers._get_extraction_provider", new=AsyncMock(return_value=_Reply()))


async def test_the_prc_government_and_china_are_one_entity():
    # openrep crs-IF12640_5.
    from intel_platform.services import extraction

    text = ("The PRC government is also an indirect shareholder in some firms. China's anti-espionage, "
            "cybersecurity, and data security laws compel firms to support PRC state security authorities.")
    reply = {"entities": [{"name": "PRC government", "entity_type": "GovernmentAgency"},
                          {"name": "China", "entity_type": "Country"},
                          {"name": "ByteDance", "entity_type": "Company"}],
             "relationships": [{"source_entity": "ByteDance", "target_entity": "PRC government",
                                "relationship_type": "FUNDED_BY"},
                               {"source_entity": "PRC government", "target_entity": "China",
                                "relationship_type": "BELONGS_TO"}]}
    with _llm_returning(reply):
        result = await extraction.extract_entities_hybrid(text, "doc-fix")
    ents, rels = result
    states = [e for e in ents if e["name"] in ("China", "PRC", "PRC government")]
    assert [e["name"] for e in states] == ["China"], [e["name"] for e in ents]
    assert states[0]["entity_type"] == "Location"
    assert "PRC government" in states[0]["aliases"]
    assert [(r["source_name"], r["rel_type"], r["target_name"]) for r in rels] == [
        ("ByteDance", "FUNDED_BY", "China")]
    assert result.relationships_dropped_by_reason["same_entity"] == 1


async def test_the_kremlin_is_russia():
    # No corpus sentence names the Kremlin as an actor ("pro-Kremlin" is the
    # only form in openrep); the form is the plan's example.
    from intel_platform.services import extraction

    text = "The Kremlin denied that Russia had supplied the drones to the militia."
    reply = {"entities": [{"name": "the Kremlin", "entity_type": "GovernmentAgency"},
                          {"name": "Russia", "entity_type": "Country"}], "relationships": []}
    with _llm_returning(reply):
        ents, _ = await extraction.extract_entities_llm(text, "doc-fix")
    assert [(e["name"], e["entity_type"]) for e in ents] == [("Russia", "Location")]
    assert "the Kremlin" in ents[0]["aliases"]


def test_a_capital_acting_for_the_state_is_the_country():
    # openrep OPENREP-SUPINTREP-0037: "Tehran asserts ..." is Iran asserting.
    text = ("Highly likely that Iran halted its nuclear weapons program in late 2003 and has not reauthorized the "
            "development of nuclear weapons. Tehran asserts its enrichment program is only meant to produce fuel for "
            "peaceful nuclear applications.")
    entities, _ = extract_entities_nlp(text, "doc-fix")
    by_name = {e["name"]: e for e in entities}
    assert "Tehran" not in by_name
    assert by_name["Iran"]["entity_type"] == "Location"
    assert "Tehran" in by_name["Iran"].get("aliases", [])


def test_a_capital_used_as_a_place_stays_a_location():
    # openrep crs-R40094_15.
    text = ("Iran has not allowed the agency to service the cameras. [D]uring the discussions in Tehran as well as in "
            "Vienna, it was clearly indicated that since that Tessa Karaj Complex is still under security and judicial "
            "investigations, the equipment related to this Complex are not included for servicing.")
    entities, _ = extract_entities_nlp(text, "doc-fix")
    by_name = {e["name"]: e for e in entities}
    assert by_name["Tehran"]["entity_type"] == "Location"
    assert "Tehran" not in (by_name["Iran"].get("aliases") or [])


def test_the_regimes_in_two_capitals_are_their_states():
    # openrep crs-R45784_21: "the regimes in Minsk and Moscow".
    from intel_platform.services.extraction import _capital_metonyms

    text = ('Prime Minister Tusk has described these migration flows as "state-led operations involving the regimes '
            'in Minsk and Moscow."')
    assert _capital_metonyms(text) == {"Minsk", "Moscow"}
    assert _capital_metonyms("Kissinger made two secret visits to Beijing in 1971.") == set()


# ── What the prompt asks of relationships ─────────────────────────────────────

def test_the_prompt_requires_both_ends_of_a_relationship_to_be_listed_entities():
    prompt = _extraction_prompt()
    assert "must each be the `name` of an entity in your `entities` list" in prompt


def test_the_prompt_allows_a_generic_association_only_within_a_sentence_and_shows_one_it_must_not_make():
    prompt = _extraction_prompt()
    assert "same sentence names both entities" in prompt
    assert "Do not emit ASSOCIATED_WITH" in prompt
    assert "Negative example" in prompt


def test_the_prompts_own_examples_follow_its_relationship_rules():
    """Example 2 dated an event it never listed, on a date its text does not
    give, and pointed COMMANDED_BY from the person to the unit."""
    import json
    import re

    prompt = _extraction_prompt()
    blocks = [json.loads(b) for b in re.findall(r"```json\n(\{.*?\})\n\s*```", prompt, re.S)
              if '"source_entity": "string' not in b]
    assert len(blocks) >= 2
    for block in blocks:
        names = {e["name"] for e in block["entities"]}
        for r in block["relationships"]:
            assert {r["source_entity"], r["target_entity"]} <= names, r
            if r["relationship_type"] == "COMMANDED_BY":
                commander = next(e for e in block["entities"] if e["name"] == r["target_entity"])
                assert commander["entity_type"] in ("Person", "Commander"), r
