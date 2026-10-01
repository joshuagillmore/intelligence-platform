"""RAG text→technique mapping for a project's prose TTP entities (Phase 2).

Phase 1 resolves TTPs that carry an explicit T-code. This maps the rest: for each
project ``TTP`` NOT already resolved by T-code, embed its text, cosine-retrieve
the top-K candidate techniques from ``attack_technique_embeddings`` (indexed by
:mod:`services.attack.embeddings`), then have an LLM confirm which candidate(s)
actually apply. Grounding the LLM in a handful of retrieved candidates sidesteps
the ~700-way classification problem.

Confirmed matches at/above ``attack_mapping_confidence_min`` are written as
``(:TTP)-[:MAPS_TO {confidence, method:"llm", rationale}]->(:AttackTechnique)``
(Phase 1 T-code resolution uses ``method:"tcode"``). Every skipped TTP carries a
reason (no candidates, rejected by the model, unreadable reply, embedding or
retrieval unavailable); an unreachable LLM raises ``LLMUnavailable`` (the route
returns 503) instead of reading as "the model rejected everything". The LLM call
is routed through the extraction/collection provider so bulk mapping won't drain
a rate-limited cloud key.
"""
from __future__ import annotations

import asyncio
import logging
from collections import Counter

from neo4j import Driver
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.config import settings
from intel_platform.llm.embeddings import EmbeddingProvider, get_embedding_provider
from intel_platform.llm.providers import _get_extraction_provider
from intel_platform.llm.skills.loader import SkillsLoader
from intel_platform.services.llm_output import json_object
from intel_platform.services.telemetry import record_degraded

logger = logging.getLogger(__name__)

# Texts per embedding API call (mirrors vector_search).
_EMBED_BATCH_SIZE = 96


class LLMUnavailable(RuntimeError):
    """No LLM could be reached, or the confirmation call failed.

    Raised rather than counted as a skip: an outage is not the model rejecting
    the candidates, and ``{"mapped": 0, "skipped": N}`` would say it was. The
    route turns it into a 503. TTPs mapped before the failure keep their edges,
    and a re-run picks up the ones still unmapped.
    """


# ---------------------------------------------------------------------------
# Neo4j reads / writes (sync driver — callers offload via asyncio.to_thread)
# ---------------------------------------------------------------------------

def _fetch_unresolved_ttps(driver: Driver, project_id: str, limit: int, remap: bool = False) -> list[dict]:
    """Project TTPs still to map, ordered by id and capped.

    By default a TTP with *any* ``MAPS_TO`` edge is done: excluding only T-code
    edges re-sent every LLM-mapped TTP to the model on every run. ``remap``
    re-selects LLM-mapped TTPs (never T-code ones, which are exact). Ordering
    by id makes the cap deterministic rather than whatever the store yields.
    """
    exclude = (
        "(t)-[:MAPS_TO {method: 'tcode'}]->(:AttackTechnique)" if remap
        else "(t)-[:MAPS_TO]->(:AttackTechnique)"
    )
    with driver.session() as session:
        return session.run(
            f"""
            MATCH (t:TTP {{project_id: $pid}})
            WHERE NOT {exclude}
            RETURN t.id AS id, coalesce(t.name, '') AS name,
                   coalesce(t.description, '') AS description
            ORDER BY t.id
            LIMIT $limit
            """,
            pid=project_id, limit=limit,
        ).data()


def _prune_llm_mappings(driver: Driver, ttp_id: str, keep: list[str]) -> int:
    """Delete this TTP's ``method:"llm"`` MAPS_TO edges to techniques not in ``keep``.

    Called only when the model gave a readable answer on a re-map: an edge it no
    longer confirms is stale. T-code edges are never touched.
    """
    with driver.session() as session:
        rec = session.run(
            """
            MATCH (t:TTP {id: $ttp_id})-[r:MAPS_TO {method: 'llm'}]->(tech:AttackTechnique)
            WHERE NOT tech.attack_id IN $keep
            DELETE r
            RETURN count(r) AS removed
            """,
            ttp_id=ttp_id, keep=keep,
        ).single()
        return int(rec["removed"]) if rec else 0


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


