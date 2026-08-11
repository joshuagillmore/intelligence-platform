import { describe, it, expect } from 'vitest';
import { labelledNodeIds, LABEL_BUDGET } from '@/lib/graphLabels';

const nodes = (n: number, prefix = 'n') =>
  Array.from({ length: n }, (_, i) => ({ id: `${prefix}${i}` }));

/** Degrees descending: n0 highest. */
const degrees = (n: number, prefix = 'n') =>
  Object.fromEntries(Array.from({ length: n }, (_, i) => [`${prefix}${i}`, n - i]));

describe('labelledNodeIds', () => {
  it('labels every node when the graph is small enough', () => {
    const got = labelledNodeIds(nodes(5), degrees(5));
    expect(got.size).toBe(5);
  });

  it('spends a fixed budget on a large graph', () => {
    // The defect: 500 nodes each drew a label, so the canvas rendered text over
    // text through the whole dense core and none of it was readable.
    const got = labelledNodeIds(nodes(500), degrees(500));
    expect(got.size).toBe(LABEL_BUDGET);
  });

  it('spends the budget on the most-connected nodes', () => {
    const got = labelledNodeIds(nodes(100), degrees(100), 3);
    expect([...got].sort()).toEqual(['n0', 'n1', 'n2']);
  });

  it('labels a small graph completely, even with no edges at all', () => {
    // Regression: the cyber panel draws a 4-node / 0-edge graph. Ranking by
    // degree excluded every node and rendered four anonymous dots. Nothing is
    // crowded when the whole graph fits, so nothing is rationed.
    const got = labelledNodeIds(nodes(4), {}, 40);
    expect(got.size).toBe(4);
  });

  it('never labels a node with no edges once it is rationing', () => {
    // Isolated nodes are the bulk of what crowded the canvas and there is
    // nothing to orient by; hover still recovers the name.
    const deg = { a: 4, b: 2, c: 0, d: 0 };
    const got = labelledNodeIds([{ id: 'a' }, { id: 'b' }, { id: 'c' }, { id: 'd' }], deg, 2);
    expect([...got].sort()).toEqual(['a', 'b']);
  });

  it('labels nothing in a large edgeless graph', () => {
    // 50 unconnected nodes past the budget: no landmarks, and hover recovers
    // any single name.
    const got = labelledNodeIds(nodes(50), {}, 10);
    expect(got.size).toBe(0);
  });

  it('always labels community super-nodes', () => {
    // An aggregate with no name says nothing about what it collapsed, and it
    // cannot be identified by hovering the way a single entity can.
    const got = labelledNodeIds(
      [{ id: 'c1', isCommunity: true }, { id: 'c2', isCommunity: true }],
      {},
      1,
    );
    expect([...got].sort()).toEqual(['c1', 'c2']);
  });

  it('does not let community nodes crowd out hubs', () => {
    const got = labelledNodeIds(
      [{ id: 'c1', isCommunity: true }, { id: 'hub' }],
      { hub: 9 },
      1,
    );
    expect(got.has('c1')).toBe(true);
    expect(got.has('hub')).toBe(true);
  });

  it('is stable across calls so labels do not flicker between renders', () => {
    // Ties broken by id: a layout that relabels different hubs each render
    // reads as flicker rather than as information.
    const tied = { a: 5, b: 5, c: 5, d: 5 };
    const first = labelledNodeIds([{ id: 'a' }, { id: 'b' }, { id: 'c' }, { id: 'd' }], tied, 2);
    const shuffled = labelledNodeIds([{ id: 'd' }, { id: 'c' }, { id: 'b' }, { id: 'a' }], tied, 2);
    expect([...first].sort()).toEqual([...shuffled].sort());
  });

  it('handles an empty graph', () => {
    expect(labelledNodeIds([], {}).size).toBe(0);
  });
});
