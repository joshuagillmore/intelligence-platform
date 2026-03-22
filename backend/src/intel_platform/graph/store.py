from __future__ import annotations

import re

from neo4j import Driver

from intel_platform.models.entities import Entity, EntityType


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
        label = _validate_label(entity.entity_type.value)
        props = self._serialize_props(entity.model_dump(exclude={"entity_type"}))
        props["entity_type"] = label
        with self._driver.session() as session:
            result = session.run(
                f"CREATE (n:{label} $props) RETURN n",
                props=props,
            )
            record = result.single()
            return dict(record["n"]) if record else {}

    def get_entity(self, entity_id: str) -> dict | None:
        with self._driver.session() as session:
            result = session.run("MATCH (n {id: $id}) RETURN n", id=entity_id)
            record = result.single()
            return dict(record["n"]) if record else None

    def search_entities(
        self, project_id: str, query: str = "", entity_type: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[dict]:
        cypher = "MATCH (n) WHERE n.project_id = $project_id"
        params: dict = {"project_id": project_id, "limit": limit, "offset": offset}
        if entity_type:
            cypher += " AND n.entity_type = $entity_type"
            params["entity_type"] = entity_type
        if query:
            cypher += " AND toLower(n.name) CONTAINS toLower($query)"
            params["query"] = query
        cypher += " RETURN n ORDER BY n.name SKIP $offset LIMIT $limit"
        with self._driver.session() as session:
            result = session.run(cypher, parameters=params)
            return [dict(record["n"]) for record in result]

    VALID_REL_TYPES = {
        "ASSOCIATED_WITH", "BELONGS_TO", "LOCATED_AT", "COMMUNICATES_WITH",
        "RESOLVES_TO", "EXPLOITS", "USES", "TARGETS", "ATTRIBUTED_TO",
        "MENTIONED_IN", "MENTIONS", "PARENT_OF", "RELATED_TO", "ASSESSES",
        "SUPPORTED_BY", "SHARED_WITH",
    }

    def create_relationship(self, rel) -> dict:
        if rel.rel_type not in self.VALID_REL_TYPES:
            raise ValueError(f"Invalid relationship type: {rel.rel_type}")
        props = self._serialize_props(rel.model_dump(exclude={"source_id", "target_id", "rel_type"}))
        with self._driver.session() as session:
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
            return dict(record["rel"]) if record else {}

    def get_relationships(self, entity_id: str) -> list[dict]:
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (n {id: $id})-[r]-(m)
                RETURN type(r) as rel_type, properties(r) as props,
                       n.id as source_id, m.id as target_id, m.name as target_name
                """,
                id=entity_id,
            )
            return [
                {"rel_type": record["rel_type"], "target_id": record["target_id"],
                 "target_name": record["target_name"], **record["props"]}
                for record in result
            ]

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

    def get_full_graph(self, project_id: str, limit: int = 500) -> dict:
        with self._driver.session() as session:
            nodes_result = session.run(
                "MATCH (n) WHERE n.project_id = $project_id RETURN properties(n) as props LIMIT $limit",
                project_id=project_id, limit=limit,
            )
            nodes = [record["props"] for record in nodes_result]
            edges_result = session.run(
                """
                MATCH (a)-[r]->(b)
                WHERE a.project_id = $project_id
                RETURN type(r) as rel_type, startNode(r).id as source_id,
                       endNode(r).id as target_id, properties(r) as props
                LIMIT $limit
                """,
                project_id=project_id, limit=limit,
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
        with self._driver.session() as session:
            session.run("MATCH (n {id: $id}) DETACH DELETE n", id=entity_id)

    def create_project(self, name: str, description: str, classification_level: str, priority: str) -> dict:
        import uuid
        from datetime import datetime, timezone
        props = {
            "id": str(uuid.uuid4()), "name": name, "description": description,
            "classification_level": classification_level, "priority": priority,
            "status": "active", "created_at": datetime.now(timezone.utc).isoformat(),
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

    def update_project(self, project_id: str, **kwargs) -> None:
        set_clauses = ", ".join(f"p.{k} = ${k}" for k in kwargs)
        with self._driver.session() as session:
            session.run(f"MATCH (p:Project {{id: $id}}) SET {set_clauses}", id=project_id, **kwargs)

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
