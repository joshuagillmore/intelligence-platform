"""Seed a deterministic demo project for E2E tests + local demos.

Writes a fixed-id project ("demo-sentinel") with a curated, cross-view set of
entities and relationships straight into Neo4j — matching the GraphStore write
shape (label = entity_type, plus entity_type/entity_category + flattened props).
Idempotent: the demo project's nodes are removed and recreated on each run. Reads
the Neo4j connection from Settings (NEO4J_URI/USER/PASSWORD), so it works locally
and in CI.

    cd backend && uv run python scripts/seed_demo.py
"""
from __future__ import annotations

import json

from neo4j import GraphDatabase

from intel_platform.config import settings

PROJECT_ID = "demo-sentinel"
PROJECT_NAME = "SENTINEL Demo"

# (label, id, name, entity_category, extra props) — ids are stable for assertions.
# entity_category is hardcoded here to mirror store.create_entity's write shape; the
# real SSOT is models.type_hierarchy.normalize_entity_type — keep these in sync if a
# view ever filters by entity_category.
_NODES = [
    ("Person", "d-p1", "Yevgeny Volkov", "Person", {"roles": ["Procurement Lead"]}),
    ("Person", "d-p2", "Maria Santos", "Person", {"roles": ["Logistics"]}),
    ("Organization", "d-o1", "Nord Industrial Group", "Organization", {"org_type": "Front Company"}),
    ("Location", "d-l1", "Rotterdam", "Location", {"latitude": 51.9225, "longitude": 4.47917, "location_type": "city"}),
    ("Location", "d-l2", "Tehran", "Location", {"latitude": 35.6892, "longitude": 51.389, "location_type": "city"}),
    ("IPAddress", "d-ip1", "45.83.12.7", "Cyber",
     {"geolocation": json.dumps({"lat": 52.37, "lon": 4.9, "city": "Amsterdam", "country": "NL", "org": "DemoHost"}),
      "asn": "AS20473"}),
    ("Domain", "d-dom1", "nord-industrial.example", "Cyber", {"registrant": "Nord Industrial Group"}),
    ("TTP", "d-ttp1", "T1566.001 Spearphishing Attachment", "Cyber", {}),
    ("TTP", "d-ttp2", "T1059.001 PowerShell", "Cyber", {}),
    ("Vulnerability", "d-v1", "CVE-2024-3400", "Cyber", {"cwe_ids": ["CWE-78"], "cvss_score": 10.0, "severity": "critical"}),
    ("ThreatActor", "d-ta1", "APT-Demo", "Campaign", {}),
    ("Malware", "d-mw1", "DemoRAT", "Cyber", {}),
]

# (source_id, REL_TYPE, target_id)
_RELS = [
    ("d-p1", "AFFILIATED_WITH", "d-o1"),
    ("d-p2", "AFFILIATED_WITH", "d-o1"),
    ("d-o1", "LOCATED_IN", "d-l1"),
    ("d-ta1", "LOCATED_IN", "d-l2"),
    ("d-ta1", "USES", "d-mw1"),
    ("d-ta1", "USES", "d-ttp1"),
    ("d-ta1", "USES", "d-ttp2"),
    ("d-ta1", "TARGETS", "d-o1"),
    ("d-mw1", "COMMUNICATES_WITH", "d-ip1"),
    ("d-ip1", "RESOLVES_TO", "d-dom1"),
    ("d-mw1", "EXPLOITS", "d-v1"),
]


def seed(driver) -> dict:
    with driver.session() as session:
        # Idempotent: wipe the demo project (and its Project node) first.
        session.run("MATCH (n {project_id: $pid}) DETACH DELETE n", pid=PROJECT_ID)
        session.run("MATCH (p:Project {id: $pid}) DETACH DELETE p", pid=PROJECT_ID)

        # Match the canonical create_project node shape (the get_project endpoint
        # reads classification_level/priority/status, so all must be present).
        session.run(
            """
            CREATE (p:Project {
                id: $pid, name: $name, description: $desc,
                classification_level: 'UNCLASSIFIED', priority: 'high', status: 'active',
                created_at: '2026-01-15T00:00:00Z', updated_at: '2026-01-15T00:00:00Z'
            })
            """,
            pid=PROJECT_ID, name=PROJECT_NAME, desc="Deterministic demo data for E2E tests.",
        )
        for label, nid, name, category, extra in _NODES:
            props = {
                "id": nid, "name": name, "project_id": PROJECT_ID,
                "entity_type": label, "entity_category": category,
                "first_seen": "2026-01-15", "created_at": "2026-01-15T00:00:00Z",
                **extra,
            }
            session.run(f"CREATE (n:{label} $props)", props=props)
        for src, rtype, tgt in _RELS:
            session.run(
                "MATCH (a {id: $src}), (b {id: $tgt}) "
                f"CREATE (a)-[:{rtype} {{project_id: $pid, confidence: 0.9}}]->(b)",
                src=src, tgt=tgt, pid=PROJECT_ID,
            )
    return {"project_id": PROJECT_ID, "nodes": len(_NODES), "relationships": len(_RELS)}


def main() -> None:
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        result = seed(driver)
        print(f"Seeded {PROJECT_NAME}: {result['nodes']} entities, {result['relationships']} relationships "
              f"(project_id={result['project_id']})")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
