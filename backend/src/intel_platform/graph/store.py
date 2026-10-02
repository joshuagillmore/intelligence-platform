from __future__ import annotations

import re

from neo4j import Driver
from neo4j.exceptions import ConstraintError

from intel_platform.models.entities import Entity, normalize_name


# Enough terms for any real query. A bound exists because each term becomes
# another CONTAINS clause, and a pasted paragraph would otherwise build a
# Cypher statement with hundreds of them.
_MAX_SEARCH_TERMS = 12


def _search_terms(query: str) -> list[str]:
    """The words a search must match, lowercased.

    Whitespace-only input yields no terms rather than a filter on " ", which
    would quietly restrict results to names that happen to contain a space.
    """
    return [t for t in (query or "").lower().split() if t][:_MAX_SEARCH_TERMS]


# Shared reference data rather than per-project entities: ATT&CK, CWE/CAPEC and
# D3FEND. These nodes carry no project_id and every project that maps to them
# links to the same node, so a project-scoped walk may end on one but must never
# pass through it — through T1566 lies every other project's phishing TTPs.
CATALOG_LABELS = (
    "AttackTechnique", "AttackGroup", "AttackSoftware", "AttackTactic",
    "AttackMitigation", "Cwe", "Capec", "D3fendTechnique",
)

# Subgraph walks are clamped to this many hops. The route allowed 5 and the
# service layer passed anything through, so hops=5 across ATT&CK hubs
# enumerated paths without end, and a negative value became `[*1..-1]`.
_MIN_HOPS = 1
_MAX_HOPS = 4
# Path enumeration stops here; the result says `truncated` when it did.
_MAX_SUBGRAPH_PATHS = 5000
# shortestPath is a bounded breadth-first search, so it keeps its own ceiling.
_SHORTEST_PATH_MAX_HOPS = 10


def _clamp_hops(hops) -> int:
    try:
        value = int(hops)
    except (TypeError, ValueError):
        value = _MIN_HOPS
    return max(_MIN_HOPS, min(_MAX_HOPS, value))


def _is_catalog(var: str) -> str:
    """Cypher predicate: `var` carries one of the catalog labels."""
    return "(" + " OR ".join(f"{var}:{label}" for label in CATALOG_LABELS) + ")"


def _not_provenance(rel: str) -> str:
    """Cypher predicate: `rel` is not a document-mention edge.

    `(:Document)-[:MENTIONS]->(:Entity)` records which documents an entity
    was extracted from. It is provenance, not a claim about the world, so the
    knowledge-graph reads (relationships, subgraphs, paths, the full graph,
    project stats) leave it out: otherwise every document becomes the most
    connected node in the network view, a two-hop walk reaches everything
    co-mentioned in any document, and the first relationships an assessor
    reads are "Document X mentions this". Mentions are read through the
    methods under "Document mentions" instead. A Report's MENTIONS edges are
    analyst links, not provenance, and stay visible as before.
    """
    return f"NOT (type({rel}) = 'MENTIONS' AND startNode({rel}):Document)"


