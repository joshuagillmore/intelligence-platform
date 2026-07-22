"""Unit tests for the MITRE ATT&CK STIX parser (pure function, no network/DB).

A small synthetic STIX 2.1 bundle exercises every branch the real 50 MB
Enterprise bundle hits: a tactic, a top-level technique with a kill-chain phase,
a sub-technique + its ``subtechnique-of`` edge, a group that ``uses`` a
technique, a mitigation that ``mitigates`` a technique, and one revoked plus one
deprecated object that must be dropped (along with any relationship touching
them).
"""
from intel_platform.services.attack.stix_parser import parse_bundle


def _bundle():
    return {
        "type": "bundle",
        "objects": [
            # --- Tactic -----------------------------------------------------
            {
                "type": "x-mitre-tactic",
                "id": "x-mitre-tactic--aaaa",
                "name": "Initial Access",
                "x_mitre_shortname": "initial-access",
                "description": "The adversary is trying to get into your network.",
                "external_references": [
                    {"source_name": "mitre-attack", "external_id": "TA0001"}
                ],
            },
            # --- Top-level technique in that tactic -------------------------
            {
                "type": "attack-pattern",
                "id": "attack-pattern--t1566",
                "name": "Phishing",
                "description": "Adversaries may send phishing messages.",
                "x_mitre_is_subtechnique": False,
                "x_mitre_platforms": ["Windows", "macOS", "Linux"],
                "x_mitre_detection": "Monitor for suspicious email attachments.",
                "kill_chain_phases": [
                    {"kill_chain_name": "mitre-attack", "phase_name": "initial-access"},
                    {"kill_chain_name": "other-framework", "phase_name": "ignore-me"},
                ],
                "external_references": [
                    {"source_name": "mitre-attack", "external_id": "T1566"}
                ],
            },
            # --- Sub-technique ---------------------------------------------
            {
                "type": "attack-pattern",
                "id": "attack-pattern--t1566-001",
                "name": "Spearphishing Attachment",
                "description": "Adversaries may send spearphishing emails with an attachment.",
                "x_mitre_is_subtechnique": True,
                "x_mitre_platforms": ["Windows"],
                "kill_chain_phases": [
                    {"kill_chain_name": "mitre-attack", "phase_name": "initial-access"}
                ],
                "external_references": [
                    {"source_name": "mitre-attack", "external_id": "T1566.001"}
                ],
            },
            # --- Group ------------------------------------------------------
            {
                "type": "intrusion-set",
                "id": "intrusion-set--g0007",
                "name": "APT28",
                "aliases": ["APT28", "Fancy Bear", "Sofacy"],
                "description": "A threat group.",
                "external_references": [
                    {"source_name": "mitre-attack", "external_id": "G0007"}
                ],
            },
            # --- Software (malware) ----------------------------------------
            {
                "type": "malware",
                "id": "malware--s0002",
                "name": "Mimikatz",
                "x_mitre_platforms": ["Windows"],
                "description": "A credential dumper.",
                "external_references": [
                    {"source_name": "mitre-attack", "external_id": "S0002"}
                ],
            },
            # --- Mitigation -------------------------------------------------
            {
                "type": "course-of-action",
                "id": "course-of-action--m1049",
                "name": "Antivirus/Antimalware",
                "description": "Use signatures to detect malicious software.",
                "external_references": [
                    {"source_name": "mitre-attack", "external_id": "M1049"}
                ],
            },
            # --- Revoked technique (must be dropped) ------------------------
            {
                "type": "attack-pattern",
                "id": "attack-pattern--revoked",
                "name": "Revoked Technique",
                "revoked": True,
                "external_references": [
                    {"source_name": "mitre-attack", "external_id": "T9998"}
                ],
            },
            # --- Deprecated group (must be dropped) -------------------------
            {
                "type": "intrusion-set",
                "id": "intrusion-set--deprecated",
                "name": "Deprecated Group",
                "x_mitre_deprecated": True,
                "external_references": [
                    {"source_name": "mitre-attack", "external_id": "G9999"}
                ],
            },
            # --- Relationships ---------------------------------------------
            {
                "type": "relationship",
                "id": "relationship--sub",
                "relationship_type": "subtechnique-of",
                "source_ref": "attack-pattern--t1566-001",
                "target_ref": "attack-pattern--t1566",
            },
            {
                "type": "relationship",
                "id": "relationship--uses",
                "relationship_type": "uses",
                "source_ref": "intrusion-set--g0007",
                "target_ref": "attack-pattern--t1566",
            },
            {
                "type": "relationship",
                "id": "relationship--mitigates",
                "relationship_type": "mitigates",
                "source_ref": "course-of-action--m1049",
                "target_ref": "attack-pattern--t1566",
            },
            # uses -> revoked technique: endpoint filtered, so edge must drop
            {
                "type": "relationship",
                "id": "relationship--uses-revoked",
                "relationship_type": "uses",
                "source_ref": "intrusion-set--g0007",
                "target_ref": "attack-pattern--revoked",
            },
            # unrelated relationship type: ignored in Phase 1
            {
                "type": "relationship",
                "id": "relationship--detects",
                "relationship_type": "detects",
                "source_ref": "course-of-action--m1049",
                "target_ref": "attack-pattern--t1566",
            },
        ],
    }