def _parse_matches(content: str) -> list[dict] | None:
    """Read the confirmation reply into matches, or ``None`` if it cannot be read.

    The skill asks for bare JSON; models add a lead-in sentence, a fence, bold,
    a list marker or a table around it. ``llm_output.json_object`` finds the
    object wherever it sits. ``None`` (no object, or no ``matches`` list in it)
    means "unparsed"; ``[]`` means the model read the candidates and confirmed
    none. Those are different findings and are counted separately.
    """
    parsed = json_object(content or "")
    if not parsed:  # json_object returns {} when nothing parses
        return None
    raw = parsed.get("matches")
    if not isinstance(raw, list):
        return None
    out: list[dict] = []
    for m in raw:
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
    """Ask the LLM which candidates apply.

    Returns the matches, or ``None`` when the reply could not be read. A failed
    call raises ``LLMUnavailable`` — an outage is not a rejection.
    """
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
    except Exception as exc:
        logger.warning("ATT&CK mapping LLM call failed", exc_info=True)
        record_degraded("attack_mapping", "llm_unavailable", detail=type(exc).__name__)
        raise LLMUnavailable("ATT&CK mapping LLM call failed") from exc
    return _parse_matches(getattr(result, "content", "") or "")


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

async def map_project_ttps(
    session: AsyncSession,
    driver: Driver,
    project_id: str,
    *,
    embedding_provider: EmbeddingProvider | None = None,
    remap: bool = False,
) -> dict:
    """RAG-map a project's unmapped TTPs to ATT&CK techniques.

    ``remap`` also re-examines TTPs the LLM mapped before; where the model now
    gives a readable answer that no longer confirms an earlier ``llm`` edge,
    that edge is removed and counted in ``stale_removed``.

    Returns ``{"mapped": int, "skipped": int, "skip_reasons": {reason: count}}``.
    A TTP counts as ``mapped`` when at least one confirmed match at/above the
    confidence floor is written. Every skipped TTP is attributed to one reason:

    * ``no_candidates`` — retrieval found no nearby technique;
    * ``rejected`` — the model read the candidates and confirmed none at/above
      the floor;
    * ``unparsed`` — the model's reply could not be read (not a rejection);
    * ``embedding_unavailable`` / ``candidate_retrieval_failed`` /
      ``technique_catalogue_not_embedded`` — the batch could not run; these
      also set ``reason`` and ``detail`` on the result.

    An unreachable LLM raises ``LLMUnavailable`` rather than degrading to skips
    (contract 14): an outage must read as an error, not as zero mappings.
    """
    # Cap the batch — /attack/map is analyst-triggerable and each TTP costs an
    # embedding + LLM call; an unbounded project TTP set would be an open-ended
    # cost/latency/memory sink. Over-cap TTPs are simply left for a later run.
    cap = int(getattr(settings, "attack_mapping_max_ttps", 200) or 200)
    ttps = await asyncio.to_thread(_fetch_unresolved_ttps, driver, project_id, cap, remap)
    remap_fields = {"stale_removed": 0} if remap else {}
    if not ttps:
        return {"mapped": 0, "skipped": 0, "skip_reasons": {}, **remap_fields}

    def _batch_skipped(reason: str, detail: str) -> dict:
        # One degraded outcome per TTP the batch could not attempt, as `skipped`
        # counts them. An unembedded catalogue is setup, not degradation.
        if reason != "technique_catalogue_not_embedded":
            for _ in ttps:
                record_degraded("attack_mapping", reason)
        return {
            "mapped": 0,
            "skipped": len(ttps),
            "skip_reasons": {reason: len(ttps)},
            "reason": reason,
            "detail": detail,
            **remap_fields,
        }

    # Embedding provider — the whole batch cannot run without it.
    if embedding_provider is None:
        try:
            embedding_provider = get_embedding_provider()
        except Exception:
            logger.warning("No embedding provider for ATT&CK mapping", exc_info=True)
            return _batch_skipped("embedding_unavailable", "No embedding provider is configured or reachable.")

    texts = [_ttp_text(t) for t in ttps]
    vectors: list[list[float]] = []
    try:
        for i in range(0, len(texts), _EMBED_BATCH_SIZE):
            result = await embedding_provider.embed(texts[i : i + _EMBED_BATCH_SIZE], input_type="search_query")
            vectors.extend(result.embeddings)
    except Exception:
        logger.warning("Embedding TTP text failed for ATT&CK mapping", exc_info=True)
        return _batch_skipped("embedding_unavailable", "The embedding provider returned an error.")
    if len(vectors) != len(ttps):
        return _batch_skipped("embedding_unavailable", "The embedding provider returned too few vectors.")

    # LLM provider (extraction/collection route so bulk mapping won't drain a
    # rate-limited cloud key) + the confirmation skill's system prompt.
    try:
        llm_provider = await _get_extraction_provider()
    except Exception as exc:
        logger.warning("No LLM provider for ATT&CK mapping", exc_info=True)
        record_degraded("attack_mapping", "llm_unavailable", detail=type(exc).__name__)
        raise LLMUnavailable("no LLM provider for ATT&CK mapping") from exc
    if llm_provider is None:
        record_degraded("attack_mapping", "llm_unavailable", detail="no provider")
        raise LLMUnavailable("no LLM provider for ATT&CK mapping")
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
        return _batch_skipped(
            "technique_catalogue_not_embedded",
            "Run POST /api/attack/embed to embed the ATT&CK catalogue before mapping.",
        )

    mapped = 0
    stale_removed = 0
    skip_reasons: Counter[str] = Counter()
    for index, (ttp, vec) in enumerate(zip(ttps, vectors)):
        try:
            candidates = await _retrieve_candidates(session, vec, top_k)
        except Exception:
            # A real pgvector error (e.g. embedding dim != the table's Vector column)
            # must not 500 the endpoint — the rest of the batch is reported as
            # not attempted, with the reason.
            logger.warning("pgvector candidate retrieval failed for ATT&CK mapping", exc_info=True)
            skip_reasons["candidate_retrieval_failed"] += len(ttps) - index
            for _ in range(len(ttps) - index):
                record_degraded("attack_mapping", "candidate_retrieval_failed")
            break
        if not candidates:
            skip_reasons["no_candidates"] += 1
            continue

        matches = await _confirm_matches(llm_provider, skill_system, _ttp_text(ttp), candidates)
        if matches is None:  # the reply could not be read — not a rejection
            skip_reasons["unparsed"] += 1
            record_degraded("attack_mapping", "unparsed")
            continue

        candidate_ids = {c["technique_id"] for c in candidates}
        confirmed: list[str] = []
        for m in matches:
            if m["technique_id"] in candidate_ids and m["confidence"] >= threshold:
                if await asyncio.to_thread(
                    _merge_mapping, driver, ttp["id"], m["technique_id"], m["confidence"], m["rationale"]
                ):
                    confirmed.append(m["technique_id"])
        if remap:
            # A readable answer that no longer confirms an earlier llm edge
            # makes that edge stale (a rejection removes them all).
            stale_removed += await asyncio.to_thread(_prune_llm_mappings, driver, ttp["id"], confirmed)
        if confirmed:
            mapped += 1
        else:
            skip_reasons["rejected"] += 1

    result = {"mapped": mapped, "skipped": sum(skip_reasons.values()), "skip_reasons": dict(skip_reasons)}
    if remap:
        result["stale_removed"] = stale_removed
    if skip_reasons.get("candidate_retrieval_failed"):
        result["reason"] = "candidate_retrieval_failed"
        result["detail"] = "Technique candidate retrieval failed; the embedding width may not match the index."
    return result
