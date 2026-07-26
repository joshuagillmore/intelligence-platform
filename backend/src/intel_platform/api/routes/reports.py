from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.db.engine import get_db
from intel_platform.graph.store import GraphStore
from intel_platform.services.graph_rag import GraphRAGPipeline
from intel_platform.services.reports import ReportService

router = APIRouter(dependencies=[Depends(verify_api_key)])
logger = logging.getLogger(__name__)

# Cap on how many supporting relationships a product carries. Enough to make the
# basis checkable without turning the response into a graph dump.
_MAX_EVIDENCE = 40


def _evidence_from_retrieval(retrieved: dict | None) -> list[dict]:
    """The relationships a product was drawn from, with their provenance.

    Edges that captured a source sentence come first — those are the ones a
    reader can actually verify. Returns [] when nothing was retrieved, which is
    the honest answer for an ungrounded product.
    """
    if not retrieved:
        return []
    edges = retrieved.get("edges") or []

    def field(edge: dict, key: str, default=None):
        # get_subgraph nests relationship properties under "props";
        # get_relationships spreads them. Read either shape.
        props = edge.get("props") or {}
        value = edge.get(key, props.get(key, default))
        return default if value is None else value

    trimmed = [
        {
            "source_name": e.get("source_name", ""),
            "target_name": e.get("target_name", ""),
            "rel_type": e.get("rel_type", ""),
            "confidence": field(e, "confidence"),
            "evidence": field(e, "evidence", ""),
            "source_doc_id": field(e, "source_doc_id", ""),
            "admiralty_rating": field(e, "admiralty_rating", ""),
            "corroboration_count": field(e, "corroboration_count", 1),
            "corroboration_agreement": field(e, "corroboration_agreement", ""),
            "method": field(e, "method", ""),
        }
        for e in edges
    ]
    trimmed.sort(key=lambda x: (not x["evidence"], -(x["confidence"] or 0)))
    return trimmed[:_MAX_EVIDENCE]


class SaveReportRequest(BaseModel):
    project_id: str
    title: str
    content: str
    report_type: str = "general"
    entity_ids: list[str] = []
    analyst: str = "system"


class GenerateReportRequest(BaseModel):
    project_id: str
    report_type: str = "general"
    skill_name: str = "report_writing"
    entity_ids: list[str] = []
    # The requirement this product answers. Without it a report is only "tell me
    # about these entities": one run collecting on Iranian intrusions into water
    # utility OT produced an assessment of the EPA website's language options and
    # topic menu, in full ICD 203 probability language, because the nav furniture
    # was among the entities passed in. Supply the PIR text, or `pir_id` to load it.
    requirement: str = ""
    pir_id: str | None = None
    include_evidence: bool = True
    probability_assessments: bool = False
    max_hops: int = Field(2, ge=1, le=4)
    token_budget: int = Field(8000, ge=500, le=32000)
    use_vector: bool = True


@router.post("/reports")
def save_report(req: SaveReportRequest, store: GraphStore = Depends(get_graph_store)):
    svc = ReportService(store)
    return svc.save_report(
        project_id=req.project_id, title=req.title, content=req.content,
        report_type=req.report_type, entity_ids=req.entity_ids, analyst=req.analyst,
    )


@router.get("/reports")
def list_reports(project_id: str, store: GraphStore = Depends(get_graph_store)):
    svc = ReportService(store)
    return svc.list_reports(project_id)


