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


def test_the_group_is_not_resolved_without_an_actor_to_resolve_to():
    rels = _rels("The group used the Fortinet vulnerability CVE-2023-27997.")
    assert not {r for r in rels if r[1] == "EXPLOITS"}
