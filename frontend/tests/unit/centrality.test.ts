import { describe, it, expect } from 'vitest';
import { rankByDegree } from '@/lib/centrality';

/**
 * /graph/centrality returns `degree` (a link count). The project hub read a
 * `centrality` field that does not exist, so every Key Entities row showed
 * 0.000 / "Low". The hub now reads `degree` and scales it by the largest
 * degree in the list, so the best-connected entity scores 1.
 */
describe('rankByDegree', () => {
  const rows = [
    { id: 'a', name: 'APT29', entity_type: 'ThreatActor', degree: 12 },
    { id: 'b', name: 'Cozy Bear C2', entity_type: 'Domain', degree: 6 },
    { id: 'c', name: 'Rotterdam', entity_type: 'Location', degree: 3 },
  ];

  it('reads degree and normalises by the maximum in the list', () => {
    const ranked = rankByDegree(rows);
    expect(ranked.map((r) => r.score)).toEqual([1, 0.5, 0.25]);
    expect(ranked.map((r) => r.degree)).toEqual([12, 6, 3]);
  });

  it('never reports every entity as zero when the rows have degrees', () => {
    expect(rankByDegree(rows).every((r) => r.score === 0)).toBe(false);
  });

  it('sorts by degree even if the server did not', () => {
    const ranked = rankByDegree([rows[2], rows[0], rows[1]]);
    expect(ranked.map((r) => r.id)).toEqual(['a', 'b', 'c']);
  });

  it('limits the list', () => {
    expect(rankByDegree(rows, 2)).toHaveLength(2);
  });

  it('scores all-zero degrees as 0 rather than NaN', () => {
    const ranked = rankByDegree([{ id: 'x', name: 'x', entity_type: 'Person', degree: 0 }]);
    expect(ranked[0].score).toBe(0);
  });

  it('returns [] for a body that is not a list', () => {
    expect(rankByDegree({ detail: 'nope' })).toEqual([]);
    expect(rankByDegree(null)).toEqual([]);
  });
});
