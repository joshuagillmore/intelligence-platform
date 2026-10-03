'use client';
import { useCallback, useEffect, useState } from 'react';
import { adminApi } from '@/lib/api';
import {
  DEGRADED_PROCESSES,
  processLabel,
  readDegraded,
  subsystemLabel,
  type DegradedSnapshot,
} from '@/lib/degraded';
import { getErrorMessage } from '@/lib/errorMessages';

/** How many reasons each subsystem row lists before "+N more". */
const TOP_REASONS = 3;

/** ` (since <local time>)`, or nothing when the body had no readable `since`. */
function sinceSuffix(since: string): string {
  const d = new Date(since);
  return since && !Number.isNaN(d.getTime()) ? ` (since ${d.toLocaleString()})` : '';
}

/**
 * Degraded outcomes (admin): work that finished, but worse than asked. A quiet
 * provider outage shows up here as a number rather than as results that are
 * merely thinner than they should be. Over the last 24 hours, from the API and
 * the collection worker (`GET /api/admin/degraded`): one total per process,
 * then one row per subsystem with the combined total, its split by process and
 * its top reasons.
 */
export default function DegradedCard() {
  const [snapshot, setSnapshot] = useState<DegradedSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await adminApi.degraded();
      setSnapshot(readDegraded(res.data));
      setError(null);
    } catch (e) {
      setSnapshot(null);
      setError(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="bg-navy-800 border border-navy-600 rounded-lg p-6">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-lg font-semibold">Degraded Outcomes</h3>
        <button onClick={load} disabled={loading} className="text-xs text-accent-blue hover:text-blue-400 disabled:opacity-50">
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>
      <p className="text-[11px] text-gray-500 mb-4 leading-snug">
        Work that completed, but worse than asked: a chunk extracted without the model, a document
        stored without embeddings, a provider that errored. Counted over the last 24 hours by the API
        and the collection worker.
      </p>
      {error ? (
        <p role="alert" className="text-red-400 text-sm">Could not load: {error}</p>
      ) : !snapshot ? (
        <p className="text-gray-500 text-sm">Loading...</p>
      ) : (
        <>
          {!snapshot.historyAvailable && (
            <p role="note" className="text-[11px] text-amber-400 mb-3 leading-snug">
              Stored counts unavailable: showing this API process only.
            </p>
          )}
          {snapshot.subsystems.length === 0 ? (
            snapshot.historyAvailable ? (
              <p className="text-sm text-green-400">
                No degraded outcomes in the last 24 hours{sinceSuffix(snapshot.since)}.
              </p>
            ) : (
              <p className="text-sm text-gray-400">Nothing counted by this API process since its last flush.</p>
            )
          ) : (
            <>
              <ul className="grid grid-cols-2 gap-2 mb-3" aria-label="Degraded outcomes by process">
                {DEGRADED_PROCESSES.map((process) => {
                  const known = snapshot.historyAvailable || process === 'api';
                  const total = snapshot.processes[process].total;
                  return (
                    <li key={process} className="bg-navy-700 rounded px-3 py-2 flex items-center justify-between gap-2">
                      <span className="text-xs text-gray-400">{processLabel(process)}</span>
                      {known ? (
                        <span className="text-sm font-mono text-threat-medium">{total.toLocaleString()}</span>
                      ) : (
                        <span className="text-[11px] text-gray-500">unavailable</span>
                      )}
                    </li>
                  );
                })}
              </ul>
              <ul className="space-y-2" aria-label="Degraded outcomes by subsystem">
                {snapshot.subsystems.map(({ subsystem, total, reasons, byProcess }) => (
                  <li key={subsystem} className="bg-navy-700 rounded p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-gray-200">{subsystemLabel(subsystem)}</span>
                      <span className="text-sm font-mono text-threat-medium" title={`${total} degraded outcome${total === 1 ? '' : 's'}`}>
                        {total.toLocaleString()}
                      </span>
                    </div>
                    {snapshot.historyAvailable && (
                      <p className="text-[10px] text-gray-500 mt-0.5">
                        {DEGRADED_PROCESSES.map((p) => `${processLabel(p)} ${byProcess[p].toLocaleString()}`).join(' · ')}
                      </p>
                    )}
                    <ul className="mt-1.5 space-y-0.5">
                      {reasons.slice(0, TOP_REASONS).map(({ reason, count }) => (
                        <li key={reason} className="flex items-center justify-between gap-2 text-xs">
                          <span className="font-mono text-gray-400 truncate" title={reason}>{reason}</span>
                          <span className="text-gray-500 flex-none">{count.toLocaleString()}</span>
                        </li>
                      ))}
                      {reasons.length > TOP_REASONS && (
                        <li className="text-[10px] text-gray-500">
                          +{reasons.length - TOP_REASONS} more reason{reasons.length - TOP_REASONS === 1 ? '' : 's'}
                        </li>
                      )}
                    </ul>
                  </li>
                ))}
              </ul>
              <p className="text-[11px] text-gray-500 mt-3">Last 24 hours{sinceSuffix(snapshot.since)}.</p>
            </>
          )}
        </>
      )}
    </div>
  );
}
