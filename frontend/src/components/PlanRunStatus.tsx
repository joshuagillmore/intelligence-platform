'use client';
import { useState } from 'react';
import { collectionPlansApi, type PlanCancelResult, type PlanExecutionStatus } from '@/lib/api';
import { readDegraded, subsystemLabel } from '@/lib/degraded';
import { getErrorMessage } from '@/lib/errorMessages';
import { canCancelRun, runBadge, type RunTone } from '@/lib/planRun';

const TONE_CLASS: Record<RunTone, string> = {
  live: 'bg-accent-periwinkle/20 text-accent-periwinkle',
  warn: 'bg-amber-500/20 text-amber-400',
  error: 'bg-red-500/20 text-red-400',
  muted: 'bg-gray-500/20 text-gray-400',
};

/**
 * Whether work is happening on a plan now, which its lifecycle status cannot
 * tell you: Collecting, Queued, Stopping (cancelled, winding down), Stalled,
 * Failed or Cancelled. Nothing when the plan is idle or its last run completed.
 */
export function PlanRunBadge({ run }: { run: PlanExecutionStatus | null | undefined }) {
  const badge = runBadge(run);
  if (!badge) return null;
  return (
    <span
      className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-wider flex items-center gap-1 ${TONE_CLASS[badge.tone]}`}
      title={badge.title}
    >
      {badge.spinning && <span className="material-symbols-outlined text-[12px] animate-spin">sync</span>}
      {badge.label}
    </span>
  );
}

interface CancelRunButtonProps {
  planId: string;
  run: PlanExecutionStatus | null | undefined;
  /** Re-read the run state; the run reads `running` until it has stopped. */
  onCancelled: (result: PlanCancelResult) => void;
  onError: (message: string) => void;
}

/** Cancel a plan's live run. Shown only while there is one to cancel. */
export function CancelRunButton({ planId, run, onCancelled, onError }: CancelRunButtonProps) {
  const [cancelling, setCancelling] = useState(false);
  if (!canCancelRun(run)) return null;
  return (
    <button
      type="button"
      disabled={cancelling}
      onClick={async (e) => {
        // Inside a clickable plan header: cancelling must not also toggle it.
        e.stopPropagation();
        setCancelling(true);
        try {
          const res = await collectionPlansApi.cancel(planId);
          onCancelled(res.data);
        } catch (err) {
          onError(`Could not cancel the run: ${getErrorMessage(err)}`);
        } finally {
          setCancelling(false);
        }
      }}
      className="text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-wider border border-red-500/30 text-red-400 hover:bg-red-900/20 transition-colors disabled:opacity-50"
      title="Stop this collection run before its next source"
    >
      {cancelling ? 'Cancelling…' : 'Cancel'}
    </button>
  );
}

/** The run's own degraded outcomes and, for a failed run, why it failed. */
export function RunDetails({ run }: { run: PlanExecutionStatus | null | undefined }) {
  if (!run) return null;
  const degraded = run.degraded && Object.keys(run.degraded).length > 0
    ? readDegraded({ ...run.degraded }).subsystems
    : [];
  const failure = run.status === 'failed' ? (run.error || run.message || '') : '';
  if (degraded.length === 0 && !failure) return null;
  return (
    <div className="space-y-1">
      {failure && (
        <p role="alert" className="text-[11px] text-red-400">Run failed: {failure}</p>
      )}
      {degraded.length > 0 && (
        <div>
          <span className="text-[10px] text-gray-500 uppercase tracking-widest font-bold block mb-1">Degraded this run</span>
          <ul className="space-y-0.5">
            {degraded.map(({ subsystem, total, reasons }) => (
              <li key={subsystem} className="text-[11px] text-gray-400">
                <span className="text-threat-medium font-mono">{total}</span>{' '}
                <span className="text-gray-300">{subsystemLabel(subsystem)}</span>
                <span className="text-gray-500">
                  {' '}({reasons.slice(0, 3).map(r => `${r.reason} ${r.count}`).join(', ')}{reasons.length > 3 ? ', …' : ''})
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
