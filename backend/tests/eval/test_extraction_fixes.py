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
