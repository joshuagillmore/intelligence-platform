"""Graph-grounded analytic agents: source evaluation, ACH, and gap analysis.

Wraps the three tradecraft skills that shipped without a workflow
(``source_evaluation``, ``hypothesis_generation``, ``gap_analysis``) as
first-class services that retrieve *real project evidence* before prompting:

* **Source evaluation** — Admiralty grading of the project's ``Document`` nodes,
  driven by measurable provenance signals (entity yield, corroboration across
  other documents, content volume, whether the source has a URL).
* **Competing hypotheses (ACH)** — the Graph-RAG subgraph + document evidence
  for the entities in scope, optionally widened with semantically similar
  passages from pgvector.
* **Gap analysis** — deterministic structural coverage gaps computed straight
  from Neo4j (isolated entities, unsourced entities, unrated documents,
  ungeocoded locations, absent entity/relationship types), then narrated.

Every technique computes its deterministic result first, so the endpoints stay
useful — and honest — when no LLM provider is configured, mirroring how
``/collection-plans/from-pir`` degrades.
"""
from __future__ import annotations

import asyncio
import logging
import re

from intel_platform.graph.store import GraphStore
from intel_platform.models.entities import SYSTEM_ENTITY_TYPES, probability_to_label
from intel_platform.services.graph_rag import GraphRAGPipeline

logger = logging.getLogger(__name__)

# Entity types excluded from "analytic substance" counts — they are containers
# and products, not intelligence subjects.
_SYSTEM_TYPES = sorted(SYSTEM_ENTITY_TYPES)

# Core subject types an intelligence picture is normally expected to carry. An
# empty bucket here is a real collection gap, not a modelling quirk.
_CORE_TYPES = ("Person", "Organization", "Location", "Event")

_MAX_DOCS = 25
_DOC_EXCERPT_CHARS = 1500

# The model is asked to close its answer with machine-readable blocks so the
# structured fields below are parsed from real output rather than guessed. Both
# patterns tolerate the list/table decoration models habitually add.
_HYPOTHESIS_RE = re.compile(
    r"^[\s\-*|]*H(\d+)\s*\|\s*(.+?)\s*\|\s*([01](?:\.\d+)?)\s*\|?\s*$", re.MULTILINE
)


def _find_rating(content: str, document_id: str) -> str:
    """Pull the Admiralty rating the model assigned to a specific document id."""
    match = re.search(
        re.escape(document_id) + r"[`'\"\s]*[:|\-–]\s*[*`]*\s*([A-Fa-f])\s*-?\s*([1-6])\b",
        content,
    )
    return f"{match.group(1).upper()}{match.group(2)}" if match else ""



def _degraded_because(reason: str) -> str:
    """One sentence naming why there is no model narrative.

    "No provider configured" and "the provider refused or failed" need
    different responses from whoever reads it, and only one of them is about
    configuration.
    """
    if reason == "generation_failed":
        return (
            "The configured LLM provider did not return a narrative (it failed or "
            "refused the request — a rate limit will do this)."
        )
    return "No LLM provider is configured."


