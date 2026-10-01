"""Collection jobs: the durable record of every collection run.

A run used to be an asyncio task inside the API process, and whether it was in
flight was answered from that task (and from an in-memory tracker for the
synchronous path). Neither survived a restart, neither was visible to a second
process, and a run could not leave the API process at all. A run is now a row:

* ``/collection-plans/{id}/execute`` inserts it. In ``inline`` worker mode the
  API process claims it at once and runs it as a task; in ``worker`` mode it
  stays ``queued`` until ``python -m intel_platform.worker`` claims it with
  ``FOR UPDATE SKIP LOCKED``.
* Whoever runs it writes ``worker_id`` and refreshes ``heartbeat_at`` every
  10 s, then writes a terminal status and a sanitised ``error``.
* ``collection_plans.current_run_state()`` reads the latest row. A ``running``
  row whose heartbeat is older than ``collection_stall_seconds`` is ``stalled``:
  its worker is presumed dead, and a new run is allowed.

All timestamps are written with the database's ``now()``, and staleness is
measured against it too, so a worker whose clock disagrees with the API's
cannot make a live run look dead or a dead one look alive.

The legacy ``/collections`` runner records its runs here as well (kind
``legacy``, keyed by the collection id); the worker never claims those.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Index,
    String,
    Text,
    case,
    func,
    insert,
    literal,
    null,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from intel_platform.db.models import Base

# kind
KIND_AGENTIC = "agentic"            # planned sources, then requirement passes
KIND_REQUIREMENTS = "requirements"  # no planned sources: requirement passes only
KIND_LEGACY = "legacy"              # the /collections runner; never claimed by a worker
WORKER_KINDS = (KIND_AGENTIC, KIND_REQUIREMENTS)

# status
QUEUED = "queued"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"
CANCELLED = "cancelled"
LIVE_STATUSES = (QUEUED, RUNNING)

# Upper bound for the sanitised error text.
ERROR_MAX = 500


class CollectionJob(Base):
    __tablename__ = "collection_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Deliberately no foreign key: legacy runs are keyed by a Neo4j collection
    # id, and a job's history should outlive the plan it ran for.
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default=KIND_AGENTIC,
        comment="agentic | requirements (worker-run); legacy (the /collections runner)")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=QUEUED,
        comment="queued | running | succeeded | failed | cancelled")
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True,
        comment="Process that claimed the job: worker:<host>:<pid>:<n> or api:<host>:<pid>")
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True,
        comment="Sanitised failure reason, safe to show an analyst; never exception text")
    # Telemetry counters are per process, so what a worker counted never
    # reaches the API's /health. The run's own counts travel on its row
    # instead, refreshed with each heartbeat and written at the end.
    degraded: Mapped[dict | None] = mapped_column(JSONB, nullable=True,
        comment="Degraded outcomes during this run: {subsystem: {reason: count}}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_collection_jobs_plan_created", "plan_id", "created_at"),
        # The worker's poll: the oldest queued job.
        Index("ix_collection_jobs_status_created", "status", "created_at"),
        # At most one live job per plan, whichever process inserts it. The
        # execute route also locks the plan row; this holds even if it did not.
        Index(
            "uq_collection_jobs_live_plan", "plan_id", unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    # created_at comes from the server; fetch it with the INSERT (RETURNING)
    # rather than lazily, which an async session cannot do.
    __mapper_args__ = {"eager_defaults": True}


def sanitise_error(message: str | None) -> str | None:
    """Bound an error for storage. Callers pass reasons, not exception text."""
    if not message:
        return None
    return message.strip()[:ERROR_MAX] or None


async def latest_job(db, plan_id: uuid.UUID) -> tuple[CollectionJob | None, datetime | None]:
    """The plan's most recent job and the database's current time."""
    row = (await db.execute(
        select(CollectionJob, func.now())
        .where(CollectionJob.plan_id == plan_id)
        .order_by(CollectionJob.created_at.desc(), CollectionJob.id.desc())
        .limit(1)
    )).first()
    if row is None:
        return None, None
    return row[0], row[1]


async def latest_job_status(db, plan_id: uuid.UUID) -> str | None:
    """Just the status of the plan's most recent job (a single-column read)."""
    result = await db.execute(
        select(CollectionJob.status)
        .where(CollectionJob.plan_id == plan_id)
        .order_by(CollectionJob.created_at.desc(), CollectionJob.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def insert_job(
    db, *, plan_id: uuid.UUID, project_id: str, kind: str,
    claimed_by: str | None = None,
) -> uuid.UUID:
    """Insert a job in the session's transaction (the caller commits).

    ``claimed_by`` inserts it already ``running`` for that process (inline
    mode, the legacy runner), so no worker can claim it in between; otherwise it
    is ``queued`` for a worker. A Core insert, so no half-loaded instance is
    left in the session's identity map.
    """
    values: dict = {
        "id": uuid.uuid4(), "plan_id": plan_id, "project_id": (project_id or "")[:64],
        "kind": kind, "status": QUEUED,
    }
    if claimed_by:
        values.update(status=RUNNING, worker_id=claimed_by[:128], started_at=func.now(), heartbeat_at=func.now())
    result = await db.execute(insert(CollectionJob).values(**values).returning(CollectionJob.id))
    return result.scalar_one()


async def claim_next(db, worker_id: str) -> uuid.UUID | None:
    """Claim the oldest queued worker job, or None. Commits.

    ``FOR UPDATE SKIP LOCKED``: two workers polling at once each take a
    different row, or nothing, and never block on each other.
    """
    row = (await db.execute(
        select(CollectionJob.id)
        .where(CollectionJob.status == QUEUED, CollectionJob.kind.in_(WORKER_KINDS))
        .order_by(CollectionJob.created_at, CollectionJob.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )).first()
    if row is None:
        await db.rollback()
        return None
    await db.execute(
        update(CollectionJob)
        .where(CollectionJob.id == row[0], CollectionJob.status == QUEUED)
        .values(status=RUNNING, worker_id=worker_id, started_at=func.now(), heartbeat_at=func.now())
    )
    await db.commit()
    return row[0]


def _owned_and_unfinished(job_id: uuid.UUID, worker_id: str):
    return (
        CollectionJob.id == job_id,
        CollectionJob.worker_id == worker_id,
        CollectionJob.finished_at.is_(None),
        CollectionJob.status.in_((RUNNING, CANCELLED)),
    )


async def heartbeat(db, job_id: uuid.UUID, worker_id: str, degraded: dict | None = None) -> str | None:
    """Refresh the heartbeat (and the run's degraded counts, when given). Commits.

    Returns the job's status, or None when this process no longer owns a live
    job by that id (it was closed as stalled and superseded) — the caller must
    stop the run, because another may already be under way.
    """
    values: dict = {"heartbeat_at": func.now()}
    if degraded:
        values["degraded"] = degraded
    result = await db.execute(
        update(CollectionJob)
        .where(*_owned_and_unfinished(job_id, worker_id))
        .values(**values)
        .returning(CollectionJob.status)
    )
    status = result.scalar_one_or_none()
    await db.commit()
    return status


async def finish(db, job_id: uuid.UUID, worker_id: str, status: str, error: str | None = None,
                 degraded: dict | None = None) -> str | None:
    """Write the terminal status (and the run's degraded counts). Commits.

    Returns the status actually stored, or None if the job was no longer
    ours. A job the analyst cancelled stays ``cancelled`` whatever the run
    did after, so the stored status can differ from the one asked for.
    """
    values: dict = {
        "status": _keep_cancelled(status),
        "error": _keep_cancelled_error(sanitise_error(error)),
        "finished_at": func.now(),
        "heartbeat_at": func.now(),
    }
    if degraded:
        values["degraded"] = degraded
    result = await db.execute(
        update(CollectionJob)
        .where(*_owned_and_unfinished(job_id, worker_id))
        .values(**values)
        .returning(CollectionJob.status)
    )
    row = result.first()
    await db.commit()
    return row[0] if row is not None else None


def _keep_cancelled(status: str):
    return case((CollectionJob.status == CANCELLED, CollectionJob.status), else_=literal(status))


def _keep_cancelled_error(error: str | None):
    value = literal(error) if error is not None else null()
    return case((CollectionJob.status == CANCELLED, CollectionJob.error), else_=value)


async def close_unfinished(db, plan_id: uuid.UUID, reason: str) -> int:
    """Close every unfinished job of a plan as failed (the caller commits).

    Used when a new run is accepted over a stalled one: the old worker is
    presumed dead, and if it is not, its next heartbeat finds the job gone and
    stops. A cancelled job still stopping counts as unfinished. Returns the
    number of rows closed.
    """
    result = await db.execute(
        update(CollectionJob)
        .where(CollectionJob.plan_id == plan_id,
               CollectionJob.status.in_(LIVE_STATUSES + (CANCELLED,)),
               CollectionJob.finished_at.is_(None))
        .values(status=FAILED, error=sanitise_error(reason), finished_at=func.now())
    )
    return result.rowcount or 0


async def cancel(db, job_id: uuid.UUID, *, still_running: bool) -> None:
    """Mark a live job cancelled (the caller commits).

    A job whose run is still going keeps ``finished_at`` empty: the run stops
    at its next check and the runner writes it then. A queued or stalled job has
    nothing left to stop, so it is finished now.
    """
    values: dict = {"status": CANCELLED}
    if not still_running:
        values["finished_at"] = func.now()
    await db.execute(
        update(CollectionJob)
        .where(CollectionJob.id == job_id, CollectionJob.status.in_(LIVE_STATUSES))
        .values(**values)
    )
