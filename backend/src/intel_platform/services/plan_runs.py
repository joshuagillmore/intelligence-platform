"""Collection-plan runs, apart from HTTP: which run is current, what state it
is in, and what a new run would collect.

The execute, status and cancel routes (``api/routes/collection_plans/
execution.py``) answer through here, so the guard that refuses a run and the
endpoint that reports one read the same thing. Whether a run is in flight is
answered from the job table, never from ``CollectionPlan.status`` (see
backend/CLAUDE.md, "Is a run in flight?").
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.collection import job_runner
from intel_platform.db import jobs

# The two events a run writes last. Used to split the activity trail into runs
# for the progress counts; whether a run is in flight comes from the job table.
TERMINAL_EVENTS = ("plan_completed", "plan_failed")


def current_run_events(events: list) -> list:
    """The events belonging to the most recent run only.

    Progress counts were summed over the whole activity trail, so a plan run
    twice reported the first run's successes and failures alongside the
    second's — "2 succeeded, 2 failed" for a run that collected one source.
    Harmless while a plan could only ever be executed once; now that a finished
    plan can be run again, the trail routinely holds several runs.
    """
    terminals = [i for i, e in enumerate(events) if e.event in TERMINAL_EVENTS]
    if not terminals:
        return events
    if terminals[-1] == len(events) - 1:
        # The trail ends on a finished run: it began after the one before it.
        return events[(terminals[-2] + 1) if len(terminals) > 1 else 0:]
    return events[terminals[-1] + 1:]


async def run_state_and_job(db: AsyncSession, plan_id: uuid.UUID):
    """(state, latest job, database now) — the one read behind the guard and the status endpoint."""
    job, now = await jobs.latest_job(db, plan_id)
    return job_runner.run_state(job, now), job, now


async def current_run_state(db: AsyncSession, plan_id: uuid.UUID) -> str:
    """``idle | running | stalled | completed | failed | cancelled`` for the plan's latest run.

    Read from the job table, which every run writes whichever process runs it
    (see collection/job_runner.run_state for the rules). The execute guard and
    ``/execution-status`` both go through here, so what the analyst is shown
    and what the API enforces cannot disagree. Only ``running`` blocks a run.
    """
    state, _job, _now = await run_state_and_job(db, plan_id)
    return state


@dataclass
class SourceReadiness:
    """How a plan's enabled sources divide up for an autonomous run."""

    # Not a file upload, and carrying the config its connector needs.
    executable: list = field(default_factory=list)
    # file_upload sources: an analyst has to upload the file.
    file_only: list = field(default_factory=list)
    # Not a file upload, but missing url/feed_url/base_url: the run skips them.
    missing_config: list = field(default_factory=list)
    # Every enabled source that is not a file upload: what a run is launched with.
    automatic: list = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def source_readiness(sources: list) -> SourceReadiness:
    """Which of a plan's sources a run would collect, and a warning for each kind it would not."""
    from intel_platform.services.plan_executor import _has_valid_config
    executable = [s for s in sources if s.enabled and s.source_type != "file_upload" and _has_valid_config(s.source_type, s.config or {})]
    file_only = [s for s in sources if s.enabled and s.source_type == "file_upload"]
    missing_config = [s for s in sources if s.enabled and s.source_type != "file_upload" and not _has_valid_config(s.source_type, s.config or {})]

    warnings = []
    if missing_config:
        names = [s.name for s in missing_config]
        warnings.append(f"{len(missing_config)} source(s) missing required config (url/feed_url/base_url) and will be skipped: {', '.join(names[:5])}")
    if file_only:
        warnings.append(f"{len(file_only)} file_upload source(s) require manual upload")
    if not executable and not file_only:
        warnings.append("No sources are ready for autonomous execution. Add URLs to source configs or upload files manually.")

    automatic = [s for s in sources if s.enabled and s.source_type != "file_upload"]
    return SourceReadiness(
        executable=executable,
        file_only=file_only,
        missing_config=missing_config,
        automatic=automatic,
        warnings=warnings,
    )


def run_routing_rules(routing_rules: dict | None, source_limit: int | None, max_results: int) -> dict:
    """The plan's routing rules for a new run, carrying that run's budget and page size.

    The budget belongs to this run only. It used to persist when a later run
    was started without one, so that run was assessed against a limit it was
    never given.
    """
    rules = {k: v for k, v in (routing_rules or {}).items() if k != "source_limit"}
    if source_limit:
        rules["source_limit"] = source_limit
    rules["max_results_per_source"] = max_results
    return rules
