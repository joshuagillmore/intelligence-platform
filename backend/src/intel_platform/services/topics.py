from __future__ import annotations
from collections import defaultdict
from intel_platform.graph.store import GraphStore


class TopicTreeService:
    def __init__(self, store: GraphStore):
        self._store = store

    def build_topic_tree(self, project_id: str) -> dict:
        """Build a hierarchical topic tree from entities and their document sources."""
        entities = self._store.search_entities(project_id=project_id, limit=10000)

        # Separate documents from other entities
        documents = [e for e in entities if e.get("entity_type") == "Document"]
        non_doc_entities = [e for e in entities if e.get("entity_type") != "Document"]

        # Group entities by type for the type-based view
        by_type: dict[str, list] = defaultdict(list)
        for e in non_doc_entities:
            etype = e.get("entity_type", "Unknown")
            by_type[etype].append({
                "id": e.get("id", ""),
                "name": e.get("name", ""),
                "entity_type": etype,
            })

        # Build tree with two main branches: By Concept and By Type
        tree = {
            "name": "Knowledge Base",
            "id": "root",
            "entity_count": len(non_doc_entities),
            "document_count": len(documents),
            "children": [],
        }

        # Branch 1: By Document Source
        doc_branch = {
            "name": "By Source Document",
            "id": "branch-docs",
            "entity_type": "branch",
            "children": [],
            "count": len(documents),
        }
        for doc in documents:
            doc_name = doc.get("name", "Unknown")
            doc_id = doc.get("id", "")
            # Get entities related to this document
            rels = self._store.get_relationships(doc_id)
            related_entities = []
            for rel in rels:
                target = self._store.get_entity(rel.get("target_id", ""))
                if target and target.get("entity_type") != "Document":
                    related_entities.append({
                        "id": target.get("id", ""),
                        "name": target.get("name", ""),
                        "entity_type": target.get("entity_type", ""),
                    })
            doc_branch["children"].append({
                "name": doc_name,
                "id": doc_id,
                "entity_type": "document_source",
                "reliability": doc.get("reliability_rating", ""),
                "children": related_entities,
                "count": len(related_entities),
            })
        tree["children"].append(doc_branch)

        # Branch 2: By Entity Type
        type_branch = {
            "name": "By Entity Type",
            "id": "branch-types",
            "entity_type": "branch",
            "children": [],
            "count": len(non_doc_entities),
        }
        for etype, elist in sorted(by_type.items()):
            type_branch["children"].append({
                "name": etype,
                "id": f"type-{etype}",
                "entity_type": "category",
                "children": sorted(elist, key=lambda x: x["name"]),
                "count": len(elist),
            })
        tree["children"].append(type_branch)

        # Branch 3: Key Themes (auto-generated from high-degree entities)
        stats_data = self._store.get_full_graph(project_id=project_id, limit=5000)
        if stats_data.get("nodes"):
            # Find entities with most connections as "themes"
            degree_map: dict[str, int] = defaultdict(int)
            for edge in stats_data.get("edges", []):
                degree_map[edge.get("source_id", "")] += 1
                degree_map[edge.get("target_id", "")] += 1

            # Top entities by degree become themes
            entity_map = {e.get("id", ""): e for e in non_doc_entities}
            top_entities = sorted(degree_map.items(), key=lambda x: x[1], reverse=True)[:10]

            theme_branch = {
                "name": "Key Themes",
                "id": "branch-themes",
                "entity_type": "branch",
                "children": [],
                "count": min(10, len(top_entities)),
            }
            for eid, degree in top_entities:
                entity = entity_map.get(eid)
                if entity:
                    # Get connected entities for this theme
                    rels = self._store.get_relationships(eid)
                    connected = []
                    for rel in rels[:15]:
                        target = self._store.get_entity(rel.get("target_id", ""))
                        if target and target.get("entity_type") != "Document" and target.get("id") != eid:
                            connected.append({
                                "id": target.get("id", ""),
                                "name": target.get("name", ""),
                                "entity_type": target.get("entity_type", ""),
                                "relationship": rel.get("rel_type", ""),
                            })
                    theme_branch["children"].append({
                        "name": entity.get("name", ""),
                        "id": eid,
                        "entity_type": entity.get("entity_type", ""),
                        "degree": degree,
                        "children": connected,
                        "count": len(connected),
                    })
            tree["children"].append(theme_branch)

        return tree

    def get_topic_context(self, entity_id: str, project_id: str) -> dict:
        """Get full context for an entity — relationships, documents, and graph position."""
        entity = self._store.get_entity(entity_id)
        if not entity:
            return {"error": "Entity not found"}

        relationships = self._store.get_relationships(entity_id)

        documents = []
        connected = []
        for rel in relationships:
            target_id = rel.get("target_id", "")
            target = self._store.get_entity(target_id)
            if not target:
                continue
            if target.get("entity_type") == "Document":
                documents.append({
                    "id": target.get("id"),
                    "name": target.get("name"),
                    "reliability_rating": target.get("reliability_rating", ""),
                    "content_preview": (target.get("content", "") or "")[:300],
                })
            else:
                connected.append({
                    "id": target.get("id"),
                    "name": target.get("name"),
                    "entity_type": target.get("entity_type"),
                    "relationship": rel.get("rel_type"),
                    "confidence": rel.get("confidence", rel.get("props", {}).get("confidence")),
                })

        return {
            "entity": {
                "id": entity.get("id"),
                "name": entity.get("name"),
                "entity_type": entity.get("entity_type"),
            },
            "documents": documents,
            "connected_entities": connected,
            "relationship_count": len(relationships),
            "document_count": len(documents),
        }
