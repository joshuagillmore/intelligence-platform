"""RAG text→technique mapping for a project's prose TTP entities (Phase 2).

Phase 1 resolves TTPs that carry an explicit T-code. This maps the rest: for each
project ``TTP`` NOT already resolved by T-code, embed its text, cosine-retrieve
the top-K candidate techniques from ``attack_technique_embeddings`` (indexed by
:mod:`services.attack.embeddings`), then have an LLM confirm which candidate(s)
actually apply. Grounding the LLM in a handful of retrieved candidates sidesteps
the ~700-way classification problem.

Confirmed matches at/above ``attack_mapping_confidence_min`` are written as
``(:TTP)-[:MAPS_TO {confidence, method:"llm", rationale}]->(:AttackTechnique)``
(Phase 1 T-code resolution uses ``method:"tcode"``). Degrades cleanly — a missing
embedding or LLM provider yields skips, never an exception — so the endpoint never
500s on a provider outage. The LLM call is routed through the extraction/collection
provider so bulk mapping won't drain a rate-limited cloud key.
"""
from __future__ import annotations

import asyncio
import json
import logging

from neo4j import Driver
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.config import settings
from intel_platform.llm.embeddings import EmbeddingProvider, get_embedding_provider
from intel_platform.llm.providers import _get_extraction_provider
from intel_platform.llm.skills.loader import SkillsLoader

logger = logging.getLogger(__name__)

# Texts per embedding API call (mirrors vector_search).
_EMBED_BATCH_SIZE = 96


# ---------------------------------------------------------------------------
# Neo4j reads / writes (sync driver — callers offload via asyncio.to_thread)
# ---------------------------------------------------------------------------

def _fetch_unresolved_ttps(driver: Driver, project_id: str, limit: int) -> list[dict]:
    """Project TTPs lacking a T-code (``method:"tcode"``) MAPS_TO edge (capped)."""
    with driver.session() as session:
        return session.run(
            """
            MATCH (t:TTP {project_id: $pid})
            WHERE NOT (t)-[:MAPS_TO {method: 'tcode'}]->(:AttackTechnique)
            RETURN t.id AS id, coalesce(t.name, '') AS name,
                   coalesce(t.description, '') AS description
            LIMIT $limit
            """,
            pid=project_id, limit=limit,
        ).data()


def _merge_mapping(driver: Driver, ttp_id: str, tech_id: str, confidence: float, rationale: str) -> bool:
    """Idempotently link a TTP to a confirmed technique with method="llm"."""
    with driver.session() as session:
        rec = session.run(
            """
            MATCH (t:TTP {id: $ttp_id})
            MATCH (tech:AttackTechnique {attack_id: $tech_id})
            MERGE (t)-[r:MAPS_TO]->(tech)
            SET r.method = 'llm', r.confidence = $confidence, r.rationale = $rationale
            RETURN count(*) AS c
            """,
            ttp_id=ttp_id, tech_id=tech_id, confidence=confidence, rationale=rationale,
        ).single()
        return bool(rec and rec["c"] > 0)


# ---------------------------------------------------------------------------
# RAG helpers
# ---------------------------------------------------------------------------

def _ttp_text(t: dict) -> str:
    name = (t.get("name") or "").strip()
    desc = (t.get("description") or "").strip()
    return f"{name}. {desc}".strip() if desc else name


async def _retrieve_candidates(session: AsyncSession, query_vec: list[float], top_k: int) -> list[dict]:
    """Cosine-nearest candidate techniques from pgvector (mirrors vector_search)."""
    stmt = sql_text(
        """
        SELECT technique_id, text,
               1 - (embedding <=> CAST(:qvec AS vector)) AS similarity
        FROM attack_technique_embeddings
        ORDER BY embedding <=> CAST(:qvec AS vector)
        LIMIT :k
        """
    )
    rows = await session.execute(stmt, {"qvec": str(query_vec), "k": top_k})
    return [
        {"technique_id": r.technique_id, "text": r.text, "similarity": float(r.similarity)}
        for r in rows
    ]


def _parse_matches(content: str) -> list[dict]:
    """Parse the skill's strict-JSON reply into confirmed matches (lenient)."""
    txt = (content or "").strip()
    if "```json" in txt:
        txt = txt.split("```json")[1].split("```")[0]
    elif "```" in txt:
        txt = txt.split("```")[1].split("```")[0]
    try:
        data = json.loads(txt.strip())
    except (ValueError, IndexError):
        return []
    raw = data.get("matches", []) if isinstance(data, dict) else []
    out: list[dict] = []
    for m in raw if isinstance(raw, list) else []:
        if not isinstance(m, dict):
            continue
        tid = (m.get("technique_id") or "").strip()
        if not tid:
            continue
        try:
            conf = float(m.get("confidence", 0))
        except (TypeError, ValueError):
            conf = 0.0
        out.append({"technique_id": tid, "confidence": conf, "rationale": (m.get("rationale") or "")[:280]})
    return out


