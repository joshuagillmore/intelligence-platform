import { describe, it, expect } from 'vitest';
import {
  filterGraph,
  normaliseGraphEdge,
  graphTruncationNote,
  displayProperties,
  type GraphFilterInput,
} from '@/app/network/graphFilters';

/**
 * The network page's filter pipeline (findings P-6, P-11, P-10, contract 3 of
 * docs/code-review-2026-09-30.md). What is on the canvas has to be what the
 * filters say, and d3 must never be handed an edge whose endpoint is not a node.
 */

type N = { id: string; name: string; entity_type: string; event_datetime?: string };
type E = { source_id: string; target_id: string; rel_type: string; confidence?: number; source: string; target: string };

const node = (id: string, entity_type = 'Organization', event_datetime?: string): N =>
  ({ id, name: id.toUpperCase(), entity_type, event_datetime });
const edge = (s: string, t: string, rel_type = 'LINKED_TO', confidence = 0.9): E =>
  ({ source_id: s, target_id: t, rel_type, confidence, source: s, target: t });

// a (2026-03) — b (2025-01) — c (undated); a — c; d isolated (2026-04)
const NODES: N[] = [
  node('a', 'Organization', '2026-03-10T00:00:00Z'),
  node('b', 'Person', '2025-01-02T00:00:00Z'),
  node('c', 'Location'),
  node('d', 'Event', '2026-04-01T00:00:00Z'),
];
const EDGES: E[] = [edge('a', 'b'), edge('a', 'c', 'LOCATED_IN', 0.4)];

function input(overrides: Partial<GraphFilterInput<N, E>> = {}): GraphFilterInput<N, E> {
  return {
    nodes: NODES,
    edges: EDGES,
    activeTypeFilters: new Set(),
    eventRange: [null, null],
    hideUndated: false,
    hiddenRelTypes: new Set(),
    confidenceThreshold: 0,
    temporalRange: [null, null],
    islandThreshold: 0,
    islandMetric: 'degree',
    entityStats: null,
    snapshotIds: null,
    ...overrides,
  };
}

const ids = (xs: { id: string }[]) => xs.map(x => x.id).sort();
const pairs = (xs: E[]) => xs.map(e => `${e.source_id}-${e.target_id}`).sort();

/** Every edge handed to d3 must have both endpoints among the nodes. */
function expectNoDanglingEdges(out: { nodes: N[]; edges: E[] }) {
  const visible = new Set(out.nodes.map(n => n.id));
  for (const e of out.edges) {
    expect(visible.has(e.source_id), `edge ${e.source_id}-${e.target_id} source hidden`).toBe(true);
    expect(visible.has(e.target_id), `edge ${e.source_id}-${e.target_id} target hidden`).toBe(true);
  }
}

describe('filterGraph', () => {
  it('passes everything through with no filters set', () => {
    const out = filterGraph(input());
    expect(ids(out.nodes)).toEqual(['a', 'b', 'c', 'd']);
    expect(pairs(out.edges)).toEqual(['a-b', 'a-c']);
  });

  it('applies the date brush on its own (P-6: it was a no-op without another filter)', () => {
    const out = filterGraph(input({ eventRange: ['2026-01', '2026-12'] }));
    // b is dated 2025 and falls outside; c is undated and stays unless hidden.
    expect(ids(out.nodes)).toEqual(['a', 'c', 'd']);
    expect(pairs(out.edges)).toEqual(['a-c']);
    expectNoDanglingEdges(out);
  });

  it('drops edges to brushed-out nodes when a confidence filter is also set (P-6)', () => {
    const out = filterGraph(input({ eventRange: ['2026-01', '2026-12'], confidenceThreshold: 0.1 }));
    expect(out.nodes.map(n => n.id)).not.toContain('b');
    expectNoDanglingEdges(out);
  });

  it('drops edges to brushed-out nodes when a relationship filter is also set (P-6)', () => {
    const out = filterGraph(input({ eventRange: ['2026-01', '2026-12'], hiddenRelTypes: new Set(['LOCATED_IN']) }));
    expect(pairs(out.edges)).toEqual([]);
    expectNoDanglingEdges(out);
  });

  it('hides undated nodes and their edges when asked', () => {
    const out = filterGraph(input({ eventRange: ['2026-01', '2026-12'], hideUndated: true }));
    expect(ids(out.nodes)).toEqual(['a', 'd']);
    expect(out.edges).toEqual([]);
  });

  it('never hands d3 a dangling edge, whatever the filter combination', () => {
    const combos: Partial<GraphFilterInput<N, E>>[] = [
      { eventRange: ['2026-01', '2026-12'] },
      { eventRange: ['2025-01', '2025-01'], confidenceThreshold: 0.5 },
      { activeTypeFilters: new Set(['Organization', 'Location']) },
      { activeTypeFilters: new Set(['Person']), eventRange: ['2026-01', '2026-12'] },
      { islandThreshold: 1, eventRange: ['2026-01', '2026-12'] },
      { snapshotIds: new Set(['a', 'b']), eventRange: ['2026-01', '2026-12'] },
      { temporalRange: ['2020-01-01', null], confidenceThreshold: 0.5 },
    ];
    for (const c of combos) expectNoDanglingEdges(filterGraph(input(c)));
  });

  it('keeps the type filter behaviour: nodes of the chosen types, edges between them', () => {
    const out = filterGraph(input({ activeTypeFilters: new Set(['Organization', 'Location']) }));
    expect(ids(out.nodes)).toEqual(['a', 'c']);
    expect(pairs(out.edges)).toEqual(['a-c']);
  });

  it('applies the degree island threshold over visible edges only', () => {
    // With b brushed out, a has degree 1 (a-c) and no longer clears 2.
    expect(ids(filterGraph(input({ islandThreshold: 2 })).nodes)).toEqual(['a']);
    expect(ids(filterGraph(input({ islandThreshold: 2, eventRange: ['2026-01', '2026-12'] })).nodes)).toEqual([]);
  });

  it('restricts to a snapshot and restores the full graph when cleared (P-11)', () => {
    const snap = filterGraph(input({ snapshotIds: new Set(['a', 'b']) }));
    expect(ids(snap.nodes)).toEqual(['a', 'b']);
    expect(pairs(snap.edges)).toEqual(['a-b']);

    // Clearing is just the input going back to null — no reliance on some
    // other filter changing to re-run the effect.
    const cleared = filterGraph(input({ snapshotIds: null }));
    expect(ids(cleared.nodes)).toEqual(['a', 'b', 'c', 'd']);
  });

  it('composes a snapshot with other filters instead of being overwritten by them (P-11)', () => {
    const out = filterGraph(input({ snapshotIds: new Set(['a', 'b', 'c']), activeTypeFilters: new Set(['Organization', 'Location']) }));
    expect(ids(out.nodes)).toEqual(['a', 'c']);
    expect(pairs(out.edges)).toEqual(['a-c']);
  });

  it('shows a snapshot member even if its only edges leave the snapshot', () => {
    const out = filterGraph(input({ snapshotIds: new Set(['b', 'd']) }));
    expect(ids(out.nodes)).toEqual(['b', 'd']);
    expect(out.edges).toEqual([]);
  });
});

