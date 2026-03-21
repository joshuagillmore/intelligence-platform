from __future__ import annotations
from collections import defaultdict
from intel_platform.graph.store import GraphStore


class TopicTreeService:
    """Build and manage topic trees from document entities."""

    def __init__(self, store: GraphStore):
        self._store = store

    def build_topic_tree(self, project_id: str) -> dict:
        """Build a topic tree from entities grouped by type and relationships."""
        entities = self._store.search_entities(project_id=project_id, limit=10000)

        # Group entities by type
        by_type: dict[str, list] = defaultdict(list)
        for e in entities:
            etype = e.get("entity_type", "Unknown")
            if etype == "Document":
                continue  # Documents are sources, not topics
            by_type[etype].append({
                "id": e.get("id", ""),
                "name": e.get("name", ""),
                "entity_type": etype,
            })

        # Build tree: root -> entity type categories -> individual entities
        tree = {
            "name": "Knowledge Base",
            "id": "root",
            "children": [],
            "entity_count": sum(len(v) for v in by_type.values()),
        }

        for etype, entities_list in sorted(by_type.items()):
            category = {
                "name": etype,
                "id": f"cat-{etype}",
                "entity_type": "category",
                "children": sorted(entities_list, key=lambda x: x["name"]),
                "count": len(entities_list),
            }
            tree["children"].append(category)

        return tree

    def get_topic_context(self, entity_id: str, project_id: str) -> dict:
        """Get context for a specific topic/entity — its relationships and source documents."""
        entity = self._store.get_entity(entity_id)
        if not entity:
            return {"error": "Entity not found"}

        relationships = self._store.get_relationships(entity_id)

        # Find source documents that mention this entity
        documents = []
        for rel in relationships:
            target = self._store.get_entity(rel.get("target_id", ""))
            if target and target.get("entity_type") == "Document":
                documents.append(target)

        # Get connected entities (non-document)
        connected = []
        for rel in relationships:
            target = self._store.get_entity(rel.get("target_id", ""))
            if target and target.get("entity_type") != "Document":
                connected.append({
                    "id": target.get("id"),
                    "name": target.get("name"),
                    "entity_type": target.get("entity_type"),
                    "relationship": rel.get("rel_type"),
                    "confidence": rel.get("confidence", rel.get("props", {}).get("confidence")),
                })

        return {
            "entity": entity,
            "documents": documents,
            "connected_entities": connected,
            "relationship_count": len(relationships),
        }
