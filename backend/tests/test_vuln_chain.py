"""Tests for the CVE→ATT&CK chain (CWE→CAPEC→ATT&CK), Phase 3a.

Split in two:
  - Pure parser tests over SYNTHETIC namespaced CWE/CAPEC XML (no network).
  - Live-Neo4j tests that load a tiny synthetic map (fictitious ``T9*`` /
    ``CWE-9*`` ids so teardown can't touch real reference nodes) and exercise
    ``resolve_cve`` + ``get_technique``'s ``enabling_cves``.
"""
import pytest

from intel_platform.graph.schema import initialize_schema
from intel_platform.models.entities import Vulnerability
from intel_platform.services.attack import graph_ops
from intel_platform.services.attack import vuln_chain

PROJECT_ID = "test-vuln-chain"

# Synthetic CAPEC — namespaced (capec-3), covering: a pattern with multiple
# related CWEs + an ATT&CK top-level technique; a pattern with a SUB-technique
# entry id and a non-ATT&CK taxonomy mapping that must be ignored; and a pattern
# with NO ATT&CK mapping at all (must be dropped).
_CAPEC_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Attack_Pattern_Catalog xmlns="http://capec.mitre.org/capec-3" Name="CAPEC" Version="3.9">
   <Attack_Patterns>
      <Attack_Pattern ID="9001" Name="Alpha">
         <Related_Weaknesses>
            <Related_Weakness CWE_ID="9001"/>
            <Related_Weakness CWE_ID="9002"/>
         </Related_Weaknesses>
         <Taxonomy_Mappings>
            <Taxonomy_Mapping Taxonomy_Name="ATTACK">
               <Entry_ID>9001</Entry_ID>
               <Entry_Name>Fake Technique</Entry_Name>
            </Taxonomy_Mapping>
         </Taxonomy_Mappings>
      </Attack_Pattern>
      <Attack_Pattern ID="9002" Name="Beta">
         <Related_Weaknesses>
            <Related_Weakness CWE_ID="9002"/>
         </Related_Weaknesses>
         <Taxonomy_Mappings>
            <Taxonomy_Mapping Taxonomy_Name="ATTACK">
               <Entry_ID>9002.001</Entry_ID>
            </Taxonomy_Mapping>
            <Taxonomy_Mapping Taxonomy_Name="WASC">
               <Entry_ID>10</Entry_ID>
            </Taxonomy_Mapping>
         </Taxonomy_Mappings>
      </Attack_Pattern>
      <Attack_Pattern ID="9003" Name="Gamma (no ATT&amp;CK mapping)">
         <Related_Weaknesses>
            <Related_Weakness CWE_ID="9003"/>
         </Related_Weaknesses>
         <Taxonomy_Mappings>
            <Taxonomy_Mapping Taxonomy_Name="OWASP Attacks">
               <Entry_ID>5</Entry_ID>
            </Taxonomy_Mapping>
         </Taxonomy_Mappings>
      </Attack_Pattern>
   </Attack_Patterns>
</Attack_Pattern_Catalog>
"""

# Synthetic CWE — namespaced (cwe-7); names only.
_CWE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Weakness_Catalog xmlns="http://cwe.mitre.org/cwe-7" Name="CWE" Version="4.20">
   <Weaknesses>
      <Weakness ID="9001" Name="Fake Weakness One"/>
      <Weakness ID="9002" Name="Fake Weakness Two"/>
      <Weakness ID="9003" Name="Fake Weakness Three"/>
   </Weaknesses>
</Weakness_Catalog>
"""


# --- Parser (pure; no network) ---------------------------------------------

def test_parse_capec_pivots_cwe_to_techniques():
    mapping = vuln_chain.parse_capec(_CAPEC_XML)
    # CWE-9001 is only on Alpha (→ T9001).
    assert mapping["CWE-9001"] == {"T9001"}
    # CWE-9002 is on Alpha (T9001) AND Beta (sub-technique T9002.001).
    assert mapping["CWE-9002"] == {"T9001", "T9002.001"}
    # Gamma has no ATT&CK taxonomy mapping → its CWE never enters the map.
    assert "CWE-9003" not in mapping


