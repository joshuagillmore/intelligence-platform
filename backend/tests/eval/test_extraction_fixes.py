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
    # "Source REPORTED Ostravik", "Imagery DOES_NOT_ESTABLISH Intent": no type
    # in the vocabulary, and calling them associations asserts what the model
    # did not.
    assert _normalize_rel_type("REPORTED") is None
    assert _normalize_rel_type("DOES_NOT_ESTABLISH") is None
    assert _normalize_rel_type("") is None


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
    for d in ("extraction_corpus", "extraction_corpus_cyber"):
        for f in (fixtures / d).glob("*_expected.json"):
            for e in json.loads(f.read_text(encoding="utf-8"))["entities"]:
                names.update(n for n in [e["name"], *e.get("aliases", [])] if len(n) > 4)
    # Names the prompt already used before the corpus existed (its cyber
    # example's C2 address is also the one the live-run documents reused).
    names -= {"China", "NATO", "Brussels", "T1059.001", "185.220.101.42"}
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


def test_the_group_is_not_resolved_without_an_actor_to_resolve_to():
    rels = _rels("The group used the Fortinet vulnerability CVE-2023-27997.")
    assert not {r for r in rels if r[1] == "EXPLOITS"}
