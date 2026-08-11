import { describe, it, expect } from 'vitest';

/** The reducer from the geo header, kept in sync with src/app/geo/page.tsx. */
type Loc = { connection_count?: number; connections?: number };
const totalConnections = (locations: Loc[]) =>
  locations.reduce((sum, l) => sum + (l.connection_count ?? l.connections ?? 0), 0);

describe('geo header connection count', () => {
  it('counts the field the API actually sends', () => {
    // The defect: the page read `connections`, which no response carries, so
    // the header said "0 Connections" beside a map drawing 128 of them.
    const fromApi = [{ connection_count: 30 }, { connection_count: 5 }, { connection_count: 0 }];
    expect(totalConnections(fromApi)).toBe(35);
  });

  it('still honours the legacy field the fallback path builds', () => {
    expect(totalConnections([{ connections: 4 }, { connections: 2 }])).toBe(6);
  });

  it('prefers the API field when both are present', () => {
    expect(totalConnections([{ connection_count: 30, connections: 0 }])).toBe(30);
  });

  it('treats a genuine zero as zero, not as missing', () => {
    // `??` rather than `||`: a location with no connections must not fall
    // through to the other field.
    expect(totalConnections([{ connection_count: 0, connections: 99 }])).toBe(0);
  });

  it('is zero for an empty map', () => {
    expect(totalConnections([])).toBe(0);
  });

  it('is zero when nothing carries either field', () => {
    expect(totalConnections([{}, {}])).toBe(0);
  });
});