def test_parse_capec_ignores_non_attack_taxonomies():
    mapping = vuln_chain.parse_capec(_CAPEC_XML)
    # Beta's WASC "10" must not become a bogus technique id.
    assert "T10" not in {t for techs in mapping.values() for t in techs}


def test_parse_cwe_names():
    names = vuln_chain.parse_cwe_names(_CWE_XML)
    assert names["CWE-9001"] == "Fake Weakness One"
    assert names["CWE-9003"] == "Fake Weakness Three"


def test_normalize_cwe_ids_handles_list_and_json_string():
    # Native Neo4j list (the enrichment write path).
    assert vuln_chain._normalize_cwe_ids(["CWE-79", "CWE-89"]) == ["CWE-79", "CWE-89"]
    # JSON-string encoding (tolerated).
    assert vuln_chain._normalize_cwe_ids('["CWE-79", "CWE-89"]') == ["CWE-79", "CWE-89"]
    # Single string.
    assert vuln_chain._normalize_cwe_ids("CWE-79") == ["CWE-79"]
    # Dedup + junk dropped.
    assert vuln_chain._normalize_cwe_ids(["CWE-79", "CWE-79", "NVD-CWE-noinfo", ""]) == ["CWE-79"]
    # Empty / None.
    assert vuln_chain._normalize_cwe_ids(None) == []
    assert vuln_chain._normalize_cwe_ids("") == []


# --- Live Neo4j ------------------------------------------------------------

@pytest.fixture
def chain_graph(neo4j_driver):
    """Fictitious AttackTechnique nodes + teardown of every synthetic ref node.

    T9001/T9002.001 exist so ENABLES edges can form; T9999 is deliberately absent
    to prove unknown-technique mappings are skipped. Global nodes (no project_id)
    aren't covered by the conftest cleanup, so this fixture removes them by exact
    id — never a prefix — so real reference nodes can't be pruned.
    """
    initialize_schema(neo4j_driver)
    tech_ids = ["T9001", "T9002.001"]
    cwe_ids = ["CWE-9001", "CWE-9002", "CWE-9003"]
    with neo4j_driver.session() as session:
        session.run(
            "UNWIND $ids AS tid MERGE (t:AttackTechnique {attack_id: tid}) "
            "SET t.name = 'Synthetic ' + tid, t.is_subtechnique = false",
            ids=tech_ids,
        )
    yield neo4j_driver
    with neo4j_driver.session() as session:
        session.run("MATCH (t:AttackTechnique) WHERE t.attack_id IN $ids DETACH DELETE t", ids=tech_ids)
        session.run("MATCH (c:Cwe) WHERE c.cwe_id IN $ids DETACH DELETE c", ids=cwe_ids)
        session.run("MATCH (m:VulnChainMeta) DETACH DELETE m")


def _load(driver):
    cwe_to_techs = {
        "CWE-9001": {"T9001"},
        "CWE-9002": {"T9001", "T9002.001"},
        "CWE-9003": {"T9999"},  # technique absent → edge skipped, Cwe still made
    }
    cwe_names = {"CWE-9001": "One", "CWE-9002": "Two", "CWE-9003": "Three"}
    return vuln_chain.load_vuln_chain(driver, cwe_to_techs, cwe_names)


