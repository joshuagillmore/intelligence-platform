"""Attribution tests for the ATT&CK subsystem against the live local Neo4j.

Ingests a small synthetic model (three groups whose ``USES`` techniques overlap a
project's observed techniques to differing degrees), maps a couple of project TTPs
by T-code, and asserts :func:`graph_ops.get_attribution` ranks groups by shared
technique count with correct coverage. Sub-techniques are collapsed to their
parent on BOTH sides, so a group that uses a sub-technique of an observed parent
still counts.

**Fictitious ids (TA9001 / T999x / G900x) are used deliberately** so the synthetic
nodes cannot collide with the real ATT&CK reference data that may already be loaded
in the shared local Neo4j — real groups don't ``USES`` T999x, so they never pollute
the ranking, and the teardown (which deletes exactly these ids) never prunes real
reference nodes. The conftest cleanup only removes ``test-`` project nodes.
"""
import pytest

from intel_platform.graph.schema import initialize_schema
from intel_platform.models.entities import TTP
from intel_platform.services.attack import graph_ops
from intel_platform.services.attack.stix_parser import parse_bundle

PROJECT_ID = "test-attack-attrib"


def _bundle():
    def tech(tid, name, sub=False):
        return {"type": "attack-pattern", "id": f"attack-pattern--{tid}",
                "name": name, "description": f"{name} description.",
                "x_mitre_is_subtechnique": sub, "x_mitre_platforms": ["Windows"],
                "kill_chain_phases": [{"kill_chain_name": "mitre-attack", "phase_name": "test-initial-access"}],
                "external_references": [{"source_name": "mitre-attack", "external_id": tid}]}

    def grp(gid, name):
        return {"type": "intrusion-set", "id": f"intrusion-set--{gid}",
                "name": name, "aliases": [name], "description": "A group.",
                "external_references": [{"source_name": "mitre-attack", "external_id": gid}]}

    def uses(src, dst):
        return {"type": "relationship", "id": f"relationship--{src}-{dst}",
                "relationship_type": "uses",
                "source_ref": f"intrusion-set--{src}", "target_ref": f"attack-pattern--{dst}"}

    return {
        "objects": [
            {"type": "x-mitre-tactic", "id": "x-mitre-tactic--test-ia",
             "name": "Test Initial Access", "x_mitre_shortname": "test-initial-access",
             "description": "Get in.",
             "external_references": [{"source_name": "mitre-attack", "external_id": "TA9001"}]},
            tech("T9990", "Synthetic Phishing"),
            tech("T9990.001", "Synthetic Spearphishing Attachment", sub=True),
            tech("T9991", "Synthetic Scripting"),
            tech("T9992", "Synthetic App Protocol"),
            grp("G9001", "SynthGroupAlpha"),
            grp("G9002", "SynthGroupBeta"),
            grp("G9003", "SynthGroupGamma"),
            {"type": "relationship", "id": "relationship--sub",
             "relationship_type": "subtechnique-of",
             "source_ref": "attack-pattern--T9990.001", "target_ref": "attack-pattern--T9990"},
            # Alpha uses both observed parents.
            uses("G9001", "T9990"),
            uses("G9001", "T9991"),
            # Beta uses the SUB-technique of an observed parent -> must still count.
            uses("G9002", "T9990.001"),
            # Gamma uses only a non-observed technique -> no overlap.
            uses("G9003", "T9992"),
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
    yield neo4j_driver, parsed
    with neo4j_driver.session() as session:
        session.run("MATCH (n) WHERE n.attack_id IN $ids DETACH DELETE n", ids=attack_ids)


def test_attribution_ranks_groups_by_shared_techniques(ingested, graph_store):
    driver, _ = ingested
    # Project observes a sub-technique (T9990.001 -> parent T9990) and T9991.
    graph_store.create_entity(TTP(name="T9990.001 Spearphishing", project_id=PROJECT_ID))
    graph_store.create_entity(TTP(name="T9991 Scripting", project_id=PROJECT_ID))
    graph_ops.resolve_ttps(driver, PROJECT_ID)

    result = graph_ops.get_attribution(driver, PROJECT_ID)

    # Observed collapses the sub-technique to its parent -> {T9990, T9991}.
    assert result["observed_total"] == 2

    groups = result["groups"]
    ids = [g["id"] for g in groups]
    # Gamma (T9992 only) has no overlap and must be absent.
    assert "G9003" not in ids

    alpha = next(g for g in groups if g["id"] == "G9001")
    assert alpha["shared_count"] == 2
    assert alpha["coverage"] == 1.0
    assert {t["id"] for t in alpha["shared_techniques"]} == {"T9990", "T9991"}

    beta = next(g for g in groups if g["id"] == "G9002")
    # Group-side sub-technique collapses to T9990 -> overlaps the observed parent.
    assert beta["shared_count"] == 1
    assert beta["coverage"] == 0.5
    assert {t["id"] for t in beta["shared_techniques"]} == {"T9990"}

    # Ranked by shared_count desc: Alpha (2) before Beta (1).
    assert ids.index("G9001") < ids.index("G9002")


def test_attribution_empty_observed_returns_no_groups(ingested):
    driver, _ = ingested
    # No project TTPs mapped -> nothing observed.
    result = graph_ops.get_attribution(driver, PROJECT_ID)
    assert result == {"observed_total": 0, "groups": []}
