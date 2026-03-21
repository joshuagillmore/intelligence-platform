from __future__ import annotations

from intel_platform.graph.store import GraphStore


class GraphRAGPipeline:
    """4-stage Graph RAG: understand -> retrieve -> assemble -> generate."""

    def __init__(self, store: GraphStore):
        self._store = store

    def understand_query(self, query: str, project_id: str) -> dict:
        """Extract target entities and intent from natural language query.
        Searches with the full query, multi-word phrases, and individual keywords."""
        candidates = []

        # 1. Search with the full query
        results = self._store.search_entities(project_id=project_id, query=query.strip(), limit=10)
        candidates.extend(results)

        # 2. Search with significant phrases (2-3 word combos)
        words = query.split()
        for n in (3, 2):
            for i in range(len(words) - n + 1):
                phrase = " ".join(words[i:i + n])
                if len(phrase) >= 4:
                    results = self._store.search_entities(project_id=project_id, query=phrase, limit=5)
                    candidates.extend(results)

        # 3. Search individual words (skip common/short words)
        stop_words = {"the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
                      "her", "was", "one", "our", "out", "what", "with", "about", "this",
                      "that", "from", "have", "how", "who", "which", "their", "been", "know",
                      "tell", "show", "find", "does"}
        for word in words:
            clean = word.strip("?.,!;:'\"").lower()
            if len(clean) >= 3 and clean not in stop_words:
                results = self._store.search_entities(project_id=project_id, query=clean, limit=5)
                candidates.extend(results)

        # 4. If still nothing found, get all entities as fallback context
        if not candidates:
            candidates = self._store.search_entities(project_id=project_id, limit=20)

        # Deduplicate by id
        seen = set()
        entities = []
        for c in candidates:
            eid = c.get("id", "")
            if eid and eid not in seen:
                seen.add(eid)
                entities.append(c)

        return {
            "query": query,
            "target_entities": entities[:15],
            "intent": "general_query",
        }

    def retrieve_context(self, understanding: dict, project_id: str, max_hops: int = 2) -> dict:
        """Retrieve relevant subgraph based on query understanding."""
        all_nodes = []
        all_edges = []
        seen_node_ids = set()

        for entity in understanding.get("target_entities", []):
            # Always include the target entity itself
            entity_id = entity.get("id", "")
            if entity_id and entity_id not in seen_node_ids:
                full_entity = self._store.get_entity(entity_id)
                if full_entity:
                    seen_node_ids.add(entity_id)
                    all_nodes.append(full_entity)

            subgraph = self._store.get_subgraph(entity_id, hops=max_hops)
            for node in subgraph.get("nodes", []):
                node_id = node.get("id", "")
                if node_id and node_id not in seen_node_ids:
                    seen_node_ids.add(node_id)
                    all_nodes.append(node)
            all_edges.extend(subgraph.get("edges", []))

        return {
            "nodes": all_nodes,
            "edges": all_edges,
            "node_count": len(all_nodes),
            "edge_count": len(all_edges),
        }

    def assemble_context(self, retrieved: dict, token_budget: int = 8000) -> str:
        """Serialize retrieved subgraph into structured natural language for LLM context."""
        lines = ["## Retrieved Intelligence Context\n"]

        # Group nodes by type
        by_type: dict[str, list] = {}
        for node in retrieved.get("nodes", []):
            entity_type = node.get("entity_type", "Unknown")
            by_type.setdefault(entity_type, []).append(node)

        for entity_type, nodes in by_type.items():
            lines.append(f"\n### {entity_type}s")
            for node in nodes[:20]:  # Limit per type
                name = node.get("name", "Unknown")
                props = {
                    k: v
                    for k, v in node.items()
                    if k not in ("id", "name", "entity_type", "project_id", "created_at")
                }
                props_str = ", ".join(f"{k}={v}" for k, v in props.items() if v) if props else ""
                lines.append(f"- **{name}**" + (f" ({props_str})" if props_str else ""))

        # Add relationships
        edges = retrieved.get("edges", [])
        if edges:
            lines.append(f"\n### Relationships ({len(edges)} total)")
            for edge in edges[:50]:  # Limit edges
                rel_type = edge.get("rel_type", "RELATED_TO")
                confidence = edge.get("confidence", edge.get("props", {}).get("confidence", "?"))
                source = edge.get("source_id", "?")[:8]
                target = edge.get("target_id", "?")[:8]
                lines.append(f"- {source}... --[{rel_type} conf={confidence}]--> {target}...")

        context = "\n".join(lines)
        # Rough token estimation (4 chars per token)
        if len(context) > token_budget * 4:
            context = context[: token_budget * 4] + "\n\n[Context truncated due to token budget]"
        return context

    def query(self, query: str, project_id: str, max_hops: int = 2, token_budget: int = 8000) -> dict:
        """Full RAG pipeline: understand -> retrieve -> assemble."""
        understanding = self.understand_query(query, project_id)
        retrieved = self.retrieve_context(understanding, project_id, max_hops=max_hops)
        context = self.assemble_context(retrieved, token_budget=token_budget)
        return {
            "query": query,
            "understanding": understanding,
            "context": context,
            "context_nodes": retrieved["node_count"],
            "context_edges": retrieved["edge_count"],
        }