def test_load_creates_enables_edges_only_for_existing_techniques(chain_graph):
    driver = chain_graph
    result = _load(driver)
    # 3 CWE nodes; edges: CWE-9001→T9001, CWE-9002→T9001, CWE-9002→T9002.001 = 3
    # (CWE-9003→T9999 skipped — no such technique).
    assert result == {"cwes": 3, "edges": 3}

    with driver.session() as session:
        # CWE-9003 exists but enables nothing.
        rec = session.run(
            "MATCH (c:Cwe {cwe_id: 'CWE-9003'}) "
            "RETURN c.name AS name, size([(c)-[:ENABLES]->() | 1]) AS edges"
        ).single()
        assert rec["name"] == "Three"
        assert rec["edges"] == 0

    # Status reflects the vuln chain.
    status = graph_ops.attack_status(driver)
    assert status["vuln_chain"]["ingested"] is True
    assert status["vuln_chain"]["cwes"] == 3


def test_load_is_idempotent(chain_graph):
    driver = chain_graph
    first = _load(driver)
    second = _load(driver)
    assert first == second
    with driver.session() as session:
        # Scope to THIS fixture's synthetic CWEs — a global count would sweep in any
        # real (:Cwe)-[:ENABLES]->(:AttackTechnique) edges from a prior real ingest.
        rec = session.run(
            "MATCH (c:Cwe)-[e:ENABLES]->(:AttackTechnique) "
            "WHERE c.cwe_id IN ['CWE-9001','CWE-9002','CWE-9003'] RETURN count(e) AS c"
        ).single()
        assert rec["c"] == 3  # no duplicate edges on re-load


def test_resolve_cve_links_vuln_to_techniques(chain_graph, graph_store):
    driver = chain_graph
    _load(driver)

    v = Vulnerability(name="CVE-2099-0001", project_id=PROJECT_ID)
    graph_store.create_entity(v)
    # Enrichment writes cwe_ids as a native Neo4j list via update_entity.
    graph_store.update_entity(v.id, {"cwe_ids": ["CWE-9001", "CWE-9002"]})

    result = vuln_chain.resolve_cve(driver, PROJECT_ID)
    # One vuln; its CWEs enable T9001 + T9002.001 = 2 distinct technique links.
    assert result == {"vulnerabilities": 1, "techniques_linked": 2}

    # Idempotent — a re-run reports the same, creates no new edges.
    assert vuln_chain.resolve_cve(driver, PROJECT_ID) == {"vulnerabilities": 1, "techniques_linked": 2}

    with driver.session() as session:
        weaknesses = session.run(
            "MATCH (v:Vulnerability {id: $id})-[:HAS_WEAKNESS]->(c:Cwe) RETURN c.cwe_id AS cid ORDER BY cid",
            id=v.id,
        ).data()
        assert [w["cid"] for w in weaknesses] == ["CWE-9001", "CWE-9002"]

        enables = session.run(
            "MATCH (v:Vulnerability {id: $id})-[e:ENABLES]->(t:AttackTechnique) "
            "RETURN t.attack_id AS tid, e.via AS via ORDER BY tid",
            id=v.id,
        ).data()
        assert [e["tid"] for e in enables] == ["T9001", "T9002.001"]
        assert all(e["via"] == "cwe-capec" for e in enables)


def test_get_technique_surfaces_enabling_cves(chain_graph, graph_store):
    driver = chain_graph
    _load(driver)

    v = Vulnerability(name="CVE-2099-0002", project_id=PROJECT_ID)
    graph_store.create_entity(v)
    graph_store.update_entity(v.id, {"cwe_ids": ["CWE-9002"]})
    vuln_chain.resolve_cve(driver, PROJECT_ID)

    detail = graph_ops.get_technique(driver, "T9001", PROJECT_ID)
    assert detail is not None
    enabling = {c["id"]: c["name"] for c in detail["enabling_cves"]}
    assert enabling.get(v.id) == "CVE-2099-0002"

    sub = graph_ops.get_technique(driver, "T9002.001", PROJECT_ID)
    assert v.id in {c["id"] for c in sub["enabling_cves"]}


def test_resolve_cve_no_vulns_is_zero(chain_graph):
    driver = chain_graph
    _load(driver)
    assert vuln_chain.resolve_cve(driver, PROJECT_ID) == {"vulnerabilities": 0, "techniques_linked": 0}
