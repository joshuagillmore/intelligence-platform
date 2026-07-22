"""Graph tests for the ATT&CK subsystem against the live local Neo4j.

Ingests a small synthetic parsed model into the global reference labels, then
exercises status / matrix / technique-detail and the TTP resolver (with a couple
of project TTP entities). The synthetic model uses real ATT&CK ids so the
resolver's regex has something to bind to; the fixture deletes exactly those
global nodes on teardown (the conftest cleanup only removes ``test-`` project
nodes, and these global nodes carry no ``project_id``).
"""
import pytest

from intel_platform.graph.schema import initialize_schema
from intel_platform.models.entities import ThreatActor, TTP
from intel_platform.services.attack import graph_ops
from intel_platform.services.attack.stix_parser import parse_bundle

PROJECT_ID = "test-attack-proj"


def test_resolver_regex_is_boundary_anchored():
    """A longer digit run must not truncate to a valid-looking code (no Neo4j)."""
    tech = graph_ops._TECH_RE
    grp = graph_ops._GROUP_RE
    assert tech.findall("uses T1566 and T1566.001 here") == ["T1566", "T1566.001"]
    # embedded in a longer number / token must NOT yield a bogus code
    assert tech.findall("T12345") == []
    assert tech.findall("T1566.0012") == ["T1566"]  # falls back to the real parent
    assert tech.findall("XT1566") == []
    assert grp.findall("attributed to G0007") == ["G0007"]
    assert grp.findall("G00071") == []


def _bundle():
    return {
        "objects": [
            {"type": "x-mitre-tactic", "id": "x-mitre-tactic--ia",
             "name": "Initial Access", "x_mitre_shortname": "initial-access",
             "description": "Get in.",
             "external_references": [{"source_name": "mitre-attack", "external_id": "TA0001"}]},
            {"type": "attack-pattern", "id": "attack-pattern--t1566",
             "name": "Phishing", "description": "Phishing messages.",
             "x_mitre_is_subtechnique": False, "x_mitre_platforms": ["Windows", "Linux"],
             "x_mitre_detection": "Monitor email.",
             "kill_chain_phases": [{"kill_chain_name": "mitre-attack", "phase_name": "initial-access"}],
             "external_references": [{"source_name": "mitre-attack", "external_id": "T1566"}]},
            {"type": "attack-pattern", "id": "attack-pattern--t1566-001",
             "name": "Spearphishing Attachment", "description": "Email with attachment.",
             "x_mitre_is_subtechnique": True, "x_mitre_platforms": ["Windows"],
             "kill_chain_phases": [{"kill_chain_name": "mitre-attack", "phase_name": "initial-access"}],
             "external_references": [{"source_name": "mitre-attack", "external_id": "T1566.001"}]},
            {"type": "intrusion-set", "id": "intrusion-set--g0007",
             "name": "APT28", "aliases": ["APT28", "Fancy Bear"], "description": "A group.",
             "external_references": [{"source_name": "mitre-attack", "external_id": "G0007"}]},
            {"type": "course-of-action", "id": "course-of-action--m1049",
             "name": "Antivirus/Antimalware", "description": "Signatures.",
             "external_references": [{"source_name": "mitre-attack", "external_id": "M1049"}]},
            {"type": "relationship", "id": "relationship--sub",
             "relationship_type": "subtechnique-of",
             "source_ref": "attack-pattern--t1566-001", "target_ref": "attack-pattern--t1566"},
            {"type": "relationship", "id": "relationship--uses",
             "relationship_type": "uses",
             "source_ref": "intrusion-set--g0007", "target_ref": "attack-pattern--t1566"},
            {"type": "relationship", "id": "relationship--mit",
             "relationship_type": "mitigates",
             "source_ref": "course-of-action--m1049", "target_ref": "attack-pattern--t1566"},
        ]
    }


@pytest.fixture
def ingested(neo4j_driver):
    """Ingest the synthetic model; delete exactly its global nodes afterwards."""
    initialize_schema(neo4j_driver)
    parsed = parse_bundle(_bundle())
    graph_ops.ingest_model(neo4j_driver, parsed, version="19.1")
    attack_ids = [
        n["attack_id"]
        for coll in (parsed.tactics, parsed.techniques, parsed.groups,
                     parsed.software, parsed.mitigations)
        for n in coll
    ]
    yield neo4j_driver, parsed
    with neo4j_driver.session() as session:
        session.run(
            "MATCH (n) WHERE n.attack_id IN $ids DETACH DELETE n", ids=attack_ids
        )
        session.run("MATCH (m:AttackMeta {id: 'attack-meta'}) DETACH DELETE m")


def test_status_reports_ingested_with_counts(ingested):
    driver, _ = ingested
    status = graph_ops.attack_status(driver)
    assert status["ingested"] is True
    assert status["version"] == "19.1"
    assert status["counts"]["tactics"] >= 1
    assert status["counts"]["techniques"] >= 2
    assert status["counts"]["groups"] >= 1
    assert status["counts"]["mitigations"] >= 1


def test_matrix_nests_subtechniques_under_parent(ingested):
    driver, _ = ingested
    matrix = graph_ops.get_matrix(driver, PROJECT_ID)
    assert matrix["ingested"] is True
    tactic = next(t for t in matrix["tactics"] if t["id"] == "TA0001")
    phishing = next(t for t in tactic["techniques"] if t["id"] == "T1566")
    assert phishing["is_subtechnique"] is False
    sub_ids = {s["id"] for s in phishing["subtechniques"]}
    assert "T1566.001" in sub_ids
    # No coverage yet -> all zero.
    assert phishing["observed_count"] == 0


