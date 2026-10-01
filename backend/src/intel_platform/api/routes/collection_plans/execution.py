"""Running a collection plan: execute, cancel, the run's status, its activity trail.

The run state itself is read in ``services/plan_runs.py`` from the job table;
this module is its HTTP face: the execute guard's 400 and 409, the status
endpoint's shape, and the activity log a poller pages through.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.api.deps import get_graph_store
from intel_platform.api.routes.collection_plans.plans import _parse_uuid, _plan_to_dict
from intel_platform.collection import job_runner
from intel_platform.db import jobs
from intel_platform.db.engine import get_db
from intel_platform.db.models import CollectionActivity, CollectionPlan, PlanStatus
from intel_platform.graph.store import GraphStore
from intel_platform.services.plan_runs import (
    TERMINAL_EVENTS,
    current_run_events,
    run_routing_rules,
    run_state_and_job,
    source_readiness,
)

# Mounted by the package router, which carries the API-key dependency.
router = APIRouter()


class ExecuteRequest(BaseModel):
    # How many results to pull per source: URLs/pages for web_scrape/database/
    # api_feed, items for rss_feed. Clamped to 1..25.
    max_results_per_source: int = 10
    # Collection budget: stop after this many sources even if the plan proposes
    # more. Pairs with `POST /pirs/{id}/assess`, which reports whether the
    # requirement was answered or the budget ran out first.
    source_limit: int | None = Field(default=None, ge=1)


@router.post("/collection-plans/{plan_id}/execute", status_code=202)
async def execute_plan_endpoint(
    plan_id: str,
    body: ExecuteRequest | None = None,
    db: AsyncSession = Depends(get_db),
    store: GraphStore = Depends(get_graph_store),
):
    """Approve and execute a collection plan: 202 with the ``job_id`` of the run.

    Inserts a ``collection_jobs`` row. In ``inline`` worker mode the API process
    runs it at once as a background task; in ``worker`` mode it is ``queued``
    for ``python -m intel_platform.worker``. The run resolves sources, acquires
    them through the registered connectors, extracts entities into the graph,
    then re-tasks against the requirement's open elements. File upload sources
    are skipped (they need a manual upload). With nothing to run the plan is
    still activated, and ``job_id`` is null.
    """
    pid = _parse_uuid(plan_id, "plan_id")
    # The plan row stays locked until this request commits, so a second
    # execute for the same plan, in this process or another, waits here and
    # then sees the first one's job. The job table's one-live-job index is the
    # backstop if anything ever skipped this lock.
    plan = await db.get(CollectionPlan, pid, with_for_update=True)
    if not plan:
        raise HTTPException(404, "Collection plan not found")
    try:
        return await _start_execution(plan, body, db, store)
    except BaseException:
        await db.rollback()
        raise


async def _start_execution(
    plan: CollectionPlan, body: ExecuteRequest | None, db: AsyncSession, store: GraphStore,
) -> dict:
    """The execute guard and launch. Runs with the plan row locked."""
    # Refuse only when a run is genuinely in flight, not because of a status
    # flag. The old guard allowed DRAFT and PAUSED only, which made "Activate" —
    # the button an analyst naturally presses before running something — set
    # ACTIVE and thereby make the plan unrunnable, recoverable only by pressing
    # Pause. It also stranded any plan whose run died: execution sets ACTIVE, so
    # a crashed run left the plan permanently unexecutable.
    if plan.status == PlanStatus.ARCHIVED:
        raise HTTPException(400, "Cannot execute an archived plan")

    state, previous, now = await run_state_and_job(db, plan.id)
    if state == "running":
        # A stalled run is deliberately not blocking: past the silence
        # threshold the previous attempt is presumed dead, and refusing forever
        # is how the old guard stranded plans.
        raise HTTPException(409, "A collection run is already in flight for this plan")
    if state == "stalled":
        # Close it before the new one: it holds the plan's one live job, and if
        # its worker is in fact alive, the next heartbeat finds the job gone
        # and stops the run.
        silent = job_runner.seconds_since(
            previous.heartbeat_at or previous.started_at or previous.created_at, now)
        await jobs.close_unfinished(
            db, plan.id, f"Stalled: no heartbeat for {silent} s; superseded by a new run")

    # Check source readiness
    readiness = source_readiness(plan.sources or [])
    all_auto = readiness.automatic
    source_limit = body.source_limit if body else None
    max_results = max(1, min(25, body.max_results_per_source if body else 10))
    # A plan raised against a PIR is collected against its open elements even
    # with no planned sources: the loop goes straight to re-tasking. It used to
    # be set ACTIVE and left there, with the requirement loop never run.
    requirement_only = not all_auto and plan.pir_id is not None
    launched = bool(all_auto) or requirement_only

    # Activate the plan, recording the collection budget it was given. The PIR
    # assessor reports "stopped on the source limit", which must rest on what
    # the run was actually allowed rather than on a number the caller re-supplies
    # at assessment time. The routing rules are also how the run's parameters
    # reach a worker in another process.
    plan.status = PlanStatus.ACTIVE
    plan.routing_rules = run_routing_rules(plan.routing_rules, source_limit, max_results)
    plan.updated_at = datetime.now(timezone.utc)

    mode = job_runner.worker_mode()
    job_id = None
    if launched:
        job_id = await jobs.insert_job(
            db, plan_id=plan.id, project_id=plan.project_id,
            kind=jobs.KIND_AGENTIC if all_auto else jobs.KIND_REQUIREMENTS,
            # Inline: this process claims it now, so no worker can take it too.
            claimed_by=job_runner.process_worker_id("api") if mode == job_runner.INLINE else None,
        )
    await db.commit()
    await db.refresh(plan)

    if launched and mode == job_runner.INLINE:
        from intel_platform.db.engine import get_session_factory

        # Bulk resolution + summarization go to the collection provider (local
        # Ollama when configured), which run_agentic_loop selects itself.
        job_runner.start_inline(job_id, get_store=lambda: store, db_factory=get_session_factory())

    if all_auto:
        message = f"Agentic execution started with {len(all_auto)} source(s)."
    elif requirement_only:
        message = "No planned sources; collecting against the requirement's open elements."
    else:
        message = "Plan activated but no automated sources found."
    if launched and mode == job_runner.WORKER:
        message += " Queued for a collection worker."
    return {
        **_plan_to_dict(plan),
        "job_id": str(job_id) if job_id else None,
        "worker_mode": mode,
        "execution_status": (
            ("started" if mode == job_runner.INLINE else "queued") if launched else "no_executable_sources"
        ),
        "message": message,
        "sources_queued": min(len(all_auto), source_limit) if source_limit else len(all_auto),
        "sources_manual": len(readiness.file_only),
        "sources_missing_config": len(readiness.missing_config),
        "source_limit": source_limit,
        "sources_over_budget": max(0, len(all_auto) - source_limit) if source_limit else 0,
        "warnings": readiness.warnings,
    }


@router.get("/collection-plans/{plan_id}/execution-status")
async def get_execution_status(plan_id: str, db: AsyncSession = Depends(get_db)):
    """Poll the execution progress of a collection plan's latest run.

    ``status`` is the job table's answer (``current_run_state``), the same one
    the execute guard enforces; the activity trail supplies the message and the
    per-run counts. ``job_status``, ``seconds_since_heartbeat`` and ``error``
    come from the job row so a caller can see why a run reads as it does.
    """
    pid = _parse_uuid(plan_id, "plan_id")
    state, job, now = await run_state_and_job(db, pid)
    job_fields = _job_fields(job, now)

    result = await db.execute(
        select(CollectionActivity)
        .where(CollectionActivity.plan_id == pid)
        .order_by(CollectionActivity.created_at.asc())
    )
    events = result.scalars().all()
    if not events:
        return {
            "plan_id": plan_id, "status": state, "message": _job_message(state, job),
            "sources_succeeded": 0, "sources_failed": 0, **job_fields,
        }

    latest = events[-1]
    # Counts are for the current run only — see current_run_events. A live run
    # whose trail still ends on the previous run's terminal event has not
    # written anything of its own yet.
    if state == "running" and latest.event in TERMINAL_EVENTS:
        this_run = []
        message = _job_message(state, job)
    else:
        this_run = current_run_events(events)
        message = latest.message
    return {
        "plan_id": plan_id,
        "status": state,
        "message": message,
        "last_event": latest.event,
        "sources_succeeded": sum(1 for e in this_run if e.event == "source_succeeded"),
        "sources_failed": sum(1 for e in this_run if e.event == "source_failed"),
        "updated_at": latest.created_at.isoformat(),
        # How long the plan has been silent, so a caller can judge for itself
        # rather than inferring liveness from the status string alone.
        "seconds_since_last_event": int(
            (datetime.now(timezone.utc) - latest.created_at).total_seconds()
        ),
        **job_fields,
    }


def _job_fields(job, now) -> dict:
    """What the status endpoint says about the job row. ``worker_id`` (a host
    name and pid) stays server-side."""
    if job is None:
        return {"job_id": None, "job_status": None}
    return {
        "job_id": str(job.id),
        "job_status": job.status,
        "heartbeat_at": job.heartbeat_at.isoformat() if job.heartbeat_at else None,
        "seconds_since_heartbeat": job_runner.seconds_since(job.heartbeat_at, now),
        "error": job.error,
        # This run's degraded outcomes ({subsystem: {reason: count}}), which
        # /health cannot show when a worker process ran it.
        "degraded": job.degraded or {},
    }


def _job_message(state: str, job) -> str:
    if job is None:
        return "No active execution"
    if state == "running":
        if job.status == jobs.QUEUED:
            return "Queued; waiting for a collection worker"
        if job.status == jobs.CANCELLED:
            return "Cancelling; the run stops before its next source"
        return "Run starting"
    if state == "stalled":
        return "No heartbeat from the run's worker; it is presumed dead. Running again is safe."
    if state == "failed":
        return job.error or "The collection run ended with an error"
    if state == "cancelled":
        return "The collection run was cancelled"
    return "Collection run complete"


@router.post("/collection-plans/{plan_id}/cancel", status_code=202)
async def cancel_plan_run(plan_id: str, db: AsyncSession = Depends(get_db)):
    """Cancel the plan's live run (queued, running, or stalled).

    A running job is marked ``cancelled`` and stops before its next source
    (``plan_should_stop`` reads it); ``stopping`` says so, and the run state
    stays ``running`` until it has. A queued or stalled job has nothing left to
    stop and is finished at once. 409 when no run is live.
    """
    pid = _parse_uuid(plan_id, "plan_id")
    # Same lock as /execute, so a cancel and a new run cannot interleave.
    plan = await db.get(CollectionPlan, pid, with_for_update=True)
    if not plan:
        raise HTTPException(404, "Collection plan not found")
    state, job, _now = await run_state_and_job(db, pid)
    if job is None or job.status not in jobs.LIVE_STATUSES:
        # Decided before the rollback, which expires `job`.
        stopping_already = job is not None and job.status == jobs.CANCELLED and state == "running"
        await db.rollback()
        if stopping_already:
            raise HTTPException(409, "The collection run is already stopping")
        raise HTTPException(409, "No collection run is in flight for this plan")

    # Read before the update: an ORM-enabled UPDATE also refreshes `job`.
    job_id, previous = job.id, job.status
    stopping = state == "running" and previous == jobs.RUNNING
    await jobs.cancel(db, job_id, still_running=stopping)
    if stopping:
        message = "Cancelled; the run stops before its next source"
    elif previous == jobs.QUEUED:
        message = "Cancelled before a worker picked it up"
    else:
        message = "Cancelled a stalled run"
    db.add(CollectionActivity(plan_id=pid, event="run_cancelled", message=message))
    await db.commit()
    return {
        "plan_id": plan_id,
        "job_id": str(job_id),
        "status": jobs.CANCELLED,
        "previous_status": previous,
        "stopping": stopping,
        "message": message,
    }


# ---------------------------------------------------------------------------
# Activity log
# ---------------------------------------------------------------------------

@router.get("/collection-plans/{plan_id}/activity")
async def get_activity(
    plan_id: str,
    since: str | None = None,
    limit: int = Query(500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
):
    """A page of a plan's activity log, oldest first.

    Without `since`, the most recent `limit` events. With `since` (an ISO-8601
    timestamp, normally the last event the caller holds), up to `limit` events
    after it — so a poller pages forward instead of reloading the trail. The UI
    polls every 3 s and every poll used to load the whole trail; a malformed
    `since` was silently ignored, which also meant "load all of it", and is now
    a 400.
    """
    stmt = select(CollectionActivity).where(
        CollectionActivity.plan_id == _parse_uuid(plan_id, "plan_id")
    )
    if since:
        # An unencoded "+00:00" offset arrives as " 00:00" once the query
        # string is decoded; restore it rather than refusing the poll.
        since = re.sub(r" (\d{2}:\d{2})$", r"+\1", since.strip())
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "since must be an ISO-8601 timestamp")
        if since_dt.tzinfo is None:
            since_dt = since_dt.replace(tzinfo=timezone.utc)
        stmt = (
            stmt.where(CollectionActivity.created_at > since_dt)
            .order_by(CollectionActivity.created_at.asc())
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()
    else:
        stmt = stmt.order_by(CollectionActivity.created_at.desc()).limit(limit)
        rows = list(reversed((await db.execute(stmt)).scalars().all()))
    return [
        {
            "id": str(a.id),
            "plan_id": str(a.plan_id),
            "source_id": str(a.source_id) if a.source_id else None,
            "event": a.event,
            "message": a.message,
            "created_at": a.created_at.isoformat(),
        }
        for a in rows
    ]
