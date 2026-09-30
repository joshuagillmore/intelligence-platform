"""Collect until the requirement is answered, or until the budget says stop.

The source loop in `agentic.py` works through a fixed list of sources the
planner proposed and then stops, whatever state the requirement is in. Its
`satisfied` verdict grades *a source's own contribution*, not whether an element
of the requirement has been answered, so nothing there can decide to go and look
again.

This adds the missing half. After the planned sources are collected, each
unanswered element is assessed against what was actually gathered; an element
that is still open produces search queries aimed at its gap, those queries are
run, and the resulting pages are collected as new sources. Repeat until every
element is answered, the attempt cap retires the stubborn ones, or the source
budget runs out.

Three separate stopping conditions, each reported as itself:

  * every element satisfied — the requirement is answered;
  * an element retired after `per_element_attempts` — tried and given up on,
    which is not the same as untried;
  * source or pass budget exhausted — stopped short, with elements still open.

An exhausted run is never reported as a satisfied one.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select

from intel_platform.db.models import (
    CollectionActivity,
    CollectionPlan,
    CollectionSource,
    Pir,
    PirRequirement,
)
from intel_platform.services.requirement_assessor import assess_requirement

logger = logging.getLogger(__name__)

# A pass is one sweep over the still-open elements. The cap is a backstop for
# the case where every pass keeps finding pages that do not settle anything.
DEFAULT_MAX_PASSES = 3
# Attempts spent on a single element before it is retired as unmet. Without
# this one unanswerable element consumes every pass and starves the others.
DEFAULT_ATTEMPTS_PER_ELEMENT = 2
# Pages pulled per query. Deliberately small: the loop's value is aiming
# successive queries, not fetching more of the same.
RESULTS_PER_QUERY = 3


@dataclass
class LoopOutcome:
    """What the loop did, in terms the analyst can act on."""

    passes_run: int = 0
    sources_added: int = 0
    satisfied: list[str] = field(default_factory=list)
    retired: list[str] = field(default_factory=list)
    still_open: list[str] = field(default_factory=list)
    stopped_on: str = "nothing_to_do"

    @property
    def answered_everything(self) -> bool:
        return bool(self.satisfied) and not self.retired and not self.still_open


async def sync_requirements(db, pir: Pir) -> list[PirRequirement]:
    """Materialise one state row per EEI, and keep them aligned with the text.

    `Pir.eeis` stays the source of truth for the criteria themselves — every
    existing consumer reads it — so a refinement that rewrites the elements
    rewrites these rows too. An element whose text is unchanged keeps its state;
    changing the wording means it is a different question and its state is reset,
    which is the honest reading.
    """
    eeis = [e for e in (pir.eeis or []) if e and str(e).strip()]
    existing = (await db.execute(
        select(PirRequirement).where(PirRequirement.pir_id == pir.id)
        .order_by(PirRequirement.ordinal)
    )).scalars().all()
    by_ordinal = {r.ordinal: r for r in existing}

    rows: list[PirRequirement] = []
    for index, text in enumerate(eeis):
        text = str(text).strip()
        row = by_ordinal.pop(index, None)
        if row is None:
            row = PirRequirement(
                pir_id=pir.id, project_id=pir.project_id, ordinal=index, text=text,
            )
            db.add(row)
        elif row.text != text:
            row.text = text
            row.status = "pending"
            row.attempts = 0
            row.next_queries = []
            row.assessment_missing = ""
            row.assessment_confidence = ""
        rows.append(row)

    for orphan in by_ordinal.values():  # the PIR now has fewer elements
        await db.delete(orphan)

    await db.flush()
    return rows


async def plan_stop_requested(db, plan_id) -> bool:
    """True when the analyst has paused or archived the plan.

    PAUSED and ARCHIVED were lifecycle flags the loops never read, so a paused
    plan went on collecting. The rule lives in `plan_executor.plan_should_stop`
    (it reads the column directly, so a stale session object cannot hide a
    pause); until that exists this reports False and the run behaves as before.
    A failed check is logged and the run continues: a transient read error is
    not a decision to stop.
    """
    try:
        from intel_platform.services.plan_executor import plan_should_stop
    except ImportError:
        return False
    try:
        return bool(await plan_should_stop(db, plan_id))
    except Exception:
        logger.warning("Could not read whether plan %s was paused; continuing", plan_id, exc_info=True)
        return False


def _source_urls(sources) -> set[str]:
    """Every page URL a plan's sources already cover.

    A re-tasked source stores one ``url``; a planned web_scrape/database source
    stores a ``urls`` list. Reading only ``url`` let re-tasking fetch planned
    pages again.
    """
    seen: set[str] = set()
    for source in sources or []:
        config = getattr(source, "config", None) or {}
        url = config.get("url")
        if isinstance(url, str) and url:
            seen.add(url)
        for u in config.get("urls") or []:
            if isinstance(u, str) and u:
                seen.add(u)
    return seen


def _log(db, plan_id, event: str, message: str, source_id=None) -> None:
    db.add(CollectionActivity(
        plan_id=plan_id, source_id=source_id, event=event, message=message,
    ))


async def run_requirement_passes(
    plan_id,
    db_factory,
    get_store,
    provider,
    acquire_source,
    source_limit: int | None = None,
    sources_already_used: int = 0,
    max_passes: int = DEFAULT_MAX_PASSES,
    attempts_per_element: int = DEFAULT_ATTEMPTS_PER_ELEMENT,
    extraction_mode: str = "",
) -> LoopOutcome:
    """Re-task collection at the elements the planned sources left unanswered.

    `acquire_source` is injected rather than imported so this module does not
    depend on the source loop that calls it.
    """
    outcome = LoopOutcome()

    async with db_factory() as db:
        plan = await db.get(CollectionPlan, plan_id)
        if not plan or not plan.pir_id:
            return outcome  # nothing to collect against
        pir = await db.get(Pir, plan.pir_id)
        if not pir:
            return outcome
        requirements = await sync_requirements(db, pir)
        if not requirements:
            outcome.stopped_on = "no_elements"
            await db.commit()
            return outcome
        project_id = pir.project_id
        # Read what the plan already covers from the database, once, and keep
        # it current as sources are added — the plan object loaded here does
        # not see sources added later in this run.
        seen_urls = _source_urls((await db.execute(
            select(CollectionSource).where(CollectionSource.plan_id == plan.id)
        )).scalars().all())
        await db.commit()

    store = get_store()
    used = sources_already_used

    stop = False
    for pass_num in range(1, max_passes + 1):
        async with db_factory() as db:
            if await plan_stop_requested(db, plan_id):
                outcome.stopped_on = "plan_stopped"
                break

            open_rows = (await db.execute(
                select(PirRequirement)
                .where(PirRequirement.pir_id == plan.pir_id, PirRequirement.status == "pending")
                .order_by(PirRequirement.ordinal)
            )).scalars().all()

            if not open_rows:
                # Left for the closing block to name: "nothing pending" means
                # answered *or* retired, and those are different outcomes.
                outcome.stopped_on = "nothing_to_do"
                break

            if source_limit is not None and used >= source_limit:
                outcome.stopped_on = "source_budget"
                _log(db, plan_id, "requirement_budget_reached",
                     f"Source budget of {source_limit} reached with "
                     f"{len(open_rows)} element(s) still open")
                await db.commit()
                break

            outcome.passes_run = pass_num
            _log(db, plan_id, "requirement_pass",
                 f"Pass {pass_num}: {len(open_rows)} element(s) still open")
            await db.commit()

            # Fair share of what remains, so one element cannot spend the whole
            # budget and leave the others untried.
            remaining = None if source_limit is None else max(0, source_limit - used)
            per_element = None if remaining is None else max(1, remaining // len(open_rows))

            asked = 0
            answered = 0
            for row in open_rows:
                if source_limit is not None and used >= source_limit:
                    break
                if await plan_stop_requested(db, plan_id):
                    outcome.stopped_on = "plan_stopped"
                    stop = True
                    break

                asked += 1
                assessment = await assess_requirement(
                    row.text, project_id, db, provider,
                    tried_queries=list(row.next_queries or []), store=store,
                )
                if getattr(assessment, "assessed", True):
                    answered += 1

                if not getattr(assessment, "assessed", True):
                    # Nobody looked: a provider outage or an unreadable reply.
                    # That is not evidence the element is unanswered, so it
                    # spends no attempt, keeps its last real assessment, and is
                    # not searched for (there is no gap to aim at). Counting it
                    # retired elements for infrastructure reasons.
                    _log(db, plan_id, "requirement_unassessed",
                         f"Could not assess element {row.ordinal + 1} this pass "
                         f"({assessment.missing[:120]}); left open: {row.text[:120]}")
                    await db.commit()
                    continue

                row.attempts += 1
                row.assessment_missing = assessment.missing
                row.assessment_confidence = assessment.confidence

                if assessment.satisfied:
                    row.status = "satisfied"
                    outcome.satisfied.append(row.text)
                    _log(db, plan_id, "requirement_satisfied",
                         f"Element answered: {row.text[:160]}")
                    await db.commit()
                    continue

                if row.attempts >= attempts_per_element:
                    # Tried and given up on. Distinct from "never attempted",
                    # and the analyst needs to see which one this is.
                    row.status = "unmet"
                    outcome.retired.append(row.text)
                    _log(db, plan_id, "requirement_retired",
                         f"Element retired after {row.attempts} attempt(s): "
                         f"{row.text[:120]} — {assessment.missing[:160]}")
                    await db.commit()
                    continue

                queries = assessment.next_queries or [row.text]
                row.next_queries = list(dict.fromkeys(list(row.next_queries or []) + queries))
                await db.commit()

                added = await _collect_for_element(
                    db, plan, row, queries, store, provider, acquire_source,
                    extraction_mode, per_element, seen=seen_urls,
                )
                used += added
                outcome.sources_added += added

                if not added:
                    _log(db, plan_id, "requirement_no_sources",
                         f"No new sources found for: {row.text[:160]}")
                    await db.commit()

            if stop:
                break
            if asked and not answered:
                # Nothing could be assessed this pass, so another pass would
                # only repeat the outage — and ending on "pass_budget" would
                # tell a budget story about an infrastructure fault.
                outcome.stopped_on = "assessor_unavailable"
                _log(db, plan_id, "requirement_assessor_unavailable",
                     f"No element could be assessed in pass {pass_num}; re-tasking stopped")
                await db.commit()
                break

    async with db_factory() as db:
        rows = (await db.execute(
            select(PirRequirement).where(PirRequirement.pir_id == plan.pir_id)
            .order_by(PirRequirement.ordinal)
        )).scalars().all()
        outcome.still_open = [r.text for r in rows if r.status == "pending"]
        if outcome.stopped_on == "nothing_to_do":
            if outcome.still_open:
                outcome.stopped_on = "pass_budget"
            elif any(r.status == "unmet" for r in rows):
                # Nothing is pending, but that is because elements were retired
                # after exhausting their attempts — not because they were
                # answered. Calling this "all_elements_resolved" produced the
                # line "0/3 element(s) answered ... stopped on
                # all_elements_resolved", which reads as success for a run that
                # answered nothing. An exhausted run must never be reported as
                # a satisfied one, and that includes its label.
                outcome.stopped_on = "elements_retired"
            else:
                outcome.stopped_on = "all_elements_answered"

        _log(db, plan_id, "requirement_loop_done",
             f"{len([r for r in rows if r.status == 'satisfied'])}/{len(rows)} element(s) "
             f"answered after {outcome.passes_run} pass(es); "
             f"{outcome.sources_added} source(s) added; stopped on {outcome.stopped_on}")
        await db.commit()

    return outcome


async def _collect_for_element(
    db, plan, row, queries, store, provider, acquire_source, extraction_mode, budget,
    seen: set[str] | None = None,
) -> int:
    """Search the gap queries and collect what they return. Returns sources added.

    `seen` is the run's set of already-covered page URLs; it is updated in place
    so the next element and the next pass do not fetch the same page again.
    """
    from intel_platform.collection.search import web_search
    from intel_platform.collection.proxy import get_active_proxy_config

    added = 0
    if seen is None:
        seen = _source_urls(getattr(plan, "sources", None))

    # get_active_proxy_config already degrades to direct on its own failures,
    # so nothing here may swallow an error into proxy=None: that silently sent
    # every re-tasking search out direct even with Tor selected.
    proxy = (await get_active_proxy_config()).get_proxy_url()

    for query in queries:
        if budget is not None and added >= budget:
            break
        try:
            import asyncio

            results = await asyncio.to_thread(
                web_search, query, RESULTS_PER_QUERY, proxy
            )
        except Exception:
            logger.warning("Gap search failed for %r", query[:80], exc_info=True)
            continue

        for result in results:
            if budget is not None and added >= budget:
                break
            url = result.get("url")
            if not url or url in seen:
                continue
            seen.add(url)

            source = CollectionSource(
                id=uuid.uuid4(), plan_id=plan.id,
                name=(result.get("title") or url)[:200],
                # Must be a key in connectors.base.CONNECTOR_REGISTRY. "web" is
                # not one: every re-tasked source raised "Unknown source type:
                # web" and the whole follow-up pass acquired nothing while the
                # gap queries themselves were working perfectly.
                source_type="web_scrape",
                # web_scrape takes a single `url`, not a list (see
                # connectors/web_scrape.py::validate_config).
                config={"url": url, "query": query},
                enabled=True,
                collection_status="pending",
            )
            db.add(source)
            # Flush before logging against it. collection_activity.source_id is
            # a foreign key, and SQLAlchemy does not know the activity row
            # depends on this insert, so without an explicit flush the two go
            # out in whatever order the unit of work chooses — and when the
            # activity lands first Postgres rejects it, taking the whole
            # re-tasking pass down. Live symptom: `requirement_pass` followed
            # five seconds later by `requirement_loop_failed`.
            await db.flush()
            _log(db, plan.id, "requirement_source_added",
                 f"Re-tasked for element {row.ordinal + 1}: {url[:200]}", source_id=source.id)
            await db.commit()

            try:
                source.collection_status = "collecting"
                result = await acquire_source(
                    source, plan, db, store, extraction_mode,
                    provider=provider, max_results=RESULTS_PER_QUERY,
                ) or {}
                if not result.get("accepted_count", result.get("record_count", 0)):
                    # Fetched, but the content gate kept nothing (a captcha, a
                    # login wall, an off-topic page). That spends no budget and
                    # is not a source added — it used to log "collected: 1
                    # record(s), 0 entities" and count against the element.
                    reasons = ", ".join(sorted({r for _u, r in result.get("rejected_pages") or []})) or "no content"
                    source.collection_status = "failed"
                    source.last_error = f"No usable content ({reasons})"[:500]
                    _log(db, plan.id, "requirement_source_rejected",
                         f"Re-tasked source yielded nothing usable ({reasons[:120]}) — {url[:140]}",
                         source_id=source.id)
                    await db.commit()
                    continue
                # Record the outcome the way the planned pass does. Without
                # this a re-tasked source sat at "pending / 0 records" forever
                # while its content was demonstrably in the graph — the plan
                # under-reported what it had collected, the dashboard counts
                # were wrong, and a later run would fetch the same page again.
                source.collection_status = "succeeded"
                source.last_success_at = datetime.now(timezone.utc)
                source.total_records_acquired = (
                    source.total_records_acquired or 0
                ) + result.get("record_count", 0)
                _log(db, plan.id, "requirement_source_acquired",
                     f"Re-tasked source collected: "
                     f"{result.get('accepted_count', result.get('record_count', 0))} "
                     f"record(s), {result.get('entities_created', 0)} entities "
                     f"— {url[:140]}", source_id=source.id)
                await db.commit()
                added += 1
            except Exception:
                logger.warning("Re-tasked acquisition failed for %s", url[:120], exc_info=True)
                source.collection_status = "failed"
                _log(db, plan.id, "requirement_source_failed",
                     f"Re-tasked source failed: {url[:200]}", source_id=source.id)
                await db.commit()

    return added