async def _confirm_matches(provider, skill_system: str, ttp_text: str, candidates: list[dict]) -> list[dict] | None:
    """Ask the LLM which candidates apply. Returns matches, or None if unreachable."""
    lines = [f"- {c['technique_id']}: {c['text']}" for c in candidates]
    prompt = (
        "Observed TTP:\n"
        f"{ttp_text}\n\n"
        "Candidate ATT&CK techniques:\n"
        + "\n".join(lines)
        + "\n\nReturn the strict JSON described in your instructions."
    )
    try:
        result = await provider.generate(
            messages=[{"role": "user", "content": prompt}],
            system=skill_system,
            temperature=0.1,
            max_tokens=1024,
        )
    except Exception:
        logger.warning("ATT&CK mapping LLM call failed", exc_info=True)
        return None
    return _parse_matches(result.content)


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

async def map_project_ttps(
    session: AsyncSession,
    driver: Driver,
    project_id: str,
    *,
    embedding_provider: EmbeddingProvider | None = None,
) -> dict:
    """RAG-map a project's un-T-code-resolved TTPs to ATT&CK techniques.

    Returns ``{"mapped": int, "skipped": int}``. A TTP counts as ``mapped`` when at
    least one confirmed match at/above the confidence floor is written; otherwise
    ``skipped`` (no candidates, LLM unreachable, or all matches below threshold).
    Never raises for provider outages — the whole batch degrades to skips.
    """
    # Cap the batch — /attack/map is analyst-triggerable and each TTP costs an
    # embedding + LLM call; an unbounded project TTP set would be an open-ended
    # cost/latency/memory sink. Over-cap TTPs are simply left for a later run.
    cap = int(getattr(settings, "attack_mapping_max_ttps", 200) or 200)
    ttps = await asyncio.to_thread(_fetch_unresolved_ttps, driver, project_id, cap)
    if not ttps:
        return {"mapped": 0, "skipped": 0}


    # Embedding provider — degrade whole batch to skips if unavailable/unreachable.
    if embedding_provider is None:
        try:
            embedding_provider = get_embedding_provider()
        except Exception:
            logger.warning("No embedding provider for ATT&CK mapping", exc_info=True)
            return {"mapped": 0, "skipped": len(ttps)}

    texts = [_ttp_text(t) for t in ttps]
    vectors: list[list[float]] = []
    try:
        for i in range(0, len(texts), _EMBED_BATCH_SIZE):
            result = await embedding_provider.embed(texts[i : i + _EMBED_BATCH_SIZE], input_type="search_query")
            vectors.extend(result.embeddings)
    except Exception:
        logger.warning("Embedding TTP text failed for ATT&CK mapping", exc_info=True)
        return {"mapped": 0, "skipped": len(ttps)}
    if len(vectors) != len(ttps):
        return {"mapped": 0, "skipped": len(ttps)}

    # LLM provider (extraction/collection route so bulk mapping won't drain a
    # rate-limited cloud key) + the confirmation skill's system prompt.
    try:
        llm_provider = await _get_extraction_provider()
    except Exception:
        logger.warning("No LLM provider for ATT&CK mapping", exc_info=True)
        return {"mapped": 0, "skipped": len(ttps)}
    skill_system = SkillsLoader().get_system_prompt("attack_mapping", include_foundation=True) or ""

    top_k = int(getattr(settings, "attack_mapping_top_k", 5) or 5)
    threshold = float(getattr(settings, "attack_mapping_confidence_min", 0.5) or 0.5)

    # The technique catalogue has to be embedded before anything can match. When
    # it is not, every TTP retrieves zero candidates and the result is
    # {"mapped": 0, "skipped": N} — indistinguishable from "the model rejected
    # every candidate". Checked here rather than earlier so a known-unreachable
    # provider still short-circuits without touching the database.
    try:
        embedded = (
            await session.execute(sql_text("SELECT count(*) FROM attack_technique_embeddings"))
        ).scalar_one()
    except Exception:
        logger.warning("Could not count ATT&CK technique embeddings", exc_info=True)
        embedded = None
    if embedded == 0:
        return {
            "mapped": 0,
            "skipped": len(ttps),
            "reason": "technique_catalogue_not_embedded",
            "detail": "Run POST /api/attack/embed to embed the ATT&CK catalogue before mapping.",
        }

    mapped = 0
    skipped = 0
    for ttp, vec in zip(ttps, vectors):
        try:
            candidates = await _retrieve_candidates(session, vec, top_k)
        except Exception:
            # A real pgvector error (e.g. embedding dim != the table's Vector column)
            # must not 500 the endpoint — degrade the rest of the batch to skips.
            logger.warning("pgvector candidate retrieval failed for ATT&CK mapping", exc_info=True)
            skipped = len(ttps) - mapped
            break
        if not candidates:
            skipped += 1
            continue

        matches = None
        if llm_provider is not None:
            matches = await _confirm_matches(llm_provider, skill_system, _ttp_text(ttp), candidates)
        if matches is None:  # provider unreachable
            skipped += 1
            continue

        candidate_ids = {c["technique_id"] for c in candidates}
        wrote = False
        for m in matches:
            if m["technique_id"] in candidate_ids and m["confidence"] >= threshold:
                if await asyncio.to_thread(
                    _merge_mapping, driver, ttp["id"], m["technique_id"], m["confidence"], m["rationale"]
                ):
                    wrote = True
        if wrote:
            mapped += 1
        else:
            skipped += 1

    return {"mapped": mapped, "skipped": skipped}
