import { describe, it, expect } from 'vitest';
import { readWatchlist } from '@/lib/api';

/**
 * GET /watchlist returns `{watched_entities: [...], count}`. Four consumers
 * read `entities`, `watchlist`, a bare array or `.items`, so the watchlist was
 * always empty and its badge always 0. One reader, used everywhere, pins the
 * real shape; anything else is an error, not an empty list.
 */
describe('readWatchlist', () => {
  const entity = { id: 'e1', name: 'APT29', entity_type: 'ThreatActor', relationship_count: 4 };

  it('reads watched_entities from the real response shape', () => {
    expect(readWatchlist({ watched_entities: [entity], count: 1 })).toEqual([entity]);
  });

  it('returns an empty list for a correctly shaped empty response (the true empty state)', () => {
    expect(readWatchlist({ watched_entities: [], count: 0 })).toEqual([]);
  });

  it('rejects the shapes the old consumers guessed at instead of reading them as empty', () => {
    expect(() => readWatchlist([entity])).toThrow();
    expect(() => readWatchlist({ entities: [entity] })).toThrow();
    expect(() => readWatchlist({ items: [entity] })).toThrow();
    expect(() => readWatchlist(null)).toThrow();
  });

  it('drops malformed rows but keeps the good ones', () => {
    expect(readWatchlist({ watched_entities: [entity, null, { name: 'no id' }], count: 3 })).toEqual([entity]);
  });
});
