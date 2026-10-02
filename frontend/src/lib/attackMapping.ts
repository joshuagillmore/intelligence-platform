import type { ResponseOf } from './apiTypes';

/**
 * Wording for a `POST /attack/map` result.
 *
 * The backend returns `mapped` and `skipped` counts, `skip_reasons` (reason ->
 * count, every skipped TTP attributed to exactly one), `stale_removed` when
 * run with `remap`, and `reason`/`detail` when the whole batch could not run.
 * An unreachable LLM is a 503, handled by the caller as a failure, never here.
 */
export type AttackMapResult = ResponseOf<'/api/attack/map', 'post'>;

export interface MapResultNote {
  text: string;
  tone: 'ok' | 'warn';
  /** The technique catalogue is not embedded, so the Embed step comes first. */
  needsEmbed: boolean;
}

/** Each reason as it reads after a count ("3 rejected by the model"). */
const REASON_LABEL: Record<string, string> = {
  no_candidates: 'with no nearby technique',
  rejected: 'rejected by the model',
  unparsed: 'with an unreadable model reply',
  embedding_unavailable: 'not embeddable (embedding provider unavailable)',
  candidate_retrieval_failed: 'not searchable (candidate retrieval failed)',
  technique_catalogue_not_embedded: 'unmatched because the techniques are not embedded',
};

const NOT_EMBEDDED = 'technique_catalogue_not_embedded';

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`;
}

function reasonBreakdown(reasons: Record<string, number>): string {
  return Object.entries(reasons)
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([reason, n]) => `${n} ${REASON_LABEL[reason] ?? reason.replace(/_/g, ' ')}`)
    .join(', ');
}

export function describeMapResult(result: AttackMapResult, opts: { isAdmin: boolean }): MapResultNote {
  const reasons = result.skip_reasons ?? {};
  const mapped = result.mapped ?? 0;
  const skipped = result.skipped ?? 0;
  const needsEmbed = result.reason === NOT_EMBEDDED || (reasons[NOT_EMBEDDED] ?? 0) > 0;
  const breakdown = reasonBreakdown(reasons);
  const stale = result.stale_removed
    ? ` · ${plural(result.stale_removed, 'earlier AI mapping')} removed (no longer confirmed)`
    : '';
  const embedAdvice = needsEmbed
    ? opts.isAdmin
      ? ' Run "Embed techniques" first, then map again.'
      : ' Ask an administrator to run "Embed techniques", then map again.'
    : '';

  if (mapped > 0) {
    return {
      text: `AI mapped ${plural(mapped, 'TTP')} to ATT&CK${skipped ? ` · ${skipped} skipped (${breakdown || 'no reason given'})` : ''}${stale}.${embedAdvice}`,
      tone: 'ok',
      needsEmbed,
    };
  }
  if (skipped > 0) {
    // The whole batch could not run: say why in the backend's words.
    const why = result.reason
      ? result.detail || REASON_LABEL[result.reason] || result.reason.replace(/_/g, ' ')
      : `${skipped} skipped (${breakdown || 'no reason given'})`;
    return {
      text: `No TTPs were mapped: ${why.replace(/\.$/, '')}${stale}.${embedAdvice}`,
      tone: 'warn',
      needsEmbed,
    };
  }
  return {
    text: `No unmapped TTPs to map — everything with a match is already resolved${stale}.`,
    tone: 'ok',
    needsEmbed: false,
  };
}
