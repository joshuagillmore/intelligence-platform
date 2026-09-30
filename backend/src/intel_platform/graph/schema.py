import logging

from neo4j import Driver
from neo4j.exceptions import ConstraintError

logger = logging.getLogger(__name__)

# The label every node the store addresses by `id` carries, alongside its type
# label. Nodes used to carry only their type (Person, Domain, ...), so a lookup
# by id with no type — `MATCH (a {id: $id})` — could use no index and scanned
# the whole database; create_relationship did about four per edge. With a
# unique constraint on Entity.id, those lookups are a single index seek.
ENTITY_LABEL = "Entity"
ENTITY_ID_CONSTRAINT = (
    f"CREATE CONSTRAINT entity_uid IF NOT EXISTS FOR (n:{ENTITY_LABEL}) REQUIRE n.id IS UNIQUE"
)
_ENTITY_LABEL_BATCH = 5000

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


def ensure_entity_label(driver: Driver, batch_size: int = _ENTITY_LABEL_BATCH) -> int:
    """Give `:Entity` to every entity node that lacks it. Returns how many.

    Idempotent, and safe to run on every boot: nodes written before the label
    existed get it once, and later runs find nothing to do. An entity node is
    one with both an `id` and an `entity_type` — everything GraphStore creates.
    Metadata nodes (an `id` but no `entity_type`) and the ATT&CK/CWE catalog
    (no `id`) are left alone.

    Candidates are read in one scan, ordered by element id so the outcome is
    the same on every run, then labelled in batches. Two legacy nodes that
    share an id cannot both take a label whose id is unique: the first keeps
    it, the other is logged and left unlabelled (still reachable through the
    store's by-id fallback) rather than failing startup.
    """
    with driver.session() as session:
        candidates = [
            record["eid"]
            for record in session.run(
                f"""
                MATCH (n)
                WHERE n.id IS NOT NULL AND n.entity_type IS NOT NULL AND NOT n:{ENTITY_LABEL}
                RETURN elementId(n) AS eid ORDER BY eid
                """
            )
        ]
        if not candidates:
            return 0

        def _label(tx, eids: list[str]) -> int:
            return tx.run(
                f"MATCH (n) WHERE elementId(n) IN $eids SET n:{ENTITY_LABEL} RETURN count(n) AS c",
                eids=eids,
            ).single()["c"]

        labelled = 0
        skipped: list[str] = []
        for start in range(0, len(candidates), batch_size):
            batch = candidates[start:start + batch_size]
            try:
                labelled += session.execute_write(_label, batch)
                continue
            except ConstraintError:
                pass
            # A duplicate id in this batch: label one at a time to find it.
            for eid in batch:
                try:
                    labelled += session.execute_write(_label, [eid])
                except ConstraintError:
                    node_id = session.run(
                        "MATCH (n) WHERE elementId(n) = $eid RETURN n.id AS id", eid=eid,
                    ).single()["id"]
                    skipped.append(node_id)
                    logger.warning(
                        "Left node %s without :%s: another node already holds id %r",
                        eid, ENTITY_LABEL, node_id,
                    )

    logger.info(
        "Added :%s to %d node(s)%s", ENTITY_LABEL, labelled,
        f"; {len(skipped)} skipped as duplicate ids" if skipped else "",
    )
    return labelled


def initialize_schema(driver: Driver) -> None:
    with driver.session() as session:
        for stmt in CONSTRAINTS + INDEXES:
            session.run(stmt)
        # Created before any node is labelled, so ensure_entity_label meets
        # duplicate ids one at a time instead of failing to create it. Guarded
        # so a database that already holds :Entity duplicates still boots; the
        # lookups then scan the label instead of seeking the index.
        try:
            # consume() so a failure is raised here, inside the guard, rather
            # than whenever the driver next touches the session.
            session.run(ENTITY_ID_CONSTRAINT).consume()
        except Exception:
            logger.warning("Could not create the unique constraint on :%s(id)", ENTITY_LABEL, exc_info=True)
    ensure_entity_label(driver)
    with driver.session() as session:
        try:
            _sync_entity_name_index(session)
        except Exception:
            logger.warning("Entity name index sync skipped", exc_info=True)
        for stmt in FULLTEXT_INDEXES:
            try:
                session.run(stmt)
            except Exception:
                pass
