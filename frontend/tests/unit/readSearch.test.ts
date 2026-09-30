import { describe, it, expect } from 'vitest';
import { readSearch } from '@/lib/search';

/**
 * Keyword search matches entity names only, capped to a page. `total` used to
 * be the capped page length, so "50 results" meant "at least 50". The API now
 * returns `count` (this page), `total` (every match) and `truncated`; the page
 * must say "N of M".
 */
describe('readSearch', () => {
  const ent = { id: 'e1', name: 'APT29', entity_type: 'ThreatActor' };
  const doc = { id: 'd1', name: 'report.pdf', entity_type: 'Document', preview: 'x' };
  const rep = { id: 'r1', name: 'INTSUM', entity_type: 'Report', report_type: 'intsum' };

  it('reads categorized lists with the true total and truncation', () => {
    const r = readSearch({ entities: [ent], documents: [doc], reports: [rep], count: 3, total: 212, truncated: true });
    expect(r.entities).toEqual([ent]);
    expect(r.documents).toEqual([doc]);
    expect(r.reports).toEqual([rep]);
    expect(r.count).toBe(3);
    expect(r.total).toBe(212);
    expect(r.truncated).toBe(true);
  });

  it('splits a flat results list by entity type', () => {
    const r = readSearch({ results: [ent, doc, rep], count: 3, total: 3, truncated: false });
    expect(r.entities).toEqual([ent]);
    expect(r.documents).toEqual([doc]);
    expect(r.reports).toEqual([rep]);
  });

  it('counts the rows shown when count is absent, and never reports a total below it', () => {
    const r = readSearch({ entities: [ent], documents: [doc], reports: [], total: 1 });
    expect(r.count).toBe(2);
    expect(r.total).toBe(2);
  });

  it('marks the result truncated when total exceeds what was returned', () => {
    const r = readSearch({ entities: [ent], documents: [], reports: [], count: 1, total: 9 });
    expect(r.truncated).toBe(true);
  });

  it('treats a correctly shaped empty result as empty, not as an error', () => {
    const r = readSearch({ entities: [], documents: [], reports: [], count: 0, total: 0, truncated: false });
    expect(r.count).toBe(0);
    expect(r.total).toBe(0);
  });

  it('throws on a body with neither shape', () => {
    expect(() => readSearch({ detail: 'x' })).toThrow();
    expect(() => readSearch(null)).toThrow();
  });
});
