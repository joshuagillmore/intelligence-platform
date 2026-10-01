"""PIR → collection plan: refine the requirement, split the refinement, and
generate the plan's sources (``/collection-plans/from-pir``).
"""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.api.routes.collection_plans.plans import _plan_to_dict
from intel_platform.connectors.base import describe_collection_capabilities
from intel_platform.db.engine import get_db
from intel_platform.db.models import CollectionPlan, CollectionSource, PlanStatus
from intel_platform.services.collection_planner import parse_plan_sources
from intel_platform.services.llm_output import normalise_line
from intel_platform.services.pir_judge import extract_eeis

logger = logging.getLogger(__name__)

# Mounted by the package router, which carries the API-key dependency.
router = APIRouter()


def refinement_system_prompt() -> str:
    """System prompt for PIR refinement, framed by the active persona.

    The persona reaches the decomposition, not just the prose. Which elements a
    requirement is split into decides what is collected against it, so a cyber
    analyst and a maritime analyst should not break the same question into the
    same elements. Personas previously reached nothing here at all.

    Built as a function rather than inline so the framing is testable without
    driving the whole from-pir route.
    """
    from intel_platform.api.routes.personas import active_persona_brief

    brief = active_persona_brief()
    return (
        (brief + "\n\n" if brief else "")
        + "You are an intelligence analyst. Given a PIR:\n"
        "1. ASSESS specificity, measurability, and time-bounds\n"
        "2. IDENTIFY hidden assumptions\n"
        "3. BREAK DOWN into 3-5 Essential Elements of Information (EEIs).\n"
        "   Each EEI must be answerable independently and must not overlap "
        "another: two elements that ask the same thing in different words "
        "cannot be judged apart, and the second is then scored against "
        "whatever evidence the first did not use. Observed: 'types of "
        "anti-ship missiles employed' and 'weapon systems used, including "
        "capabilities and ranges' are one element, not two.\n"
        "4. PROPOSE a refined, more actionable PIR\n"
        "Return the refined PIR on the first line, then your analysis."
    )


# The label the requirement hides behind. "Refined PIR" is the form the prompt
# asks for; models also answer "Priority Intelligence Requirement (PIR)",
# "Proposed PIR", "Revised requirement", "4. Proposed Refined PIR" as a numbered
# heading, or a table row. Lines are normalised first (`normalise_line`), so
# emphasis, blockquotes, headings and list numbering are already gone and the
# pattern only has to describe the words.
_PIR_NOUN = r"(?:priority\s+intelligence\s+requirement|pir)(?:\s*\(\s*pir\s*\))?"
_QUALIFIER = r"(?:proposed|revised|refined|improved|updated|final|rewritten|new)"
_PIR_LABEL = re.compile(
    rf"^(?:(?:{_QUALIFIER}[\s,]+)+(?:{_PIR_NOUN}|requirement|version)|{_PIR_NOUN})"
    r"\s*(?:[:\-–—|]\s*(?P<body>.*))?$",
    re.IGNORECASE,
)

# The prompt's own section names. A reply that opens on one of these is
# analysis, not a requirement: "### 1. Assessment" was once stored as the PIR
# and then drove source resolution and the judge. Matched against the whole
# normalised line, so a requirement that merely begins "Identify …" survives —
# only the prompt's step text ("IDENTIFY hidden assumptions") is a section.
_SECTION_HEADING = re.compile(
    r"^(?:step\s*\d+\s*[:.\-]?\s*)?(?:"
    r"assess(?:ment)?(?:\s+of\s+(?:the\s+)?(?:original\s+)?(?:pir|requirement))?"
    r"|assess\s+specificity\b.*"
    r"|specificity(?:\s*,?\s*(?:and\s+)?(?:measurability|time[-\s]?bound(?:s|edness)?))*"
    r"|(?:identify\s+)?hidden\s+assumptions?(?:\s*\.\.\.)?|identify\s+hidden\s+assumptions\b.*"
    r"|break\s*down\b.*|breakdown"
    r"|(?:\d+\s*[-–]\s*\d+\s+)?essential\s+elements(?:\s+of\s+information)?(?:\s*\(\s*eeis?\s*\))?"
    r"|eeis?|propose\s+a\s+refined\b.*"
    r"|analysis|critique|rationale|summary|overview|recommendations?|assumptions?"
    r")\s*[:.]?$",
    re.IGNORECASE,
)

