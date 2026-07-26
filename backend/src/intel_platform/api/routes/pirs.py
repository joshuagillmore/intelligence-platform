"""Priority Intelligence Requirement (PIR) routes — the requirements spine.

A PIR is what a project is trying to answer. It is persisted per project and
carries the chain forward: every collection plan raised against it stores its
`pir_id`, so a PIR reports back the plans it drove and what they acquired.

Lives in Postgres alongside `collection_plans` (see `db/models.Pir`): the plan is
the thing a PIR drives, and keeping both in one store makes PIR → plan a join
rather than a cross-datastore lookup.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.api.routes.collection_plans import _parse_uuid
from intel_platform.db.engine import get_db
from intel_platform.db.models import (
    PIR_PRIORITIES,
    PIR_STATUSES,
    CollectionPlan,
    Pir,
    PirStatus,
)
from intel_platform.models.requests import CreatePirRequest, UpdatePirRequest
from intel_platform.models.responses import PirPlanLink, PirResponse

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])

TITLE_MAX = 256


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_status(status: str) -> str:
    if status not in PIR_STATUSES:
        raise HTTPException(400, f"Invalid status: {status!r}. Expected one of {list(PIR_STATUSES)}")
    return status


def _validate_priority(priority: str) -> str:
    if priority not in PIR_PRIORITIES:
        raise HTTPException(400, f"Invalid priority: {priority!r}. Expected one of {list(PIR_PRIORITIES)}")
    return priority


def derive_title(text: str) -> str:
    """A short label for a PIR that the analyst did not title."""
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= 120:
        return cleaned
    return cleaned[:117].rstrip() + "..."


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _plan_link(plan: CollectionPlan) -> PirPlanLink:
    sources = plan.sources or []
    return PirPlanLink(
        id=str(plan.id),
        name=plan.name,
        status=plan.status,
        source_count=len(sources),
        records_acquired=sum(s.total_records_acquired or 0 for s in sources),
        created_at=plan.created_at.isoformat() if plan.created_at else "",
    )


def _pir_to_response(pir: Pir, plans: list[CollectionPlan] | None = None) -> PirResponse:
    links = [_plan_link(p) for p in (plans or [])]
    return PirResponse(
        id=str(pir.id),
        project_id=pir.project_id,
        title=pir.title or "",
        text=pir.text or "",
        refined_text=pir.refined_text or "",
        eeis=list(pir.eeis or []),
        priority=pir.priority or "medium",
        status=pir.status or PirStatus.OPEN,
        created_by=pir.created_by or "",
        created_at=pir.created_at.isoformat() if pir.created_at else "",
        updated_at=pir.updated_at.isoformat() if pir.updated_at else "",
        plan_count=len(links),
        plans=links,
    )


async def _plans_by_pir(db: AsyncSession, pir_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[CollectionPlan]]:
    """Load the collection plans raised against each PIR (one query, no N+1)."""
    if not pir_ids:
        return {}
    stmt = (
        select(CollectionPlan)
        .where(CollectionPlan.pir_id.in_(pir_ids))
        .order_by(CollectionPlan.created_at.desc())
    )
    result = await db.execute(stmt)
    grouped: dict[uuid.UUID, list[CollectionPlan]] = {}
    for plan in result.scalars().all():
        grouped.setdefault(plan.pir_id, []).append(plan)
    return grouped


# ---------------------------------------------------------------------------
# Shared helper — used by /collection-plans/from-pir so a plan generated from
# free text still lands on a persisted requirement instead of vanishing.
# ---------------------------------------------------------------------------

async def get_or_create_pir(
    db: AsyncSession,
    project_id: str,
    text: str,
    pir_id: str | None = None,
    created_by: str = "analyst",
) -> Pir | None:
    """Resolve the PIR a collection run belongs to.

    - `pir_id` given → that PIR (404 if unknown, 400 if it belongs elsewhere).
    - otherwise → reuse an existing live PIR in the project with the same text,
      or create one. Reuse keeps repeat runs of the same question on one
      requirement instead of spawning a duplicate per run.
    Returns None only when there is nothing to anchor (no id and no text).
    """
    if pir_id:
        pir = await db.get(Pir, _parse_uuid(pir_id, "pir_id"))
        if not pir:
            raise HTTPException(404, "PIR not found")
        if pir.project_id != project_id:
            raise HTTPException(400, "PIR belongs to a different project")
        return pir

    cleaned = (text or "").strip()
    if not cleaned:
        return None

    stmt = (
        select(Pir)
        .where(
            Pir.project_id == project_id,
            Pir.text == cleaned,
            Pir.status != PirStatus.ARCHIVED,
        )
        .order_by(Pir.created_at.desc())
        .limit(1)
    )
    existing = (await db.execute(stmt)).scalars().first()
    if existing:
        return existing

    pir = Pir(
        project_id=project_id,
        title=derive_title(cleaned),
        text=cleaned,
        status=PirStatus.OPEN,
        created_by=created_by,
    )
    db.add(pir)
    await db.flush()
    return pir


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.post("/pirs", response_model=PirResponse)
async def create_pir(req: CreatePirRequest, db: AsyncSession = Depends(get_db)) -> PirResponse:
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(400, "PIR text is required")

    pir = Pir(
        project_id=req.project_id,
        title=(req.title or "").strip()[:TITLE_MAX] or derive_title(text),
        text=text,
        refined_text=(req.refined_text or "").strip(),
        eeis=[e for e in (req.eeis or []) if e and e.strip()],
        priority=_validate_priority(req.priority),
        status=_validate_status(req.status),
        created_by=req.created_by,
    )
    db.add(pir)
    await db.commit()
    await db.refresh(pir)
    return _pir_to_response(pir)


@router.get("/pirs", response_model=list[PirResponse])
async def list_pirs(
    project_id: str,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[PirResponse]:
    """List a project's requirements, newest first, each with the plans it drove."""
    stmt = select(Pir).where(Pir.project_id == project_id).order_by(Pir.created_at.desc())
    if status:
        stmt = stmt.where(Pir.status == _validate_status(status))
    pirs = (await db.execute(stmt)).scalars().all()

    grouped = await _plans_by_pir(db, [p.id for p in pirs])
    return [_pir_to_response(p, grouped.get(p.id, [])) for p in pirs]