class AnalyticAgentService:
    """Evidence-grounded runners for the three structured analytic techniques."""

    def __init__(self, store: GraphStore):
        self._store = store

    # ── shared LLM seam ────────────────────────────────────────────────────
    @staticmethod
    async def _generate(
        skill_name: str, prompt: str, temperature: float = 0.3, max_tokens: int = 4096,
    ) -> dict:
        """Run a skill prompt through the orchestrator's provider selection.

        Returns ``{"content", "model", "tokens_used", "degraded", "reason"}``.
        ``degraded`` is True when no provider is configured or generation
        failed — callers fall back to their deterministic output instead of
        surfacing an error string as if it were analysis.

        ``reason`` distinguishes the two, because they call for different
        actions and the fallback text used to assert the wrong one: with a
        Cohere key rate-limited at 20 calls/minute, every technique told the
        analyst "No LLM provider is configured" while the provider was
        configured and reachable. That sends someone to check settings that
        are correct.
        """
        # Imported at call time so tests can patch the single provider seam,
        # matching assess.py / reports.py.
        from intel_platform.api.routes.llm import _get_provider

        provider = await _get_provider()
        if not provider:
            return {"content": "", "model": "none", "tokens_used": 0,
                    "degraded": True, "reason": "no_provider"}

        from intel_platform.llm.skills.loader import SkillsLoader

        system = SkillsLoader().get_system_prompt(skill_name, include_foundation=True) or ""
        try:
            result = await provider.generate(
                messages=[{"role": "user", "content": prompt}],
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception:
            # SECURITY: never leak provider/internal detail to the client.
            logger.exception("LLM generation failed for analytic skill %s", skill_name)
            return {"content": "", "model": "none", "tokens_used": 0,
                    "degraded": True, "reason": "generation_failed"}
        return {
            "content": result.content,
            "model": result.model,
            "tokens_used": result.total_tokens,
            "degraded": False,
            "reason": "",
        }

    # ── source evaluation ──────────────────────────────────────────────────
    def _source_metrics(self, project_id: str, document_ids: list[str], limit: int) -> list[dict]:
        """Measured provenance signals for the documents in scope."""
        limit = max(1, min(limit, _MAX_DOCS))
        with self._store._driver.session() as session:
            result = session.run(
                """
                MATCH (d:Document)
                WHERE d.project_id = $pid AND ($ids = [] OR d.id IN $ids)
                OPTIONAL MATCH (d)-[]->(e)
                WHERE e.entity_type IS NOT NULL AND NOT e.entity_type IN $system
                WITH d, collect(DISTINCT e.name)[..20] AS entity_names, count(DISTINCT e) AS entity_count
                RETURN d.id AS id, d.name AS name, coalesce(d.url, '') AS url,
                       coalesce(d.reliability_rating, '') AS reliability_rating,
                       coalesce(d.content, '') AS content,
                       toString(d.created_at) AS created_at,
                       entity_names, entity_count
                ORDER BY entity_count DESC, d.name
                LIMIT $limit
                """,
                pid=project_id, ids=document_ids or [], system=_SYSTEM_TYPES, limit=limit,
            )
            docs = [dict(record) for record in result]

            corroboration: dict[str, int] = {}
            doc_ids = [d["id"] for d in docs]
            if doc_ids:
                corr = session.run(
                    """
                    MATCH (d:Document)-[]->(e)
                    WHERE d.id IN $ids AND e.entity_type IS NOT NULL AND NOT e.entity_type IN $system
                    MATCH (other:Document)-[]->(e)
                    WHERE other.project_id = $pid AND other.id <> d.id
                    RETURN d.id AS id, count(DISTINCT other) AS corroborating_docs
                    """,
                    ids=doc_ids, pid=project_id, system=_SYSTEM_TYPES,
                )
                corroboration = {r["id"]: r["corroborating_docs"] for r in corr}

        metrics = []
        for doc in docs:
            content = doc.pop("content", "") or ""
            metrics.append({
                "document_id": doc["id"],
                "name": doc["name"],
                "url": doc["url"],
                "current_rating": doc["reliability_rating"],
                "created_at": doc["created_at"] or "",
                "content_length": len(content),
                "entity_count": doc["entity_count"],
                "entity_names": doc["entity_names"],
                "corroborating_documents": corroboration.get(doc["id"], 0),
                "excerpt": content[:_DOC_EXCERPT_CHARS],
            })
        return metrics

    @staticmethod
    def _source_evidence_block(metrics: list[dict]) -> str:
        lines = ["## Source Dossier (measured from the project's own holdings)\n"]
        for m in metrics:
            lines.append(f"\n### Document `{m['document_id']}` — {m['name']}")
            lines.append(f"- Origin URL: {m['url'] or 'none recorded (ingested text / upload)'}")
            lines.append(f"- Analyst rating on file: {m['current_rating'] or 'unrated'}")
            lines.append(f"- Collected: {m['created_at'] or 'unknown'}")
            lines.append(f"- Content volume: {m['content_length']} characters")
            lines.append(f"- Entities extracted: {m['entity_count']}")
            lines.append(
                f"- Corroboration: {m['corroborating_documents']} other document(s) in this "
                "project reference at least one of the same entities"
            )
            if m["entity_names"]:
                lines.append(f"- Named entities: {', '.join(m['entity_names'])}")
            if m["excerpt"]:
                lines.append(f"- Excerpt:\n```\n{m['excerpt']}\n```")
        return "\n".join(lines)

    @staticmethod
    def _source_fallback_markdown(metrics: list[dict], reason: str = "") -> str:
        lines = [
            "# Source Evaluation — measured signals only",
            "",
            f"{_degraded_because(reason)} No Admiralty rating has been assigned. "
            "The provenance signals below are measured directly from the project's "
            "holdings and are what a rating would be based on.",
            "",
            "| Document | Origin | Rating on file | Entities | Corroborating docs | Chars |",
            "|---|---|---|---|---|---|",
        ]
        for m in metrics:
            origin = "web" if m["url"] else "uploaded/ingested"
            lines.append(
                f"| {m['name']} | {origin} | {m['current_rating'] or 'unrated'} | "
                f"{m['entity_count']} | {m['corroborating_documents']} | {m['content_length']} |"
            )
        return "\n".join(lines)

    async def evaluate_sources(
        self, project_id: str, document_ids: list[str] | None = None,
        limit: int = 10, apply_ratings: bool = False,
    ) -> dict:
        """Grade the project's sources on the NATO Admiralty scale."""
        metrics = await asyncio.to_thread(
            self._source_metrics, project_id, document_ids or [], limit,
        )
        if not metrics:
            return {
                "analysis": (
                    "No documents are held for this project, so there is nothing to "
                    "evaluate. Collect or ingest sources first."
                ),
                "skill_applied": "source_evaluation",
                "model": "none", "tokens_used": 0,
                "retrieval_mode": "ungrounded",
                "documents_evaluated": 0,
                "evaluations": [], "metrics": [], "ratings_applied": 0,
            }

        evidence = self._source_evidence_block(metrics)
        prompt = (
            "Evaluate every source below using the NATO Admiralty Rating System.\n\n"
            f"{evidence}\n\n"
            "For each document give: the rating (letter for source reliability, digit "
            "for information credibility), the reasoning behind each half of the "
            "rating, and what would raise or lower it. Judge only on the measured "
            "signals and excerpt shown — do not assume anything about the publisher "
            "that is not evidenced here, and say so explicitly where the evidence is "
            "too thin to judge (rating F or 6).\n\n"
            "Close your answer with a machine-readable block, one line per document, "
            "in exactly this form and nothing else on the line:\n\n"
            "RATINGS:\n"
            + "\n".join(f"{m['document_id']}: <rating>" for m in metrics)
        )

        gen = await self._generate("source_evaluation", prompt, temperature=0.3, max_tokens=4096)
        analysis = gen["content"] or self._source_fallback_markdown(metrics, gen.get("reason", ""))

        parsed: dict[str, str] = {}
        for m in metrics:
            rating = _find_rating(gen["content"] or "", m["document_id"])
            if rating:
                parsed[m["document_id"]] = rating

        evaluations = [
            {
                "document_id": m["document_id"],
                "name": m["name"],
                "current_rating": m["current_rating"],
                "admiralty_rating": parsed.get(m["document_id"], ""),
                "entity_count": m["entity_count"],
                "corroborating_documents": m["corroborating_documents"],
            }
            for m in metrics
        ]

        applied = 0
        if apply_ratings and parsed:
            def _write() -> int:
                written = 0
                for doc_id, rating in parsed.items():
                    if self._store.update_entity(doc_id, {"reliability_rating": rating}):
                        written += 1
                return written

            applied = await asyncio.to_thread(_write)

        return {
            "analysis": analysis,
            "skill_applied": "source_evaluation",
            "model": gen["model"],
            "tokens_used": gen["tokens_used"],
            "retrieval_mode": "grounded",
            "documents_evaluated": len(metrics),
            "evaluations": evaluations,
            "metrics": [{k: v for k, v in m.items() if k != "excerpt"} for m in metrics],
            "ratings_applied": applied,
        }

    # ── competing hypotheses (ACH) ─────────────────────────────────────────
    async def _graph_context(
        self, project_id: str, question: str, entity_ids: list[str],
        max_hops: int, token_budget: int,
    ) -> tuple[str, int, int, list[str]]:
        """Graph-RAG context for the entities in scope (explicit IDs win)."""
        pipeline = GraphRAGPipeline(self._store)

        def _resolve_names() -> list[str]:
            names = []
            for eid in entity_ids:
                ent = self._store.get_entity(eid)
                if ent:
                    names.append(ent.get("name", eid))
            return names

        entity_names = await asyncio.to_thread(_resolve_names) if entity_ids else []

        if entity_ids:
            understanding = {
                "query": ", ".join(entity_names) or question,
                "target_entities": [{"id": eid} for eid in entity_ids],
                "intent": "structured_analysis",
            }
        else:
            understanding = await asyncio.to_thread(
                pipeline.understand_query, question, project_id,
            )
        retrieved = await asyncio.to_thread(
            pipeline.retrieve_context, understanding, project_id, max_hops,
        )
        context = pipeline.assemble_context(retrieved, token_budget=token_budget)
        return context, retrieved.get("node_count", 0), retrieved.get("edge_count", 0), entity_names

    @staticmethod
    async def _vector_passages(question: str, project_id: str, session, token_budget: int) -> tuple[str, int]:
        """Semantically similar document passages, or nothing if unavailable."""
        if session is None:
            return "", 0
        try:
            from intel_platform.services.vector_search import vector_search
            hits = await vector_search(question, project_id, session, limit=15)
        except Exception:
            logger.warning("Vector search unavailable during ACH retrieval", exc_info=True)
            return "", 0
        if not hits:
            return "", 0
        budget = token_budget * 2
        used = 0
        passages = []
        for hit in hits:
            chunk = hit.get("chunk_text", "")
            if not chunk or used + len(chunk) > budget:
                continue
            passages.append(f"[similarity={hit['similarity']:.3f}, doc={hit['document_id']}]\n{chunk}")
            used += len(chunk)
        if not passages:
            return "", 0
        return "\n\n### Semantically Similar Document Passages\n" + "\n\n".join(passages), len(hits)

    @staticmethod
    def _parse_hypotheses(content: str) -> list[dict]:
        seen: set[str] = set()
        hypotheses = []
        for num, statement, prob in _HYPOTHESIS_RE.findall(content or ""):
            key = f"H{num}"
            if key in seen:
                continue
            seen.add(key)
            try:
                probability = float(prob)
            except ValueError:
                continue
            probability = min(max(probability, 0.0), 1.0)
            hypotheses.append({
                "id": key,
                "statement": statement.strip().strip("*"),
                "probability": probability,
                "probability_label": probability_to_label(probability),
            })
        return hypotheses

    async def generate_hypotheses(
        self, project_id: str, question: str, entity_ids: list[str] | None = None,
        max_hops: int = 2, token_budget: int = 8000, session=None, use_vector: bool = True,
        save_assessment: bool = False, analyst: str = "llm",
    ) -> dict:
        """Run Analysis of Competing Hypotheses against retrieved project evidence."""
        entity_ids = entity_ids or []
        context, nodes, edges, entity_names = await self._graph_context(
            project_id, question, entity_ids, max_hops, token_budget,
        )
        vector_block, vector_hits = ("", 0)
        if use_vector:
            vector_block, vector_hits = await self._vector_passages(
                question, project_id, session, token_budget,
            )
        context += vector_block
        grounded = bool(nodes or edges or vector_hits)

        focus = f" Focus entities: {', '.join(entity_names)}." if entity_names else ""
        if grounded:
            prompt = (
                f"Apply Analysis of Competing Hypotheses to this question.\n\n"
                f"**Question:** {question}{focus}\n\n{context}\n\n"
                "Work the full ACH process:\n"
                "1. Enumerate the competing hypotheses, including at least one that "
                "contradicts the most obvious reading of the evidence.\n"
                "2. List the significant evidence and arguments, each tied to the "
                "specific entity, relationship, or document excerpt above.\n"
                "3. Build the consistency matrix as a markdown table (rows = evidence, "
                "columns = hypotheses, cells = C / I / N).\n"
                "4. Identify the hypothesis with the fewest inconsistencies and say which "
                "single item of evidence would most change the conclusion.\n"
                "5. State the diagnostic gaps — what evidence is absent that would "
                "discriminate between the surviving hypotheses.\n\n"
                "Every item of evidence must come from the context above; do not invent "
                "sources or facts. Where the evidence is silent, say so."
            )
        else:
            prompt = (
                f"Apply Analysis of Competing Hypotheses to this question.\n\n"
                f"**Question:** {question}{focus}\n\n"
                "No graph relationships or source documents were retrieved for this "
                "question in the project. State that limitation explicitly, then set out "
                "the hypotheses that would need to be tested and exactly what evidence "
                "would discriminate between them. Do not fabricate evidence or citations."
            )
        prompt += (
            "\n\nClose your answer with a machine-readable block, one line per "
            "hypothesis, in exactly this form and nothing else on the line:\n\n"
            "HYPOTHESES:\n"
            "H1 | <hypothesis statement> | <probability 0.00-1.00>\n"
            "H2 | <hypothesis statement> | <probability 0.00-1.00>"
        )

        gen = await self._generate("hypothesis_generation", prompt, temperature=0.4, max_tokens=8192)
        if gen["degraded"]:
            analysis = (
                "# Analysis of Competing Hypotheses — not generated\n\n"
                f"{_degraded_because(gen.get('reason', ''))} No hypotheses were generated. "
                f"The retrieval below is real and ready for an analyst to work manually.\n\n"
                f"**Question:** {question}\n\n"
                f"Retrieved {nodes} graph entities, {edges} relationships"
                + (f", {vector_hits} similar document passages" if vector_hits else "")
                + ".\n\n" + context
            )
        else:
            analysis = gen["content"]

        hypotheses = self._parse_hypotheses(gen["content"])
        response = {
            "question": question,
            "analysis": analysis,
            "hypotheses": hypotheses,
            "skill_applied": "hypothesis_generation",
            "model": gen["model"],
            "tokens_used": gen["tokens_used"],
            "retrieval_mode": "grounded" if grounded else "ungrounded",
            "context_nodes": nodes,
            "context_edges": edges,
            "vector_hits": vector_hits,
            "focus_entities": entity_names,
        }

        # Persist exactly like /assess/generate: the leading hypothesis is a
        # judgment about the focus entity, so it becomes an Assessment node.
        if save_assessment and hypotheses and entity_ids and not gen["degraded"]:
            from intel_platform.services.assessment import AssessmentService

            leading = max(hypotheses, key=lambda h: h["probability"])
            saved = await asyncio.to_thread(
                AssessmentService(self._store).create_assessment,
                entity_ids[0], project_id, analysis, leading["probability"], analyst,
                "Analysis of Competing Hypotheses (ACH) over Graph-RAG evidence",
            )
            if "error" not in saved:
                response["assessment_id"] = saved["assessment_id"]
                response["probability"] = saved["probability"]
                response["probability_label"] = saved["probability_label"]

        return response

    # ── gap analysis ───────────────────────────────────────────────────────
    def _coverage(self, project_id: str) -> dict:
        """Deterministic coverage counters computed straight from Neo4j."""
        with self._store._driver.session() as session:
            degrees = session.run(
                """
                MATCH (n)
                WHERE n.project_id = $pid AND NOT coalesce(n.entity_type, '') IN $system
                WITH n, size([(n)--() | 1]) AS degree
                RETURN count(n) AS total,
                       sum(CASE WHEN degree = 0 THEN 1 ELSE 0 END) AS isolated,
                       sum(CASE WHEN degree = 1 THEN 1 ELSE 0 END) AS single_link,
                       sum(CASE WHEN coalesce(n.source_doc_id, '') = '' THEN 1 ELSE 0 END) AS unsourced,
                       collect(CASE WHEN degree = 0 THEN n.name END)[..10] AS isolated_names,
                       collect(CASE WHEN degree = 1 THEN n.name END)[..10] AS single_link_names,
                       collect(CASE WHEN coalesce(n.source_doc_id, '') = '' THEN n.name END)[..10]
                           AS unsourced_names
                """,
                pid=project_id, system=_SYSTEM_TYPES,
            ).single()

            docs = session.run(
                """
                MATCH (d:Document {project_id: $pid})
                RETURN count(d) AS total,
                       sum(CASE WHEN coalesce(d.reliability_rating, '') = '' THEN 1 ELSE 0 END) AS unrated,
                       collect(CASE WHEN coalesce(d.reliability_rating, '') = '' THEN d.name END)[..10]
                           AS unrated_names
                """,
                pid=project_id,
            ).single()

            geo = session.run(
                """
                MATCH (n)
                WHERE n.project_id = $pid
                  AND (n.entity_category = 'Location' OR n.entity_type = 'Location')
                RETURN count(n) AS total,
                       sum(CASE WHEN n.latitude IS NULL OR n.longitude IS NULL THEN 1 ELSE 0 END)
                           AS ungeocoded,
                       collect(CASE WHEN n.latitude IS NULL OR n.longitude IS NULL THEN n.name END)[..10]
                           AS ungeocoded_names
                """,
                pid=project_id,
            ).single()

            types = session.run(
                """
                MATCH (n) WHERE n.project_id = $pid AND n.entity_type IS NOT NULL
                RETURN n.entity_type AS entity_type, count(*) AS count
                ORDER BY count DESC
                """,
                pid=project_id,
            )
            type_counts = {r["entity_type"]: r["count"] for r in types}

            rels = session.run(
                """
                MATCH (a)-[r]->(b) WHERE a.project_id = $pid
                RETURN type(r) AS rel_type, count(*) AS count
                ORDER BY count DESC
                """,
                pid=project_id,
            )
            rel_counts = {r["rel_type"]: r["count"] for r in rels}

        return {
            "entities": (degrees["total"] if degrees else 0) or 0,
            "isolated": (degrees["isolated"] if degrees else 0) or 0,
            "single_link": (degrees["single_link"] if degrees else 0) or 0,
            "unsourced": (degrees["unsourced"] if degrees else 0) or 0,
            "isolated_names": list(degrees["isolated_names"]) if degrees else [],
            "single_link_names": list(degrees["single_link_names"]) if degrees else [],
            "unsourced_names": list(degrees["unsourced_names"]) if degrees else [],
            "documents": (docs["total"] if docs else 0) or 0,
            "unrated_documents": (docs["unrated"] if docs else 0) or 0,
            "unrated_document_names": list(docs["unrated_names"]) if docs else [],
            "locations": (geo["total"] if geo else 0) or 0,
            "ungeocoded_locations": (geo["ungeocoded"] if geo else 0) or 0,
            "ungeocoded_names": list(geo["ungeocoded_names"]) if geo else [],
            "entity_type_counts": type_counts,
            "relationship_type_counts": rel_counts,
            "relationships": sum(rel_counts.values()),
        }

    @staticmethod
    def _structural_gaps(coverage: dict) -> list[dict]:
        """Turn coverage counters into named, prioritised gaps."""
        gaps: list[dict] = []

        def add(kind: str, title: str, detail: str, priority: str, count: int, examples: list[str]) -> None:
            gaps.append({
                "kind": kind, "title": title, "detail": detail,
                "priority": priority, "count": count, "examples": [e for e in examples if e][:10],
            })

        if coverage["isolated"]:
            add(
                "connection", "Isolated entities",
                "Extracted but never linked to anything else — either the relationship "
                "was missed at extraction or no source connects them yet.",
                "high", coverage["isolated"], coverage["isolated_names"],
            )
        if coverage["single_link"]:
            add(
                "connection", "Single-link entities",
                "One relationship only, so nothing corroborates their place in the "
                "picture. Prime candidates for targeted collection.",
                "medium", coverage["single_link"], coverage["single_link_names"],
            )
        if coverage["unsourced"]:
            add(
                "provenance", "Entities with no source document",
                "No source document is recorded, so claims about them cannot be traced "
                "back to collected material.",
                "high", coverage["unsourced"], coverage["unsourced_names"],
            )
        if coverage["unrated_documents"]:
            add(
                "provenance", "Unrated sources",
                "Documents carry no Admiralty reliability rating, so every judgment "
                "drawn from them is uncaveated. Run source evaluation.",
                "medium", coverage["unrated_documents"], coverage["unrated_document_names"],
            )
        if coverage["ungeocoded_locations"]:
            add(
                "geographic", "Ungeocoded locations",
                "Location entities without coordinates are invisible to geospatial "
                "analysis and to the map view.",
                "medium", coverage["ungeocoded_locations"], coverage["ungeocoded_names"],
            )
        missing_types = [t for t in _CORE_TYPES if not coverage["entity_type_counts"].get(t)]
        if missing_types:
            add(
                "coverage", "Absent entity types",
                "No entities of these core types have been collected at all: "
                + ", ".join(missing_types) + ".",
                "medium", len(missing_types), missing_types,
            )
        if coverage["relationships"] and not coverage["relationship_type_counts"].get("ATTRIBUTED_TO"):
            add(
                "attribution", "No attribution relationships",
                "The graph holds no ATTRIBUTED_TO edges, so nothing in this project is "
                "formally attributed to an actor.",
                "medium", 0, [],
            )
        if not coverage["documents"]:
            add(
                "collection", "No source documents",
                "The project holds no documents at all — every entity is unsupported.",
                "high", 0, [],
            )
        return gaps

    @staticmethod
    def _gap_evidence_block(coverage: dict, gaps: list[dict], focus_names: list[str]) -> str:
        lines = ["## Measured Coverage (computed from the knowledge graph)\n"]
        lines.append(
            f"- Entities: {coverage['entities']} | Relationships: {coverage['relationships']} "
            f"| Documents: {coverage['documents']}"
        )
        lines.append(
            f"- Isolated entities: {coverage['isolated']} | Single-link: {coverage['single_link']} "
            f"| Unsourced: {coverage['unsourced']}"
        )
        lines.append(
            f"- Unrated documents: {coverage['unrated_documents']} | "
            f"Ungeocoded locations: {coverage['ungeocoded_locations']} of {coverage['locations']}"
        )
        if coverage["entity_type_counts"]:
            top = sorted(coverage["entity_type_counts"].items(), key=lambda kv: -kv[1])[:12]
            lines.append("- Entity types held: " + ", ".join(f"{t} ({c})" for t, c in top))
        if coverage["relationship_type_counts"]:
            top_rel = sorted(coverage["relationship_type_counts"].items(), key=lambda kv: -kv[1])[:12]
            lines.append("- Relationship types held: " + ", ".join(f"{t} ({c})" for t, c in top_rel))
        if focus_names:
            lines.append("- Analyst focus entities: " + ", ".join(focus_names))

        if gaps:
            lines.append("\n### Structural gaps detected\n")
            for gap in gaps:
                examples = f" e.g. {', '.join(gap['examples'])}" if gap["examples"] else ""
                lines.append(
                    f"- **{gap['title']}** ({gap['kind']}, priority {gap['priority']}, "
                    f"count {gap['count']}): {gap['detail']}{examples}"
                )
        return "\n".join(lines)

    @staticmethod
    def _gap_fallback_markdown(coverage: dict, gaps: list[dict], reason: str = "") -> str:
        lines = [
            "# Intelligence Gap Analysis — measured gaps only",
            "",
            f"{_degraded_because(reason)} There is no narrative; the gaps below are "
            "computed directly from the knowledge graph and are actionable as-is.",
            "",
            f"**Coverage:** {coverage['entities']} entities · {coverage['relationships']} "
            f"relationships · {coverage['documents']} documents",
            "",
        ]
        if not gaps:
            lines.append("No structural gaps detected by the coverage checks.")
            return "\n".join(lines)
        lines += ["| Gap | Type | Priority | Count | Examples |", "|---|---|---|---|---|"]
        for gap in gaps:
            lines.append(
                f"| {gap['title']} | {gap['kind']} | {gap['priority']} | {gap['count']} | "
                f"{', '.join(gap['examples']) or '—'} |"
            )
        return "\n".join(lines)

    async def analyze_gaps(
        self, project_id: str, entity_ids: list[str] | None = None, focus: str = "",
        max_hops: int = 2, token_budget: int = 8000,
    ) -> dict:
        """Identify intelligence gaps from measured graph coverage, then narrate them."""
        entity_ids = entity_ids or []
        coverage = await asyncio.to_thread(self._coverage, project_id)
        gaps = self._structural_gaps(coverage)

        context = ""
        nodes = edges = 0
        focus_names: list[str] = []
        if entity_ids:
            question = focus or "What is missing from the picture around these entities?"
            context, nodes, edges, focus_names = await self._graph_context(
                project_id, question, entity_ids, max_hops, token_budget,
            )

        evidence = self._gap_evidence_block(coverage, gaps, focus_names)
        scope = (
            f"the entities {', '.join(focus_names)}" if focus_names else "this project as a whole"
        )
        prompt = (
            f"Identify the intelligence gaps for {scope}.\n\n{evidence}\n"
            + (f"\n{context}\n" if context else "")
            + (f"\nAnalyst's stated focus / PIR: {focus}\n" if focus else "")
            + "\nFor each gap give: what is missing, why it matters to the current "
            "picture, a concrete collection approach that would close it, and a "
            "priority. Start from the structural gaps measured above — explain what "
            "they mean analytically rather than restating the numbers — then add gaps "
            "that only a reading of the evidence reveals (uninvestigated connections, "
            "temporal holes, geographic holes, attribution holes). Do not invent "
            "entities or sources that are not shown above."
        )

        gen = await self._generate("gap_analysis", prompt, temperature=0.3, max_tokens=4096)
        analysis = gen["content"] or self._gap_fallback_markdown(coverage, gaps, gen.get("reason", ""))

        return {
            "analysis": analysis,
            "skill_applied": "gap_analysis",
            "model": gen["model"],
            "tokens_used": gen["tokens_used"],
            "retrieval_mode": "grounded" if (coverage["entities"] or nodes) else "ungrounded",
            "coverage": coverage,
            "structural_gaps": gaps,
            "context_nodes": nodes,
            "context_edges": edges,
            "focus_entities": focus_names,
        }
