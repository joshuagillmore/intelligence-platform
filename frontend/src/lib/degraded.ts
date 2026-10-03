/**
 * Reading `GET /api/admin/degraded`: degraded outcomes (a chunk extracted by
 * NLP because the model failed, a document stored without embeddings, an
 * enrichment provider that errored...) counted per subsystem and reason over
 * the last 24 hours, by the API process and by the collection worker.
 *
 * The body (`Model<'DegradedResponse'>`) is
 * `{since, processes: {api, worker}, total, history_available}`, each count
 * map `{"<subsystem>": {"<reason>": count}}` holding only subsystems that
 * degraded at least once. `total` is the sum of the processes. When
 * `history_available` is false the backend could not read the stored counts,
 * so the figures are the API process's unflushed ones only: that is not
 * "nothing degraded" anywhere else.
 */
import type { Model } from './apiTypes';

export type DegradedBody = Model<'DegradedResponse'>;
type DegradedCounts = Model<'DegradedCounts'>;

/** The processes that report counts, in display order. */
export type DegradedProcess = keyof DegradedBody['processes'];
export const DEGRADED_PROCESSES: readonly DegradedProcess[] = ['api', 'worker'];

export interface DegradedReason {
  reason: string;
  count: number;
}

export interface DegradedSubsystem {
  subsystem: string;
  total: number;
  /** Most frequent first. */
  reasons: DegradedReason[];
}

/** A subsystem in the combined view, with its total in each process. */
export interface DegradedCombinedSubsystem extends DegradedSubsystem {
  byProcess: Record<DegradedProcess, number>;
}

export interface DegradedProcessCounts {
  total: number;
  /** Most degraded first. */
  subsystems: DegradedSubsystem[];
}

export interface DegradedSnapshot {
  /** Start of the window (24 hours before the answer), ISO-8601; '' if the body lacked it. */
  since: string;
  /** Every process combined, most degraded first. */
  subsystems: DegradedCombinedSubsystem[];
  /** Each process's own counts. */
  processes: Record<DegradedProcess, DegradedProcessCounts>;
  /** False when the stored counts could not be read: the figures are then the API process's own only. */
  historyAvailable: boolean;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function isDegradedBody(data: unknown): data is DegradedBody {
  return (
    isObject(data) &&
    isObject(data.processes) &&
    DEGRADED_PROCESSES.every((p) => isObject((data.processes as Record<string, unknown>)[p])) &&
    isObject(data.total) &&
    typeof data.history_available === 'boolean'
  );
}

/**
 * One count map, `{"<subsystem>": {"<reason>": count}}` (a process's, the
 * total, or a collection run's own `degraded`): the subsystems with a positive
 * total, most degraded first. Non-count values are ignored, not guessed at,
 * and anything but an object reads as no subsystems.
 */
export function readDegradedCounts(counts: DegradedCounts | null | undefined): DegradedSubsystem[] {
  if (!isObject(counts)) return [];
  const subsystems: DegradedSubsystem[] = [];
  for (const [subsystem, value] of Object.entries(counts)) {
    if (!isObject(value)) continue;
    const reasons = Object.entries(value)
      .filter((entry): entry is [string, number] => typeof entry[1] === 'number' && entry[1] > 0)
      .map(([reason, count]) => ({ reason, count }))
      .sort((a, b) => b.count - a.count || a.reason.localeCompare(b.reason));
    const total = reasons.reduce((sum, r) => sum + r.count, 0);
    if (total > 0) subsystems.push({ subsystem, total, reasons });
  }
  return subsystems.sort((a, b) => b.total - a.total || a.subsystem.localeCompare(b.subsystem));
}

/**
 * The snapshot in a `/admin/degraded` body. Throws when the body does not have
 * the contract's shape (including the per-process body that preceded it): an
 * unreadable answer must not render as "nothing degraded".
 */
export function readDegraded(data: unknown): DegradedSnapshot {
  if (!isDegradedBody(data)) {
    throw new Error('Unexpected degraded-outcomes response shape.');
  }
  const processes = Object.fromEntries(
    DEGRADED_PROCESSES.map((p) => {
      const subsystems = readDegradedCounts(data.processes[p]);
      return [p, { total: subsystems.reduce((sum, s) => sum + s.total, 0), subsystems }];
    }),
  ) as Record<DegradedProcess, DegradedProcessCounts>;
  const subsystems = readDegradedCounts(data.total).map((s) => ({
    ...s,
    byProcess: Object.fromEntries(
      DEGRADED_PROCESSES.map((p) => [p, processes[p].subsystems.find((x) => x.subsystem === s.subsystem)?.total ?? 0]),
    ) as Record<DegradedProcess, number>,
  }));
  return {
    since: typeof data.since === 'string' ? data.since : '',
    subsystems,
    processes,
    historyAvailable: data.history_available,
  };
}

/** Display names for the subsystems the backend counts. */
const SUBSYSTEM_LABELS: Record<string, string> = {
  extraction: 'Extraction',
  embeddings: 'Embeddings',
  enrichment: 'Enrichment',
  llm: 'LLM',
  topics: 'Topics',
  attack_mapping: 'ATT&CK mapping',
  collection: 'Collection',
};

export function subsystemLabel(subsystem: string): string {
  return SUBSYSTEM_LABELS[subsystem] ?? subsystem.replace(/_/g, ' ');
}

/** Display names for the processes. */
const PROCESS_LABELS: Record<DegradedProcess, string> = {
  api: 'API',
  worker: 'Worker',
};

export function processLabel(process: DegradedProcess): string {
  return PROCESS_LABELS[process];
}