@router.get("/pirs/{pir_id}", response_model=PirResponse)
async def get_pir(pir_id: str, db: AsyncSession = Depends(get_db)) -> PirResponse:
    pir = await db.get(Pir, _parse_uuid(pir_id, "pir_id"))
    if not pir:
        raise HTTPException(404, "PIR not found")
    grouped = await _plans_by_pir(db, [pir.id])
    return _pir_to_response(pir, grouped.get(pir.id, []))


@router.put("/pirs/{pir_id}", response_model=PirResponse)
async def update_pir(
    pir_id: str, req: UpdatePirRequest, db: AsyncSession = Depends(get_db)
) -> PirResponse:
    pir = await db.get(Pir, _parse_uuid(pir_id, "pir_id"))
    if not pir:
        raise HTTPException(404, "PIR not found")

    if req.status is not None:
        pir.status = _validate_status(req.status)
    if req.priority is not None:
        pir.priority = _validate_priority(req.priority)
    if req.title is not None:
        pir.title = req.title.strip()[:TITLE_MAX]
    if req.text is not None:
        text = req.text.strip()
        if not text:
            raise HTTPException(400, "PIR text cannot be empty")
        pir.text = text
        if not pir.title:
            pir.title = derive_title(text)
    if req.refined_text is not None:
        pir.refined_text = req.refined_text.strip()
    if req.eeis is not None:
        pir.eeis = [e for e in req.eeis if e and e.strip()]

    pir.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(pir)
    grouped = await _plans_by_pir(db, [pir.id])
    return _pir_to_response(pir, grouped.get(pir.id, []))


