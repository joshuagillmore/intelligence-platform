from __future__ import annotations

import re

from neo4j import Driver

from intel_platform.models.entities import Entity


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
        with self._driver.session() as session:
            result = session.run(
                f"CREATE (n:{label} $props) RETURN n",
                props=props,
            )
            record = result.single()
            node = dict(record["n"]) if record else {}

        # Invalidate graph cache for the project
        project_id = getattr(entity, "project_id", None) or props.get("project_id")
        if project_id:
            from intel_platform.services.graph_cache import graph_cache
            graph_cache.invalidate(project_id)

        return node

    def get_entity(self, entity_id: str) -> dict | None:
        with self._driver.session() as session:
            result = session.run("MATCH (n {id: $id}) RETURN n", id=entity_id)
            record = result.single()
            return dict(record["n"]) if record else None

    def update_entity(self, entity_id: str, props: dict) -> dict | None:
        """Merge `props` onto an existing node (by id). Returns the node or None.

        Used by enrichment to write looked-up properties (asn, dns_records,
        cvss_score, enriched flags) onto an already-extracted observable node.
        """
        if not props:
            return self.get_entity(entity_id)
        clean = self._serialize_props(props)
        with self._driver.session() as session:
            result = session.run(
                "MATCH (n {id: $id}) SET n += $props RETURN n",
                id=entity_id, props=clean,
            )
            record = result.single()
            node = dict(record["n"]) if record else None

        if node:
            project_id = node.get("project_id")
            if project_id:
                from intel_platform.services.graph_cache import graph_cache
                graph_cache.invalidate(project_id)
        return node

    def get_geolocatable_entities(self, project_id: str, limit: int = 2000) -> list[dict]:
        """Nodes that can appear on the map: any Location-category node, an
        IPAddress carrying a GeoIP `geolocation` blob, or any node already
        carrying latitude/longitude. Superset of the old Location-only query so
        IP/WHOIS geo (and future geocoded subtypes) surface on the map.
        """
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (n) WHERE n.project_id = $project_id AND (
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
        cypher = "MATCH (n) WHERE n.project_id = $project_id AND toLower(n.name) = toLower($name)"
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
        cypher = "MATCH (n) WHERE n.project_id = $project_id"
        params: dict = {"project_id": project_id}
        if entity_type:
            cypher += " AND n.entity_type = $entity_type"
            params["entity_type"] = entity_type
        for i, term in enumerate(_search_terms(query)):
            cypher += f" AND toLower(n.name) CONTAINS $q{i}"
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
        cypher = "MATCH (n) WHERE n.project_id = $project_id"
        params: dict = {"project_id": project_id, "limit": limit, "offset": offset}
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
        for i, term in enumerate(_search_terms(query)):
            cypher += f" AND toLower(n.name) CONTAINS $q{i}"
            params[f"q{i}"] = term
        cypher += " RETURN n ORDER BY n.name SKIP $offset LIMIT $limit"
        with self._driver.session() as session:
            result = session.run(cypher, parameters=params)
            return [dict(record["n"]) for record in result]

    VALID_REL_TYPES = {
        "ASSOCIATED_WITH", "BELONGS_TO", "LOCATED_AT", "COMMUNICATES_WITH",
        "RESOLVES_TO", "EXPLOITS", "USES", "TARGETS", "ATTRIBUTED_TO",
        "MENTIONED_IN", "MENTIONS", "PARENT_OF", "RELATED_TO", "ASSESSES",
        "SUPPORTED_BY", "SHARED_WITH", "OCCURRED_ON",
        "COMMANDED_BY", "FUNDED_BY", "SUPPLIED_BY", "DEPLOYED_AT",
    }

    def search_entity_by_name(self, project_id: str, name: str, limit: int = 20) -> list[dict]:
        """Search entities by name using the fulltext index for efficient resolution.

        Returns candidate entities for fuzzy matching — much faster than loading
        all entities when the project is large.
        """
        with self._driver.session() as session:
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

    def create_relationship(self, rel) -> dict:
        if rel.rel_type not in self.VALID_REL_TYPES:
            raise ValueError(f"Invalid relationship type: {rel.rel_type}")
        props = self._serialize_props(rel.model_dump(exclude={"source_id", "target_id", "rel_type"}))
        with self._driver.session() as session:
            # Corroboration: the same claim asserted by a second document is not a
            # second edge, it is the same edge with more support. Previously every
            # assertion created a duplicate, so corroboration_count sat at 1
            # forever and the graph accumulated near-identical edges.
            existing = session.run(
                """
                MATCH (a {id: $source_id})-[r]->(b {id: $target_id})
                WHERE type(r) = $rel_type
                RETURN r LIMIT 1
                """,
                source_id=rel.source_id, target_id=rel.target_id, rel_type=rel.rel_type,
            ).single()

            if existing:
                current = dict(existing["r"])
                new_doc = props.get("source_doc_id") or ""
                sources = list(current.get("corroboration_sources") or [])
                if current.get("source_doc_id") and current["source_doc_id"] not in sources:
                    sources.append(current["source_doc_id"])

                # Only a *different* source corroborates. Two mentions inside one
                # document are one source, not two — that distinction is the whole
                # point of a corroboration count.
                corroborated = bool(new_doc) and new_doc not in sources
                if corroborated:
                    sources.append(new_doc)

                # Contradiction. A source that denies what another asserts must not
                # be absorbed as further agreement — that is how contested
                # reporting silently becomes settled fact.
                prior_polarity = str(current.get("polarity") or "asserts").lower()
                new_polarity = str(props.get("polarity") or "asserts").lower()
                prior_agreement = str(current.get("corroboration_agreement") or "AGREE").upper()
                if prior_polarity != new_polarity:
                    agreement = "CONFLICT"
                elif prior_agreement == "CONFLICT":
                    agreement = "CONFLICT"  # once disputed, stays disputed until reviewed
                else:
                    agreement = prior_agreement

                update = {
                    "corroboration_count": max(len(sources), 1) if sources else int(current.get("corroboration_count") or 1),
                    "corroboration_sources": sources,
                    "corroboration_agreement": agreement,
                    # Keep the strongest assessed confidence — except once sources
                    # disagree, where the prior confidence no longer stands alone.
                    "confidence": (
                        min(float(current.get("confidence") or 0), float(props.get("confidence") or 0))
                        if agreement == "CONFLICT"
                        else max(float(current.get("confidence") or 0), float(props.get("confidence") or 0))
                    ),
                    # Keep the first captured sentence; it is the primary reference.
                    "evidence": current.get("evidence") or props.get("evidence", ""),
                    "source_doc_id": current.get("source_doc_id") or new_doc,
                    "last_seen": props.get("last_seen") or current.get("last_seen"),
                    # The edge keeps the polarity it was first asserted with; the
                    # disagreement is carried by corroboration_agreement.
                    "polarity": prior_polarity,
                }
                result = session.run(
                    """
                    MATCH (a {id: $source_id})-[r]->(b {id: $target_id})
                    WHERE type(r) = $rel_type
                    SET r += $update
                    RETURN type(r) as rel_type, r as rel
                    """,
                    source_id=rel.source_id, target_id=rel.target_id,
                    rel_type=rel.rel_type, update=self._serialize_props(update),
                )
            else:
                result = session.run(
                    """
                    MATCH (a {id: $source_id})
                    MATCH (b {id: $target_id})
                    CALL apoc.create.relationship(a, $rel_type, $props, b) YIELD rel
                    RETURN type(rel) as rel_type, rel
                    """,
                    source_id=rel.source_id, target_id=rel.target_id,
                    rel_type=rel.rel_type, props=props,
                )
            record = result.single()
            rel_data = dict(record["rel"]) if record else {}

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

    def get_relationships(self, entity_id: str) -> list[dict]:
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (n {id: $id})-[r]-(m)
                RETURN type(r) as rel_type, properties(r) as props,
                       n.id as source_id, n.name as source_name,
                       m.id as target_id, m.name as target_name
                """,
                id=entity_id,
            )
            return [
                {"rel_type": record["rel_type"], "target_id": record["target_id"],
                 "target_name": record["target_name"],
                 "source_id": record["source_id"], "source_name": record["source_name"],
                 **record["props"]}
                for record in result
            ]

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
                """
                MATCH (n)-[r]-(m)
                WHERE n.id IN $ids
                RETURN n.id as key, type(r) as rel_type, properties(r) as props,
                       n.id as source_id, n.name as source_name,
                       m.id as target_id, m.name as target_name
                """,
                ids=list(entity_ids),
            )
            out: dict[str, list[dict]] = {}
            for record in result:
                out.setdefault(record["key"], []).append({
                    "rel_type": record["rel_type"], "target_id": record["target_id"],
                    "target_name": record["target_name"],
                    "source_id": record["source_id"], "source_name": record["source_name"],
                    **record["props"],
                })
            return out

    def get_subgraph(self, entity_id: str, hops: int = 1) -> dict:
        with self._driver.session() as session:
            result = session.run(
                f"""
                MATCH path = (start {{id: $id}})-[*1..{hops}]-(connected)
                UNWIND nodes(path) as n
                WITH collect(DISTINCT n) as nodes, collect(relationships(path)) as all_rels
                UNWIND all_rels as path_rels
                UNWIND path_rels as r
                WITH nodes, collect(DISTINCT r) as rels
                RETURN
                    [n IN nodes | properties(n)] as nodes,
                    [r IN rels | {{
                        rel_type: type(r),
                        source_id: startNode(r).id,
                        target_id: endNode(r).id,
                        props: properties(r)
                    }}] as edges
                """,
                id=entity_id,
            )
            record = result.single()
            if not record:
                return {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0}
            return {
                "nodes": record["nodes"], "edges": record["edges"],
                "node_count": len(record["nodes"]), "edge_count": len(record["edges"]),
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
        """
        with self._driver.session() as session:
            nodes_result = session.run(
                """
                MATCH (n) WHERE n.project_id = $project_id
                OPTIONAL MATCH (n)-[r]-()
                WITH n, count(r) AS degree
                ORDER BY degree DESC
                LIMIT $limit
                RETURN properties(n) as props
                """,
                project_id=project_id, limit=limit,
            )
            nodes = [self._strip_heavy_props(record["props"]) for record in nodes_result]
            node_ids = [n.get("id") for n in nodes if n.get("id")]
            # Restricted to the nodes actually returned. The edge query used to
            # run its own independent LIMIT over the whole project, so nothing
            # stopped it describing nodes the caller never received; that it
            # never did was luck of the scan order, not a guarantee.
            edges_result = session.run(
                """
                MATCH (a)-[r]->(b)
                WHERE a.id IN $node_ids AND b.id IN $node_ids
                RETURN type(r) as rel_type, startNode(r).id as source_id,
                       endNode(r).id as target_id, properties(r) as props
                LIMIT $limit
                """,
                node_ids=node_ids, limit=limit,
            )
            edges = [
                {"rel_type": r["rel_type"], "source_id": r["source_id"],
                 "target_id": r["target_id"], **r["props"]}
                for r in edges_result
            ]
            return {"nodes": nodes, "edges": edges,
                    "node_count": len(nodes), "edge_count": len(edges)}

    def find_shortest_path(self, entity_id_1: str, entity_id_2: str) -> dict:
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH path = shortestPath((a {id: $id1})-[*..10]-(b {id: $id2}))
                RETURN [n IN nodes(path) | properties(n)] as nodes,
                       [r IN relationships(path) | {
                           rel_type: type(r),
                           source_id: startNode(r).id,
                           target_id: endNode(r).id,
                           props: properties(r)
                       }] as edges,
                       length(path) as path_length
                """,
                id1=entity_id_1,
                id2=entity_id_2,
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
            result = session.run("CREATE (n:Project $props) RETURN n", props=props)
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
                MATCH (n {project_id: $pid}) WHERE NOT n:Project AND n.created_at IS NOT NULL
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
                """
                OPTIONAL MATCH (n {project_id: $pid}) WHERE NOT n:Project
                WITH count(n) as entity_count
                OPTIONAL MATCH (d:Document {project_id: $pid})
                WITH entity_count, count(d) as doc_count
                OPTIONAL MATCH (a {project_id: $pid})-[r]->(b {project_id: $pid})
                RETURN entity_count, doc_count, count(r) as rel_count
                """,
                pid=project_id,
            )
            record = result.single()
            return {"entity_count": record["entity_count"],
                    "document_count": record["doc_count"],
                    "relationship_count": record["rel_count"]}
