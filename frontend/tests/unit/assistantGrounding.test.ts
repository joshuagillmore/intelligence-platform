import { describe, it, expect } from 'vitest';
import {
  parseGrounding,
  parseRagContext,
  groundingSummary,
  sanitizeGrounding,
  compactGroundingForStorage,
} from '@/lib/assistantGrounding';

/**
 * These fixtures are the real shapes the backend emits, not invented ones:
 * `context` follows `GraphRAGPipeline.assemble_context` (+ the vector-passage
 * section `HybridRetriever.retrieve` appends), and the top-level fields follow
 * `POST /api/query` in `backend/src/intel_platform/api/routes/query.py`.
 */
const CONTEXT = `## Intelligence Context from Knowledge Graph

### Persons (2)
- Marcus Kellerman (entity_category: person, reliability_rating: B)
- Ana Sokolova

### IPAddresss (1)
- 203.0.113.42 (asn: AS64500, geolocation: NL)

### Relationships (3 unique)
- Marcus Kellerman --[EMPLOYED_BY]--> Meridian Logistics (confidence: 0.91)
- Meridian Logistics --[OPERATES_IN]--> Rotterdam
- 203.0.113.42 --[COMMUNICATES_WITH]--> Ana Sokolova (confidence: 0.6)

### Source Document Evidence (2 documents)

**port-report-2026.pdf** [source reliability: B]:
\`\`\`
Kellerman was observed at the Rotterdam terminal.
A second visit followed in March.
\`\`\`

**cable-114.txt** [source reliability: unrated]:
\`\`\`
Sokolova's travel records list ### three entries.
\`\`\`

### Semantically Similar Document Passages
[similarity=0.834, doc=doc-abc-123]
The terminal lease was transferred in late 2025.

[similarity=0.702, doc=doc-def-456]
Shipping manifests reference a shell company.`;

const HYBRID_RESPONSE = {
  query: 'Who is connected to Rotterdam?',
  answer: 'Marcus Kellerman is connected via Meridian Logistics.',
  model: 'claude-sonnet-4-5',
  tokens_used: 1234,
  context: CONTEXT,
  context_nodes: 24,
  context_edges: 31,
  vector_results: 12,
  retrieval_mode: 'hybrid',
};

describe('parseRagContext', () => {
  const parsed = parseRagContext(CONTEXT);

  it('extracts entities and strips the pluralising "s" the backend appends to the type', () => {
    expect(parsed.entities).toEqual([
      { name: 'Marcus Kellerman', type: 'Person', detail: 'entity_category: person, reliability_rating: B' },
      { name: 'Ana Sokolova', type: 'Person', detail: undefined },
      { name: '203.0.113.42', type: 'IPAddress', detail: 'asn: AS64500, geolocation: NL' },
    ]);
  });

  it('does not mistake the Relationships/Evidence/Passages headings for entity types', () => {
    const types = new Set(parsed.entities.map(e => e.type));
    expect(types.has('Relationship')).toBe(false);
    expect(types.has('Source Document Evidence')).toBe(false);
  });

  it('extracts relationships with optional confidence', () => {
    expect(parsed.relationships).toEqual([
      { source: 'Marcus Kellerman', relType: 'EMPLOYED_BY', target: 'Meridian Logistics', confidence: '0.91' },
      { source: 'Meridian Logistics', relType: 'OPERATES_IN', target: 'Rotterdam', confidence: undefined },
      { source: '203.0.113.42', relType: 'COMMUNICATES_WITH', target: 'Ana Sokolova', confidence: '0.6' },
    ]);
  });

  it('extracts source documents with their reliability rating and excerpt', () => {
    expect(parsed.documents).toHaveLength(2);
    expect(parsed.documents[0]).toMatchObject({ name: 'port-report-2026.pdf', reliability: 'B' });
    expect(parsed.documents[0].excerpt).toContain('Rotterdam terminal');
    expect(parsed.documents[1]).toMatchObject({ name: 'cable-114.txt', reliability: 'unrated' });
  });

  it('does not treat "###" inside a fenced excerpt as a new section', () => {
    // The second document's excerpt contains a literal "###"; if the fence were
    // not honoured, parsing would derail and drop the passages section.
    expect(parsed.documents[1].excerpt).toContain('### three entries');
    expect(parsed.passages).toHaveLength(2);
  });

  it('extracts semantic passages with document id and similarity', () => {
    expect(parsed.passages[0]).toEqual({
      documentId: 'doc-abc-123',
      similarity: 0.834,
      text: 'The terminal lease was transferred in late 2025.',
    });
    expect(parsed.passages[1].documentId).toBe('doc-def-456');
  });

  it('recovers a partial citation when the backend truncates mid-excerpt', () => {
    const truncated = `### Source Document Evidence (1 documents)

**half.txt** [source reliability: C]:
\`\`\`
This excerpt was cut off by the token`;
    const out = parseRagContext(truncated);
    expect(out.documents).toEqual([
      { name: 'half.txt', reliability: 'C', excerpt: 'This excerpt was cut off by the token' },
    ]);
  });

  it('returns empty lists for text that is not an assembled context', () => {
    expect(parseRagContext('just some prose')).toEqual({
      entities: [], relationships: [], documents: [], passages: [],
    });
  });
});

