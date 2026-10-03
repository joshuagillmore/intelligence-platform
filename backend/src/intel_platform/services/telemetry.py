"""Countable degraded outcomes.

A degraded outcome is a request or a job that completed, but worse than asked:
a chunk extracted by NLP because the model failed, a document stored without
its embeddings, an enrichment provider that errored, a topic left with its
algorithmic label. Each call site already logs it; what was missing was a count
an operator can read without grepping logs, so a quiet provider outage shows up
as a number rather than as results that are merely thinner than they should be.

Counting is in memory, per process. Each count lands in two places:

* the **lifetime** counts since process start (``since``), which reset on
  restart. ``/health`` reports their totals per subsystem (`totals()`), so it
  describes the process that answered;
* the **pending** counts since the last flush. Each process (the API and the
  collection worker) writes them to Postgres (``degraded_events``, one row per
  subsystem and reason) every :data:`FLUSH_SECONDS` and at shutdown, and the
  worker also at the end of each job (`flush()`, `flushing()`).
  ``GET /api/admin/degraded`` sums the last 24 hours of rows by process, plus
  the API's own pending counts (`recent()`), so an outage only the worker saw
  still reaches the admin card. Rows older than :data:`RETAIN_DAYS` are
  deleted by the flushes.

Subsystems in use: ``extraction``, ``embeddings``, ``enrichment``, ``llm``,
``topics``, ``attack_mapping``, ``collection``.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

SUBSYSTEMS = ("extraction", "embeddings", "enrichment", "llm", "topics", "attack_mapping", "collection")

# The processes that flush, as stored in degraded_events.process.
API = "api"
WORKER = "worker"
PROCESSES = (API, WORKER)

# How often a running process writes its pending counts.
FLUSH_SECONDS = 60.0
# The admin view's window.
WINDOW_HOURS = 24
# A shutdown must not hang on an unreachable database.
_SHUTDOWN_FLUSH_SECONDS = 5.0
# Rows older than this are deleted by a flush that wrote rows, at most once
# every _PRUNE_SECONDS per process, so the table stays a few days deep.
RETAIN_DAYS = 7
_PRUNE_SECONDS = 3600.0

# Reasons are meant to be a small vocabulary ("provider_error", "unparsed", an
# exception type). A caller that passes something unbounded must not grow the
# table without limit, so past this many distinct reasons in one subsystem the
# rest are counted under OVERFLOW_REASON.
MAX_REASONS_PER_SUBSYSTEM = 50
MAX_REASON_LENGTH = 80
OVERFLOW_REASON = "other"

_lock = threading.Lock()
_counts: dict[str, dict[str, int]] = {}
_since = datetime.now(timezone.utc)

# Counted since the last flush took them, and when that was.
_pending: dict[str, dict[str, int]] = {}
_pending_since = _since
# Flushes under way, and flushes finished, so `recent()` can tell whether one
# moved counts from memory to the table while it was reading both.
_flushing = 0
_flushes_done = 0
# When this process last pruned old rows (time.monotonic()), or None.
_last_prune: float | None = None


def _clean(value: str, fallback: str) -> str:
    value = " ".join(str(value or "").split())[:MAX_REASON_LENGTH]
    return value or fallback


def _add(into: dict[str, dict[str, int]], subsystem: str, reason: str, count: int) -> None:
    bucket = into.setdefault(subsystem, {})
    bucket[reason] = bucket.get(reason, 0) + count


def _copy(counts: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    return {subsystem: dict(reasons) for subsystem, reasons in counts.items() if reasons}


def record_degraded(subsystem: str, reason: str, *, detail: str = "") -> None:
    """Count one degraded outcome of ``subsystem`` for ``reason``.

    ``reason`` is what is counted, so keep it short and stable (no ids, no
    exception messages). ``detail`` goes to the log line only — it is never
    counted or returned by the API. Never raises: telemetry must not turn a
    degraded outcome into a failed one.
    """
    try:
        subsystem = _clean(subsystem, "unknown")
        reason = _clean(reason, "unspecified")
        with _lock:
            reasons = _counts.setdefault(subsystem, {})
            if reason not in reasons and len(reasons) >= MAX_REASONS_PER_SUBSYSTEM:
                reason = OVERFLOW_REASON
            reasons[reason] = reasons.get(reason, 0) + 1
            _add(_pending, subsystem, reason, 1)
        logger.info("degraded %s: %s%s", subsystem, reason, f" ({detail})" if detail else "")
    except Exception:  # pragma: no cover - defensive
        logger.debug("record_degraded failed", exc_info=True)


def snapshot() -> dict[str, dict[str, int] | str]:
    """Every count since process start: ``{subsystem: {reason: count}}`` plus
    ``since`` (ISO-8601, UTC). Only subsystems that degraded at least once appear."""
    with _lock:
        out: dict[str, dict[str, int] | str] = {name: dict(reasons) for name, reasons in _counts.items()}
    out["since"] = _since.isoformat()
    return out


def totals() -> dict[str, int]:
    """``{subsystem: total}`` across reasons — the /health summary."""
    with _lock:
        return {name: sum(reasons.values()) for name, reasons in _counts.items()}


def pending() -> dict[str, dict[str, int]]:
    """``{subsystem: {reason: count}}`` counted since the last flush took them (a copy)."""
    with _lock:
        return _copy(_pending)


def reset() -> None:
    """Forget every count, pending ones included, and restart ``since`` (tests)."""
    global _since, _pending_since, _last_prune
    with _lock:
        _counts.clear()
        _pending.clear()
        _since = _pending_since = datetime.now(timezone.utc)
        _last_prune = None


# ---------------------------------------------------------------------------
# Flushing to Postgres
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Drained:
    """What :func:`drain` took: the counts and the window they were counted in."""

    window_start: datetime
    window_end: datetime
    counts: dict[str, dict[str, int]]


def drain() -> Drained:
    """Take the pending counts and start a new window.

    The lifetime counts (`snapshot()`, `totals()`, ``/health``) are untouched.
    A caller that cannot store what it took hands it back with `_restore`.
    """
    global _pending_since
    now = datetime.now(timezone.utc)
    with _lock:
        counts = _copy(_pending)
        _pending.clear()
        start, _pending_since = _pending_since, now
    return Drained(start, now, counts)


def _restore(batch: Drained) -> None:
    """Put back counts a flush could not write, so the next flush retries them
    over a window that starts where this one did."""
    global _pending_since
    with _lock:
        for subsystem, reasons in batch.counts.items():
            for reason, count in reasons.items():
                _add(_pending, subsystem, reason, count)
        _pending_since = min(_pending_since, batch.window_start)


def _default_factory():
    from intel_platform.db.engine import get_session_factory

    return get_session_factory()


async def flush(process: str, *, db_factory=None) -> int:
    """Write the pending counts to ``degraded_events``, one row per (subsystem,
    reason) stamped with ``process``, this host and the window; return the
    number of rows written.

    With nothing pending it touches no database. Never raises: a write that
    fails (Postgres down or not configured) is logged at debug and the counts
    are kept, so the next flush retries them. Cancellation is the exception: it
    also keeps the counts, then propagates. A flush that wrote rows also deletes
    the rows older than :data:`RETAIN_DAYS`, at most once an hour.
    """
    global _flushing, _flushes_done
    if process not in PROCESSES:
        logger.debug("Not flushing degraded counts for unknown process %r", process)
        return 0
    with _lock:
        _flushing += 1
    try:
        batch = drain()
        if not batch.counts:
            return 0
        written = 0
        try:
            from intel_platform.db.models import DegradedEvent

            host = socket.gethostname()
            rows = [
                DegradedEvent(process=process, host=host, subsystem=subsystem, reason=reason, count=count,
                              window_start=batch.window_start, window_end=batch.window_end)
                for subsystem, reasons in batch.counts.items()
                for reason, count in reasons.items()
            ]
            async with (db_factory or _default_factory())() as db:
                db.add_all(rows)
                await db.commit()
                written = len(rows)
        except Exception:
            logger.debug("Could not flush degraded counts for %s; keeping them for the next flush",
                         process, exc_info=True)
        finally:
            if not written:
                _restore(batch)
    finally:
        with _lock:
            _flushing -= 1
            _flushes_done += 1
    if written:
        await _prune_if_due(batch.window_end, db_factory)
    return written


async def _prune_if_due(now: datetime, db_factory) -> None:
    """Delete the rows whose window ended more than :data:`RETAIN_DAYS` before
    ``now``, if this process has not tried in the last :data:`_PRUNE_SECONDS`.

    Best effort, outside the flush's bookkeeping: rows that old are outside
    every read, and a failure is logged and tried again an hour later.
    """
    global _last_prune
    tick = time.monotonic()
    with _lock:
        if _last_prune is not None and tick - _last_prune < _PRUNE_SECONDS:
            return
        _last_prune = tick
    try:
        from sqlalchemy import delete

        from intel_platform.db.models import DegradedEvent

        async with (db_factory or _default_factory())() as db:
            result = await db.execute(
                delete(DegradedEvent).where(DegradedEvent.window_end < now - timedelta(days=RETAIN_DAYS))
            )
            await db.commit()
        if result.rowcount:
            logger.debug("Pruned %d degraded-count row(s) older than %d days", result.rowcount, RETAIN_DAYS)
    except Exception:
        logger.debug("Could not prune old degraded counts", exc_info=True)


async def flush_every(process: str, interval: float = FLUSH_SECONDS, *, db_factory=None) -> None:
    """Flush every ``interval`` seconds until cancelled."""
    while True:
        await asyncio.sleep(interval)
        await flush(process, db_factory=db_factory)


@contextlib.asynccontextmanager
async def flushing(process: str, *, interval: float = FLUSH_SECONDS, db_factory=None):
    """Flush every ``interval`` seconds while the body runs, and once more when it ends.

    The API's lifespan and the worker's entrypoint run inside this. The last
    flush is bounded, so an unreachable database cannot hold up a shutdown.
    """
    task = asyncio.create_task(flush_every(process, interval, db_factory=db_factory))
    try:
        yield task
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        try:
            await asyncio.wait_for(flush(process, db_factory=db_factory), timeout=_SHUTDOWN_FLUSH_SECONDS)
        except asyncio.TimeoutError:
            logger.debug("The final flush of degraded counts for %s timed out", process)


# ---------------------------------------------------------------------------
# Reading them back
# ---------------------------------------------------------------------------

async def _stored(since: datetime, db_factory) -> dict[str, dict[str, dict[str, int]]]:
    """``{process: {subsystem: {reason: count}}}`` over the rows whose window
    ended at or after ``since``."""
    from sqlalchemy import func, select

    from intel_platform.db.models import DegradedEvent

    out: dict[str, dict[str, dict[str, int]]] = {}
    async with (db_factory or _default_factory())() as db:
        result = await db.execute(
            select(DegradedEvent.process, DegradedEvent.subsystem, DegradedEvent.reason,
                   func.sum(DegradedEvent.count))
            .where(DegradedEvent.window_end >= since)
            .group_by(DegradedEvent.process, DegradedEvent.subsystem, DegradedEvent.reason)
        )
        for process, subsystem, reason, count in result.all():
            if process in PROCESSES and count:
                _add(out.setdefault(process, {}), subsystem, reason, int(count))
    return out


async def recent(*, hours: int = WINDOW_HOURS, live_process: str = API, db_factory=None) -> dict:
    """Degraded counts of the last ``hours`` hours, per process and in total.

    The stored rows of every process, plus this process's pending counts (not
    flushed yet) under ``live_process``. ``history_available`` is False when the
    rows could not be read: the counts are then this process's pending ones
    only, which is not the same as nothing having degraded elsewhere.

    A flush in this process moves counts from memory to the table; when one
    overlaps the read, the read is repeated so they are counted once.
    """
    if live_process not in PROCESSES:
        raise ValueError(f"unknown process {live_process!r}")
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stored: dict[str, dict[str, dict[str, int]]] = {}
    live: dict[str, dict[str, int]] = {}
    history_available = True
    for _attempt in range(3):
        with _lock:
            before = (_flushing, _flushes_done)
        try:
            stored, history_available = await _stored(since, db_factory), True
        except Exception:
            logger.warning("Could not read stored degraded counts", exc_info=True)
            stored, history_available = {}, False
        live = pending()
        with _lock:
            settled = before[0] == 0 and (_flushing, _flushes_done) == before
        if settled:
            break
        await asyncio.sleep(0.05)

    processes = {name: stored.get(name, {}) for name in PROCESSES}
    for subsystem, reasons in live.items():
        for reason, count in reasons.items():
            _add(processes[live_process], subsystem, reason, count)
    total: dict[str, dict[str, int]] = {}
    for counts in processes.values():
        for subsystem, reasons in counts.items():
            for reason, count in reasons.items():
                _add(total, subsystem, reason, count)
    return {
        "since": since.isoformat(),
        "processes": processes,
        "total": total,
        "history_available": history_available,
    }
