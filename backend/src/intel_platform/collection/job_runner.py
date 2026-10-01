"""Running a collection job, wherever it runs.

One code path for both worker modes (``settings.collection_worker_mode``):

* ``inline`` (the default) — ``/execute`` inserts the job already ``running``
  for the API process and starts :func:`run_job` as an asyncio task there.
* ``worker`` — ``/execute`` only inserts it ``queued``;
  ``python -m intel_platform.worker`` claims it and calls :func:`run_job`.

Either way the job row is the evidence: :func:`run_job` heartbeats it every
:data:`HEARTBEAT_SECONDS` and writes a terminal status and a sanitised error,
and :func:`run_state` turns the latest row into the state the execute guard and
``/execution-status`` report. Nothing here is consulted in memory.
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
import os
import socket
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from intel_platform.config import settings
from intel_platform.db import jobs

logger = logging.getLogger(__name__)

# How often a running job proves it is alive.
HEARTBEAT_SECONDS = 10.0

INLINE = "inline"
WORKER = "worker"

_DEFAULT_STALL_SECONDS = 120


def worker_mode() -> str:
    """``inline`` or ``worker``. Anything else is treated as ``inline``."""
    mode = str(getattr(settings, "collection_worker_mode", INLINE) or INLINE).strip().lower()
    return WORKER if mode == WORKER else INLINE


def stall_seconds() -> int:
    """How long a live job may go without a heartbeat before it is ``stalled``."""
    try:
        value = int(getattr(settings, "collection_stall_seconds", _DEFAULT_STALL_SECONDS))
    except (TypeError, ValueError):
        value = _DEFAULT_STALL_SECONDS
    # Never at or below the heartbeat interval: a healthy run would flap.
    return max(value, int(HEARTBEAT_SECONDS * 3))


def process_worker_id(role: str) -> str:
    """``<role>:<host>:<pid>``: which process claimed a job, for the logs."""
    return f"{role}:{socket.gethostname()}:{os.getpid()}"[:128]


# ---------------------------------------------------------------------------
# Run state
# ---------------------------------------------------------------------------

def run_state(job, now: datetime | None, stall_after: int | None = None) -> str:
    """``idle | running | stalled | completed | failed | cancelled`` for a plan's latest job.

    * no job → ``idle``
    * ``succeeded`` → ``completed``; ``failed`` → ``failed``; a ``cancelled``
      job whose run has stopped → ``cancelled``
    * otherwise the run is live (``queued``, ``running``, or cancelled but
      still stopping): ``running`` while its last sign of life — heartbeat,
      else start, else creation — is within the stall window, ``stalled``
      beyond it. Only ``running`` blocks a new run.
    """
    if job is None:
        return "idle"
    if job.status == jobs.SUCCEEDED:
        return "completed"
    if job.status == jobs.FAILED:
        return "failed"
    if job.status == jobs.CANCELLED and job.finished_at is not None:
        return "cancelled"
    if job.status not in (jobs.QUEUED, jobs.RUNNING, jobs.CANCELLED):
        return "idle"
    last = job.heartbeat_at or job.started_at or job.created_at
    if last is None or now is None:
        return "running"
    window = stall_seconds() if stall_after is None else stall_after
    return "stalled" if (now - last).total_seconds() > window else "running"


def seconds_since(moment: datetime | None, now: datetime | None) -> int | None:
    if moment is None or now is None:
        return None
    return max(0, int((now - moment).total_seconds()))


# ---------------------------------------------------------------------------
# Degraded outcomes, per run
# ---------------------------------------------------------------------------

# The counts for the run executing in this context: {subsystem: {reason: n}}.
# run_job sets a fresh dict before it starts the run's task, which copies the
# context, so everything the run does (including tasks and threads it starts)
# adds to that one dict. services.telemetry counts per process, so without
# this a worker's counts would never reach the API.
_run_degraded: contextvars.ContextVar[dict | None] = contextvars.ContextVar("collection_run_degraded", default=None)


def record_run_degraded(subsystem: str, reason: str) -> None:
    """Count a degraded outcome against the job running in this context, if any."""
    counts = _run_degraded.get()
    if counts is None:
        return
    bucket = counts.setdefault(subsystem, {})
    bucket[reason] = bucket.get(reason, 0) + 1


def _snapshot(counts: dict) -> dict | None:
    return {subsystem: dict(reasons) for subsystem, reasons in counts.items()} or None


# ---------------------------------------------------------------------------
# Executing a claimed job
# ---------------------------------------------------------------------------

@dataclass
class _Ownership:
    lost: bool = False
    beats: int = 0
    statuses: list = field(default_factory=list)


async def _heartbeat(job_id, worker_id, db_factory, interval, run_task, ownership: _Ownership,
                     counts: dict | None = None) -> None:
    """Refresh the job's heartbeat (and its degraded counts so far) until cancelled.

    A database error is logged and retried: a blip is not a reason to stop a
    run. Finding the job no longer ours is: it was closed as stalled and a new
    run may already be collecting, so this one is cancelled.
    """
    while True:
        await asyncio.sleep(interval)
        try:
            async with db_factory() as db:
                status = await jobs.heartbeat(db, job_id, worker_id, _snapshot(counts or {}))
        except Exception:
            logger.warning("Heartbeat for collection job %s failed; retrying", job_id, exc_info=True)
            continue
        ownership.beats += 1
        ownership.statuses.append(status)
        if status is None:
            logger.error("Collection job %s is no longer owned by %s; stopping its run", job_id, worker_id)
            ownership.lost = True
            run_task.cancel()
            return


async def _finish(db_factory, job_id, worker_id, status, error, counts: dict | None = None) -> None:
    try:
        async with db_factory() as db:
            if not await jobs.finish(db, job_id, worker_id, status, error, _snapshot(counts or {})):
                logger.warning("Collection job %s was closed by someone else before it finished", job_id)
    except Exception:
        # The row stays `running` and goes `stalled` after the window, which
        # still frees the plan; the run itself is over either way.
        logger.exception("Could not record the end of collection job %s", job_id)


def _max_results(rules: dict) -> int:
    """Per-source result count the run was started with (routing_rules, 1..25)."""
    try:
        value = int(rules.get("max_results_per_source") or 10)
    except (TypeError, ValueError):
        value = 10
    return max(1, min(25, value))


def _source_limit(rules: dict) -> int | None:
    """The run's source budget (routing_rules), or None for no budget."""
    try:
        value = int(rules["source_limit"]) if rules.get("source_limit") is not None else None
    except (TypeError, ValueError):
        return None
    return value if value and value > 0 else None


