from __future__ import annotations
import asyncio
import copy
import hashlib
import json
import logging
import time
from collections import defaultdict
import networkx as nx
from intel_platform.graph.store import GraphStore
from intel_platform.services.telemetry import record_degraded
from intel_platform.models.entities import SYSTEM_ENTITY_TYPES
from intel_platform.services.document_clustering import cluster_documents
from intel_platform.services.text_utils import extract_relevant_passages, count_keyword_matches

logger = logging.getLogger(__name__)

# Module-level caches — survive across per-request TopicTreeService instances
_cluster_doc_map: dict[str, dict[str, list[str]]] = {}
_cluster_keywords: dict[str, dict[str, list[str]]] = {}
# (project, node, content hash, level, history hash) -> (timestamp, summary)
_summary_cache: dict[tuple[str, ...], tuple[float, str]] = {}
_SUMMARY_TTL = 300  # 5 minutes
_SUMMARY_CACHE_MAX = 200  # PERF: cap to prevent unbounded growth

# Summary SSE framing (contract 7). Every `data:` payload is a JSON value: text
# is a JSON *string*, so the model's newlines travel escaped inside it instead
# of terminating the event. Sent raw, a client splitting on lines kept only the
# lines starting `data: ` and a six-line summary arrived as "## Key Findingsps".
_SSE_SLICE_CHARS = 80
_SSE_DONE = "data: [DONE]\n\n"
_SSE_ERROR = "data: " + json.dumps({"error": "Summary generation failed"}) + "\n\n"


def _sse_text_frames(text: str):
    """`text` as `data: "<json string>"` events, in slices of `_SSE_SLICE_CHARS`."""
    for i in range(0, len(text), _SSE_SLICE_CHARS):
        yield "data: " + json.dumps(text[i:i + _SSE_SLICE_CHARS]) + "\n\n"


def apply_topic_edits(tree: dict, edits: list) -> dict:
    """The algorithmic tree with an analyst's `TopicEdit` rows applied.

    The rename, add and delete endpoints wrote rows nothing read, so every edit
    vanished on the next load. Applied here, after the tree is built, as an
    overlay: the algorithmic tree stays cacheable and the overlay is re-read on
    every request, so an edit shows immediately without invalidating the cache
    (and in every worker, not just the one that took the edit).

    `edits` are applied in order (callers pass them oldest first): ``add``
    places a user node under `parent_id` (at the root if that node no longer
    exists, rather than losing it); ``rename``/``move`` set a non-empty name or
    description and re-parent when `parent_id` is set; ``delete`` removes the
    node and its subtree. Algorithmic ids are not stable across rebuilds, so an
    edit whose node is gone is counted in ``edits_unmatched`` rather than
    silently dropped.

    Returns a new tree; the input is not mutated, since it is the cached one.
    """
    out = copy.deepcopy(tree) if edits else dict(tree)
    applied = unmatched = 0

    def locate(node: dict, node_id: str, parent: dict | None = None):
        if node.get("id") == node_id:
            return node, parent
        for child in node.get("children") or []:
            found = locate(child, node_id, node)
            if found:
                return found
        return None

    for edit in edits:
        kind = (getattr(edit, "edit_type", "") or "").lower()
        node_id = getattr(edit, "node_id", "") or ""
        parent_id = getattr(edit, "parent_id", "") or ""

        if kind == "add":
            if locate(out, node_id):
                unmatched += 1   # already present; a second add would duplicate it
                continue
            host = locate(out, parent_id) if parent_id else None
            target = host[0] if host else out
            target.setdefault("children", []).append({
                "id": node_id,
                "name": getattr(edit, "name", "") or "Untitled topic",
                "description": getattr(edit, "description", "") or "",
                "entity_type": "user_topic",
                "user_created": True,
                "children": [],
                "count": 0,
            })
            applied += 1
            continue

        found = locate(out, node_id)
        if not found:
            unmatched += 1
            continue
        node, parent = found

        if kind == "delete":
            if parent is None:
                unmatched += 1   # the root is not deletable
                continue
            parent["children"] = [c for c in parent.get("children", []) if c is not node]
            applied += 1
            continue

        if kind in ("rename", "move"):
            if parent_id and parent_id != (parent or {}).get("id"):
                new_parent = locate(out, parent_id)
                # Never under itself or its own descendant — that would detach
                # the subtree from the tree entirely.
                if not new_parent or parent is None or locate(node, parent_id):
                    unmatched += 1
                    continue
                parent["children"] = [c for c in parent.get("children", []) if c is not node]
                new_parent[0].setdefault("children", []).append(node)
            if getattr(edit, "name", ""):
                node["name"] = edit.name
            if getattr(edit, "description", ""):
                node["description"] = edit.description
            node["edited"] = True
            applied += 1
            continue

        unmatched += 1   # an edit type this overlay does not know

    out["edits_applied"] = applied
    out["edits_unmatched"] = unmatched
    return out