@router.post("/reports/generate")
async def generate_report(
    req: GenerateReportRequest,
    store: GraphStore = Depends(get_graph_store),
    session: AsyncSession = Depends(get_db),
):
    """Generate an intelligence product grounded in real Graph-RAG retrieval.

    Resolves the analyst-selected entities by exact ID (not a fuzzy text
    search — the analyst already chose them), retrieves their subgraph and
    source document evidence via the existing GraphRAGPipeline, optionally
    enriches with semantically similar passages via vector search, and
    generates the report through the requested skill. Falls back to an
    ungrounded prompt — with the limitation stated explicitly — only when
    retrieval finds no graph or document evidence at all.
    """
    pipeline = GraphRAGPipeline(store)

    # Neo4j driver is synchronous; offload the store reads so this async handler
    # doesn't block the event loop.
    def _resolve_entity_names() -> list[str]:
        names: list[str] = []
        for eid in req.entity_ids:
            ent = store.get_entity(eid)
            if ent:
                names.append(ent.get("name", eid))
        return names

    entity_names: list[str] = await asyncio.to_thread(_resolve_entity_names)

    # Resolve the requirement this product is answering. It steers retrieval and
    # is stated to the writer, so the product addresses the question rather than
    # narrating whichever entities happened to be selected.
    requirement = (req.requirement or "").strip()
    if not requirement and req.pir_id:
        from intel_platform.api.routes.collection_plans import _parse_uuid
        from intel_platform.db.models import Pir

        # Outside the try: a malformed pir_id is a client error and must surface
        # as a 400, not silently produce an ungrounded product.
        pir_uuid = _parse_uuid(req.pir_id, "pir_id")
        try:
            pir = await session.get(Pir, pir_uuid)
        except Exception:
            logger.warning("Could not load PIR for report grounding", exc_info=True)
            pir = None
        # Scope to the requested project — a PIR from another project must not
        # become this report's subject and retrieval query.
        if pir and pir.project_id == req.project_id:
            requirement = (pir.refined_text or pir.text or "").strip()
        elif pir:
            raise HTTPException(400, "pir_id does not belong to project_id")

    context = ""
    context_nodes = 0
    context_edges = 0
    vector_hits = 0
    # Stays None when nothing was retrieved (no entity_ids), which the evidence
    # helper treats as "no supporting evidence" rather than failing.
    retrieved: dict | None = None

    if req.entity_ids:
        understanding = {
            # Lead the retrieval query with the requirement when there is one:
            # entity names alone pull whatever is adjacent, which is how crawl
            # furniture ended up anchoring a report.
            "query": requirement or ", ".join(entity_names) or req.report_type,
            "target_entities": [{"id": eid} for eid in req.entity_ids],
            "intent": "report_generation",
        }
        retrieved = await asyncio.to_thread(
            pipeline.retrieve_context, understanding, req.project_id, req.max_hops
        )
        context = pipeline.assemble_context(retrieved, token_budget=req.token_budget)
        context_nodes = retrieved.get("node_count", 0)
        context_edges = retrieved.get("edge_count", 0)

        if req.use_vector and (entity_names or requirement):
            try:
                from intel_platform.services.vector_search import vector_search
                vec_results = await vector_search(
                    requirement or ", ".join(entity_names), req.project_id, session, limit=15,
                )
            except Exception:
                logger.warning("Vector search failed during report generation", exc_info=True)
                vec_results = []
            vector_hits = len(vec_results)
            if vec_results:
                char_budget = req.token_budget * 2
                char_count = 0
                passages = []
                for vr in vec_results:
                    chunk = vr.get("chunk_text", "")
                    if not chunk:
                        continue
                    if char_count + len(chunk) > char_budget:
                        break
                    passages.append(f"[similarity={vr['similarity']:.3f}, doc={vr['document_id']}]\n{chunk}")
                    char_count += len(chunk)
                if passages:
                    context += "\n\n### Semantically Similar Document Passages\n" + "\n\n".join(passages)

    retrieval_mode = "grounded" if (context_nodes or context_edges or vector_hits) else "ungrounded"

    from intel_platform.llm.skills.loader import SkillsLoader
    loader = SkillsLoader()
    system = loader.get_system_prompt(req.skill_name, include_foundation=True) or ""

    instructions = [f"Generate a {req.report_type} intelligence product"]
    if requirement:
        instructions.append(
            f"answering this intelligence requirement: {requirement}\n"
            "The requirement is the subject of the product. Entities supplied below are "
            "candidate evidence, not the topic — collected material includes web page "
            "furniture (site navigation, language selectors, topic menus, cookie notices), "
            "and none of it belongs in an assessment. Where the collection does not answer "
            "the requirement, say so plainly under information gaps rather than writing "
            "judgements about whatever else was collected"
        )
    if entity_names:
        instructions.append(
            f"drawing on these entities where they bear on the requirement: {', '.join(entity_names)}"
            if requirement else f"covering: {', '.join(entity_names)}"
        )
    if req.include_evidence:
        instructions.append(
            "Include evidence chains — cite the specific graph relationships and "
            "document excerpts below for every assessment"
        )
    if req.probability_assessments:
        instructions.append("Include probability assessments using standard intelligence community language")

    if retrieval_mode == "grounded":
        prompt = (
            f"{'. '.join(instructions)}.\n\n{context}\n\n"
            "Base every claim strictly on the context above; do not invent sources, "
            "evidence, or evidence chains that aren't shown there. Weight and caveat "
            "claims according to each source's stated reliability."
        )
    else:
        # No graph or document evidence for these entities — fall back to a bare
        # prompt, but require the model to say so rather than fabricate citations.
        entity_context = ", ".join(entity_names) or "the selected entities"
        prompt = (
            f"{'. '.join(instructions)}.\n\n"
            f"No source documents or graph relationships were found for {entity_context} "
            "in this project. State this limitation explicitly and do not fabricate "
            "evidence, citations, or evidence chains."
        )

    from intel_platform.api.routes.llm import _get_provider
    provider = await _get_provider()
    if not provider:
        return {
            "content": "No LLM provider configured. Add API keys to .env file.",
            "model": "none",
            "tokens_used": 0,
            "skill_applied": req.skill_name,
            "retrieval_mode": retrieval_mode,
            "context_nodes": context_nodes,
            "context_edges": context_edges,
        }

    try:
        result = await provider.generate(
            messages=[{"role": "user", "content": prompt}],
            system=system,
            temperature=0.3,
            max_tokens=8192,
        )
    except Exception:
        # SECURITY: don't leak internal error details to the client
        logger.exception("LLM generation failed during report generation")
        return {
            "content": "Report generation failed. Check LLM provider configuration.",
            "model": "none",
            "tokens_used": 0,
            "skill_applied": req.skill_name,
            "retrieval_mode": retrieval_mode,
            "context_nodes": context_nodes,
            "context_edges": context_edges,
        }

    response = {
        "content": result.content,
        "model": result.model,
        "tokens_used": result.total_tokens,
        "skill_applied": req.skill_name,
        "retrieval_mode": retrieval_mode,
        "context_nodes": context_nodes,
        "context_edges": context_edges,
        # The relationships the product was actually drawn from, with their
        # provenance. Only counts were returned before, so a reader had no way
        # to check a claim — the evidence existed but never left the backend.
        "evidence": _evidence_from_retrieval(retrieved),
    }
    if req.skill_name in ("threat_assessment", "report_writing"):
        prob_match = re.search(r'PROBABILITY:\s*([01]\.\d+)', result.content)
        if prob_match:
            response["probability"] = float(prob_match.group(1))
    return response


@router.get("/reports/{report_id}")
def get_report(report_id: str, store: GraphStore = Depends(get_graph_store)):
    svc = ReportService(store)
    report = svc.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.delete("/reports/{report_id}")
def delete_report(report_id: str, store: GraphStore = Depends(get_graph_store)):
    svc = ReportService(store)
    svc.delete_report(report_id)
    return {"status": "deleted"}