def test_parse_extracts_nodes_with_attack_ids():
    parsed = parse_bundle(_bundle())

    assert [t["attack_id"] for t in parsed.tactics] == ["TA0001"]
    assert parsed.tactics[0]["shortname"] == "initial-access"

    tech_ids = {t["attack_id"] for t in parsed.techniques}
    assert tech_ids == {"T1566", "T1566.001"}

    assert [g["attack_id"] for g in parsed.groups] == ["G0007"]
    assert parsed.groups[0]["aliases"] == ["APT28", "Fancy Bear", "Sofacy"]

    assert [s["attack_id"] for s in parsed.software] == ["S0002"]
    assert parsed.software[0]["software_type"] == "malware"

    assert [m["attack_id"] for m in parsed.mitigations] == ["M1049"]


def test_technique_fields_and_tactic_join():
    parsed = parse_bundle(_bundle())
    top = next(t for t in parsed.techniques if t["attack_id"] == "T1566")
    sub = next(t for t in parsed.techniques if t["attack_id"] == "T1566.001")

    assert top["is_subtechnique"] is False
    assert sub["is_subtechnique"] is True
    assert top["platforms"] == ["Windows", "macOS", "Linux"]
    assert "suspicious email" in top["detection"]
    # only the mitre-attack kill-chain phase is kept, foreign frameworks dropped
    assert top["tactic_shortnames"] == ["initial-access"]


def test_relationships_resolved_to_attack_ids():
    parsed = parse_bundle(_bundle())
    rels = set(parsed.relationships)

    assert ("T1566.001", "SUBTECHNIQUE_OF", "T1566") in rels
    assert ("G0007", "USES", "T1566") in rels
    assert ("M1049", "MITIGATES", "T1566") in rels


def test_revoked_and_deprecated_dropped():
    parsed = parse_bundle(_bundle())

    all_ids = (
        {t["attack_id"] for t in parsed.techniques}
        | {g["attack_id"] for g in parsed.groups}
    )
    assert "T9998" not in all_ids  # revoked technique
    assert "G9999" not in all_ids  # deprecated group

    # A relationship whose endpoint was filtered out must not survive.
    assert all("T9998" not in (s, d) for s, _, d in parsed.relationships)
    # `detects` is not a Phase-1 relationship type.
    assert all(rt != "detects" for _, rt, _ in parsed.relationships)


def test_attack_id_from_external_reference_not_stix_id():
    """The ATT&CK ID is never the STIX ``id`` — it comes from external_references."""
    parsed = parse_bundle(_bundle())
    # STIX ids look like "attack-pattern--...": none should leak into attack_id.
    for coll in (parsed.tactics, parsed.techniques, parsed.groups,
                 parsed.software, parsed.mitigations):
        for node in coll:
            assert "--" not in node["attack_id"]
