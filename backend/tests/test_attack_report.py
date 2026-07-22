"""Tests for the ATT&CK-structured intelligence product (``services.attack.report``)
against the live local Neo4j.

Ingests a small synthetic model (a tactic, two techniques, a group that USES both,
a mitigation that MITIGATES one), maps a couple of project TTPs by T-code, and
seeds a project CVE that ENABLES an observed technique. Asserts every structured
section populates and the markdown is non-empty; an empty project yields a valid
empty product. The LLM narrative is mocked (or asserted to degrade to null) — no
real LLM call is made.

**Fictitious ids (TA9001 / T999x / G9001 / M9001) are used deliberately** so the
synthetic nodes cannot collide with real ATT&CK reference data in the shared local
Neo4j; the fixture deletes exactly those global nodes on teardown, and the conftest
cleanup removes the ``test-`` project nodes.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from intel_platform.graph.schema import initialize_schema
from intel_platform.models.entities import TTP, Vulnerability
from intel_platform.services.attack import graph_ops, report
from intel_platform.services.attack.stix_parser import parse_bundle

PROJECT_ID = "test-attack-report"
EMPTY_PROJECT_ID = "test-attack-report-empty"


def _run(coro):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)


def _bundle():
    def tech(tid, name):
        return {"type": "attack-pattern", "id": f"attack-pattern--{tid}",
                "name": name, "description": f"{name} description.",
                "x_mitre_is_subtechnique": False, "x_mitre_platforms": ["Windows"],
                "kill_chain_phases": [{"kill_chain_name": "mitre-attack", "phase_name": "test-initial-access"}],
                "external_references": [{"source_name": "mitre-attack", "external_id": tid}]}

    return {
        "objects": [
            {"type": "x-mitre-tactic", "id": "x-mitre-tactic--test-ia",
             "name": "Test Initial Access", "x_mitre_shortname": "test-initial-access",
             "description": "Get in.",
             "external_references": [{"source_name": "mitre-attack", "external_id": "TA9001"}]},
            tech("T9990", "Synthetic Phishing"),
            tech("T9991", "Synthetic Scripting"),
            {"type": "intrusion-set", "id": "intrusion-set--G9001",
             "name": "SynthGroupAlpha", "aliases": ["SynthGroupAlpha"], "description": "A group.",
             "external_references": [{"source_name": "mitre-attack", "external_id": "G9001"}]},
            {"type": "course-of-action", "id": "course-of-action--M9001",
             "name": "Synthetic User Training", "description": "Train users.",
             "external_references": [{"source_name": "mitre-attack", "external_id": "M9001"}]},
            # Group uses both observed techniques.
            {"type": "relationship", "id": "relationship--uses-1", "relationship_type": "uses",
             "source_ref": "intrusion-set--G9001", "target_ref": "attack-pattern--T9990"},
            {"type": "relationship", "id": "relationship--uses-2", "relationship_type": "uses",
             "source_ref": "intrusion-set--G9001", "target_ref": "attack-pattern--T9991"},
            # Mitigation addresses T9990 only.
            {"type": "relationship", "id": "relationship--mit", "relationship_type": "mitigates",
             "source_ref": "course-of-action--M9001", "target_ref": "attack-pattern--T9990"},
        ]
    }


@pytest.fixture
def ingested(neo4j_driver):
    initialize_schema(neo4j_driver)
    parsed = parse_bundle(_bundle())
    graph_ops.ingest_model(neo4j_driver, parsed, version="19.1")
    attack_ids = [
        n["attack_id"]
        for coll in (parsed.tactics, parsed.techniques, parsed.groups,
                     parsed.software, parsed.mitigations)
        for n in coll
    ]
    yield neo4j_driver
    with neo4j_driver.session() as session:
        session.run("MATCH (n) WHERE n.attack_id IN $ids DETACH DELETE n", ids=attack_ids)
        session.run("MATCH (m:AttackMeta {id: 'attack-meta'}) DETACH DELETE m")


def _seed_project(driver, graph_store):
    """Two observed TTPs (T9990, T9991) + a CVE that ENABLES T9990."""
    graph_store.create_entity(TTP(name="T9990 Phishing", project_id=PROJECT_ID))
    graph_store.create_entity(TTP(name="T9991 Scripting", project_id=PROJECT_ID))
    graph_ops.resolve_ttps(driver, PROJECT_ID)

    vuln = Vulnerability(name="CVE-2099-0001", project_id=PROJECT_ID)
    graph_store.create_entity(vuln)
    with driver.session() as session:
        session.run(
            """
            MATCH (v:Vulnerability {id: $vid})
            MATCH (tech:AttackTechnique {attack_id: 'T9990'})
            MERGE (v)-[:ENABLES {via: 'cwe-capec'}]->(tech)
            """,
            vid=vuln.id,
        )


def _patch_narrative(text: str | None, *, raise_exc: Exception | None = None):
    """Patch report._get_provider so no real LLM is called."""
    if raise_exc is not None:
        return patch("intel_platform.services.attack.report._get_provider",
                     new=AsyncMock(side_effect=raise_exc))
    provider = MagicMock()
    provider.generate = AsyncMock(return_value=SimpleNamespace(content=text))
    return patch("intel_platform.services.attack.report._get_provider",
                 new=AsyncMock(return_value=provider))


# --- Structured assembly (pure graph reads, no LLM) ------------------------

def test_assemble_structured_populates_all_sections(ingested, graph_store):
    driver = ingested
    _seed_project(driver, graph_store)

    structured = report.assemble_structured(driver, PROJECT_ID)

    # observed_by_tactic: TA9001 with both observed techniques.
    tactics = structured["observed_by_tactic"]
    assert len(tactics) == 1
    tactic = tactics[0]
    assert tactic["tactic_id"] == "TA9001"
    ids = {t["id"] for t in tactic["techniques"]}
    assert ids == {"T9990", "T9991"}
    assert all(t["observed_count"] == 1 for t in tactic["techniques"])
    assert all("tcode" in t["methods"] for t in tactic["techniques"])

    # attribution: SynthGroupAlpha shares both.
    attribution = structured["attribution"]
    alpha = next(g for g in attribution if g["id"] == "G9001")
    assert alpha["shared_count"] == 2
    assert alpha["coverage"] == 1.0

    # key_mitigations: M9001 covers T9990 (1 technique).
    mitigations = structured["key_mitigations"]
    m = next(x for x in mitigations if x["id"] == "M9001")
    assert m["technique_count"] == 1

    # cve_enabled: T9990 is observed AND CVE-enabled.
    cve_enabled = structured["cve_enabled"]
    assert len(cve_enabled) == 1
    assert cve_enabled[0]["technique_id"] == "T9990"
    assert {c["name"] for c in cve_enabled[0]["cves"]} == {"CVE-2099-0001"}


def test_build_report_full_with_mocked_narrative(ingested, graph_store):
    driver = ingested
    _seed_project(driver, graph_store)

    with _patch_narrative("Bottom line: two initial-access techniques observed."):
        result = _run(report.build_report(driver, PROJECT_ID))

    assert result["project_id"] == PROJECT_ID
    assert result["narrative"] == "Bottom line: two initial-access techniques observed."
    md = result["markdown"]
    assert md.strip()
    assert "# ATT&CK Intelligence Product" in md
    assert "## Observed Techniques by Tactic" in md
    assert "## Candidate Attribution" in md
    assert "suggestive" in md.lower()          # attribution framed as suggestive
    assert "## Key Mitigations" in md
    assert "T9990" in md and "M9001" in md
    assert "Executive Summary" in md           # narrative section rendered


def test_narrative_degrades_to_null_without_provider(ingested, graph_store):
    driver = ingested
    _seed_project(driver, graph_store)

    with _patch_narrative(None, raise_exc=RuntimeError("no provider reachable")):
        result = _run(report.build_report(driver, PROJECT_ID))

    assert result["narrative"] is None
    # Structured sections + deterministic markdown still stand on their own.
    assert result["markdown"].strip()
    assert result["observed_by_tactic"]
    assert "Executive Summary" not in result["markdown"]


def test_empty_project_returns_valid_empty_product(ingested):
    driver = ingested

    with _patch_narrative(None, raise_exc=RuntimeError("no provider")):
        result = _run(report.build_report(driver, EMPTY_PROJECT_ID))

    assert result["project_id"] == EMPTY_PROJECT_ID
    assert result["observed_by_tactic"] == []
    assert result["attribution"] == []
    assert result["key_mitigations"] == []
    assert result["cve_enabled"] == []
    assert result["narrative"] is None
    md = result["markdown"]
    assert md.strip()
    assert "No techniques have been observed" in md
