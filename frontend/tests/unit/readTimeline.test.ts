import { describe, it, expect } from 'vitest';
import { readTimeline } from '@/lib/timeline';

/**
 * GET /timeline returns `events`, `count` (this page), `total` (true count),
 * `truncated`, and `types_present`. The page used a fixed type list that left
 * out TTP, Malware, Campaign and URL (so those events could never be shown),
 * and reported the truncated page length as if it were the whole timeline.
 */
describe('readTimeline', () => {
  const ev = (id: string, entity_type: string) => ({
    id, name: id, entity_type, timestamp: '2026-09-01T00:00:00Z', event_type: 'event',
  });

  it('reads the page, the true total and the truncation flag', () => {
    const t = readTimeline({
      events: [ev('a', 'TTP'), ev('b', 'Person')],
      count: 2, total: 812, truncated: true, types_present: ['Person', 'TTP', 'Malware'],
    });
    expect(t.events).toHaveLength(2);
    expect(t.count).toBe(2);
    expect(t.total).toBe(812);
    expect(t.truncated).toBe(true);
  });

  it('builds the type list from types_present, including types a fixed list omitted', () => {
    const t = readTimeline({
      events: [ev('a', 'TTP')], count: 1, total: 1, truncated: false,
      types_present: ['Campaign', 'Malware', 'TTP', 'URL'],
    });
    expect(t.types).toEqual(expect.arrayContaining(['Campaign', 'Malware', 'TTP', 'URL']));
  });

  it('also lists any type seen in the events, so no event is unfilterable', () => {
    const t = readTimeline({
      events: [ev('a', 'Satellite')], count: 1, total: 1, truncated: false, types_present: ['Person'],
    });
    expect(t.types).toEqual(expect.arrayContaining(['Person', 'Satellite']));
  });

  it('treats a correctly shaped empty timeline as empty, not as an error', () => {
    const t = readTimeline({ events: [], count: 0, total: 0, truncated: false, types_present: [] });
    expect(t.events).toEqual([]);
    expect(t.total).toBe(0);
    expect(t.types).toEqual([]);
  });

  it('falls back to the page length when total is missing, and never reports less than the page', () => {
    expect(readTimeline({ events: [ev('a', 'Person')] }).total).toBe(1);
    expect(readTimeline({ events: [ev('a', 'Person'), ev('b', 'Person')], total: 1 }).total).toBe(2);
  });

  it('throws on a body with no events list', () => {
    expect(() => readTimeline({ detail: 'nope' })).toThrow();
    expect(() => readTimeline(null)).toThrow();
  });
});
