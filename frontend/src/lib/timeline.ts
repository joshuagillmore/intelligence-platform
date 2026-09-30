/**
 * Reading a `GET /timeline` body.
 *
 * The backend returns the newest events first (by event date, falling back to
 * when the entity was created), capped to a page: `events`, `count` (this
 * page), `total` (every matching event), `truncated`, and `types_present` (the
 * entity types that occur in the project's timeline, not just in this page).
 */
export interface TimelineEvent {
  id: string;
  name: string;
  entity_type: string;
  timestamp: string;
  event_type: string;
}

export interface Timeline {
  events: TimelineEvent[];
  /** Events in this page. */
  count: number;
  /** Events that exist in full; never less than `count`. */
  total: number;
  truncated: boolean;
  /** Every type to offer in the filter: `types_present` plus any type seen in
   *  the page, so no loaded event is unfilterable. Sorted. */
  types: string[];
}

export function readTimeline(data: unknown): Timeline {
  const body = (data && typeof data === 'object' && !Array.isArray(data) ? data : null) as
    | Record<string, unknown>
    | null;
  if (!body || !Array.isArray(body.events)) throw new Error('Unexpected timeline response shape.');
  const events = body.events.filter(
    (e): e is TimelineEvent => !!e && typeof e === 'object' && typeof (e as TimelineEvent).id === 'string',
  );
  const count = events.length;
  const total = typeof body.total === 'number' && Number.isFinite(body.total) ? Math.max(body.total, count) : count;
  const truncated = body.truncated === true || total > count;
  const present = Array.isArray(body.types_present)
    ? body.types_present.filter((t): t is string => typeof t === 'string' && t.length > 0)
    : [];
  const types = Array.from(new Set([...present, ...events.map((e) => e.entity_type).filter(Boolean)])).sort();
  return { events, count, total, truncated, types };
}
