import { describe, it, expect } from 'vitest';
import { collapseToCommunities } from '@/lib/graphLayout';

/**
 * Nodes with no community (no community_id, or the -1 "unassigned" marker)
 * are not a community. Grouping them all under -1 merged every unassigned
 * node into one "Community" super-node, inventing a cluster that does not
 * exist and hiding the nodes themselves.
 */
const node = (id: string, community_id?: number, pagerank = 0) => ({
  id, name: id, entity_type: 'Person', community_id, pagerank,
});
const edge = (s: string, t: string) => ({ source_id: s, target_id: t, rel_type: 'KNOWS' });

describe('collapseToCommunities', () => {
  it('collapses a real community into one super-node', () => {
    const { nodes } = collapseToCommunities([node('a', 1, 0.5), node('b', 1, 0.1)], []);
    expect(nodes).toHaveLength(1);
    expect(nodes[0].isCommunity).toBe(true);
    expect(nodes[0].id).toBe('community-1');
  });

  it('keeps nodes without a community as individual nodes', () => {
    const { nodes } = collapseToCommunities([node('x'), node('y'), node('z')], []);
    expect(nodes.map((n) => n.id).sort()).toEqual(['x', 'y', 'z']);
    expect(nodes.some((n) => n.isCommunity)).toBe(false);
  });

  it('keeps nodes marked community -1 as individual nodes', () => {
    const { nodes } = collapseToCommunities([node('x', -1), node('y', -1)], []);
    expect(nodes.map((n) => n.id).sort()).toEqual(['x', 'y']);
    expect(nodes.some((n) => n.id === 'community--1')).toBe(false);
  });

  it('routes edges from unassigned nodes to their own ids, not a shared super-node', () => {
    const { edges } = collapseToCommunities(
      [node('a', 1), node('b', 1), node('x'), node('y')],
      [edge('x', 'a'), edge('y', 'b'), edge('x', 'y')],
    );
    const pairs = edges.map((e) => [e.source_id, e.target_id].sort().join('|')).sort();
    expect(pairs).toEqual(['community-1|x', 'community-1|y', 'x|y']);
  });
});
