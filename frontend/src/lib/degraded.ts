/**
 * Reading `GET /api/admin/degraded`: degraded outcomes (a chunk extracted by
 * NLP because the model failed, a document stored without embeddings, an
 * enrichment provider that errored...) counted per subsystem and reason since
 * the API process started.
 *
 * The body is `{"since": "<ISO-8601>", "<subsystem>": {"<reason>": count}}`.
 * `since` is the only non-object key, and only subsystems that degraded at
 * least once appear, so a body with nothing but `since` means nothing degraded.
 */

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

export interface DegradedSnapshot {
  /** When counting started (process start), ISO-8601; '' if the body lacked it. */
  since: string;
  /** Most degraded first. */
  subsystems: DegradedSubsystem[];
}

/**
 * The snapshot in a `/admin/degraded` body. Throws when the body is not an
 * object: an unreadable answer must not render as "nothing degraded".
 */
export function readDegraded(data: unknown): DegradedSnapshot {
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    throw new Error('Unexpected degraded-outcomes response shape.');
  }
  const body = data as Record<string, unknown>;
  const since = typeof body.since === 'string' ? body.since : '';
  const subsystems: DegradedSubsystem[] = [];
  for (const [subsystem, value] of Object.entries(body)) {
    if (subsystem === 'since' || !value || typeof value !== 'object' || Array.isArray(value)) continue;
    const reasons = Object.entries(value as Record<string, unknown>)
      .filter((entry): entry is [string, number] => typeof entry[1] === 'number' && entry[1] > 0)
      .map(([reason, count]) => ({ reason, count }))
      .sort((a, b) => b.count - a.count || a.reason.localeCompare(b.reason));
    const total = reasons.reduce((sum, r) => sum + r.count, 0);
    if (total > 0) subsystems.push({ subsystem, total, reasons });
  }
  subsystems.sort((a, b) => b.total - a.total || a.subsystem.localeCompare(b.subsystem));
  return { since, subsystems };
}

/** Display names for the subsystems the backend counts (contract 1). */
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