@router.delete("/pirs/{pir_id}")
async def delete_pir(pir_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a PIR. Plans raised against it survive, unlinked — the collected
    intelligence outlives the question that prompted it."""
    parsed = _parse_uuid(pir_id, "pir_id")
    pir = await db.get(Pir, parsed)
    if not pir:
        raise HTTPException(404, "PIR not found")

    await db.execute(
        update(CollectionPlan).where(CollectionPlan.pir_id == parsed).values(pir_id=None)
    )
    await db.delete(pir)
    await db.commit()
    return {"deleted": True, "id": pir_id}


# ---------------------------------------------------------------------------
# Satisfaction assessment — does the collected intelligence answer the PIR?
# ---------------------------------------------------------------------------

_EEI_LINE = re.compile(
    r"^\s*(?:[-*•]|\d+[.)]|EEI\s*\d*\s*[:.\-])\s*(?P<body>.{8,300}?)\s*$",
    re.IGNORECASE,
)

_EEI_HEADING = re.compile(r"essential elements|\bEEIs?\b", re.IGNORECASE)

# Crawled pages yield large numbers of URLs, bare domains and the Document nodes
# themselves. They are legitimate graph content but carry almost no answer to a
# requirement, and they crowd the substantive entities out of the judge's window.
_LOW_SIGNAL_TYPES = frozenset({"URL", "Domain", "Document", "Topic", "Report", "Collection"})

# Models double-label: "3. EEI 3: Specific devices…". The outer marker is
# consumed by _EEI_LINE, so strip the inner one too or it lands in the criterion.
_EEI_PREFIX = re.compile(r"^EEI\s*\d*\s*[:.\-]\s*", re.IGNORECASE)

# Refinements narrate their own work ("The refined version provides a clearer
# focus on…"). Captured as a criterion it can never be satisfied by collection,
# so it would sit in unmet_criteria forever and block SATISFIED.
_EEI_META = re.compile(
    r"\b(?:refined|revised|original|updated)\s+"
    r"(?:pir|version|requirement|statement|question|wording)\b",
    re.IGNORECASE,
)


def _clean_eei(raw: str) -> str:
    """Normalise one captured line into a usable collection criterion.

    Observed live, in order of appearance: an inner `EEI 3:` label surviving the
    outer marker, `**bold**` runs left mid-string by "**Initial Access
    Vectors:** Determine…", and section labels like "Refined PIR:" picked up as
    if they were criteria. A criterion that is only a label cannot be judged,
    so it is dropped rather than assessed and reported as unmet.
    """
    body = _EEI_PREFIX.sub("", raw.strip().strip("*_ ")).replace("**", "").strip("*_ ").strip()
    # A real criterion states something; a trailing colon means this was a
    # heading introducing the content below it.
    if not body or body.endswith(":"):
        return ""
    # Commentary about the refinement is not something collection can answer.
    if _EEI_META.search(body):
        return ""
    return body


def extract_eeis(analysis: str, limit: int = 8) -> list[str]:
    """Pull Essential Elements of Information out of an LLM refinement.

    The refinement prompt already asks the model to break the requirement into
    EEIs, so they exist in the analysis prose — they were simply never captured
    onto the PIR, which left `Pir.eeis` empty and satisfaction unmeasurable.
    """
    if not analysis:
        return []
    eeis: list[str] = []
    in_section = False
    for raw in analysis.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if _EEI_HEADING.search(line) and len(line) < 120:
            in_section = True
            # A heading may carry the first EEI inline after its colon.
            tail = _clean_eei(line.split(":", 1)[1]) if ":" in line else ""
            if len(tail) >= 8:
                eeis.append(tail)
            continue
        if not in_section:
            continue
        match = _EEI_LINE.match(line)
        if match:
            body = _clean_eei(match.group("body"))
            if body and body.lower() not in {e.lower() for e in eeis}:
                eeis.append(body)
        elif line.startswith("#") or line.startswith("**"):
            # A new heading ends the EEI list.
            in_section = False
        if len(eeis) >= limit:
            break
    return eeis[:limit]


# Models emit the verdict block inconsistently: some print "EEI_ASSESSMENT:" once
# as a header, others repeat it on every line, and some wrap the line in bold.
_VERDICT_LINE = re.compile(
    r"^\s*\**\s*(?:EEI_ASSESSMENT\s*:)?\s*\**\s*(?:EEI\s*)?(\d+)\s*\|\s*"
    r"(SATISFIED|PARTIAL|UNMET)\s*\|\s*(.+?)\s*\**\s*$",
    re.IGNORECASE,
)


def parse_verdicts(narrative: str, eeis: list[str]) -> list[dict]:
    """Read the `N | VERDICT | justification` block back out of the model's reply.

    A verdict the parser misses is indistinguishable from an unassessed
    requirement, so this is deliberately permissive about how the line is
    labelled and strict about its three fields.
    """
    out: list[dict] = []
    seen: set[int] = set()
    for line in (narrative or "").split("\n"):
        m = _VERDICT_LINE.match(line.strip())
        if not m:
            continue
        idx = int(m.group(1)) - 1
        if not (0 <= idx < len(eeis)) or idx in seen:
            continue
        seen.add(idx)
        out.append({
            "index": idx,
            "eei": eeis[idx],
            "verdict": m.group(2).upper(),
            "justification": m.group(3).strip().rstrip("*").strip(),
        })
    return out


class AssessPirRequest(BaseModel):
    """Optional inputs for a satisfaction assessment."""

    # The collection budget this PIR was given. Reported back so a PARTIAL
    # result can distinguish "we answered it" from "we ran out of sources".
    source_limit: int | None = Field(default=None, ge=1)


@router.post("/pirs/{pir_id}/assess")
async def assess_pir(
    pir_id: str,
    req: AssessPirRequest | None = None,
    db: AsyncSession = Depends(get_db),
    store=Depends(get_graph_store),
):
    """Judge whether what has been collected answers the PIR.

    Either the requirement is satisfied or collection stopped at its source
    limit — and in that case the analyst needs to know *which* elements are
    still unanswered, rather than being handed a pile of documents and left to
    infer it. Each EEI is judged against the project's own graph, never against
    the model's background knowledge.
    """
    parsed = _parse_uuid(pir_id, "pir_id")
    pir = await db.get(Pir, parsed)
    if not pir:
        raise HTTPException(404, "PIR not found")

    plans = (
        await db.execute(select(CollectionPlan).where(CollectionPlan.pir_id == parsed))
    ).scalars().all()
    sources_used = sum(len(p.sources or []) for p in plans)
    limit = req.source_limit if req else None

    eeis = [e for e in (pir.eeis or []) if e and e.strip()]
    if not eeis:
        # Fall back to the requirement itself, so an un-decomposed PIR is still
        # assessable instead of silently reporting "nothing to check".
        eeis = [pir.refined_text or pir.text]

    entities = store.search_entities(pir.project_id, limit=600)
    by_type: dict[str, int] = {}
    for ent in entities:
        key = ent.get("entity_type", "?")
        by_type[key] = by_type.get(key, 0) + 1

    # `search_entities` orders by name, so a naive head-slice hands the judge an
    # alphabetical sample dominated by crawl furniture — measured on a live run:
    # 400 entities considered, the ThreatActors and Campaigns never shown, and
    # the requirement wrongly reported as having no evidence at all. Rank so the
    # substantive entities are the ones that fit in the window.
    substantive = [e for e in entities if e.get("entity_type") not in _LOW_SIGNAL_TYPES]
    ranked = substantive or entities

    facts: list[str] = []
    seen_facts: set[str] = set()
    for ent in ranked[:150]:
        for rel in store.get_relationships(ent.get("id", ""))[:6]:
            if rel.get("target_name") and rel.get("source_name"):
                line = (
                    f"{rel['source_name']} --{rel.get('rel_type', '?')}--> {rel['target_name']}"
                )
                if rel.get("evidence"):
                    line += f" :: {str(rel['evidence'])[:200]}"
                if line not in seen_facts:
                    seen_facts.add(line)
                    facts.append(line)
        if len(facts) >= 200:
            break

    context = (
        f"Entity types collected: {by_type}\n\n"
        f"Named entities ({min(len(ranked), 200)} of {len(entities)}, "
        "web furniture such as URLs and bare domains omitted):\n"
        + ", ".join(e.get("name", "") for e in ranked[:200])
        + "\n\nAsserted relationships and their evidence:\n"
        + "\n".join(facts[:200])
    )

    assessments: list[dict] = []
    narrative = ""
    model_name = ""
    try:
        from intel_platform.llm.providers import _get_provider

        provider = await _get_provider()
        numbered = "\n".join(f"{i + 1}. {e}" for i, e in enumerate(eeis))
        result = await provider.generate(
            messages=[{"role": "user", "content": (
                f"PRIORITY INTELLIGENCE REQUIREMENT:\n{pir.refined_text or pir.text}\n\n"
                f"ESSENTIAL ELEMENTS OF INFORMATION:\n{numbered}\n\n"
                f"COLLECTED INTELLIGENCE:\n{context}\n\n"
                "Judge each EEI ONLY against the collected intelligence above. Do not use "
                "background knowledge: an element the collection did not answer is unmet, "
                "however well you happen to know the subject.\n\n"
                f"End with a machine-readable block: exactly {len(eeis)} lines, one per EEI, "
                f"numbered 1 to {len(eeis)}, no line omitted even when the verdict is UNMET.\n"
                "EEI_ASSESSMENT:\n"
                "1 | SATISFIED | one-line justification citing the collected evidence\n"
                "2 | UNMET | one-line statement of what is missing"
            )}],
            system=(
                "You are an intelligence collection manager judging whether a requirement "
                "has been answered. You are rigorous about the difference between 'the "
                "collection answered this' and 'this is generally known'. The unmet "
                "elements are the most useful part of your output — they drive the next "
                "collection cycle. Verdicts are SATISFIED, PARTIAL or UNMET."
            ),
            temperature=0.2,
            max_tokens=1600,
        )
        narrative = result.content or ""
        model_name = getattr(result, "model", "") or ""
        assessments = parse_verdicts(narrative, eeis)

        # Models routinely return fewer verdicts than there are elements — one
        # of five on a live DRC run. Those elements are reported UNASSESSED,
        # which is honest but useless to the analyst, so ask once more for just
        # the missing ones rather than leaving the requirement half-judged.
        missing = [i for i in range(len(eeis)) if i not in {a["index"] for a in assessments}]
        if missing and len(missing) < len(eeis):
            retry = await provider.generate(
                messages=[{"role": "user", "content": (
                    f"COLLECTED INTELLIGENCE:\n{context}\n\n"
                    "You did not return a verdict for these elements. Judge each one "
                    "against the collected intelligence above and nothing else:\n"
                    + "\n".join(f"{i + 1}. {eeis[i]}" for i in missing)
                    + "\n\nReturn only these lines, one per element:\n"
                    "N | SATISFIED|PARTIAL|UNMET | one-line justification"
                )}],
                system="You are an intelligence collection manager. Return only the verdict lines.",
                temperature=0.2,
                max_tokens=800,
            )
            extra = [a for a in parse_verdicts(retry.content or "", eeis) if a["index"] in missing]
            if extra:
                assessments.extend(extra)
                narrative += "\n\n[second pass for unjudged elements]\n" + (retry.content or "")
    except Exception:
        logger.warning("PIR assessment failed for %s", pir_id, exc_info=True)

    # An element the model did not return a verdict for has NOT been shown to be
    # answered. Treating silence as success declared a requirement SATISFIED off
    # one verdict out of five, so unjudged elements are made explicit instead.
    # Whether the model returned anything at all — distinct from whether every
    # element got a verdict. A total judging failure must leave the stored status
    # untouched rather than reopening a satisfied requirement.
    any_verdict = bool(assessments)
    judged = {a["index"] for a in assessments}
    for i, eei in enumerate(eeis):
        if i not in judged:
            assessments.append({
                "index": i,
                "eei": eei,
                "verdict": "UNASSESSED",
                "justification": "The judging model returned no verdict for this element.",
            })
    assessments.sort(key=lambda a: a["index"])

    satisfied = [a for a in assessments if a["verdict"] == "SATISFIED"]
    unmet = [a for a in assessments if a["verdict"] != "SATISFIED"]

    if any_verdict and not unmet:
        status = PirStatus.SATISFIED
    elif any(a["verdict"] in ("SATISFIED", "PARTIAL") for a in assessments):
        # A PARTIAL verdict means the collection did answer part of the element.
        # Reporting that as OPEN loses the distinction between "we have something
        # on this" and "we have nothing at all", which is what drives whether the
        # next cycle re-collects or refines.
        status = PirStatus.PARTIAL
    else:
        status = PirStatus.OPEN

    # Only move the stored status when there was a real judgement behind it —
    # a failed LLM call must not silently reopen a satisfied requirement.
    if any_verdict:
        pir.status = status
        pir.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(pir)

    exhausted = bool(limit) and sources_used >= limit
    if not any_verdict:
        recommendation = "Assessment unavailable — the judging model returned no verdicts."
    elif status == PirStatus.SATISFIED:
        recommendation = (
            f"Requirement answered — all {len(eeis)} element(s) satisfied. "
            "No further collection needed."
        )
    elif exhausted:
        recommendation = (
            f"Collection budget exhausted ({sources_used}/{limit} sources) with "
            f"{len(unmet)} element(s) unanswered. Raise a follow-up plan targeting them."
        )
    else:
        recommendation = (
            f"{len(unmet)} element(s) still unanswered and collection budget remains "
            f"({sources_used}/{limit if limit else 'unbounded'} sources) — continue collection."
        )

    return {
        "pir_id": str(pir.id),
        "status": pir.status,
        "eeis_total": len(eeis),
        "eeis_satisfied": len(satisfied),
        "assessments": assessments,
        "unmet_criteria": [
            {"eei": a["eei"], "verdict": a["verdict"], "why": a["justification"]} for a in unmet
        ],
        "entities_considered": len(entities),
        "sources_used": sources_used,
        "source_limit": limit,
        "stopped_on_source_limit": exhausted and status != PirStatus.SATISFIED,
        "recommendation": recommendation,
        "model": model_name,
        "narrative": narrative,
    }
