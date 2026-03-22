from __future__ import annotations
from collections import defaultdict
import networkx as nx
from intel_platform.graph.store import GraphStore


class TopicTreeService:
    def __init__(self, store: GraphStore):
        self._store = store

    def build_topic_tree(self, project_id: str) -> dict:
        """Build a deep hierarchical topic tree using graph community structure."""
        entities = self._store.search_entities(project_id=project_id, limit=10000)
        graph_data = self._store.get_full_graph(project_id=project_id, limit=10000)

        documents = [e for e in entities if e.get("entity_type") == "Document"]
        non_docs = [e for e in entities if e.get("entity_type") != "Document"]
        entity_map = {e.get("id", ""): e for e in non_docs}

        # Build NetworkX graph for community detection
        G = nx.Graph()
        for e in non_docs:
            G.add_node(e["id"], **{k: v for k, v in e.items() if k != "id" and not isinstance(v, (dict, list))})
        for edge in graph_data.get("edges", []):
            sid, tid = edge.get("source_id", ""), edge.get("target_id", "")
            if sid in entity_map and tid in entity_map:
                G.add_edge(sid, tid)

        tree = {
            "name": "Knowledge Base",
            "id": "root",
            "entity_count": len(non_docs),
            "document_count": len(documents),
            "children": [],
        }

        # Branch 1: Thematic Clusters (community-based) — primary topic view
        themes_branch = self._build_theme_branch(G, entity_map, non_docs)
        if themes_branch["children"]:
            tree["children"].append(themes_branch)

        # Branch 2: By Source Document (with entity drilldown)
        doc_branch = self._build_document_branch(documents)
        if doc_branch["children"]:
            tree["children"].append(doc_branch)

        # Branch 3: Geographic Themes (locations grouped by region)
        geo_branch = self._build_geo_branch(non_docs)
        if geo_branch["children"]:
            tree["children"].append(geo_branch)

        # Branch 4: Actors & Organizations
        actor_branch = self._build_actor_branch(non_docs, G)
        if actor_branch["children"]:
            tree["children"].append(actor_branch)

        return tree

    def _build_theme_branch(self, G: nx.Graph, entity_map: dict, all_entities: list) -> dict:
        """Detect communities and name them by their most central entity."""
        branch = {
            "name": "Thematic Clusters",
            "id": "branch-themes",
            "entity_type": "branch",
            "children": [],
            "count": 0,
        }

        if len(G.nodes) < 2:
            return branch

        # Community detection
        try:
            import community as community_louvain
            partition = community_louvain.best_partition(G)
        except ImportError:
            from networkx.algorithms.community import greedy_modularity_communities
            communities = greedy_modularity_communities(G)
            partition = {}
            for i, comm in enumerate(communities):
                for node in comm:
                    partition[node] = i

        # Group by community
        comm_groups: dict[int, list[str]] = defaultdict(list)
        for node_id, comm_id in partition.items():
            comm_groups[comm_id].append(node_id)

        # For each community, find the most central node as the "theme name"
        # and create sub-groups by entity type within the community
        for comm_id, node_ids in sorted(comm_groups.items(), key=lambda x: -len(x[1])):
            if len(node_ids) < 2:
                continue

            # Find most connected node in this community
            subgraph = G.subgraph(node_ids)
            if not subgraph.nodes:
                continue
            central_node = max(subgraph.nodes, key=lambda n: subgraph.degree(n))
            central_entity = entity_map.get(central_node, {})
            theme_name = central_entity.get("name", f"Cluster {comm_id}")

            # Group community members by type
            by_type: dict[str, list] = defaultdict(list)
            for nid in node_ids:
                entity = entity_map.get(nid)
                if entity:
                    etype = entity.get("entity_type", "Unknown")
                    by_type[etype].append({
                        "id": nid,
                        "name": entity.get("name", ""),
                        "entity_type": etype,
                    })

            type_children = []
            for etype, elist in sorted(by_type.items()):
                type_children.append({
                    "name": etype,
                    "id": f"theme-{comm_id}-{etype}",
                    "entity_type": "sub_category",
                    "children": sorted(elist, key=lambda x: x["name"]),
                    "count": len(elist),
                })

            theme = {
                "name": f"{theme_name} Network",
                "id": f"theme-{comm_id}",
                "entity_type": "theme",
                "central_entity": theme_name,
                "children": type_children,
                "count": len(node_ids),
            }
            branch["children"].append(theme)

        branch["count"] = sum(c["count"] for c in branch["children"])
        return branch

    def _build_document_branch(self, documents: list) -> dict:
        """Documents with their related entities."""
        branch = {
            "name": "Source Documents",
            "id": "branch-docs",
            "entity_type": "branch",
            "children": [],
            "count": len(documents),
        }
        for doc in documents:
            doc_id = doc.get("id", "")
            rels = self._store.get_relationships(doc_id)
            related = []
            for rel in rels:
                target = self._store.get_entity(rel.get("target_id", ""))
                if target and target.get("entity_type") != "Document":
                    related.append({
                        "id": target.get("id", ""),
                        "name": target.get("name", ""),
                        "entity_type": target.get("entity_type", ""),
                    })
            branch["children"].append({
                "name": doc.get("name", "Unknown"),
                "id": doc_id,
                "entity_type": "document_source",
                "reliability": doc.get("reliability_rating", ""),
                "children": related,
                "count": len(related),
            })
        return branch

    def _build_category_branch(self, entities: list) -> dict:
        """Entities grouped by parent category, then by specific type."""
        from intel_platform.models.type_hierarchy import get_parent_category

        branch = {
            "name": "By Category",
            "id": "branch-categories",
            "entity_type": "branch",
            "children": [],
            "count": len(entities),
        }
        by_category: dict[str, list] = defaultdict(list)
        for e in entities:
            etype = e.get("entity_type", "Unknown")
            category = e.get("entity_category", get_parent_category(etype))
            by_category[category].append({
                "id": e.get("id", ""),
                "name": e.get("name", ""),
                "entity_type": etype,
            })

        for cat_name, cat_entities in sorted(by_category.items()):
            # Sub-group by specific type within category
            by_specific: dict[str, list] = defaultdict(list)
            for e in cat_entities:
                by_specific[e["entity_type"]].append(e)

            cat_children = []
            for specific_type, specific_entities in sorted(by_specific.items()):
                cat_children.append({
                    "name": specific_type,
                    "id": f"cat-{cat_name}-{specific_type}",
                    "entity_type": "sub_category",
                    "children": sorted(specific_entities, key=lambda x: x["name"]),
                    "count": len(specific_entities),
                })

            branch["children"].append({
                "name": cat_name,
                "id": f"cat-{cat_name}",
                "entity_type": "category",
                "children": cat_children,
                "count": len(cat_entities),
            })

        return branch

    def _build_type_branch(self, entities: list) -> dict:
        """Entities grouped by type."""
        by_type: dict[str, list] = defaultdict(list)
        for e in entities:
            etype = e.get("entity_type") or "Unknown"
            name = e.get("name") or "Unnamed"
            by_type[etype].append({
                "id": e.get("id", ""),
                "name": name,
                "entity_type": etype,
            })
        branch = {
            "name": "By Entity Type",
            "id": "branch-types",
            "entity_type": "branch",
            "children": [],
            "count": len(entities),
        }
        for etype, elist in sorted(by_type.items()):
            branch["children"].append({
                "name": etype,
                "id": f"type-{etype}",
                "entity_type": "category",
                "children": sorted(elist, key=lambda x: x["name"]),
                "count": len(elist),
            })
        return branch

    def _build_geo_branch(self, entities: list) -> dict:
        """Locations grouped by region heuristics."""
        REGIONS = {
            "East Asia": {"china", "japan", "south korea", "north korea", "taiwan", "mongolia", "beijing", "tokyo", "seoul", "pyongyang", "shanghai", "hong kong"},
            "Southeast Asia": {"vietnam", "philippines", "malaysia", "indonesia", "thailand", "myanmar", "singapore", "cambodia", "laos", "manila", "jakarta", "bangkok", "hanoi"},
            "South Asia": {"india", "pakistan", "afghanistan", "bangladesh", "sri lanka", "nepal", "mumbai", "delhi", "islamabad", "kabul"},
            "Central Asia": {"kazakhstan", "uzbekistan", "tajikistan", "turkmenistan", "kyrgyzstan"},
            "Middle East": {"iran", "iraq", "syria", "yemen", "saudi arabia", "qatar", "uae", "dubai", "tehran", "baghdad", "riyadh", "istanbul", "turkey", "israel", "tel aviv", "jordan", "lebanon", "kuwait", "bahrain", "oman"},
            "East Africa": {"djibouti", "ethiopia", "kenya", "tanzania", "somalia", "eritrea", "sudan", "south sudan", "uganda", "mozambique", "madagascar", "mombasa", "nairobi", "addis ababa", "dar es salaam"},
            "West Africa": {"nigeria", "ghana", "senegal", "mali", "niger", "cameroon", "dakar", "lagos", "abuja"},
            "North Africa": {"egypt", "libya", "tunisia", "algeria", "morocco", "cairo"},
            "Southern Africa": {"south africa", "zimbabwe", "botswana", "namibia", "angola", "johannesburg", "cape town"},
            "Europe": {"russia", "ukraine", "germany", "france", "united kingdom", "poland", "romania", "netherlands", "belgium", "spain", "italy", "sweden", "norway", "finland", "greece", "moscow", "london", "paris", "berlin", "brussels", "kyiv", "kharkiv"},
            "North America": {"united states", "canada", "mexico", "washington", "washington dc", "new york", "california", "texas"},
            "South America": {"brazil", "argentina", "colombia", "chile", "venezuela", "peru"},
            "Oceania": {"australia", "new zealand", "darwin", "sydney"},
            "Maritime": {"south china sea", "east china sea", "persian gulf", "red sea", "caspian sea", "black sea", "indian ocean", "pacific ocean", "atlantic ocean", "mediterranean", "strait of hormuz", "suez canal"},
        }

        locations = [e for e in entities if e.get("entity_type") == "Location"]
        branch = {
            "name": "Geographic Regions",
            "id": "branch-geo",
            "entity_type": "branch",
            "children": [],
            "count": len(locations),
        }

        assigned = set()
        for region_name, keywords in REGIONS.items():
            region_locs = []
            for loc in locations:
                name_lower = loc.get("name", "").lower().strip()
                # Strip "the " prefix
                clean = name_lower
                if clean.startswith("the "):
                    clean = clean[4:]
                if clean in keywords and loc["id"] not in assigned:
                    region_locs.append({
                        "id": loc.get("id", ""),
                        "name": loc.get("name", ""),
                        "entity_type": "Location",
                    })
                    assigned.add(loc["id"])
            if region_locs:
                branch["children"].append({
                    "name": region_name,
                    "id": f"geo-{region_name.lower().replace(' ', '-')}",
                    "entity_type": "region",
                    "children": sorted(region_locs, key=lambda x: x["name"]),
                    "count": len(region_locs),
                })

        # Unassigned locations
        unassigned = [
            {"id": loc.get("id", ""), "name": loc.get("name", ""), "entity_type": "Location"}
            for loc in locations if loc["id"] not in assigned
        ]
        if unassigned:
            branch["children"].append({
                "name": "Other Locations",
                "id": "geo-other",
                "entity_type": "region",
                "children": sorted(unassigned, key=lambda x: x["name"]),
                "count": len(unassigned),
            })

        return branch

    def _build_actor_branch(self, entities: list, G: nx.Graph) -> dict:
        """People and organizations with their connections, sorted by importance."""
        actors = [e for e in entities if e.get("entity_type") in ("Person", "Organization", "ThreatActor")]
        branch = {
            "name": "Actors & Organizations",
            "id": "branch-actors",
            "entity_type": "branch",
            "children": [],
            "count": len(actors),
        }

        # Sort by degree (most connected first)
        actor_with_degree = []
        for a in actors:
            aid = a.get("id", "")
            degree = G.degree(aid) if aid in G else 0
            actor_with_degree.append((a, degree))
        actor_with_degree.sort(key=lambda x: -x[1])

        # Group: People vs Organizations
        people = []
        orgs = []
        for a, degree in actor_with_degree:
            entry = {
                "id": a.get("id", ""),
                "name": a.get("name", ""),
                "entity_type": a.get("entity_type", ""),
                "connections": degree,
            }
            if a.get("entity_type") == "Person":
                people.append(entry)
            else:
                orgs.append(entry)

        if people:
            branch["children"].append({
                "name": "Key Personnel",
                "id": "actors-people",
                "entity_type": "category",
                "children": people,
                "count": len(people),
            })
        if orgs:
            branch["children"].append({
                "name": "Organizations",
                "id": "actors-orgs",
                "entity_type": "category",
                "children": orgs,
                "count": len(orgs),
            })

        return branch

    def get_topic_context(self, entity_id: str, project_id: str) -> dict:
        """Get full context for an entity including source documents."""
        entity = self._store.get_entity(entity_id)
        if not entity:
            return {"error": "Entity not found"}

        relationships = self._store.get_relationships(entity_id)
        seen_doc_ids: set[str] = set()

        documents = []
        connected = []
        for rel in relationships:
            target_id = rel.get("target_id", "")
            target = self._store.get_entity(target_id)
            if not target:
                continue
            if target.get("entity_type") == "Document":
                if target_id not in seen_doc_ids:
                    seen_doc_ids.add(target_id)
                    documents.append({
                        "id": target.get("id"),
                        "name": target.get("name"),
                        "reliability_rating": target.get("reliability_rating", ""),
                        "content_preview": (target.get("content", "") or "")[:500],
                    })
            else:
                connected.append({
                    "id": target.get("id"),
                    "name": target.get("name"),
                    "entity_type": target.get("entity_type"),
                    "rel_type": rel.get("rel_type"),
                    "confidence": rel.get("confidence", rel.get("props", {}).get("confidence")),
                })

        # If no documents found via relationships, look up by source_doc_id
        if not documents:
            source_doc_id = entity.get("source_doc_id", "") or entity.get("source", "")
            if source_doc_id and source_doc_id not in seen_doc_ids:
                doc = self._store.get_entity(source_doc_id)
                if doc and doc.get("entity_type") == "Document":
                    seen_doc_ids.add(source_doc_id)
                    documents.append({
                        "id": doc.get("id"),
                        "name": doc.get("name"),
                        "reliability_rating": doc.get("reliability_rating", ""),
                        "content_preview": (doc.get("content", "") or "")[:500],
                    })

        # If still no documents, search for project documents that mention this entity
        if not documents:
            entity_name = entity.get("name", "").lower()
            if entity_name:
                project_docs = self._store.search_entities(
                    project_id=project_id, entity_type="Document", limit=50,
                )
                for doc_meta in project_docs:
                    doc_id = doc_meta.get("id", "")
                    if doc_id in seen_doc_ids:
                        continue
                    doc_full = self._store.get_entity(doc_id)
                    if doc_full:
                        content = (doc_full.get("content", "") or "").lower()
                        if entity_name in content:
                            seen_doc_ids.add(doc_id)
                            documents.append({
                                "id": doc_full.get("id"),
                                "name": doc_full.get("name"),
                                "reliability_rating": doc_full.get("reliability_rating", ""),
                                "content_preview": (doc_full.get("content", "") or "")[:500],
                            })

        return {
            "entity": {
                "id": entity.get("id"),
                "name": entity.get("name"),
                "entity_type": entity.get("entity_type"),
            },
            "documents": documents,
            "source_documents": documents,  # Include both keys for frontend compat
            "connected_entities": connected,
            "relationship_count": len(relationships),
            "document_count": len(documents),
        }