# A line introducing what follows rather than stating it.
_PREAMBLE = re.compile(
    r"^(?:here(?:'s|\s+is|\s+are)|below\s+is|sure|certainly|of\s+course|okay|ok\b|great"
    r"|i(?:'ve|\s+have|'ll|\s+will)|let\s+me|the\s+following)\b",
    re.IGNORECASE,
)


def _clean_candidate(text: str) -> str:
    """A normalised line with the quoting a model puts round a requirement removed."""
    return (text or "").strip().strip('"“”').strip("*_ |").strip()


def _candidate_kind(text: str) -> str:
    """Whether a cleaned line is the requirement: "ok", "skip" or "stop".

    "skip" is a line that introduces what follows (a preamble, anything ending
    in a colon) — keep looking. "stop" is one of the prompt's own sections: the
    reply has moved on to analysis, and taking the next line would store the
    model's critique as the requirement.
    """
    if not re.search(r"[^\W\d_]{2,}", text):
        return "skip"   # markdown punctuation, a rule, a bare number
    if _SECTION_HEADING.match(text):
        return "stop"
    if text.endswith(":") or _PREAMBLE.match(text):
        return "skip"
    return "ok"


def _split_refinement_parsed(content: str, fallback: str) -> tuple[str, str, bool]:
    """Split an LLM refinement into (refined PIR, analysis, parsed).

    `parsed` is False when nothing in the reply could be taken as the
    requirement and `fallback` was returned in its place. The caller must not
    store that fallback as a refinement: it is the original text wearing the
    refinement's name, and once written it was never corrected.

    The prompt asks for the refined PIR on the first line. Replies routinely
    arrive as a markdown-only line, then a blockquoted label, then the
    requirement in italics, then a critique of the rewrite — so the label is
    searched for across the whole reply before falling back to the first line
    that is neither a preamble nor one of the prompt's section headings.
    """
    text = (content or "").strip()
    if not text:
        return fallback, "", False

    lines = text.split("\n")

    def _requirement_from(start: int) -> tuple[str, str, bool]:
        for j in range(start, len(lines)):
            cleaned = _clean_candidate(normalise_line(lines[j]))
            kind = _candidate_kind(cleaned)
            if kind == "ok":
                return cleaned, "\n".join(lines[j + 1:]).strip(), True
            if kind == "stop":
                break
        return fallback, "", False

    # Pass 1: the labelled requirement, wherever it sits in the reply.
    for i, raw in enumerate(lines):
        label = _PIR_LABEL.match(normalise_line(raw))
        if not label:
            continue
        body = _clean_candidate(label.group("body") or "")
        kind = _candidate_kind(body) if body else "skip"
        if kind == "ok":
            return body, "\n".join(lines[i + 1:]).strip(), True
        if kind == "stop":
            return fallback, "", False
        return _requirement_from(i + 1)

    # Pass 2: no label anywhere — the first line that states something.
    return _requirement_from(0)


def _split_refinement(content: str, fallback: str) -> tuple[str, str]:
    """(refined PIR, analysis) — `_split_refinement_parsed` without the flag."""
    refined, analysis, _parsed = _split_refinement_parsed(content, fallback)
    return refined, analysis


class SubmitPIRRequest(BaseModel):
    """Submit a PIR to create a full collection plan via LLM."""
    project_id: str
    pir: str = ""
    # Run against an already-persisted requirement. Omit to have one created (or
    # an identical live one reused) from `pir` — either way the plan ends up
    # linked to a PIR the project hub can show.
    pir_id: str | None = None
    extraction_mode: str = "hybrid"
    created_by: str = "analyst"


# ---------------------------------------------------------------------------
# PIR → Plan (LLM-driven collection plan generation)
# ---------------------------------------------------------------------------