describe('normaliseGraphEdge (contract 4)', () => {
  it('passes the current /graph shape through', () => {
    const e = normaliseGraphEdge({ source_id: 'a', target_id: 'b', rel_type: 'LINKED_TO', confidence: 0.7 });
    expect(e.source_id).toBe('a');
    expect(e.target_id).toBe('b');
    expect(e.rel_type).toBe('LINKED_TO');
    expect(e.confidence).toBe(0.7);
  });

  it('reads the contract-4 keys source/target/type', () => {
    const e = normaliseGraphEdge({
      source: 'a', target: 'b', type: 'LOCATED_IN',
      evidence: 'Acme is based in Lyon.', method: 'llm', source_doc_id: 'doc-1',
    });
    expect(e.source_id).toBe('a');
    expect(e.target_id).toBe('b');
    expect(e.rel_type).toBe('LOCATED_IN');
    expect(e.evidence).toBe('Acme is based in Lyon.');
    expect(e.method).toBe('llm');
    expect(e.source_doc_id).toBe('doc-1');
  });

  it('never turns provenance into "[object Object]"', () => {
    const e = normaliseGraphEdge({
      source_id: 'a', target_id: 'b', rel_type: 'X',
      evidence: ['First sentence.', 'Second sentence.'],
      method: { name: 'hybrid' },
      source_doc_id: 42,
    });
    expect(e.evidence).toBe('First sentence.\nSecond sentence.');
    expect(e.method).toBe('');
    expect(e.source_doc_id).toBe('42');
    expect(JSON.stringify(e)).not.toContain('[object Object]');
  });

  it('leaves provenance empty when the backend sent none', () => {
    const e = normaliseGraphEdge({ source_id: 'a', target_id: 'b', rel_type: 'X' });
    expect(e.evidence).toBe('');
    expect(e.source_doc_id).toBe('');
  });
});

describe('graphTruncationNote (contract 3)', () => {
  it('says nothing when the graph is complete', () => {
    expect(graphTruncationNote(false, 120, 120)).toBeNull();
    expect(graphTruncationNote(false, 120, 800)).toBeNull();
  });

  it('says "Showing N of M entities" when truncated and the total is known', () => {
    expect(graphTruncationNote(true, 120, 800)).toBe('Showing 120 of 800 entities');
  });

  it('still says it is truncated when the total is unknown', () => {
    const note = graphTruncationNote(true, 120, null);
    expect(note).toContain('120');
    expect(note).toMatch(/truncated/i);
  });

  it('does not claim a total smaller than what is shown', () => {
    const note = graphTruncationNote(true, 120, 100);
    expect(note).not.toContain('of 100');
  });
});

describe('displayProperties (entityFields for the properties panel)', () => {
  it('shows fields of a flattened entity, which the panel used to skip', () => {
    const rows = displayProperties({ id: 'e1', name: 'Acme', entity_type: 'Organization', asn: 'AS13335', enriched: true });
    expect(rows).toEqual([['asn', 'AS13335'], ['enriched', 'true']]);
  });

  it('still reads a nested properties bag', () => {
    const rows = displayProperties({ id: 'e1', name: 'Acme', entity_type: 'Organization', properties: { country: 'FR' } });
    expect(rows).toEqual([['country', 'FR']]);
  });

  it('renders lists and objects readably, never "[object Object]"', () => {
    const rows = Object.fromEntries(displayProperties({
      id: 'e1', name: 'x', entity_type: 'Domain',
      aliases: ['a', 'b'], geolocation: { lat: 1, lon: 2 },
    }));
    expect(rows.aliases).toBe('a, b');
    expect(rows.geolocation).toBe('{"lat":1,"lon":2}');
  });

  it('skips header fields, the project id, empty values and document content, and truncates long text', () => {
    const rows = Object.fromEntries(displayProperties({
      id: 'd1', name: 'Doc', entity_type: 'Document', project_id: 'p-1',
      content: 'x'.repeat(10_000), summary: 'y'.repeat(1_000), empty: '', missing: null,
    }));
    expect(Object.keys(rows)).toEqual(['summary']);
    expect(rows.summary.length).toBeLessThan(400);
  });
});
