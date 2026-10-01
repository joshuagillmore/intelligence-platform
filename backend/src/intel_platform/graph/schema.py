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

# One node per named entity: `create_entity` MERGEs on exactly these three
# properties, and the constraint is what makes that MERGE safe under
# concurrency — its index lock serialises two builds creating the same entity,
# where a lookup-then-create let both through. Nodes without a normalized_name
# (Documents, Reports, Assessments, metadata) are outside it: a uniqueness
# constraint only binds nodes that have every property it names.
ENTITY_NAME_KEY = "entity_name_key"
ENTITY_NAME_KEY_CONSTRAINT = (
    f"CREATE CONSTRAINT {ENTITY_NAME_KEY} IF NOT EXISTS FOR (n:{ENTITY_LABEL}) "
    "REQUIRE (n.project_id, n.normalized_name, n.entity_type) IS UNIQUE"
)

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


_NAME_KEY_BATCH = 2000


def _keyed_entity_types() -> list[str]:
    """The entity types create_entity keys by name (see models.entities)."""
    from intel_platform.models.entities import UNKEYED_ENTITY_TYPES, EntityType

    return sorted(t.value for t in EntityType if t.value not in UNKEYED_ENTITY_TYPES)


def ensure_normalized_names(driver: Driver, batch_size: int = _NAME_KEY_BATCH) -> dict[str, int]:
    """Give every named entity its `normalized_name`, merging the duplicates that exposes.

    Idempotent and cheap once done: only nodes still lacking the property are
    read. Nodes written before the key existed are grouped by
    (project_id, normalized_name, entity_type); a group of more than one is
    the duplication the key now forbids, so its members are merged into one
    survivor exactly as the merge route merges — every edge recreated in its
    own direction, mentions and source documents moved — and each merge is
    logged. The survivor is the node that already holds the key, else the
    earliest created (then lowest id), so every run picks the same one.

    A member that cannot be merged safely (an edge could not be moved, or its
    id is not unique) is left without a normalized_name and logged: it stays
    outside the constraint rather than blocking it or startup.

    Returns `{"named": n, "merged": n, "kept": n}`.
    """
    from intel_platform.graph.merge import merge_entity_into
    from intel_platform.graph.store import GraphStore
    from intel_platform.models.entities import normalize_name

    outcome = {"named": 0, "merged": 0, "kept": 0}
    with driver.session() as session:
        rows = [
            dict(r) for r in session.run(
                f"""
                MATCH (n:{ENTITY_LABEL})
                WHERE n.normalized_name IS NULL AND n.name IS NOT NULL AND n.project_id IS NOT NULL
                  AND n.entity_type IN $keyed
                RETURN elementId(n) AS eid, n.id AS id, n.name AS name, n.entity_type AS entity_type,
                       n.project_id AS project_id, coalesce(toString(n.created_at), '') AS created_at
                ORDER BY eid
                """,
                keyed=_keyed_entity_types(),
            )
        ]
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for row in rows:
        key_name = normalize_name(str(row["name"]))
        if key_name:
            groups.setdefault((row["project_id"], key_name, row["entity_type"]), []).append(row)
    if not groups:
        return outcome

    # Nodes that already hold a key the backfill is about to assign.
    holders: dict[tuple[str, str, str], dict] = {}
    keys = [{"p": p, "nn": nn, "t": t} for p, nn, t in sorted(groups)]
    with driver.session() as session:
        for start in range(0, len(keys), batch_size):
            for r in session.run(
                f"""
                UNWIND $keys AS k
                MATCH (h:{ENTITY_LABEL} {{project_id: k.p, normalized_name: k.nn, entity_type: k.t}})
                RETURN k.p AS p, k.nn AS nn, k.t AS t, h.id AS id, elementId(h) AS eid
                ORDER BY eid
                """,
                keys=keys[start:start + batch_size],
            ):
                holders.setdefault((r["p"], r["nn"], r["t"]), {"id": r["id"], "eid": r["eid"]})

    id_counts: dict[str, int] = {}
    for row in rows:
        id_counts[row["id"]] = id_counts.get(row["id"], 0) + 1

    store = GraphStore(driver)
    to_name: list[dict] = []
    for key in sorted(groups):
        members = sorted(groups[key], key=lambda r: (r["created_at"], r["id"] or "", r["eid"]))
        holder = holders.get(key)
        survivor = holder or members[0]
        if holder is None:
            to_name.append({"eid": survivor["eid"], "nn": key[1]})
        member_ids = {m["id"] for m in members if m["id"]}
        for member in members:
            if member["eid"] == survivor["eid"]:
                continue
            if not member["id"] or member["id"] == survivor["id"] or id_counts.get(member["id"], 0) > 1:
                outcome["kept"] += 1
                logger.warning(
                    "Left %s %r (%s) without a normalized_name: its id is not unique, so it cannot be "
                    "merged into %s safely",
                    key[2], member["name"], member["eid"], survivor["id"],
                )
                continue
            merged = merge_entity_into(
                store, survivor["id"], member["id"], project_id=key[0], skip_ids=member_ids - {survivor["id"]},
            )
            if merged.deleted:
                outcome["merged"] += 1
                logger.info(
                    "Merged duplicate %s %r (%s) into %s in project %r: same normalized name %r; "
                    "%d edge(s) moved",
                    key[2], member["name"], member["id"], survivor["id"], key[0], key[1], merged.transferred,
                )
            else:
                outcome["kept"] += 1
                logger.warning(
                    "Kept duplicate %s %r (%s) beside %s without a normalized_name: %d edge(s) could not be moved",
                    key[2], member["name"], member["id"], survivor["id"], merged.failed,
                )

    def _name(tx, batch: list[dict]) -> int:
        return tx.run(
            "UNWIND $rows AS row MATCH (n) WHERE elementId(n) = row.eid "
            "SET n.normalized_name = row.nn RETURN count(n) AS c",
            rows=batch,
        ).single()["c"]

    with driver.session() as session:
        for start in range(0, len(to_name), batch_size):
            batch = to_name[start:start + batch_size]
            try:
                outcome["named"] += session.execute_write(_name, batch)
                continue
            except ConstraintError:
                pass
            # Something took one of these keys since it was read: one at a time.
            for row in batch:
                try:
                    outcome["named"] += session.execute_write(_name, [row])
                except ConstraintError:
                    outcome["kept"] += 1
                    logger.warning("Left node %s without a normalized_name: key %r is taken", row["eid"], row["nn"])

    logger.info(
        "Entity name keys: %d named, %d duplicate(s) merged, %d left unkeyed",
        outcome["named"], outcome["merged"], outcome["kept"],
    )
    return outcome


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
    # The key is backfilled, and the duplicates it exposes merged, before the
    # constraint over it is created: the constraint cannot be created while
    # two nodes share a key.
    try:
        ensure_normalized_names(driver)
    except Exception:
        logger.warning("Entity name-key backfill failed; it will be retried on the next start", exc_info=True)
    with driver.session() as session:
        try:
            session.run(ENTITY_NAME_KEY_CONSTRAINT).consume()
        except Exception:
            # Duplicates the backfill could not merge. Startup continues; the
            # MERGE in create_entity still dedupes, without the race guarantee.
            logger.warning("Could not create the %s constraint", ENTITY_NAME_KEY, exc_info=True)
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