async def run_job(
    job_id: uuid.UUID,
    *,
    worker_id: str,
    db_factory=None,
    get_store=None,
    get_provider=None,
    heartbeat_seconds: float | None = None,
) -> str:
    """Execute one claimed job to a terminal status; return the status written.

    The caller has already made the row ``running`` with this ``worker_id``
    (the worker's claim, or the inline insert). Cancelling the task that runs
    this records the job ``failed`` ("the worker stopped") and re-raises.
    """
    if db_factory is None:
        from intel_platform.db.engine import get_session_factory

        db_factory = get_session_factory()
    if get_store is None:
        from intel_platform.api.deps import get_neo4j_driver
        from intel_platform.graph.store import GraphStore

        store = GraphStore(get_neo4j_driver())
        get_store = lambda: store  # noqa: E731
    interval = HEARTBEAT_SECONDS if heartbeat_seconds is None else heartbeat_seconds

    from intel_platform.db.models import CollectionPlan

    try:
        async with db_factory() as db:
            job = await db.get(jobs.CollectionJob, job_id)
            plan = await db.get(CollectionPlan, job.plan_id) if job is not None else None
            rules = dict(plan.routing_rules or {}) if plan is not None else {}
    except Exception:
        logger.exception("Could not load collection job %s", job_id)
        await _finish(db_factory, job_id, worker_id, jobs.FAILED, "The job could not be loaded; see worker logs")
        return jobs.FAILED
    if job is None:
        logger.error("Collection job %s does not exist", job_id)
        return jobs.FAILED
    if plan is None:
        await _finish(db_factory, job_id, worker_id, jobs.FAILED, "The plan no longer exists")
        return jobs.FAILED

    from intel_platform.collection import agentic

    # The run's task copies this context, so its degraded outcomes land here.
    counts: dict = {}
    token = _run_degraded.set(counts)
    try:
        run = asyncio.create_task(agentic.run_agentic_loop(
            plan_id=plan.id,
            db_factory=db_factory,
            get_store=get_store,
            get_provider=get_provider,
            max_results_per_source=_max_results(rules),
            source_limit=_source_limit(rules),
        ))
    finally:
        _run_degraded.reset(token)
    ownership = _Ownership()
    beat = asyncio.create_task(_heartbeat(job_id, worker_id, db_factory, interval, run, ownership, counts))
    status, error = jobs.SUCCEEDED, None
    try:
        failure = await run
        if failure:
            status, error = jobs.FAILED, failure
    except asyncio.CancelledError:
        status = jobs.FAILED
        error = (
            "Superseded: the job was closed as stalled while this run was still going"
            if ownership.lost else
            "The collection worker stopped before the run finished"
        )
        if not ownership.lost:
            beat.cancel()
            await _finish(db_factory, job_id, worker_id, status, error, counts)
            raise
    except Exception as exc:
        logger.exception("Collection job %s failed", job_id)
        status, error = jobs.FAILED, f"Collection run failed ({type(exc).__name__}); see worker logs"
    finally:
        beat.cancel()
    if not ownership.lost:
        await _finish(db_factory, job_id, worker_id, status, error, counts)
    logger.info("Collection job %s for plan %s finished: %s", job_id, plan.id, status)
    return status