class TopicTreeService:
    def __init__(self, store: GraphStore):
        self._store = store

    async def build_topic_tree(self, project_id: str, method: str = "tfidf", granularity: str = "medium") -> dict:
        """Build a deep hierarchical topic tree using graph community structure.

        The store reads (synchronous driver, up to 10,000 entities and the full
        graph), tf-idf clustering and community detection all run in worker
        threads. On the event loop a cold build stalled every other request,
        the health check included, for its whole duration (~20 s measured).
        """
        entities, graph_data, full_docs = await asyncio.to_thread(self._load_tree_inputs, project_id)

        documents = [e for e in entities if e.get("entity_type") == "Document"]
        non_docs = [e for e in entities if e.get("entity_type") not in SYSTEM_ENTITY_TYPES]

        tree = {
            "name": "Knowledge Base",
            "id": "root",
            "entity_count": len(non_docs),
            "document_count": len(documents),
            "children": [],
        }

        # Topics (document content clustering)
        topic_branch = await self._build_topic_branch(full_docs, project_id, method=method, granularity=granularity)
        if topic_branch and topic_branch.get("children"):
            tree["children"].extend(topic_branch.get("children", []))
            # Surfaced at the root because that is what a caller reads. Topic
            # names drive what an analyst clicks into; whether they came from a
            # model or from raw keyword extraction is part of the answer.
            for field in ("label_source", "labels_refined", "labels_failed"):
                tree[field] = topic_branch.get(field)

        # Entity-based branches — only shown when enough content entities exist
        if non_docs:
            tree["children"].extend(
                await asyncio.to_thread(self._build_entity_branches, non_docs, graph_data)
            )

        # Detect cross-cutting themes: documents appearing in multiple topic clusters
        cross_references = self._detect_cross_references(project_id, full_docs)
        if cross_references:
            tree["cross_references"] = cross_references

        return tree

    def _load_tree_inputs(self, project_id: str) -> tuple[list[dict], dict, list[dict]]:
        """Every store read the tree needs, in one worker-thread call."""
        entities = self._store.search_entities(project_id=project_id, limit=10000)
        graph_data = self._store.get_full_graph(project_id=project_id, limit=10000)
        full_docs = self._store.search_entities(project_id=project_id, entity_type="Document", limit=500)
        return entities, graph_data, full_docs

    def _build_entity_branches(self, non_docs: list[dict], graph_data: dict) -> list[dict]:
        """Theme, type, geography and actor branches. CPU work: run off the loop."""
        # A project scan can hand back bookkeeping nodes (a Watchlist entry
        # carries project_id but no entity id); they are not entities and
        # must not take the whole tree down with a KeyError.
        non_docs = [e for e in non_docs if e.get("id")]
        entity_map = {e["id"]: e for e in non_docs}

        # Build NetworkX graph for community detection
        G = nx.Graph()
        for e in non_docs:
            G.add_node(e["id"], **{k: v for k, v in e.items() if k != "id" and not isinstance(v, (dict, list))})
        for edge in graph_data.get("edges", []):
            sid, tid = edge.get("source_id", ""), edge.get("target_id", "")
            if sid in entity_map and tid in entity_map:
                G.add_edge(sid, tid)

        MIN_ENTITY_BRANCH_SIZE = 3
        candidates = [
            # Thematic clusters via community detection on the entity graph
            self._build_theme_branch(G, entity_map, non_docs),
            # Entities grouped by type (Person, Organization, Location, etc.)
            self._build_type_branch(non_docs),
            # Geographic regions
            self._build_geo_branch(non_docs),
            # Key actors and organizations
            self._build_actor_branch(non_docs, G),
        ]
        return [
            b for b in candidates
            if b.get("children") and b.get("count", 0) >= MIN_ENTITY_BRANCH_SIZE
        ]

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

    async def _build_topic_branch(self, documents: list, project_id: str, method: str = "tfidf", granularity: str = "medium") -> dict | None:
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

        if method == "semantic":
            from intel_platform.services.document_clustering import cluster_semantic
            tree_node, doc_map, kw_map = await cluster_semantic(doc_pairs, project_id, granularity=granularity)
        else:
            # tf-idf clustering is CPU work; keep it off the event loop.
            tree_node, doc_map, kw_map = await asyncio.to_thread(cluster_documents, doc_pairs, project_id)
        if tree_node is None:
            return None

        # Refine topic labels with an LLM. This is the bulk of the build —
        # measured at 19.3s of a 20.6s cold response — so a failure here is
        # both the most likely and the least visible: the tree comes back
        # looking the same, with keyword labels the analyst cannot distinguish
        # from model-generated ones.
        try:
            from intel_platform.services.document_clustering import refine_labels_with_llm
            await refine_labels_with_llm(tree_node, doc_pairs)
        except Exception as exc:
            logger.warning("Topic label refinement failed; keeping keyword labels", exc_info=True)
            tree_node["label_source"] = "keywords"
            record_degraded("topics", "label_refinement_failed", detail=type(exc).__name__)
        # One per topic left with its keyword label after a refinement attempt.
        for _ in range(int(tree_node.get("labels_failed") or 0)):
            record_degraded("topics", "label_failed")

        # Update module-level caches
        _cluster_doc_map.update(doc_map)
        _cluster_keywords.update(kw_map)

        # Wrap in branch node, carrying the label provenance up with it —
        # refinement records it on the refined node, and this wrapper is what
        # the caller sees.
        branch = {
            "name": "Topics",
            "id": "branch-themes",
            "entity_type": "branch",
            "children": tree_node.get("children", []) if tree_node.get("children") else [tree_node],
            "count": tree_node.get("count", 0),
            "label_source": tree_node.get("label_source", "keywords"),
            "labels_refined": tree_node.get("labels_refined", 0),
            "labels_failed": tree_node.get("labels_failed", 0),
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
            # Document -> entity provenance is the MENTIONS edge, which the
            # relationship reads deliberately hide (it is not an analytic link).
            related = [
                {"id": e.get("id", ""), "name": e.get("name", ""), "entity_type": e.get("entity_type", "")}
                for e in self._store.entities_mentioned_in(doc_id, doc.get("project_id", ""))
            ]
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

        # Get context for this node. get_topic_context hits the synchronous Neo4j
        # driver (and may rebuild clusters), so offload it off the event loop.
        context = await asyncio.to_thread(self.get_topic_context, entity_id, project_id)
        excerpts = context.get("document_excerpts", [])
        keywords = context.get("keywords", [])
        entity_name = context.get("entity", {}).get("name", "Unknown")

        # Check summary cache. The level and the conversation so far change the
        # answer, so they are part of the key: a "corpus" request used to be
        # served the "topic" summary, and a follow-up question the first reply.
        content_hash = hashlib.md5(
            str(sorted([e.get("name", "") for e in excerpts])).encode()
        ).hexdigest()
        history_hash = hashlib.md5(
            json.dumps(conversation_history or [], sort_keys=True, default=str).encode()
        ).hexdigest()
        cache_key = (project_id, entity_id, content_hash, level, history_hash)
        cached = _summary_cache.get(cache_key)
        if cached and (time.time() - cached[0]) < _SUMMARY_TTL:
            for frame in _sse_text_frames(cached[1]):
                yield frame
            yield _SSE_DONE
            return

        # Build provider (centralized selection respecting runtime overrides)
        from intel_platform.llm.providers import _get_provider
        provider = await _get_provider()

        if not provider:
            logger.warning("Topic summary requested with no LLM provider available")
            record_degraded("topics", "summary_no_provider")
            yield _SSE_ERROR
            yield _SSE_DONE
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

        # Generate, then stream in slices for non-streaming providers.
        try:
            result = await provider.generate(
                messages=messages,
                system=system,
                temperature=0.3,
                max_tokens=4096,
            )
            full_response = result.content or ""
        except Exception:
            # Logged here; the client gets a fixed message. The exception text
            # (hosts, credentials in URLs, provider error bodies) was streamed
            # to the analyst and cached as though it were the summary.
            logger.exception("Topic summary generation failed for %s", entity_id)
            record_degraded("topics", "summary_failed")
            full_response = None

        if full_response is None:
            yield _SSE_ERROR
            yield _SSE_DONE
            return
        if not full_response.strip():
            record_degraded("topics", "summary_empty")
            yield _SSE_ERROR
            yield _SSE_DONE
            return

        for frame in _sse_text_frames(full_response):
            yield frame

        # Cache only a real summary (evict oldest if cache is full)
        if len(_summary_cache) >= _SUMMARY_CACHE_MAX:
            oldest_key = min(_summary_cache, key=lambda k: _summary_cache[k][0])
            del _summary_cache[oldest_key]
        _summary_cache[cache_key] = (time.time(), full_response)

        yield _SSE_DONE

    def _rebuild_topic_clusters_sync(self, project_id: str) -> None:
        """Synchronously repopulate the module-level cluster caches.

        `get_topic_context` is a synchronous method (the `/topics/{entity_id}`
        route calls it without awaiting, and several tests call it directly),
        so on a cache miss it cannot await the full `build_topic_tree`, which
        is async because it supports semantic (embedding-based) clustering and
        LLM-based label refinement. Those aren't needed just to answer "which
        documents belong to this cluster", so this helper redoes only the
        synchronous tfidf clustering step that populates `_cluster_doc_map`
        and `_cluster_keywords`.
        """
        global _cluster_doc_map, _cluster_keywords

        full_docs = self._store.search_entities(project_id=project_id, entity_type="Document", limit=500)
        doc_pairs: list[tuple[str, str]] = []
        for doc in full_docs:
            doc_id = doc.get("id", "")
            content = doc.get("content", "") or ""
            if doc_id and content.strip():
                doc_pairs.append((doc_id, content))

        if not doc_pairs:
            return

        tree_node, doc_map, kw_map = cluster_documents(doc_pairs, project_id)
        if tree_node is None:
            return

        _cluster_doc_map.update(doc_map)
        _cluster_keywords.update(kw_map)

    def get_topic_context(self, entity_id: str, project_id: str) -> dict:
        """Get full context for an entity including source documents."""
        global _cluster_doc_map, _cluster_keywords

        # Handle topic cluster nodes
        if entity_id.startswith("topic-"):
            project_clusters = _cluster_doc_map.get(project_id, {})
            doc_ids = project_clusters.get(entity_id, [])

            # If cache expired, rebuild the clustering caches to repopulate
            if not doc_ids:
                self._rebuild_topic_clusters_sync(project_id)
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
                            "name": doc.get("name") or "",
                            "content": full_content[:3000],
                        })
                    # Entities extracted from this document: the MENTIONS edge
                    # is the provenance record (hidden from relationship reads).
                    for mentioned in self._store.entities_mentioned_in(doc_id, project_id):
                        eid = mentioned.get("id", "")
                        if eid and eid not in seen_entity_ids:
                            seen_entity_ids.add(eid)
                            connected_entities.append({
                                "id": eid,
                                "name": mentioned.get("name"),
                                "entity_type": mentioned.get("entity_type"),
                                "rel_type": "MENTIONED_IN",
                                "confidence": None,
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
        # The documents that mention this entity come from the MENTIONS edges,
        # which relationship reads hide; the analytic links below do not
        # include them.
        mentioning, _total = self._store.documents_mentioning(
            entity_id, entity.get("project_id", ""), limit=20,
        )
        for doc_row in mentioning:
            doc_id = doc_row.get("id", "")
            if not doc_id or doc_id in seen_doc_ids:
                continue
            seen_doc_ids.add(doc_id)
            full = self._store.get_entity(doc_id) or {}
            documents.append({
                "id": doc_id,
                "name": doc_row.get("name") or full.get("name"),
                "reliability_rating": full.get("reliability_rating", ""),
                "content_preview": (full.get("content", "") or "")[:500],
            })
        for rel in relationships:
            target_id = rel.get("neighbor_id") or rel.get("target_id", "")
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

        # Build LLM-ready excerpts + keywords from the resolved documents. The
        # entity path previously returned neither, so stream_summary fed the
        # model an empty "Source documents:" block and it refused with "no
        # source documents were provided" (the cluster path already does this).
        document_excerpts: list[dict[str, str]] = []
        for d in documents:
            doc_full = self._store.get_entity(d.get("id", ""))
            content = (doc_full.get("content", "") if doc_full else "") or ""
            if content:
                document_excerpts.append({
                    "name": d.get("name") or "",
                    "content": content[:3000],
                })
        # Focus the summary on this entity and the entities it connects to.
        keywords = [entity.get("name", "")] + [c.get("name", "") for c in connected[:8]]
        keywords = [k for k in keywords if k]

        return {
            "entity": {
                "id": entity.get("id"),
                "name": entity.get("name"),
                "entity_type": entity.get("entity_type"),
            },
            "documents": documents,
            "source_documents": documents,  # Include both keys for frontend compat
            "document_excerpts": document_excerpts,
            "connected_entities": connected,
            "keywords": keywords,
            "relationship_count": len(relationships),
            "document_count": len(documents),
        }
