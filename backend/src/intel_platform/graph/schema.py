import logging

from neo4j import Driver

logger = logging.getLogger(__name__)

CONSTRAINTS = [
    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Person) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT org_id IF NOT EXISTS FOR (n:Organization) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT loc_id IF NOT EXISTS FOR (n:Location) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT event_id IF NOT EXISTS FOR (n:Event) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT ip_id IF NOT EXISTS FOR (n:IPAddress) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT domain_id IF NOT EXISTS FOR (n:Domain) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT url_id IF NOT EXISTS FOR (n:URL) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT email_id IF NOT EXISTS FOR (n:EmailAddress) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT hash_id IF NOT EXISTS FOR (n:Hash) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT vuln_id IF NOT EXISTS FOR (n:Vulnerability) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT ttp_id IF NOT EXISTS FOR (n:TTP) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT malware_id IF NOT EXISTS FOR (n:Malware) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT actor_id IF NOT EXISTS FOR (n:ThreatActor) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT campaign_id IF NOT EXISTS FOR (n:Campaign) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT doc_id IF NOT EXISTS FOR (n:Document) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT topic_id IF NOT EXISTS FOR (n:Topic) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT report_id IF NOT EXISTS FOR (n:Report) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT assessment_id IF NOT EXISTS FOR (n:Assessment) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT project_id IF NOT EXISTS FOR (n:Project) REQUIRE n.id IS UNIQUE",
    # MITRE ATT&CK reference model — global (no project_id), keyed by attack_id.
    "CREATE CONSTRAINT attack_tactic_id IF NOT EXISTS FOR (n:AttackTactic) REQUIRE n.attack_id IS UNIQUE",
    "CREATE CONSTRAINT attack_technique_id IF NOT EXISTS FOR (n:AttackTechnique) REQUIRE n.attack_id IS UNIQUE",
    "CREATE CONSTRAINT attack_group_id IF NOT EXISTS FOR (n:AttackGroup) REQUIRE n.attack_id IS UNIQUE",
    "CREATE CONSTRAINT attack_software_id IF NOT EXISTS FOR (n:AttackSoftware) REQUIRE n.attack_id IS UNIQUE",
    "CREATE CONSTRAINT attack_mitigation_id IF NOT EXISTS FOR (n:AttackMitigation) REQUIRE n.attack_id IS UNIQUE",
    # CWE weakness reference nodes (Phase 3a CVE->ATT&CK chain) — global, keyed by cwe_id.
    "CREATE CONSTRAINT cwe_id IF NOT EXISTS FOR (n:Cwe) REQUIRE n.cwe_id IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX entity_project IF NOT EXISTS FOR (n:Person) ON (n.project_id)",
    "CREATE INDEX org_project IF NOT EXISTS FOR (n:Organization) ON (n.project_id)",
    "CREATE INDEX ip_project IF NOT EXISTS FOR (n:IPAddress) ON (n.project_id)",
    "CREATE INDEX domain_project IF NOT EXISTS FOR (n:Domain) ON (n.project_id)",
    "CREATE INDEX url_project IF NOT EXISTS FOR (n:URL) ON (n.project_id)",
    "CREATE INDEX email_project IF NOT EXISTS FOR (n:EmailAddress) ON (n.project_id)",
    "CREATE INDEX actor_project IF NOT EXISTS FOR (n:ThreatActor) ON (n.project_id)",
    "CREATE INDEX doc_project IF NOT EXISTS FOR (n:Document) ON (n.project_id)",
]

# Labels `entity_name_search` must cover: every type extraction can produce.
#
# A label missing here is invisible to cross-document deduplication, because
# search_entity_by_name short-circuits on fulltext hits, so every extraction
# mints another node. Measured on a live graph: 86 duplicated (name, type)
# pairs and 192 redundant rows — about a tenth of the graph — and every one of
# them was in an unindexed label. "Newnew Polar Bear" existed five times as a
# Document while the lookup happily returned an unrelated Organization.
#
# Project, User, Snapshot, Collection and Date are deliberately absent: they are
# not analyst-facing entities and resolution should never merge against them.
# The MITRE reference labels (Attack*, Cwe) are absent for the same reason —
# they are shared reference data, not per-project entities, and indexing them
# would let one project's resolution match another's catalogue.
ENTITY_NAME_LABELS = [
    "Person", "Organization", "ThreatActor", "Domain", "IPAddress", "URL",
    "EmailAddress", "Malware", "Campaign", "Location", "Event", "Hash",
    "Vulnerability", "TTP", "Topic", "Report", "Assessment",
    # Added after the duplicate measurement above — all were unindexed.
    "Document", "Custom", "Ship", "Financial", "Quantity", "Infrastructure",
    "Product", "Software", "Technology", "Aircraft", "Drone", "Radar",
    "Submarine", "Weapon",
]

ENTITY_NAME_INDEX = "entity_name_search"

FULLTEXT_INDEXES = [
    f"""CREATE FULLTEXT INDEX {ENTITY_NAME_INDEX} IF NOT EXISTS
       FOR (n:{'|'.join(ENTITY_NAME_LABELS)})
       ON EACH [n.name]""",
]


def _sync_entity_name_index(session) -> None:
    """Recreate the name index when its labels no longer match the code.

    `CREATE FULLTEXT INDEX ... IF NOT EXISTS` is a no-op once the index exists,
    so adding a label to ENTITY_NAME_LABELS silently does nothing on any
    database that already ran. Every deployment therefore kept whatever label
    set it was first created with, and entities of the newer types accumulated
    duplicates for as long as the database lived. The existing code comment
    warned about this and asked a human to drop the index by hand; nobody did.
    """
    try:
        existing = session.run(
            "SHOW INDEXES YIELD name, labelsOrTypes WHERE name = $n RETURN labelsOrTypes",
            parameters={"n": ENTITY_NAME_INDEX},
        ).single()
    except Exception:
        logger.debug("Could not read index metadata; leaving %s alone", ENTITY_NAME_INDEX)
        return

    if existing is None:
        return  # not created yet — the CREATE below makes it

    current = set(existing["labelsOrTypes"] or [])
    if current == set(ENTITY_NAME_LABELS):
        return

    added = sorted(set(ENTITY_NAME_LABELS) - current)
    logger.info(
        "Rebuilding %s: %d label(s) missing from the index (%s). Entities of "
        "those types could not be deduplicated across documents.",
        ENTITY_NAME_INDEX, len(added), ", ".join(added) or "none",
    )
    session.run(f"DROP INDEX {ENTITY_NAME_INDEX} IF EXISTS")


def initialize_schema(driver: Driver) -> None:
    with driver.session() as session:
        for stmt in CONSTRAINTS + INDEXES:
            session.run(stmt)
        try:
            _sync_entity_name_index(session)
        except Exception:
            logger.warning("Entity name index sync skipped", exc_info=True)
        for stmt in FULLTEXT_INDEXES:
            try:
                session.run(stmt)
            except Exception:
                pass