# ---------------------------------------------------------------------------
# Inline mode: the API process runs the job itself
# ---------------------------------------------------------------------------

# Strong references only. asyncio.create_task does not keep one, and a
# garbage-collected task cancels a live collection. Never read for state.
_background: set[asyncio.Task] = set()


def start_inline(job_id: uuid.UUID, *, get_store=None, get_provider=None, db_factory=None) -> asyncio.Task:
    task = asyncio.create_task(run_job(
        job_id, worker_id=process_worker_id("api"),
        db_factory=db_factory, get_store=get_store, get_provider=get_provider,
    ))
    _background.add(task)
    task.add_done_callback(_background.discard)
    return task


# ---------------------------------------------------------------------------
# The legacy /collections runner
# ---------------------------------------------------------------------------

_LEGACY_NAMESPACE = uuid.UUID("6f1c3c0e-9a7b-4d5e-8f21-0b6a4c2d9e17")


def legacy_job_key(collection_id: str) -> uuid.UUID:
    """The job table's plan_id for a legacy collection id (a UUID, or derived from it)."""
    try:
        return uuid.UUID(str(collection_id))
    except ValueError:
        return uuid.uuid5(_LEGACY_NAMESPACE, str(collection_id))


class LegacyJob:
    """Best-effort job row for a legacy ``/collections`` run.

    That path's state lives in Neo4j and it has always run without Postgres, so
    a database problem here is logged and otherwise ignored: recording the run
    must never be what stops it.
    """

    def __init__(self, collection_id: str, project_id: str, db_factory=None,
                 heartbeat_seconds: float | None = None):
        self._key = legacy_job_key(collection_id)
        self._project_id = project_id
        self._db_factory = db_factory
        self._interval = HEARTBEAT_SECONDS if heartbeat_seconds is None else heartbeat_seconds
        self._worker_id = process_worker_id("api")
        self.job_id: uuid.UUID | None = None
        self._beat: asyncio.Task | None = None

    def _factory(self):
        if self._db_factory is None:
            from intel_platform.db.engine import get_session_factory

            self._db_factory = get_session_factory()
        return self._db_factory

    async def start(self) -> None:
        try:
            factory = self._factory()
            async with factory() as db:
                # A legacy run left live by a dead process would hold the
                # one-live-job index for this key. The route has already
                # accepted a new run, so the old one is over by definition.
                await jobs.close_unfinished(db, self._key, "Superseded by a new run")
                self.job_id = await jobs.insert_job(
                    db, plan_id=self._key, project_id=self._project_id,
                    kind=jobs.KIND_LEGACY, claimed_by=self._worker_id,
                )
                await db.commit()
        except Exception:
            logger.warning("Could not record legacy collection run %s as a job", self._key, exc_info=True)
            self.job_id = None
            return
        self._beat = asyncio.create_task(self._heartbeat())

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                async with self._factory()() as db:
                    await jobs.heartbeat(db, self.job_id, self._worker_id)
            except Exception:
                logger.debug("Legacy job heartbeat failed", exc_info=True)

    async def finish(self, status: str, error: str | None = None) -> None:
        if self._beat is not None:
            self._beat.cancel()
        if self.job_id is None:
            return
        try:
            async with self._factory()() as db:
                await jobs.finish(db, self.job_id, self._worker_id, status, error)
        except Exception:
            logger.warning("Could not record the end of legacy collection run %s", self._key, exc_info=True)