def _clean_aliases(values) -> list[str]:
    """The non-empty strings in `values`, stripped, each once ignoring case, in order."""
    if isinstance(values, str) or not isinstance(values, (list, tuple)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        alias = value.strip()
        if alias and alias.lower() not in seen:
            seen.add(alias.lower())
            out.append(alias)
    return out


def _alias_union(var: str, param: str) -> str:
    """Cypher expression: `var`'s aliases plus those in `param` it lacks.

    Compared ignoring case; an alias that is the node's own name is left out.
    Aliases only accumulate: a second document naming a country another way
    adds that form and never takes away the forms earlier ones recorded.
    """
    return (
        f"reduce(acc = coalesce({var}.aliases, []), a IN {param} | "
        f"CASE WHEN toLower(a) IN [x IN acc | toLower(x)] OR toLower(a) = toLower(coalesce({var}.name, '')) "
        f"THEN acc ELSE acc + a END)"
    )


def _matches_term(var: str, param: str) -> str:
    """Cypher predicate: the lowercased term `param` is in `var`'s name or in one of its aliases."""
    return (
        f"(toLower({var}.name) CONTAINS {param} "
        f"OR any(a IN coalesce({var}.aliases, []) WHERE toLower(a) CONTAINS {param}))"
    )


def _validate_label(label: str) -> str:
    """Validate entity label. Must be alphanumeric (Neo4j label requirement)."""
    if not label or not re.match(r'^[A-Za-z][A-Za-z0-9_]*$', label):
        return "Entity"  # Fallback for invalid labels
    return label


class GraphStore:
    def __init__(self, driver: Driver):
        self._driver = driver

    @staticmethod
    def _serialize_props(props: dict) -> dict:
        """Ensure all property values are Neo4j-compatible primitives."""
        clean = {}
        for k, v in props.items():
            if v is None:
                continue
            if isinstance(v, dict):
                import json
                clean[k] = json.dumps(v)
            elif isinstance(v, (list, tuple)):
                # Neo4j supports lists of primitives
                clean[k] = [str(item) for item in v]
            elif hasattr(v, 'isoformat'):
                clean[k] = v.isoformat()
            else:
                clean[k] = v
        return clean

    def create_entity(self, entity: Entity) -> dict:
        from intel_platform.models.type_hierarchy import normalize_entity_type

        specific_type = entity.entity_type.value
        _, parent_category = normalize_entity_type(specific_type)

        label = _validate_label(specific_type)
        props = self._serialize_props(entity.model_dump(exclude={"entity_type"}))
        props["entity_type"] = specific_type
        props["entity_category"] = parent_category
        # Every document that mentions the entity; later ones are appended on
        # merge by record_entity_source. source_doc_id stays the first.
        if props.get("source_doc_id"):
            props["source_doc_ids"] = [props["source_doc_id"]]

        # One MERGE on the entity's key. A named entity is keyed by
        # (project_id, normalized_name, entity_type), which the entity_name_key
        # constraint makes unique, so two builds that meet the same entity at
        # once make one node: the constraint's index lock serialises them and
        # the second matches what the first created. A record type (Document,
        # Report, Assessment) has no normalized_name and is keyed by its id.
        #
        # On a match nothing is overwritten: the node keeps the name, id and
        # properties of whoever created it, and the caller learns that it
        # merged from the returned id differing from the one it sent.
        if props.get("normalized_name"):
            key = (
                "{project_id: $props.project_id, normalized_name: $props.normalized_name, "
                "entity_type: $props.entity_type}"
            )
        else:
            key = "{id: $props.id}"
        # Every entity also carries the shared :Entity label, whose unique `id`
        # constraint is what makes the by-id lookups an index seek.
        add_label = "" if label == "Entity" else f", n:{label}"
        cypher = f"MERGE (n:Entity {key}) ON CREATE SET n += $props{add_label} RETURN n"

        def _merge(tx) -> dict:
            record = tx.run(cypher, props=props).single()
            return dict(record["n"]) if record else {}

        with self._driver.session() as session:
            try:
                node = session.execute_write(_merge)
            except ConstraintError:
                # A concurrent creator committed between this MERGE's lookup
                # and its write. The key now exists, so the retry matches it.
                node = session.execute_write(_merge)

        # Invalidate graph cache for the project
        project_id = getattr(entity, "project_id", None) or props.get("project_id")
        if project_id:
            from intel_platform.services.graph_cache import graph_cache
            graph_cache.invalidate(project_id)

        return node

    def get_entity(self, entity_id: str) -> dict | None:
        with self._driver.session() as session:
            record = session.run("MATCH (n:Entity {id: $id}) RETURN n", id=entity_id).single()
            if record is None:
                # A node written by raw Cypher elsewhere since the last startup
                # (a legacy Collection, a test fixture) has no :Entity label
                # until ensure_entity_label runs again. Only a miss pays for
                # the unindexed lookup.
                record = session.run("MATCH (n {id: $id}) RETURN n", id=entity_id).single()
            return dict(record["n"]) if record else None

    def update_entity(self, entity_id: str, props: dict) -> dict | None:
        """Merge `props` onto an existing node (by id). Returns the node or None.

        Used by enrichment to write looked-up properties (asn, dns_records,
        cvss_score, enriched flags) onto an already-extracted observable node.
        `aliases` are added to the node's own (see `add_aliases`), never
        written over them.
        """
        if not props:
            return self.get_entity(entity_id)
        clean = self._serialize_props(props)
        # normalized_name is derived from the name, never written directly: a
        # caller setting it could move the node onto another entity's key. A
        # rename moves the key with it, on nodes that are keyed at all.
        clean.pop("normalized_name", None)
        rekey = ""
        params: dict = {"id": entity_id, "props": clean}
        if "name" in clean:
            rekey = " SET n.normalized_name = CASE WHEN n.normalized_name IS NULL THEN NULL ELSE $nn END"
            params["nn"] = normalize_name(str(clean["name"])) or None
        merge_aliases = ""
        if "aliases" in clean:
            # The lock is taken before the list is read, as in add_aliases.
            params["aliases"] = _clean_aliases(clean.pop("aliases"))
            merge_aliases = (
                f" SET n._aliases_lock = true SET n.aliases = {_alias_union('n', '$aliases')}"
                " REMOVE n._aliases_lock"
            )
        with self._driver.session() as session:
            record = session.run(
                f"MATCH (n:Entity {{id: $id}}) SET n += $props{rekey}{merge_aliases} RETURN n", parameters=params,
            ).single()
            if record is None:
                # Unlabelled node (see get_entity).
                record = session.run(
                    f"MATCH (n {{id: $id}}) SET n += $props{rekey}{merge_aliases} RETURN n", parameters=params,
                ).single()
            node = dict(record["n"]) if record else None

        if node:
            project_id = node.get("project_id")
            if project_id:
                from intel_platform.services.graph_cache import graph_cache
                graph_cache.invalidate(project_id)
        return node

    def record_entity_source(self, entity_id: str, source_doc_id: str) -> None:
        """Add a document to the entity's `source_doc_ids`, once.

        `source_doc_id` was set only when the entity was created, so a later
        document that merged into it left no trace and retrieval could only
        reach the first. An entity written before the list existed starts it
        from its `source_doc_id`. The first SET takes the node's write lock
        before the list is read, so concurrent builds cannot drop each
        other's documents.
        """
        if not source_doc_id:
            return
        with self._driver.session() as session:
            session.run(
                """
                MATCH (n:Entity {id: $id})
                SET n._sources_lock = true
                WITH n, coalesce(
                    n.source_doc_ids,
                    CASE WHEN coalesce(n.source_doc_id, '') = '' THEN [] ELSE [n.source_doc_id] END
                ) AS docs
                SET n.source_doc_ids = CASE WHEN $doc IN docs THEN docs ELSE docs + $doc END
                REMOVE n._sources_lock
                """,
                id=entity_id, doc=source_doc_id,
            )

    def add_aliases(self, aliases: dict[str, list[str]]) -> int:
        """Add `{entity_id: [alias, ...]}` to the entities' `aliases`. Returns nodes written.

        A union, never an overwrite: an alias already on the node (in any
        case) or equal to its name is skipped, and every alias it had stays.
        One statement for a whole build. The first SET takes each node's write
        lock before its list is read, so concurrent builds cannot drop each
        other's aliases; rows go in id order so they queue rather than deadlock.
        """
        rows = [
            {"id": entity_id, "aliases": cleaned}
            for entity_id, values in sorted(aliases.items())
            if entity_id and (cleaned := _clean_aliases(values))
        ]
        if not rows:
            return 0

        def _write(tx) -> tuple[int, list]:
            record = tx.run(
                f"""
                UNWIND $rows AS row
                MATCH (n:Entity {{id: row.id}})
                SET n._aliases_lock = true
                SET n.aliases = {_alias_union('n', 'row.aliases')}
                REMOVE n._aliases_lock
                RETURN count(n) AS written, collect(DISTINCT n.project_id) AS projects
                """,
                rows=rows,
            ).single()
            return (record["written"], list(record["projects"])) if record else (0, [])

        with self._driver.session() as session:
            written, projects = session.execute_write(_write)
        from intel_platform.services.graph_cache import graph_cache
        for project_id in projects:
            if project_id:
                graph_cache.invalidate(project_id)
        return written

    # ── Document mentions ────────────────────────────────────────────────
    # `(:Document)-[:MENTIONS {count, first_seen, project_id}]->(:Entity)`:
    # which documents an entity was extracted from, and how often. Written by
    # graph_builder on every build, backfilled from `source_doc_ids` by
    # schema.ensure_mentions_edges. Left out of the knowledge-graph reads (see
    # _not_provenance) and read through these methods instead.

    def record_mentions(self, project_id: str, mentions: dict[tuple[str, str], int]) -> int:
        """Write `{(document_id, entity_id): count}` as MENTIONS edges. Returns how many.

        One statement for the whole build. An existing edge has `count` added
        to it and keeps its `first_seen`. A pair whose document is not a
        Document node in the project (an inline extraction, a collection id
        standing in for a document) writes nothing, rather than an edge to
        nowhere or across projects.
        """
        rows = [
            {"doc_id": doc_id, "entity_id": entity_id, "count": int(count)}
            for (doc_id, entity_id), count in sorted(mentions.items())
            if doc_id and entity_id and count > 0
        ]
        if not rows:
            return 0
        from datetime import datetime, timezone

        def _write(tx) -> int:
            # Sorted rows lock nodes in one order, so concurrent builds that
            # share entities queue rather than deadlock.
            return tx.run(
                """
                UNWIND $rows AS row
                MATCH (d:Document {id: row.doc_id})
                MATCH (e:Entity {id: row.entity_id})
                WHERE d.project_id = $project_id AND e.project_id = $project_id AND NOT e:Document
                MERGE (d)-[m:MENTIONS]->(e)
                ON CREATE SET m.count = row.count, m.first_seen = $now, m.project_id = $project_id
                ON MATCH SET m.count = coalesce(m.count, 0) + row.count
                RETURN count(m) AS n
                """,
                rows=rows, project_id=project_id, now=datetime.now(timezone.utc).isoformat(),
            ).single()["n"]

        with self._driver.session() as session:
            return session.execute_write(_write)

    def move_mentions(self, from_id: str, to_id: str) -> int:
        """Re-point the documents that mention `from_id` at `to_id`. Returns edges moved.

        For a merge: counts add up, the earlier `first_seen` wins, and the
        merged entity's `source_doc_ids` join the survivor's, so neither the
        evidence chain nor the retrievers lose a document to the merge.
        """
        def _move(tx) -> int:
            moved = tx.run(
                """
                MATCH (d:Document)-[old:MENTIONS]->(src:Entity {id: $from_id})
                MATCH (dst:Entity {id: $to_id})
                MERGE (d)-[m:MENTIONS]->(dst)
                ON CREATE SET m = properties(old)
                ON MATCH SET
                    m.count = coalesce(m.count, 0) + coalesce(old.count, 1),
                    m.first_seen = CASE
                        WHEN m.first_seen IS NULL OR (old.first_seen IS NOT NULL AND old.first_seen < m.first_seen)
                        THEN old.first_seen ELSE m.first_seen END
                DELETE old
                RETURN count(*) AS n
                """,
                from_id=from_id, to_id=to_id,
            ).single()["n"]
            tx.run(
                """
                MATCH (src:Entity {id: $from_id}), (dst:Entity {id: $to_id})
                WITH dst, [x IN [src.source_doc_id] + coalesce(src.source_doc_ids, [])
                           WHERE x IS NOT NULL AND x <> ''] AS extra
                WHERE size(extra) > 0
                SET dst._sources_lock = true
                WITH dst, extra, coalesce(
                    dst.source_doc_ids,
                    CASE WHEN coalesce(dst.source_doc_id, '') = '' THEN [] ELSE [dst.source_doc_id] END
                ) AS docs
                SET dst.source_doc_ids = reduce(acc = docs, x IN extra | CASE WHEN x IN acc THEN acc ELSE acc + x END)
                REMOVE dst._sources_lock
                """,
                from_id=from_id, to_id=to_id,
            ).consume()
            return moved

        with self._driver.session() as session:
            return session.execute_write(_move)

    def entities_mentioned_in(self, doc_id: str, project_id: str) -> list[dict]:
        """The entities a document mentions, by name: `{id, name, entity_type}`."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (d:Document {id: $doc_id})-[:MENTIONS]->(e:Entity)
                WHERE e.project_id = $project_id AND NOT e:Document
                RETURN e.id AS id, e.name AS name, e.entity_type AS entity_type
                ORDER BY e.name, e.id
                """,
                doc_id=doc_id, project_id=project_id,
            )
            return [dict(record) for record in result]

    def count_entities_mentioned(self, doc_ids: list[str], project_id: str) -> dict[str, int]:
        """How many entities each document mentions. Documents mentioning none are absent."""
        if not doc_ids:
            return {}
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (d:Document)-[:MENTIONS]->(e:Entity)
                WHERE d.id IN $doc_ids AND e.project_id = $project_id AND NOT e:Document
                RETURN d.id AS doc_id, count(DISTINCT e) AS n
                """,
                doc_ids=list(doc_ids), project_id=project_id,
            )
            return {record["doc_id"]: record["n"] for record in result}

    def documents_mentioning(
        self, entity_id: str, project_id: str, limit: int = 20, offset: int = 0,
    ) -> tuple[list[dict], int]:
        """The documents in `project_id` that mention an entity, and how many there are.

        Most mentions first, then the earliest seen. Each row carries the
        document's content so the caller can cut evidence passages from it;
        `limit` bounds how much text one call moves.
        """
        with self._driver.session() as session:
            total = session.run(
                """
                MATCH (d:Document)-[:MENTIONS]->(:Entity {id: $id})
                WHERE d.project_id = $project_id
                RETURN count(DISTINCT d) AS n
                """,
                id=entity_id, project_id=project_id,
            ).single()["n"]
            rows = session.run(
                """
                MATCH (d:Document)-[m:MENTIONS]->(:Entity {id: $id})
                WHERE d.project_id = $project_id
                RETURN d.id AS id, d.name AS name, coalesce(d.url, '') AS url,
                       coalesce(d.source_doc_id, '') AS source_doc_id,
                       coalesce(m.count, 1) AS mention_count, m.first_seen AS first_seen,
                       coalesce(d.content, '') AS content
                ORDER BY mention_count DESC, first_seen, d.id
                SKIP $offset LIMIT $limit
                """,
                id=entity_id, project_id=project_id, offset=max(0, int(offset)), limit=max(0, int(limit)),
            )
            return [dict(record) for record in rows], total

    def mentioning_documents(self, entity_ids: list[str], project_id: str, limit: int) -> list[dict]:
        """Documents that mention any of `entity_ids`, ranked, at most `limit`.

        Ranked by the earliest entity in `entity_ids` they mention — callers
        pass the entities they care about most first — then by how many
        mentions they carry. One statement however many entities are passed:
        retrieval used to fetch documents one id at a time. Rows are
        `{id, name, reliability_rating}`; content is fetched separately, for
        the few documents that will be quoted.
        """
        ids = [i for i in dict.fromkeys(entity_ids) if i]
        if not ids or limit <= 0:
            return []
        with self._driver.session() as session:
            result = session.run(
                """
                UNWIND range(0, size($ids) - 1) AS i
                MATCH (d:Document)-[m:MENTIONS]->(e:Entity {id: $ids[i]})
                WHERE d.project_id = $project_id
                WITH d, min(i) AS rank, sum(coalesce(m.count, 1)) AS weight
                ORDER BY rank, weight DESC, d.id
                LIMIT $limit
                RETURN d.id AS id, d.name AS name, coalesce(d.reliability_rating, '') AS reliability_rating
                """,
                ids=ids, project_id=project_id, limit=int(limit),
            )
            return [dict(record) for record in result]

    def documents_content(self, doc_ids: list[str], project_id: str) -> dict[str, dict]:
        """`{id: {name, content, reliability_rating}}` for Documents of the project."""
        if not doc_ids:
            return {}
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (d:Document) WHERE d.id IN $ids AND d.project_id = $project_id
                RETURN d.id AS id, d.name AS name, coalesce(d.content, '') AS content,
                       coalesce(d.reliability_rating, '') AS reliability_rating
                """,
                ids=list(doc_ids), project_id=project_id,
            )
            return {
                r["id"]: {"name": r["name"], "content": r["content"], "reliability_rating": r["reliability_rating"]}
                for r in result
            }

    def get_geolocatable_entities(self, project_id: str, limit: int = 2000) -> list[dict]:
        """Nodes that can appear on the map: any Location-category node, an
        IPAddress carrying a GeoIP `geolocation` blob, or any node already
        carrying latitude/longitude. Superset of the old Location-only query so
        IP/WHOIS geo (and future geocoded subtypes) surface on the map.
        """
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (n:Entity) WHERE n.project_id = $project_id AND (
                    n.entity_category = 'Location' OR n.entity_type = 'Location'
                    OR (n.latitude IS NOT NULL AND n.longitude IS NOT NULL)
                    OR (n.entity_type = 'IPAddress' AND n.geolocation IS NOT NULL AND n.geolocation <> '')
                )
                RETURN n LIMIT $limit
                """,
                project_id=project_id, limit=limit,
            )
            return [dict(record["n"]) for record in result]

    def find_entity_by_exact_name(
        self, project_id: str, name: str, entity_type: str | None = None,
    ) -> dict | None:
        """Deterministic case-insensitive exact-name match within a project.

        Used to dedup enrichment-created related nodes (e.g. a country parent):
        the fulltext top-N can miss a high-frequency name like "Russia", which
        would spawn duplicate roll-up nodes. Optional entity_type narrows it.
        """
        cypher = "MATCH (n:Entity) WHERE n.project_id = $project_id AND toLower(n.name) = toLower($name)"
        params: dict = {"project_id": project_id, "name": name}
        if entity_type:
            cypher += " AND n.entity_type = $entity_type"
            params["entity_type"] = entity_type
        cypher += " RETURN n LIMIT 1"
        with self._driver.session() as session:
            record = session.run(cypher, **params).single()
            return dict(record["n"]) if record else None

    def _entity_filter(self, project_id: str, query: str, entity_type: str | None) -> tuple[str, dict]:
        """The WHERE clause shared by searching and counting.

        Built once so a total can never describe a different set than the page
        it accompanies — the count is what tells the analyst the list is
        truncated, and a count of something else would be worse than none.
        """
        cypher = "MATCH (n:Entity) WHERE n.project_id = $project_id"
        params: dict = {"project_id": project_id}
        if entity_type:
            cypher += " AND n.entity_type = $entity_type"
            params["entity_type"] = entity_type
        # Every term must appear somewhere in the name, in any order.
        #
        # This matched the whole query as one literal substring, so any search
        # of more than one word returned nothing: on a 5,486-entity project
        # about Baltic cable sabotage, "Baltic" and "cable" each returned
        # results and "Baltic cable" returned zero — no entity is named that
        # exactly. An analyst typing a phrase, which is how anyone uses a
        # search box, got a well-formed empty page.
        #
        # A term may also be in one of the entity's aliases: a search for
        # "Kremlin" finds Russia once a document has named it that way.
        for i, term in enumerate(_search_terms(query)):
            cypher += f" AND {_matches_term('n', f'$q{i}')}"
            params[f"q{i}"] = term
        return cypher, params

    def count_entities(self, project_id: str, query: str = "", entity_type: str | None = None) -> int:
        """How many entities match, ignoring the page size.

        Every list view showed the first 50 with nothing to say so: the geo map
        plotted 50 of 398 locations, and the network sidebar grouped 50 of
        5,486 entities into type headings that read as totals. ~0.015s warm.
        """
        cypher, params = self._entity_filter(project_id, query, entity_type)
        with self._driver.session() as session:
            record = session.run(cypher + " RETURN count(n) AS total", parameters=params).single()
            return record["total"] if record else 0

    def search_entities(
        self, project_id: str, query: str = "", entity_type: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[dict]:
        """One page of the entities `_entity_filter` matches, by name, each with its `relationship_count`.

        `relationship_count` is the entity's degree over the knowledge graph:
        every edge touching it except the Document MENTIONS edges that record
        where it was extracted from (``_not_provenance``), so it counts what
        `get_relationships` lists. Computed after the page is cut, so a page
        costs one expansion per row it returns, not one per match.
        """
        cypher, params = self._entity_filter(project_id, query, entity_type)
        params.update(limit=limit, offset=offset)
        cypher += f"""
            WITH n ORDER BY n.name SKIP $offset LIMIT $limit
            OPTIONAL MATCH (n)-[r]-() WHERE {_not_provenance('r')}
            WITH n, count(DISTINCT r) AS relationship_count
            RETURN n, relationship_count ORDER BY n.name
        """
        with self._driver.session() as session:
            result = session.run(cypher, parameters=params)
            return [
                {**dict(record["n"]), "relationship_count": record["relationship_count"]}
                for record in result
            ]

    VALID_REL_TYPES = {
        "ASSOCIATED_WITH", "BELONGS_TO", "LOCATED_AT", "COMMUNICATES_WITH",
        "RESOLVES_TO", "EXPLOITS", "USES", "TARGETS", "ATTRIBUTED_TO",
        "MENTIONED_IN", "MENTIONS", "PARENT_OF", "RELATED_TO", "ASSESSES",
        "SUPPORTED_BY", "SHARED_WITH", "OCCURRED_ON",
        "COMMANDED_BY", "FUNDED_BY", "SUPPLIED_BY", "DEPLOYED_AT",
    }

    def search_entity_by_name(
        self, project_id: str, name: str, limit: int = 20, match_aliases: bool = True,
    ) -> list[dict]:
        """Search entities by name using the fulltext index for efficient resolution.

        Returns candidate entities for fuzzy matching — much faster than loading
        all entities when the project is large. With `match_aliases`, up to
        `limit` entities carrying `name` as one of their aliases (ignoring
        case) follow the name hits: the name index covers names only, and
        resolution matches aliases too, so the entity "Fancy Bear" names must
        be among the candidates for it to be found. That costs a scan of the
        project's entities (~14 ms at 22k), so a caller that will not match
        aliases turns it off.
        """
        with self._driver.session() as session:
            candidates = self._candidates_by_name(session, project_id, name, limit)
            if not match_aliases:
                return candidates
            result = session.run(
                """
                MATCH (n:Entity)
                WHERE n.project_id = $project_id AND n.aliases IS NOT NULL
                  AND any(a IN n.aliases WHERE toLower(a) = toLower($search_name))
                RETURN n
                LIMIT $limit
                """,
                parameters={"search_name": name, "project_id": project_id, "limit": limit},
            )
            seen = {c.get("id") for c in candidates}
            return candidates + [n for n in (dict(record["n"]) for record in result) if n.get("id") not in seen]

    @staticmethod
    def _candidates_by_name(session, project_id: str, name: str, limit: int) -> list[dict]:
        # Try fulltext index first
        try:
            result = session.run(
                """
                CALL db.index.fulltext.queryNodes("entity_name_search", $search_name)
                YIELD node, score
                WHERE node.project_id = $project_id
                RETURN node
                LIMIT $limit
                """,
                parameters={"search_name": name, "project_id": project_id, "limit": limit},
            )
            candidates = [dict(record["node"]) for record in result]
            if candidates:
                return candidates
        except Exception:
            pass  # Fulltext index may not exist; fall through

        # Fallback: CONTAINS search
        result = session.run(
            """
            MATCH (n)
            WHERE n.project_id = $project_id
            AND toLower(n.name) CONTAINS toLower($search_name)
            RETURN n
            LIMIT $limit
            """,
            parameters={"search_name": name, "project_id": project_id, "limit": limit},
        )
        return [dict(record["n"]) for record in result]

    # Distinct evidence sentences kept per list on one edge.
    _MAX_EVIDENCE = 20

    @classmethod
    def _merge_assertion(cls, current: dict, props: dict) -> dict:
        """The update that folds one more assertion of a claim into its edge.

        Agreement and disagreement are relative to the polarity the edge was
        first asserted with. An agreeing source corroborates; a disagreeing one
        is recorded in `contradicting_sources` and turns the edge CONFLICT, and
        is never counted as corroboration — it was, because the source was
        appended before its polarity was compared. Evidence sentences are kept
        per side (`evidence_all`, `contradicting_evidence`) instead of only the
        first; `evidence` stays the first sentence, the primary reference.
        """
        new_doc = props.get("source_doc_id") or ""
        new_evidence = props.get("evidence") or ""
        prior_polarity = str(current.get("polarity") or "asserts").lower()
        new_polarity = str(props.get("polarity") or "asserts").lower()
        agrees = new_polarity == prior_polarity

        sources = list(current.get("corroboration_sources") or [])
        if current.get("source_doc_id") and current["source_doc_id"] not in sources:
            sources.append(current["source_doc_id"])
        contradicting = list(current.get("contradicting_sources") or [])
        evidence_all = list(current.get("evidence_all") or ([current["evidence"]] if current.get("evidence") else []))
        contradicting_evidence = list(current.get("contradicting_evidence") or [])

        # Only a *different* source corroborates. Two mentions inside one
        # document are one source, not two — that distinction is the whole
        # point of a corroboration count.
        side_sources, side_evidence = (sources, evidence_all) if agrees else (contradicting, contradicting_evidence)
        if new_doc and new_doc not in side_sources:
            side_sources.append(new_doc)
        if new_evidence and new_evidence not in side_evidence and len(side_evidence) < cls._MAX_EVIDENCE:
            side_evidence.append(new_evidence)

        # Contradiction. A source that denies what another asserts must not
        # be absorbed as further agreement — that is how contested reporting
        # silently becomes settled fact. Once disputed, stays disputed until
        # reviewed.
        prior_agreement = str(current.get("corroboration_agreement") or "AGREE").upper()
        agreement = "CONFLICT" if (not agrees or prior_agreement == "CONFLICT") else prior_agreement

        prior_conf = float(current.get("confidence") or 0)
        new_conf = float(props.get("confidence") or 0)
        return {
            "corroboration_count": len(sources) if sources else int(current.get("corroboration_count") or 1),
            "corroboration_sources": sources,
            "contradicting_sources": contradicting,
            "corroboration_agreement": agreement,
            # Keep the strongest assessed confidence — except once sources
            # disagree, where the prior confidence no longer stands alone.
            "confidence": min(prior_conf, new_conf) if agreement == "CONFLICT" else max(prior_conf, new_conf),
            "evidence": current.get("evidence") or (new_evidence if agrees else ""),
            # The offset belongs to the evidence it locates.
            "evidence_offset": (
                current.get("evidence_offset", -1) if current.get("evidence")
                else (props.get("evidence_offset", -1) if agrees and new_evidence else -1)
            ),
            "evidence_all": evidence_all,
            "contradicting_evidence": contradicting_evidence,
            "source_doc_id": current.get("source_doc_id") or (new_doc if agrees else ""),
            "last_seen": props.get("last_seen") or current.get("last_seen"),
            # The edge keeps the polarity it was first asserted with; the
            # disagreement is carried by corroboration_agreement.
            "polarity": prior_polarity,
        }

    def create_relationship(self, rel) -> dict:
        if rel.rel_type not in self.VALID_REL_TYPES:
            raise ValueError(f"Invalid relationship type: {rel.rel_type}")
        project_id = getattr(rel, "project_id", "") or ""
        props = self._serialize_props(
            rel.model_dump(exclude={"source_id", "target_id", "rel_type", "project_id"})
        )
        # The type is interpolated, not a parameter, so MERGE can name it; it
        # is safe because it has just been checked against the allowlist.
        rel_type = rel.rel_type
        # With a project, both endpoints are matched inside it: an edge can
        # never join two projects, and the edge is stamped with its project.
        scope = ""
        if project_id:
            props["project_id"] = project_id
            scope = "WHERE a.project_id = $project_id AND b.project_id = $project_id"

        def _upsert(tx) -> dict:
            # Corroboration: the same claim asserted by a second document is not
            # a second edge, it is the same edge with more support.
            #
            # One write transaction. MERGE between two bound nodes locks both,
            # so concurrent assertions of one claim make one edge; the lock SET
            # then holds the edge itself until commit, so the read-modify-write
            # below cannot interleave with another. It was a lookup followed by
            # a separate create or update, so concurrent builds duplicated the
            # edge or wrote back each other's stale source lists.
            record = tx.run(
                f"""
                MATCH (a:Entity {{id: $source_id}})
                MATCH (b:Entity {{id: $target_id}})
                {scope}
                MERGE (a)-[r:{rel_type}]->(b)
                ON CREATE SET r = $props
                SET r._upsert_lock = true
                REMOVE r._upsert_lock
                WITH r, coalesce(r.id = $new_id, false) AS created
                ORDER BY created DESC, elementId(r)
                LIMIT 1
                RETURN r, created, elementId(r) AS eid
                """,
                source_id=rel.source_id, target_id=rel.target_id,
                props=props, new_id=props.get("id"), project_id=project_id,
            ).single()
            if record is None:
                return {}  # an endpoint is missing, or outside the project
            if record["created"]:
                return dict(record["r"])
            update = self._merge_assertion(dict(record["r"]), props)
            if project_id:
                update["project_id"] = project_id
            return dict(tx.run(
                "MATCH ()-[r]->() WHERE elementId(r) = $eid SET r += $update RETURN r",
                eid=record["eid"], update=self._serialize_props(update),
            ).single()["r"])

        with self._driver.session() as session:
            rel_data = session.execute_write(_upsert)

        # Invalidate graph cache — resolve project_id from source entity
        project_id = getattr(rel, "project_id", None) or props.get("project_id")
        if not project_id:
            source_entity = self.get_entity(rel.source_id)
            if source_entity:
                project_id = source_entity.get("project_id")
        if project_id:
            from intel_platform.services.graph_cache import graph_cache
            graph_cache.invalidate(project_id)

        return rel_data

    # What a relationship read returns for each edge touching the queried node
    # `n`. The match is undirected so both ends are found, but the endpoints are
    # read from the edge itself: this used to report `n` as the source and the
    # neighbour as the target for every edge, so an incoming edge came back
    # reversed and entity merge rebuilt it that way.
    _REL_ROW = """
        type(r) AS rel_type, properties(r) AS props,
        startNode(r).id AS source_id, startNode(r).name AS source_name,
        endNode(r).id AS target_id, endNode(r).name AS target_name,
        CASE WHEN startNode(r) = n THEN 'out' ELSE 'in' END AS direction,
        m.id AS neighbor_id, m.name AS neighbor_name
    """

    @staticmethod
    def _rel_from_record(record) -> dict:
        """One relationship, properties spread flat.

        The structural keys are written after the properties so an edge
        property can never shadow where the edge actually points.
        """
        return {
            **record["props"],
            "rel_type": record["rel_type"],
            "source_id": record["source_id"], "source_name": record["source_name"],
            "target_id": record["target_id"], "target_name": record["target_name"],
            # Relative to the queried entity: "out" when it is the start node.
            "direction": record["direction"],
            # The other end, whichever way the edge points.
            "neighbor_id": record["neighbor_id"], "neighbor_name": record["neighbor_name"],
        }

    def get_relationships(self, entity_id: str) -> list[dict]:
        """Every edge touching the entity, in its true direction.

        `source_*`/`target_*` are the edge's real start and end nodes;
        `direction` is "out" when the queried entity is the source and "in"
        when it is the target; `neighbor_*` is the other end either way.
        """
        with self._driver.session() as session:
            result = session.run(
                f"MATCH (n:Entity {{id: $id}})-[r]-(m) WHERE {_not_provenance('r')} RETURN {self._REL_ROW}",
                id=entity_id,
            )
            return [self._rel_from_record(record) for record in result]

    def get_relationships_bulk(self, entity_ids: list[str]) -> dict[str, list[dict]]:
        """Relationships for many entities in one round trip.

        Same per-entity shape as `get_relationships`, keyed by entity id. The
        geo view called that once per location and then a second time to build
        location-to-location edges: 796 queries for 398 locations, 10.2s of an
        11.2s response.

        Entities with no relationships are absent from the mapping, so callers
        should use `.get(id, [])` — an absent key is "none", not "unknown".
        """
        if not entity_ids:
            return {}
        with self._driver.session() as session:
            result = session.run(
                f"""
                MATCH (n:Entity)-[r]-(m)
                WHERE n.id IN $ids AND {_not_provenance('r')}
                RETURN n.id AS key, {self._REL_ROW}
                """,
                ids=list(entity_ids),
            )
            out: dict[str, list[dict]] = {}
            for record in result:
                out.setdefault(record["key"], []).append(self._rel_from_record(record))
            return out

    def get_subgraph(self, entity_id: str, hops: int = 1, project_id: str | None = None) -> dict:
        """Everything within `hops` of the entity, as nodes and directed edges.

        `hops` is clamped to 1..4. With `project_id`, the start node must be in
        that project, every other node on a path must be too, and a catalog
        node (see CATALOG_LABELS) may only end a path. Without it the walk is
        unscoped, as before. At most `_MAX_SUBGRAPH_PATHS` paths are read;
        `truncated` says whether that budget cut the walk short.
        """
        hops = _clamp_hops(hops)
        params: dict = {"id": entity_id, "max_paths": _MAX_SUBGRAPH_PATHS}
        start_scope = ""
        # Document mentions are provenance, not part of the walk.
        path_scope = f"WHERE all(r IN relationships(path) WHERE {_not_provenance('r')})"
        if project_id:
            params["project_id"] = project_id
            start_scope = "WHERE start.project_id = $project_id"
            path_scope += f"""
                  AND all(x IN nodes(path) WHERE x.project_id = $project_id OR {_is_catalog('x')})
                  AND none(x IN nodes(path)[1..-1] WHERE {_is_catalog('x')})
            """
        with self._driver.session() as session:
            result = session.run(
                f"""
                MATCH (start:Entity {{id: $id}}) {start_scope}
                MATCH path = (start)-[*1..{hops}]-(connected)
                {path_scope}
                WITH path LIMIT $max_paths + 1
                WITH collect(path) AS all_paths
                WITH all_paths[..$max_paths] AS paths, size(all_paths) > $max_paths AS truncated
                UNWIND paths AS p
                UNWIND nodes(p) AS n
                WITH paths, truncated, collect(DISTINCT n) AS nodes
                UNWIND paths AS p
                UNWIND relationships(p) AS r
                WITH truncated, nodes, collect(DISTINCT r) AS rels
                RETURN
                    truncated,
                    [n IN nodes | properties(n)] as nodes,
                    [r IN rels | {{
                        rel_type: type(r),
                        source_id: startNode(r).id,
                        target_id: endNode(r).id,
                        props: properties(r)
                    }}] as edges
                """,
                parameters=params,
            )
            record = result.single()
            if not record:
                return {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0, "truncated": False}
            return {
                "nodes": record["nodes"], "edges": record["edges"],
                "node_count": len(record["nodes"]), "edge_count": len(record["edges"]),
                "truncated": bool(record["truncated"]),
            }

    @staticmethod
    def _strip_heavy_props(props: dict) -> dict:
        """Remove large fields from node properties for graph visualization."""
        stripped = {}
        for k, v in props.items():
            if k == "content":
                continue  # Skip full document content
            if isinstance(v, str) and len(v) > 200:
                stripped[k] = v[:200] + "..."
            else:
                stripped[k] = v
        return stripped

    def get_full_graph(self, project_id: str, limit: int = 500) -> dict:
        """The project subgraph, most-connected first.

        `limit` is a display budget, not a filter: this project holds 5,486
        entities and the view shows 500. Selection was `MATCH (n) ... LIMIT`
        with no ordering, so which 500 an analyst saw was whatever order the
        scan happened to produce — and since URL nodes outnumber everything
        else, the Network Analysis view rendered 500 nodes joined by 82 edges,
        439 of them isolated dots. 211 were URLs.

        Spending the budget on the connected core instead turns the same view
        into 500 nodes and 500 edges of Organizations, Campaigns, Locations,
        Events and People. Isolated nodes still appear, but only once the
        connected ones have had their turn — an entity with no links is a
        finding worth seeing, just not ahead of the graph itself.

        Costs ~2.1s cold against ~0.25s before: ranking needs the relationship
        counts, and an unlabeled `project_id` match cannot use a label index.
        The route caches for 30s, so only the first caller pays it.

        The selection is deterministic — nodes by degree then id, edges by
        confidence then endpoints — so two builds of one project keep the same
        slice. Ties used to fall to scan order. `truncated` is True when the
        budget cut nodes or edges: analytics read the 10,000-node build as if
        it were the whole project, with nothing to say it might not be.
        """
        limit = max(0, int(limit))
        with self._driver.session() as session:
            # One row past the budget, so a full page is distinguishable from a
            # truncated one without a separate count.
            nodes_result = session.run(
                f"""
                MATCH (n:Entity) WHERE n.project_id = $project_id
                OPTIONAL MATCH (n)-[r]-() WHERE {_not_provenance('r')}
                WITH n, count(r) AS degree
                ORDER BY degree DESC, n.id
                LIMIT $limit + 1
                RETURN properties(n) as props
                """,
                project_id=project_id, limit=limit,
            )
            nodes = [self._strip_heavy_props(record["props"]) for record in nodes_result]
            truncated = len(nodes) > limit
            nodes = nodes[:limit]
            node_ids = [n.get("id") for n in nodes if n.get("id")]
            # Restricted to the nodes actually returned. The edge query used to
            # run its own independent LIMIT over the whole project, so nothing
            # stopped it describing nodes the caller never received; that it
            # never did was luck of the scan order, not a guarantee.
            edges_result = session.run(
                f"""
                MATCH (a)-[r]->(b)
                WHERE a.id IN $node_ids AND b.id IN $node_ids AND {_not_provenance('r')}
                WITH r, a.id AS source_id, b.id AS target_id
                ORDER BY coalesce(r.confidence, 0.0) DESC, source_id, type(r), target_id
                LIMIT $limit + 1
                RETURN type(r) as rel_type, source_id, target_id, properties(r) as props
                """,
                node_ids=node_ids, limit=limit,
            )
            edges = [
                {"rel_type": r["rel_type"], "source_id": r["source_id"],
                 "target_id": r["target_id"], **r["props"]}
                for r in edges_result
            ]
            truncated = truncated or len(edges) > limit
            edges = edges[:limit]
            return {"nodes": nodes, "edges": edges,
                    "node_count": len(nodes), "edge_count": len(edges),
                    "truncated": truncated}

    def find_shortest_path(self, entity_id_1: str, entity_id_2: str, project_id: str | None = None) -> dict:
        """Shortest undirected path between two entities, up to 10 hops.

        With `project_id`, both ends and every node between them must belong to
        that project. Both ends are entities, so a catalog node could only ever
        be interior — which the scoping rule forbids — and none qualify.
        """
        params: dict = {"id1": entity_id_1, "id2": entity_id_2}
        end_scope = ""
        # Two entities named in one document are not connected by that alone.
        path_scope = f"WHERE all(r IN relationships(path) WHERE {_not_provenance('r')})"
        if project_id:
            params["project_id"] = project_id
            end_scope = "WHERE a.project_id = $project_id AND b.project_id = $project_id"
            path_scope += " AND all(x IN nodes(path) WHERE x.project_id = $project_id)"
        with self._driver.session() as session:
            result = session.run(
                f"""
                MATCH (a:Entity {{id: $id1}}), (b:Entity {{id: $id2}}) {end_scope}
                MATCH path = shortestPath((a)-[*..{_SHORTEST_PATH_MAX_HOPS}]-(b))
                {path_scope}
                RETURN [n IN nodes(path) | properties(n)] as nodes,
                       [r IN relationships(path) | {{
                           rel_type: type(r),
                           source_id: startNode(r).id,
                           target_id: endNode(r).id,
                           props: properties(r)
                       }}] as edges,
                       length(path) as path_length
                """,
                parameters=params,
            )
            record = result.single()
            if not record:
                return {"nodes": [], "edges": [], "path_length": -1, "found": False}
            return {
                "nodes": record["nodes"],
                "edges": record["edges"],
                "path_length": record["path_length"],
                "found": True,
            }

    def delete_entity(self, entity_id: str) -> None:
        # Look up project_id before deleting so we can invalidate the cache
        entity = self.get_entity(entity_id)
        project_id = entity.get("project_id") if entity else None

        with self._driver.session() as session:
            summary = session.run("MATCH (n:Entity {id: $id}) DETACH DELETE n", id=entity_id).consume()
            if summary.counters.nodes_deleted == 0 and entity is not None:
                # Unlabelled node (see get_entity).
                session.run("MATCH (n {id: $id}) DETACH DELETE n", id=entity_id)

        if project_id:
            from intel_platform.services.graph_cache import graph_cache
            graph_cache.invalidate(project_id)

    def create_project(self, name: str, description: str, classification_level: str, priority: str) -> dict:
        import uuid
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        props = {
            "id": str(uuid.uuid4()), "name": name, "description": description,
            "classification_level": classification_level, "priority": priority,
            "status": "active", "created_at": now, "updated_at": now,
            "entity_type": "Project", "project_id": "",
        }
        with self._driver.session() as session:
            result = session.run("CREATE (n:Project:Entity $props) RETURN n", props=props)
            record = result.single()
            return dict(record["n"]) if record else {}

    def list_projects(self) -> list[dict]:
        with self._driver.session() as session:
            result = session.run(
                "MATCH (p:Project) RETURN properties(p) as props ORDER BY p.created_at DESC"
            )
            return [record["props"] for record in result]

    def get_project(self, project_id: str) -> dict | None:
        with self._driver.session() as session:
            result = session.run("MATCH (p:Project {id: $id}) RETURN p", id=project_id)
            record = result.single()
            return dict(record["p"]) if record else None

    ALLOWED_PROJECT_FIELDS = {"name", "description", "classification_level", "priority", "status"}

    def update_project(self, project_id: str, **kwargs) -> None:
        from datetime import datetime, timezone
        safe_kwargs = {k: v for k, v in kwargs.items() if k in self.ALLOWED_PROJECT_FIELDS}
        if not safe_kwargs:
            return
        safe_kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
        set_clauses = ", ".join(f"p.{k} = ${k}" for k in safe_kwargs)
        with self._driver.session() as session:
            session.run(f"MATCH (p:Project {{id: $id}}) SET {set_clauses}", id=project_id, **safe_kwargs)

    def get_latest_entity_time(self, project_id: str) -> str | None:
        """Get the latest entity created_at time in a project."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (n:Entity {project_id: $pid}) WHERE NOT n:Project AND n.created_at IS NOT NULL
                RETURN n.created_at as created_at ORDER BY n.created_at DESC LIMIT 1
                """,
                pid=project_id,
            )
            record = result.single()
            if not record or not record["created_at"]:
                return None
            val = record["created_at"]
            if hasattr(val, "isoformat"):
                return val.isoformat()
            return str(val)

    def get_project_stats(self, project_id: str) -> dict:
        with self._driver.session() as session:
            result = session.run(
                f"""
                OPTIONAL MATCH (n:Entity {{project_id: $pid}}) WHERE NOT n:Project
                WITH count(n) as entity_count
                OPTIONAL MATCH (d:Document {{project_id: $pid}})
                WITH entity_count, count(d) as doc_count
                OPTIONAL MATCH (a {{project_id: $pid}})-[r]->(b {{project_id: $pid}}) WHERE {_not_provenance('r')}
                RETURN entity_count, doc_count, count(r) as rel_count
                """,
                pid=project_id,
            )
            record = result.single()
            return {"entity_count": record["entity_count"],
                    "document_count": record["doc_count"],
                    "relationship_count": record["rel_count"]}
