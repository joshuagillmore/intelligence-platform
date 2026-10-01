"""Collection worker: executes queued collection jobs outside the API process.

    uv run python -m intel_platform.worker            # poll forever
    uv run python -m intel_platform.worker --once     # run at most one job, then exit

Used when ``COLLECTION_WORKER_MODE=worker``: ``/collection-plans/{id}/execute``
then only inserts a ``queued`` row in ``collection_jobs`` and this process
claims it (``FOR UPDATE SKIP LOCKED``, so several workers never take the same
job), stamps its ``worker_id``, heartbeats it every 10 s from a background task
while the agentic loop and the requirement passes run, and writes the terminal
status and a sanitised error. See ``collection/job_runner.py``.

One job at a time per process; run more processes for more parallelism. On
SIGTERM/SIGINT it stops claiming, cancels the job in hand (recorded ``failed``:
"the worker stopped") and exits 0. A worker that dies without that leaves its
job ``running`` with a heartbeat that stops; after ``collection_stall_seconds``
the plan reads ``stalled`` and may be run again.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import itertools
import logging
import signal
import sys

from intel_platform.collection import job_runner
from intel_platform.db import jobs

logger = logging.getLogger("intel_platform.worker")

_POLL_SECONDS = 2.0
# Backoff ceiling while the database is unreachable or not yet migrated.
_MAX_BACKOFF_SECONDS = 30.0

_sequence = itertools.count(1)


def new_worker_id() -> str:
    """Unique per worker loop, even for two loops in one process (tests)."""
    return f"{job_runner.process_worker_id('worker')}:{next(_sequence)}"[:128]


async def _wait(stop: asyncio.Event, seconds: float) -> None:
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=seconds)


async def run_worker(
    *,
    stop: asyncio.Event,
    db_factory=None,
    get_store=None,
    get_provider=None,
    worker_id: str | None = None,
    poll_seconds: float = _POLL_SECONDS,
    once: bool = False,
    heartbeat_seconds: float | None = None,
) -> int:
    """Claim and run jobs until ``stop`` is set (or after one job with ``once``).

    Returns the number of jobs run.
    """
    if db_factory is None:
        from intel_platform.db.engine import get_session_factory

        db_factory = get_session_factory()
    worker_id = worker_id or new_worker_id()
    logger.info("Collection worker %s started", worker_id)
    ran = 0
    backoff = poll_seconds
    while not stop.is_set():
        try:
            async with db_factory() as db:
                job_id = await jobs.claim_next(db, worker_id)
            backoff = poll_seconds
        except Exception:
            # Postgres down, or the API has not created the table yet.
            logger.warning("Collection worker could not poll for jobs; retrying in %.0f s", backoff, exc_info=True)
            await _wait(stop, backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)
            continue
        if job_id is None:
            if once:
                break
            await _wait(stop, poll_seconds)
            continue

        logger.info("Collection worker %s claimed job %s", worker_id, job_id)
        task = asyncio.create_task(job_runner.run_job(
            job_id, worker_id=worker_id, db_factory=db_factory,
            get_store=get_store, get_provider=get_provider, heartbeat_seconds=heartbeat_seconds,
        ))
        stopper = asyncio.create_task(stop.wait())
        await asyncio.wait({task, stopper}, return_when=asyncio.FIRST_COMPLETED)
        stopper.cancel()
        if not task.done():
            logger.warning("Collection worker %s stopping; cancelling job %s", worker_id, job_id)
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            try:
                await task
            except Exception:
                # run_job records its own failures; anything escaping it is a
                # bug, and must not take the worker down with it.
                logger.exception("Collection job %s escaped its runner", job_id)
        ran += 1
        if once:
            break
    logger.info("Collection worker %s stopped after %d job(s)", worker_id, ran)
    return ran


def _install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError, ValueError):
            # Windows' event loops have no add_signal_handler.
            signal.signal(sig, lambda *_args: loop.call_soon_threadsafe(stop.set))


async def _main(args: argparse.Namespace) -> int:
    from intel_platform.api.deps import get_neo4j_driver
    from intel_platform.db.engine import get_engine
    from intel_platform.graph.store import GraphStore

    stop = asyncio.Event()
    _install_signal_handlers(stop)
    driver = get_neo4j_driver()
    store = GraphStore(driver)
    try:
        await run_worker(stop=stop, get_store=lambda: store, poll_seconds=args.poll_seconds, once=args.once)
    finally:
        driver.close()
        await get_engine().dispose()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m intel_platform.worker", description=__doc__.splitlines()[0])
    parser.add_argument("--once", action="store_true", help="run at most one queued job, then exit")
    parser.add_argument("--poll-seconds", type=float, default=_POLL_SECONDS, help="idle poll interval")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return asyncio.run(_main(args))


if __name__ == "__main__":
    sys.exit(main())
