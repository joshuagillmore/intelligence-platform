/**
 * Reading a collection plan's run state (`GET /collection-plans/{id}/
 * execution-status`, backed by the job table) for display, and the execute
 * response for what to tell the analyst.
 *
 * `status` is the run state; `job_status` is the job row's. They differ in two
 * cases that matter here: a queued run reads `running` (so pollers keep
 * polling) with `job_status: queued`, and a cancelled run that is still winding
 * down reads `running` with `job_status: cancelled` until it stops.
 */
import type { PlanExecuteResult, PlanExecutionStatus } from './api';

export type RunTone = 'live' | 'warn' | 'error' | 'muted';

export interface RunBadgeInfo {
  label: string;
  tone: RunTone;
  /** Work is happening (or winding down) right now. */
  spinning: boolean;
  title: string;
}

/** A run that is in flight, including one queued or winding down. */
export function isRunInFlight(run: PlanExecutionStatus | null | undefined): boolean {
  return run?.status === 'running';
}

/** Cancelled while mid-flight: stops before its next source. */
export function isRunStopping(run: PlanExecutionStatus | null | undefined): boolean {
  return run?.status === 'running' && run.job_status === 'cancelled';
}

/** Whether `POST /cancel` has something to cancel: a live run (queued or
 *  running) that is not already stopping, or a stalled one. */
export function canCancelRun(run: PlanExecutionStatus | null | undefined): boolean {
  if (!run) return false;
  if (run.status === 'stalled') return true;
  return run.status === 'running' && run.job_status !== 'cancelled';
}

function minutes(seconds: number | null | undefined): number {
  return Math.round((seconds || 0) / 60);
}

/** The badge for a plan's run, or null when nothing is worth a badge (idle,
 *  or the last run completed). */
export function runBadge(run: PlanExecutionStatus | null | undefined): RunBadgeInfo | null {
  if (!run) return null;
  switch (run.status) {
    case 'running':
      if (run.job_status === 'cancelled') {
        return { label: 'Stopping', tone: 'warn', spinning: true, title: run.message || 'Cancelled; the run stops before its next source.' };
      }
      if (run.job_status === 'queued') {
        return { label: 'Queued', tone: 'live', spinning: false, title: run.message || 'Waiting for a collection worker.' };
      }
      return { label: 'Collecting', tone: 'live', spinning: true, title: run.message || 'A collection run is in flight.' };
    case 'stalled': {
      const silent = run.seconds_since_heartbeat ?? run.seconds_since_last_event;
      return {
        label: 'Stalled',
        tone: 'warn',
        spinning: false,
        title: `Silent for ${minutes(silent)} min — the run is presumed dead. Running again is safe.`,
      };
    }
    case 'failed':
      return { label: 'Failed', tone: 'error', spinning: false, title: run.error || run.message || 'The collection run ended with an error.' };
    case 'cancelled':
      return { label: 'Cancelled', tone: 'muted', spinning: false, title: run.message || 'The collection run was cancelled.' };
    default:
      return null;
  }
}

/**
 * What to tell the analyst after `POST /execute`, or null when the run simply
 * started. Nothing to run, a queue wait and skipped sources are all things an
 * analyst would otherwise only discover by watching nothing happen.
 */
export function executeNotice(result: Partial<PlanExecuteResult> | null | undefined): string | null {
  if (!result) return null;
  const parts: string[] = [];
  if (result.execution_status === 'no_executable_sources' || result.execution_status === 'queued') {
    if (result.message) parts.push(result.message);
  }
  if (result.sources_over_budget) {
    parts.push(`${result.sources_over_budget} source(s) exceed this run's source limit.`);
  }
  for (const w of result.warnings ?? []) parts.push(w.endsWith('.') ? w : `${w}.`);
  return parts.length > 0 ? parts.join(' ') : null;
}
