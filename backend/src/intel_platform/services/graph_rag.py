from __future__ import annotations

from intel_platform.graph.store import GraphStore


class GraphRAGPipeline:
    """4-stage Graph RAG: understand → retrieve → assemble → generate."""

    def __init__(self, store: GraphStore):
        self._store = store

    def understand_query(self, query: str, project_id: str) -> dict:
        """Extract target entities and intent from natural language query."""
        candidates = []

        results = self._store.search_entities(project_id=project_id, query=query.strip(), limit=10)
        candidates.extend(results)

        words = query.split()
        for n in (3, 2):
            for i in range(len(words) - n + 1):
                phrase = " ".join(words[i:i + n])
                if len(phrase) >= 4:
                    results = self._store.search_entities(project_id=project_id, query=phrase, limit=5)
                    candidates.extend(results)

        stop_words = {"the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
                      "her", "was", "one", "our", "out", "what", "with", "about", "this",
                      "that", "from", "have", "how", "who", "which", "their", "been", "know",
                      "tell", "show", "find", "does"}
        for word in words:
            clean = word.strip("?.,!;:'\"").lower()
            if len(clean) >= 3 and clean not in stop_words:
                results = self._store.search_entities(project_id=project_id, query=clean, limit=5)
                candidates.extend(results)

        if not candidates:
            candidates = self._store.search_entities(project_id=project_id, limit=20)

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
        """Retrieve relevant subgraph with entity names resolved for relationships."""
        all_nodes = []
        all_edges = []
        seen_node_ids = set()
        node_name_map: dict[str, str] = {}  # id -> name

        for entity in understanding.get("target_entities", []):
            entity_id = entity.get("id", "")
            if entity_id and entity_id not in seen_node_ids:
                full_entity = self._store.get_entity(entity_id)
                if full_entity:
                    seen_node_ids.add(entity_id)
                    all_nodes.append(full_entity)
                    node_name_map[entity_id] = full_entity.get("name", entity_id)

            subgraph = self._store.get_subgraph(entity_id, hops=max_hops)
            for node in subgraph.get("nodes", []):
                node_id = node.get("id", "")
                if node_id and node_id not in seen_node_ids:
                    seen_node_ids.add(node_id)
                    all_nodes.append(node)
                    node_name_map[node_id] = node.get("name", node_id)
            all_edges.extend(subgraph.get("edges", []))

        # Resolve edge names
        for edge in all_edges:
            edge["source_name"] = node_name_map.get(edge.get("source_id", ""), edge.get("source_id", "?"))
            edge["target_name"] = node_name_map.get(edge.get("target_id", ""), edge.get("target_id", "?"))

        # Retrieve source document text for evidence
        doc_texts: dict[str, str] = {}
        for node in all_nodes:
            if node.get("entity_type") == "Document":
                content = node.get("content", "")
                if content:
                    doc_texts[node.get("name", "")] = content[:2000]  # Cap per doc

        return {
            "nodes": all_nodes,
            "edges": all_edges,
            "node_count": len(all_nodes),
            "edge_count": len(all_edges),
            "node_name_map": node_name_map,
            "doc_texts": doc_texts,
        }

    def assemble_context(self, retrieved: dict, token_budget: int = 8000) -> str:
        """Serialize retrieved subgraph into structured natural language for LLM reasoning."""
        lines = ["## Intelligence Context from Knowledge Graph\n"]

        # Entities grouped by type (exclude Documents from entity list)
        by_type: dict[str, list] = {}
        for node in retrieved.get("nodes", []):
            entity_type = node.get("entity_type", "Unknown")
            if entity_type == "Document":
                continue
            by_type.setdefault(entity_type, []).append(node)

        for entity_type, nodes in sorted(by_type.items()):
            lines.append(f"\n### {entity_type}s ({len(nodes)})")
            for node in nodes[:25]:
                name = node.get("name", "Unknown")
                # Include key properties
                props_parts = []
                for k in ("entity_category", "reliability_rating", "asn", "geolocation",
                          "cve_id", "technique_id", "tactic", "malware_type",
                          "attributed_nation", "motivation"):
                    v = node.get(k)
                    if v:
                        props_parts.append(f"{k}: {v}")
                props_str = f" ({', '.join(props_parts)})" if props_parts else ""
                lines.append(f"- {name}{props_str}")

        # Relationships with full entity names
        edges = retrieved.get("edges", [])
        if edges:
            # Deduplicate edges
            seen_edges = set()
            unique_edges = []
            for edge in edges:
                key = (edge.get("source_name", ""), edge.get("target_name", ""), edge.get("rel_type", ""))
                if key not in seen_edges:
                    seen_edges.add(key)
                    unique_edges.append(edge)

            lines.append(f"\n### Relationships ({len(unique_edges)} unique)")
            for edge in unique_edges[:60]:
                src = edge.get("source_name", "?")
                tgt = edge.get("target_name", "?")
                rel = edge.get("rel_type", "RELATED_TO")
                conf = edge.get("confidence", edge.get("props", {}).get("confidence", ""))
                conf_str = f" (confidence: {conf})" if conf else ""
                lines.append(f"- {src} --[{rel}]--> {tgt}{conf_str}")

        # Source document excerpts for evidence
        doc_texts = retrieved.get("doc_texts", {})
        if doc_texts:
            lines.append(f"\n### Source Document Evidence ({len(doc_texts)} documents)")
            for doc_name, text in list(doc_texts.items())[:5]:
                lines.append(f"\n**{doc_name}:**")
                # Include relevant excerpt (first 1000 chars)
                excerpt = text[:1000].strip()
                if len(text) > 1000:
                    excerpt += "..."
                lines.append(f"```\n{excerpt}\n```")

        context = "\n".join(lines)
        if len(context) > token_budget * 4:
            context = context[:token_budget * 4] + "\n\n[Context truncated due to token budget]"
        return context

    async def query(self, query: str, project_id: str, max_hops: int = 2, token_budget: int = 8000) -> dict:
        """Full RAG pipeline: understand → retrieve → assemble → generate with LLM."""
        understanding = self.understand_query(query, project_id)
        retrieved = self.retrieve_context(understanding, project_id, max_hops=max_hops)
        context = self.assemble_context(retrieved, token_budget=token_budget)

        # Stage 4: LLM Generation — reason over the graph context
        answer = ""
        model = "none"
        tokens_used = 0

        try:
            from intel_platform.config import settings
            provider = None
            if settings.cohere_api_key:
                from intel_platform.llm.cohere_provider import CohereProvider
                provider = CohereProvider(api_key=settings.cohere_api_key)
            elif settings.anthropic_api_key:
                from intel_platform.llm.anthropic import AnthropicProvider
                provider = AnthropicProvider(api_key=settings.anthropic_api_key)
            elif settings.openai_api_key:
                from intel_platform.llm.openai_provider import OpenAIProvider
                provider = OpenAIProvider(api_key=settings.openai_api_key)

            if provider:
                from intel_platform.llm.skills.loader import SkillsLoader
                loader = SkillsLoader()
                system = loader.get_system_prompt("foundation", include_foundation=False) or ""
                system += "\n\nYou are answering intelligence analyst queries using knowledge graph data. "
                system += "Base your answer ONLY on the provided context. Cite entities and relationships. "
                system += "If the context doesn't contain enough information, say so explicitly."

                prompt = f"""Answer this intelligence question using the knowledge graph context below.

**Question:** {query}

{context}

Provide a structured answer with:
1. Direct answer to the question
2. Supporting evidence from the graph (cite specific entities and relationships)
3. Confidence assessment
4. Information gaps (what's missing that would improve the answer)"""

                result = await provider.generate(
                    messages=[{"role": "user", "content": prompt}],
                    system=system,
                    temperature=0.3,
                    max_tokens=4096,
                )
                answer = result.content
                model = result.model
                tokens_used = result.total_tokens
        except Exception as e:
            answer = f"LLM generation failed: {str(e)}\n\nRaw context:\n{context[:2000]}"

        # Fallback if no LLM available
        if not answer:
            answer = context

        return {
            "query": query,
            "answer": answer,
            "model": model,
            "tokens_used": tokens_used,
            "context": context,
            "context_nodes": retrieved["node_count"],
            "context_edges": retrieved["edge_count"],
        }