@router.post("/collection-plans/from-pir")
async def create_plan_from_pir(req: SubmitPIRRequest, db: AsyncSession = Depends(get_db)):
    """Submit a PIR → LLM refines it, generates a collection plan with sources.

    Flow: PIR → LLM refinement → LLM plan generation → create Plan + Sources → DRAFT
    Returns the plan ready for user approval.

    The PIR itself is persisted first (or resolved from `pir_id`), so the plan is
    always anchored to a requirement the project hub can list and track.
    """
    # Local import: the PIR routes import this package's _parse_uuid.
    from intel_platform.api.routes.pirs import get_or_create_pir

    # Step 0: Anchor the run on a first-class PIR before any LLM work, so an
    # unknown pir_id fails fast and the requirement survives an LLM outage.
    pir_record = await get_or_create_pir(
        db, req.project_id, req.pir, pir_id=req.pir_id, created_by=req.created_by,
    )
    pir_text = (req.pir or "").strip() or (pir_record.text if pir_record else "")
    if not pir_text:
        raise HTTPException(400, "A PIR (text or pir_id) is required")

    # Step 1: Get the LLM provider
    provider = None
    llm_available = False
    llm_status = ""
    try:
        # Use the collection provider (local Ollama when configured) so autonomous
        # plan/source generation doesn't hit a rate-limited cloud key — matching the
        # execute path. Falls back to the default provider when no collection provider.
        from intel_platform.api.routes.llm import _get_collection_provider
        provider = await _get_collection_provider()
        if provider:
            llm_available = True
            llm_status = f"Using {provider.name()}"
    except Exception as e:
        logger.warning("Failed to get LLM provider for PIR plan generation: %s", e)
        llm_status = f"LLM unavailable: {e}"

    refined_pir = pir_text
    refined_ok = False
    plan_description = ""
    # Why a plan came back thin, in the plan's own words rather than the UI's
    # guess. Without this the analyst was shown "The LLM may have been
    # rate-limited" for any failure at all, including ones that were nothing of
    # the sort.
    failures: list[str] = []

    if provider:
        # Step 2: Refine the PIR
        try:
            from intel_platform.llm.skills.loader import SkillsLoader
            loader = SkillsLoader()

            from intel_platform.api.routes.personas import active_persona_temperature

            refine_result = await provider.generate(
                messages=[{"role": "user", "content": f"Refine this Priority Intelligence Requirement (PIR):\n\n{pir_text}"}],
                system=refinement_system_prompt(),
                temperature=active_persona_temperature(0.3),
            )
            refined_pir, plan_description, refined_ok = _split_refinement_parsed(
                refine_result.content, pir_text,
            )
            if not refined_ok:
                failures.append("refinement returned no usable requirement")
                # No requirement could be read, but the reply is still the
                # model's analysis — keep it so the EEIs it lists are captured.
                plan_description = (refine_result.content or "").strip()
        except Exception as e:
            # `%s` alone loses everything when the exception carries no message —
            # a timeout stringifies to "" and the log line read literally
            # "PIR refinement failed: ", which is undiagnosable. Record the type
            # and the traceback, and keep the reason for the response.
            logger.warning("PIR refinement failed: %s: %s", type(e).__name__, e, exc_info=True)
            failures.append(f"refinement failed ({type(e).__name__})")

        # Step 3: Generate collection plan with sources
        try:
            system = loader.get_system_prompt("collection_planning", include_foundation=True) or ""
            plan_result = await provider.generate(
                messages=[{"role": "user", "content": (
                    f"Create a collection plan for this PIR:\n\n{refined_pir}\n\n"
                    f"Original requirement, for domain context:\n{pir_text}\n\n"
                    "The sources MUST match the subject matter of that requirement. A maritime,"
                    " economic, political or humanitarian PIR needs maritime, economic, political"
                    " or humanitarian sources — do not default to cyber-threat sources unless the"
                    " requirement is actually about cyber.\n\n"
                    "For each source, output a numbered list item in EXACTLY this format:\n"
                    'N. [SOURCE_TYPE] Description of what to collect\n'
                    '   CONFIG: {"key": "value"}\n\n'
                    "These are the ONLY collection methods this system has. "
                    "Propose a source only if one of them can actually reach it:\n"
                    f"{describe_collection_capabilities()}\n\n"
                    "A plan is judged on what it collects, not on how complete it "
                    "looks. Every source you list that this system cannot reach is a "
                    "row the analyst has to work out is dead. Prefer four sources that "
                    "will return data to seven that read well.\n\n"
                    "Include 3-7 concrete, actionable sources with REAL URLs.\n"
                    "Focus on publicly accessible sources relevant to the PIR.\n"
                    "Examples of the FORMAT only — pick sources for the actual subject, not these:\n"
                    '1. [web_scrape] UKMTO maritime incident advisories\n'
                    '   CONFIG: {"url": "https://www.ukmto.org/incidents"}\n'
                    '2. [rss_feed] Reuters world news feed\n'
                    '   CONFIG: {"feed_url": "https://feeds.reuters.com/reuters/worldNews"}'
                )}],
                system=system,
                temperature=0.4,
            )
            plan_text = plan_result.content
        except Exception as e:
            logger.warning("Plan generation failed: %s: %s", type(e).__name__, e, exc_info=True)
            failures.append(f"source generation failed ({type(e).__name__})")
            plan_text = ""
    else:
        plan_text = ""

    # Step 4: Create the plan, linked to the requirement it serves
    stored = (pir_record.refined_text or "").strip() if pir_record else ""
    if pir_record and refined_ok and (not stored or stored == (pir_record.text or "").strip()):
        # Carry the LLM's refinement back onto the requirement so the analyst
        # does not have to re-derive it on the next run — only when there is a
        # refinement to carry. This used to run on failure too, storing the
        # original text as its own refinement, and the "already refined" guard
        # then meant no later success could ever correct it. A stored value
        # equal to the original text is exactly that fallback, so a success now
        # replaces it; any other stored wording is someone's refinement and is
        # kept.
        pir_record.refined_text = refined_pir

    if pir_record and not pir_record.eeis:
        # The refinement is asked to decompose the requirement into EEIs, and
        # capturing them is what makes satisfaction measurable later
        # (`/pirs/{id}/assess`) and what the collection loop re-tasks against.
        #
        # Search the whole refinement, not just the analysis half: a model that
        # puts the EEI list above the split point would otherwise have it
        # discarded, and the requirement would look undecomposed.
        captured = extract_eeis(plan_description) or extract_eeis(refined_pir)
        if captured:
            pir_record.eeis = captured
        else:
            # Observed live: the model returned a refined PIR plus a "Why this
            # version works" critique and no EEI section at all, while still
            # referring to "the EEIs". Every downstream capability that needs
            # them — assessment, the requirement loop, the gap count — then does
            # nothing, and reported success while doing it.
            logger.warning(
                "No EEIs captured for PIR %s; the refinement produced no "
                "Essential Elements section", getattr(pir_record, "id", "?"),
            )
            failures.append("no essential elements were extracted from the refinement")

    plan = CollectionPlan(
        project_id=req.project_id,
        name=f"PIR: {pir_text[:80]}{'...' if len(pir_text) > 80 else ''}",
        description=plan_description,
        requirement=pir_text,
        pir=pir_text,
        pir_id=pir_record.id if pir_record else None,
        refined_pir=refined_pir,
        status=PlanStatus.DRAFT,
        routing_rules={
            "extract_entities": True,
            "store_documents": True,
            "extraction_mode": req.extraction_mode,
        },
        created_by=req.created_by,
    )
    db.add(plan)
    await db.flush()

    # Step 5: Parse LLM plan text into sources with configs
    sources_created = []
    if plan_text:
        parsed_sources = parse_plan_sources(plan_text)
        for ps in parsed_sources:
            source = CollectionSource(
                plan_id=plan.id,
                name=ps["name"],
                source_type=ps["source_type"],
                config=ps.get("config", {}),
                enabled=True,
            )
            db.add(source)
            sources_created.append(source)

    await db.commit()
    await db.refresh(plan)

    result = _plan_to_dict(plan)
    result["llm_plan_text"] = plan_text
    result["llm_available"] = llm_available
    result["llm_status"] = llm_status
    # What went wrong, if anything, in the plan's own words. A caller seeing a
    # plan with no sources previously had to guess why, and the UI guessed
    # "the LLM may have been rate-limited" for every cause including the ones
    # that were nothing of the sort.
    result["generation_failures"] = failures
    result["eeis_captured"] = len(getattr(pir_record, "eeis", None) or []) if pir_record else 0
    if not llm_available:
        result["llm_requirements"] = {
            "message": "An LLM provider is required for autonomous plan generation. "
                       "Without an LLM, plans must be created manually with sources and URLs.",
            "supported_providers": ["anthropic", "openai", "cohere", "ollama"],
            "configuration": "Set one of: ANTHROPIC_API_KEY, OPENAI_API_KEY, COHERE_API_KEY "
                             "in .env, or configure Ollama at OLLAMA_BASE_URL.",
            "minimum_capability": "The LLM must support structured output generation "
                                  "(tool calling or JSON mode). Recommended: Claude Sonnet 4, "
                                  "GPT-4o, Command A, or Qwen 3 30B+ via Ollama.",
        }
    return result