describe('parseGrounding', () => {
  it('reads the counts the API actually returns (numbers, not lists)', () => {
    const g = parseGrounding(HYBRID_RESPONSE)!;
    expect(g.retrievalMode).toBe('hybrid');
    expect(g.nodeCount).toBe(24);
    expect(g.edgeCount).toBe(31);
    expect(g.vectorCount).toBe(12);
    expect(g.model).toBe('claude-sonnet-4-5');
    expect(g.tokensUsed).toBe(1234);
    expect(g.hasDetail).toBe(true);
  });

  it('handles a graph-only response (no vector_results key)', () => {
    const g = parseGrounding({
      query: 'q', answer: 'a', model: 'none', tokens_used: 0,
      context: '### Persons (1)\n- Ana Sokolova',
      context_nodes: 3, context_edges: 1, retrieval_mode: 'graph',
    })!;
    expect(g.retrievalMode).toBe('graph');
    expect(g.vectorCount).toBeNull();
    // model "none" means no provider ran — don't show it as a citation.
    expect(g.model).toBeNull();
    expect(g.entities).toHaveLength(1);
  });

  it('still reports counts when the response carries no context text', () => {
    const g = parseGrounding({ answer: 'a', context_nodes: 5, context_edges: 2, retrieval_mode: 'graph' })!;
    expect(g.hasDetail).toBe(false);
    expect(g.nodeCount).toBe(5);
  });

  it('returns null when there is no grounding information at all', () => {
    expect(parseGrounding({ answer: 'hello' })).toBeNull();
    expect(parseGrounding(null)).toBeNull();
    expect(parseGrounding('not an object')).toBeNull();
  });
});

describe('sanitizeGrounding', () => {
  // The panel renders in the root layout and the app has no error boundary, so
  // a bad persisted grounding reaching a `.map` would blank every route until
  // the user cleared localStorage by hand.
  it.each([
    ['missing arrays', {}],
    ['null arrays', { entities: null, relationships: null, documents: null, passages: null }],
    ['scalars where arrays belong', { entities: 5, relationships: 'x', documents: {}, passages: true }],
    ['an older shape', { retrieval_mode: 'hybrid', nodes: 4 }],
  ])('coerces %s into renderable empty lists', (_label, stored) => {
    const g = sanitizeGrounding(stored)!;
    expect(g.entities).toEqual([]);
    expect(g.relationships).toEqual([]);
    expect(g.documents).toEqual([]);
    expect(g.passages).toEqual([]);
    expect(g.hasDetail).toBe(false);
    expect(() => groundingSummary(g)).not.toThrow();
  });

  it('drops non-object array members that would break rendering', () => {
    const g = sanitizeGrounding({ entities: [null, 'nope', { name: 'Real', type: 'Person' }] })!;
    expect(g.entities).toEqual([{ name: 'Real', type: 'Person' }]);
  });

  it('round-trips a genuine grounding', () => {
    const original = parseGrounding(HYBRID_RESPONSE)!;
    const restored = sanitizeGrounding(JSON.parse(JSON.stringify(original)))!;
    expect(restored.entities).toEqual(original.entities);
    expect(restored.nodeCount).toBe(24);
    expect(restored.hasDetail).toBe(true);
  });

  it('returns null for values that are not groundings at all', () => {
    expect(sanitizeGrounding(null)).toBeNull();
    expect(sanitizeGrounding('nope')).toBeNull();
  });
});

describe('compactGroundingForStorage', () => {
  it('clips excerpts and passages so a thread cannot exhaust the storage quota', () => {
    const big = parseGrounding({
      ...HYBRID_RESPONSE,
      context: `### Source Document Evidence (1 documents)\n\n**big.txt** [source reliability: A]:\n\`\`\`\n${'x'.repeat(1000)}\n\`\`\``,
    })!;
    expect(big.documents[0].excerpt.length).toBe(1000);

    const compact = compactGroundingForStorage(big)!;
    expect(compact.documents[0].excerpt.length).toBe(200);
    // Citation identity survives — only the bulk text is clipped.
    expect(compact.documents[0].name).toBe('big.txt');
    expect(compact.nodeCount).toBe(24);
    // The in-memory original is untouched.
    expect(big.documents[0].excerpt.length).toBe(1000);
  });

  it('passes null through', () => {
    expect(compactGroundingForStorage(null)).toBeNull();
  });
});

describe('long-line guard', () => {
  it('skips pathological lines instead of feeding them to a backtracking regex', () => {
    // Two lazy groups around literal delimiters backtrack quadratically; the
    // guard keeps a malformed 200KB line from stalling the render.
    const evil = `### Relationships (1 unique)\n- ${'a '.repeat(100_000)}--[X]--> b`;
    const start = Date.now();
    const out = parseRagContext(evil);
    expect(Date.now() - start).toBeLessThan(500);
    expect(out.relationships).toEqual([]);
  });

  it('still parses relationship lines of a realistic length', () => {
    const name = 'A'.repeat(300);
    const out = parseRagContext(`### Relationships (1 unique)\n- ${name} --[LINKS_TO]--> Target`);
    expect(out.relationships).toEqual([
      { source: name, relType: 'LINKS_TO', target: 'Target', confidence: undefined },
    ]);
  });
});

describe('groundingSummary', () => {
  it('summarises the recovered citations', () => {
    expect(groundingSummary(parseGrounding(HYBRID_RESPONSE)!))
      .toBe('3 entities · 3 links · 2 docs · 2 passages');
  });

  it('falls back to raw counts when nothing was parsed', () => {
    const g = parseGrounding({ context_nodes: 5, context_edges: 2, retrieval_mode: 'graph' })!;
    expect(groundingSummary(g)).toBe('5 nodes · 2 edges');
  });
});