def test_technique_detail_has_tactic_group_mitigation(ingested):
    driver, _ = ingested
    detail = graph_ops.get_technique(driver, "T1566", PROJECT_ID)
    assert detail is not None
    assert detail["name"] == "Phishing"
    assert detail["platforms"] == ["Windows", "Linux"]
    assert "Monitor email" in detail["detection"]
    assert {t["id"] for t in detail["tactics"]} == {"TA0001"}
    assert {g["id"] for g in detail["groups"]} == {"G0007"}
    assert {m["id"] for m in detail["mitigations"]} == {"M1049"}

    sub = graph_ops.get_technique(driver, "T1566.001", PROJECT_ID)
    assert sub["is_subtechnique"] is True
    assert sub["parent_id"] == "T1566"


def test_get_technique_missing_returns_none(ingested):
    driver, _ = ingested
    assert graph_ops.get_technique(driver, "T0000", PROJECT_ID) is None


def test_resolve_maps_ttps_and_actors_then_counts(ingested, graph_store):
    driver, _ = ingested

    # Two TTP entities whose names carry technique ids, plus a named actor.
    graph_store.create_entity(TTP(name="T1566", project_id=PROJECT_ID))
    graph_store.create_entity(
        TTP(name="T1566.001 Spearphishing Attachment", project_id=PROJECT_ID)
    )
    graph_store.create_entity(ThreatActor(name="Fancy Bear", project_id=PROJECT_ID))

    result = graph_ops.resolve_ttps(driver, PROJECT_ID)
    assert result["mapped"] == 3  # two TTPs + one actor by alias

    # Idempotent — a second run creates no new edges but still reports matches.
    assert graph_ops.resolve_ttps(driver, PROJECT_ID)["mapped"] == 3

    matrix = graph_ops.get_matrix(driver, PROJECT_ID)
    tactic = next(t for t in matrix["tactics"] if t["id"] == "TA0001")
    phishing = next(t for t in tactic["techniques"] if t["id"] == "T1566")
    sub = next(s for s in phishing["subtechniques"] if s["id"] == "T1566.001")
    assert sub["observed_count"] == 1
    # Top-level count rolls up its sub-technique's coverage: 1 (direct) + 1 (sub).
    assert phishing["observed_count"] == 2

    detail = graph_ops.get_technique(driver, "T1566", PROJECT_ID)
    related_names = {e["name"] for e in detail["related_entities"]}
    assert "T1566" in related_names


def test_resolve_sets_tcode_method_and_confidence(ingested, graph_store):
    """The UNWIND-batched resolver stamps method="tcode"/confidence=1.0 on edges."""
    driver, _ = ingested
    graph_store.create_entity(TTP(name="T1566 Phishing", project_id=PROJECT_ID))
    graph_store.create_entity(ThreatActor(name="APT28", project_id=PROJECT_ID))

    assert graph_ops.resolve_ttps(driver, PROJECT_ID)["mapped"] == 2

    with driver.session() as session:
        rows = session.run(
            """
            MATCH (:TTP {project_id: $pid})-[r:MAPS_TO]->(:AttackTechnique {attack_id: 'T1566'})
            RETURN r.method AS method, r.confidence AS confidence
            """,
            pid=PROJECT_ID,
        ).data()
        assert rows and all(r["method"] == "tcode" and r["confidence"] == 1.0 for r in rows)

        actor = session.run(
            """
            MATCH (:ThreatActor {project_id: $pid})-[r:MAPS_TO]->(:AttackGroup {attack_id: 'G0007'})
            RETURN r.method AS method, r.confidence AS confidence
            """,
            pid=PROJECT_ID,
        ).single()
        assert actor["method"] == "tcode" and actor["confidence"] == 1.0


def test_matrix_carries_observed_methods(ingested, graph_store):
    """Matrix cells expose the distinct MAPS_TO methods so the UI can flag AI maps."""
    driver, _ = ingested
    graph_store.create_entity(TTP(name="T1566 Phishing", project_id=PROJECT_ID))
    graph_ops.resolve_ttps(driver, PROJECT_ID)

    matrix = graph_ops.get_matrix(driver, PROJECT_ID)
    tactic = next(t for t in matrix["tactics"] if t["id"] == "TA0001")
    phishing = next(t for t in tactic["techniques"] if t["id"] == "T1566")
    assert phishing["methods"] == ["tcode"]


def test_navigator_layer_shape_and_scores(ingested, graph_store):
    driver, _ = ingested
    graph_store.create_entity(TTP(name="T1566 Phishing", project_id=PROJECT_ID))
    graph_ops.resolve_ttps(driver, PROJECT_ID)

    layer = graph_ops.navigator_layer(driver, PROJECT_ID)
    assert layer["versions"] == {"layer": "4.5", "navigator": "4.9.0", "attack": "19"}
    assert layer["domain"] == "enterprise-attack"
    entry = next(e for e in layer["techniques"] if e["techniqueID"] == "T1566")
    assert entry["score"] == 1
    assert entry["tactic"] == "initial-access"
    assert layer["gradient"]["colors"] == ["#ffffff", "#ff6666"]
