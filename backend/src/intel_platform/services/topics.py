from __future__ import annotations
import hashlib
import time
from collections import defaultdict
import networkx as nx
from intel_platform.graph.store import GraphStore
from intel_platform.services.document_clustering import cluster_documents
from intel_platform.services.text_utils import extract_relevant_passages, count_keyword_matches

# Module-level caches — survive across per-request TopicTreeService instances
_cluster_doc_map: dict[str, dict[str, list[str]]] = {}
_cluster_keywords: dict[str, dict[str, list[str]]] = {}
_summary_cache: dict[tuple[str, str, str], tuple[float, str]] = {}  # (project, node, hash) -> (timestamp, summary)
_SUMMARY_TTL = 300  # 5 minutes


class TopicTreeService:
    def __init__(self, store: GraphStore):
        self._store = store

    async def build_topic_tree(self, project_id: str) -> dict:
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

        # Topics (document content clustering) — only branch in the tree
        full_docs = self._store.search_entities(project_id=project_id, entity_type="Document", limit=500)
        topic_branch = await self._build_topic_branch(full_docs, project_id)
        if topic_branch and topic_branch.get("children"):
            tree["children"].extend(topic_branch.get("children", []))

        # Detect cross-cutting themes: documents appearing in multiple topic clusters
        cross_references = self._detect_cross_references(project_id, full_docs)
        if cross_references:
            tree["cross_references"] = cross_references

        return tree

    def _detect_cross_references(
        self, project_id: str, documents: list,
    ) -> list[dict]:
        """Find documents that appear in multiple topic clusters."""
        project_clusters = _cluster_doc_map.get(project_id, {})
        if not project_clusters:
            return []

        # Build reverse map: doc_id -> list of topic_ids
        doc_to_topics: dict[str, list[str]] = defaultdict(list)
        for topic_id, doc_ids in project_clusters.items():
            for doc_id in doc_ids:
                doc_to_topics[doc_id].append(topic_id)

        # Build name lookup
        doc_name_map = {d.get("id", ""): d.get("name", "") for d in documents}

        cross_refs = []
        for doc_id, topic_ids in doc_to_topics.items():
            if len(topic_ids) > 1:
                cross_refs.append({
                    "doc_id": doc_id,
                    "doc_name": doc_name_map.get(doc_id, doc_id),
                    "topic_ids": topic_ids,
                })

        return cross_refs

    async def _build_topic_branch(self, documents: list, project_id: str) -> dict | None:
        """Cluster documents by content and return a Topics branch node."""
        global _cluster_doc_map, _cluster_keywords

        # Extract (doc_id, content) pairs — skip docs without content
        doc_pairs: list[tuple[str, str]] = []
        id_to_name: dict[str, str] = {}
        for doc in documents:
            doc_id = doc.get("id", "")
            content = doc.get("content", "") or ""
            name = doc.get("name", doc_id)
            if doc_id and content.strip():
                doc_pairs.append((doc_id, content))
                id_to_name[doc_id] = name

        if not doc_pairs:
            return None

        tree_node, doc_map, kw_map = cluster_documents(doc_pairs, project_id)
        if tree_node is None:
            return None

        # Refine topic labels with LLM (falls back gracefully if no provider)
        try:
            from intel_platform.services.document_clustering import refine_labels_with_llm
            await refine_labels_with_llm(tree_node, doc_pairs)
        except Exception:
            pass  # Keep keyword labels on any failure

        # Update module-level caches
        _cluster_doc_map.update(doc_map)
        _cluster_keywords.update(kw_map)

        # Wrap in branch node
        branch = {
            "name": "Topics",
            "id": "branch-themes",
            "entity_type": "branch",
            "children": tree_node.get("children", []) if tree_node.get("children") else [tree_node],
            "count": tree_node.get("count", 0),
        }
        return branch

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

    async def stream_summary(
        self,
        entity_id: str,
        project_id: str,
        level: str = "topic",
        conversation_history: list[dict] | None = None,
    ):
        """Stream an LLM-generated intelligence summary as SSE events."""
        global _summary_cache

        # Get context for this node
        context = self.get_topic_context(entity_id, project_id)
        excerpts = context.get("document_excerpts", [])
        keywords = context.get("keywords", [])
        entity_name = context.get("entity", {}).get("name", "Unknown")

        # Check summary cache
        content_hash = hashlib.md5(
            str(sorted([e.get("name", "") for e in excerpts])).encode()
        ).hexdigest()
        cache_key = (project_id, entity_id, content_hash)
        cached = _summary_cache.get(cache_key)
        if cached and (time.time() - cached[0]) < _SUMMARY_TTL:
            yield f"data: {cached[1]}\n\n"
            yield "data: [DONE]\n\n"
            return

        # Build provider (centralized selection respecting runtime overrides)
        from intel_platform.api.routes.llm import _get_provider
        provider = _get_provider()

        if not provider:
            yield "data: No LLM provider configured.\n\n"
            yield "data: [DONE]\n\n"
            return

        from intel_platform.llm.skills.loader import SkillsLoader
        loader = SkillsLoader()
        system = loader.get_system_prompt("topic_summarization", include_foundation=True) or ""

        # Build messages
        level_instruction = {
            "topic": f"Provide a TOPIC-level intelligence summary about \"{entity_name}\".",
            "document": f"Provide a DOCUMENT-level analysis of \"{entity_name}\".",
            "corpus": "Provide a CORPUS-level overview of all topics in this knowledge base.",
        }.get(level, f"Summarize \"{entity_name}\".")

        excerpt_text = ""
        if excerpts:
            excerpt_text = "\n\n---\n\n".join(
                f"**{e['name']}:**\n{e['content']}" for e in excerpts[:10]
            )

        user_content = f"{level_instruction}\n\nKeywords: {', '.join(keywords)}\n\nSource documents:\n{excerpt_text}"

        messages: list[dict] = []
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_content})

        # Generate and stream
        full_response = ""
        try:
            result = await provider.generate(
                messages=messages,
                system=system,
                temperature=0.3,
                max_tokens=4096,
            )
            full_response = result.content
            # Send in chunks to simulate streaming for non-streaming providers
            chunk_size = 80
            for i in range(0, len(full_response), chunk_size):
                chunk = full_response[i:i + chunk_size]
                yield f"data: {chunk}\n\n"
        except Exception as e:
            yield f"data: Error generating summary: {str(e)}\n\n"

        # Cache the full response
        if full_response:
            _summary_cache[cache_key] = (time.time(), full_response)

        yield "data: [DONE]\n\n"

    def get_topic_context(self, entity_id: str, project_id: str) -> dict:
        """Get full context for an entity including source documents."""
        global _cluster_doc_map, _cluster_keywords

        # Handle topic cluster nodes
        if entity_id.startswith("topic-"):
            project_clusters = _cluster_doc_map.get(project_id, {})
            doc_ids = project_clusters.get(entity_id, [])

            # If cache expired, rebuild tree to repopulate
            if not doc_ids:
                self.build_topic_tree(project_id)
                project_clusters = _cluster_doc_map.get(project_id, {})
                doc_ids = project_clusters.get(entity_id, [])

            keywords = _cluster_keywords.get(project_id, {}).get(entity_id, [])

            documents = []
            document_excerpts: list[dict[str, str]] = []
            connected_entities = []
            seen_entity_ids: set[str] = set()

            for doc_id in doc_ids:
                doc = self._store.get_entity(doc_id)
                if doc and doc.get("entity_type") == "Document":
                    full_content = doc.get("content", "") or ""

                    # Extract relevant excerpts using topic keywords
                    relevant = extract_relevant_passages(
                        full_content, keywords, max_chars=1500, max_passages=3,
                    ) if keywords else []
                    kw_matches = count_keyword_matches(full_content, keywords) if keywords else {}

                    documents.append({
                        "id": doc.get("id"),
                        "name": doc.get("name"),
                        "reliability_rating": doc.get("reliability_rating", ""),
                        "content_preview": full_content[:500],
                        "relevant_excerpts": relevant,
                        "keyword_matches": kw_matches,
                        "relevance_score": sum(kw_matches.values()),
                    })
                    # Include longer excerpt for LLM summary generation
                    if full_content:
                        document_excerpts.append({
                            "name": doc.get("name", ""),
                            "content": full_content[:3000],
                        })
                    # Find entities extracted from this document
                    rels = self._store.get_relationships(doc_id)
                    for rel in rels:
                        target = self._store.get_entity(rel.get("target_id", ""))
                        if target and target.get("entity_type") != "Document":
                            eid = target.get("id", "")
                            if eid not in seen_entity_ids:
                                seen_entity_ids.add(eid)
                                connected_entities.append({
                                    "id": eid,
                                    "name": target.get("name"),
                                    "entity_type": target.get("entity_type"),
                                    "rel_type": rel.get("rel_type", "ASSOCIATED_WITH"),
                                    "confidence": rel.get("confidence"),
                                })

            # Sort documents by relevance score (most keyword matches first)
            documents.sort(key=lambda d: d.get("relevance_score", 0), reverse=True)

            return {
                "entity": {"id": entity_id, "name": ", ".join(keywords) or "Topic Cluster", "entity_type": "topic"},
                "documents": documents,
                "source_documents": documents,
                "document_excerpts": document_excerpts,
                "connected_entities": connected_entities,
                "keywords": keywords,
                "document_count": len(documents),
            }

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
