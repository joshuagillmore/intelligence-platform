import { describe, it, expect } from 'vitest';
import { parseGrounding, parseRagContext, groundingSummary } from '@/lib/assistantGrounding';

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
