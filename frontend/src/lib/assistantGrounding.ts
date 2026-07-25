/**
 * Citations / grounding for Graph-RAG answers.
 *
 * WHAT THE BACKEND ACTUALLY RETURNS (`POST /api/query`, see
 * `backend/src/intel_platform/api/routes/query.py`):
 *
 *   { query, answer, model, tokens_used, context,
 *     context_nodes: number,   // node COUNT, not a list
 *     context_edges: number,   // edge COUNT, not a list
 *     vector_results: number,  // hybrid mode only — count of vector hits
 *     retrieval_mode: 'hybrid' | 'graph' }
 *
 * There is no structured citation array. The only per-item grounding the API
 * exposes is `context` — the exact text handed to the LLM, assembled by
 * `GraphRAGPipeline.assemble_context` (+ the vector passages appended by
 * `HybridRetriever.retrieve`). That text has a stable, documented structure, so
 * we parse it rather than invent citation data the API does not have:
 *
 *   ## Intelligence Context from Knowledge Graph
 *   ### <EntityType>s (<n>)
 *   - <name> (<k>: <v>, <k>: <v>)
 *   ### Relationships (<n> unique)
 *   - <source> --[<REL_TYPE>]--> <target> (confidence: <c>)
 *   ### Source Document Evidence (<n> documents)
 *   **<doc name>** [source reliability: <rating>]:
 *   ```
 *   <excerpt>
 *   ```
 *   ### Semantically Similar Document Passages
 *   [similarity=<0..1>, doc=<document_id>]
 *   <chunk>
 *
 * Everything here is best-effort and tolerant: the backend truncates `context`
 * at the token budget mid-section, so a half-parsed tail is normal. When
 * nothing parses we still surface the counts, which are always authoritative.
 */

export interface GroundingEntity {
  name: string;
  type: string;
  /** Raw "k: v, k: v" property blob the backend put in the context line. */
  detail?: string;
}

export interface GroundingRelationship {
  source: string;
  relType: string;
  target: string;
  confidence?: string;
}

export interface GroundingDocument {
  name: string;
  reliability: string;
  excerpt: string;
}

export interface GroundingPassage {
  documentId: string;
  similarity: number;
  text: string;
}

export interface AssistantGrounding {
  retrievalMode: string | null;
  model: string | null;
  tokensUsed: number | null;
  nodeCount: number | null;
  edgeCount: number | null;
  vectorCount: number | null;
  entities: GroundingEntity[];
  relationships: GroundingRelationship[];
  documents: GroundingDocument[];
  passages: GroundingPassage[];
  /** True when at least one concrete citation (not just a count) was recovered. */
  hasDetail: boolean;
}

/** Caps so a huge context can never blow up the panel or localStorage. */
const MAX_ENTITIES = 60;
const MAX_RELATIONSHIPS = 60;
const MAX_DOCUMENTS = 8;
const MAX_PASSAGES = 12;
const MAX_EXCERPT_CHARS = 1200;

type Section = 'entity' | 'relationships' | 'documents' | 'passages' | 'other';

const ENTITY_LINE = /^-\s+(.*?)(?:\s+\(([^()]*)\))?$/;
const RELATIONSHIP_LINE = /^-\s+(.*?)\s+--\[(.*?)\]-->\s+(.*?)(?:\s+\(confidence:\s*([^)]*)\))?$/;
const DOCUMENT_HEADING = /^\*\*(.+?)\*\*\s*\[source reliability:\s*([^\]]*)\]:\s*$/;
const PASSAGE_HEADING = /^\[similarity=([0-9.]+),\s*doc=(.+?)\]\s*$/;

function toCount(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (Array.isArray(value)) return value.length;
  return null;
}

function toText(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

/** Classify a `### ` heading into one of the known context sections. */
function classifyHeading(heading: string): { section: Section; entityType?: string } {
  if (/^Relationships\s*\(/.test(heading)) return { section: 'relationships' };
  if (/^Source Document Evidence\s*\(/.test(heading)) return { section: 'documents' };
  if (/^Semantically Similar Document Passages\b/.test(heading)) return { section: 'passages' };

  // Entity sections are `### <EntityType>s (<n>)` — the backend appends a bare
  // "s" to the type, so "IPAddress" arrives as "IPAddresss". Strip exactly one.
  const entity = heading.match(/^(.+?)s\s*\((\d+)\)$/);
  if (entity) return { section: 'entity', entityType: entity[1] };
  return { section: 'other' };
}

/**
 * Parse the assembled RAG `context` string into citation records.
 * Exported for testing; `parseGrounding` is what callers use.
 */
export function parseRagContext(context: string): Pick<
  AssistantGrounding,
  'entities' | 'relationships' | 'documents' | 'passages'
> {
  const entities: GroundingEntity[] = [];
  const relationships: GroundingRelationship[] = [];
  const documents: GroundingDocument[] = [];
  const passages: GroundingPassage[] = [];

  let section: Section = 'other';
  let entityType = '';

  // Document-evidence state: a heading line, then a fenced excerpt block.
  let pendingDoc: { name: string; reliability: string } | null = null;
  let inFence = false;
  let fenceLines: string[] = [];

  // Passage state: a `[similarity=…, doc=…]` marker, then free text until the
  // next marker or the end of the section.
  let pendingPassage: { documentId: string; similarity: number; text: string[] } | null = null;

  const flushPassage = () => {
    if (!pendingPassage) return;
    const text = pendingPassage.text.join('\n').trim();
    if (text && passages.length < MAX_PASSAGES) {
      passages.push({
        documentId: pendingPassage.documentId,
        similarity: pendingPassage.similarity,
        text: text.slice(0, MAX_EXCERPT_CHARS),
      });
    }
    pendingPassage = null;
  };

  for (const raw of context.split('\n')) {
    const line = raw.trimEnd();

    // A fenced excerpt swallows every line until its closing fence, so it must
    // be checked before heading detection (excerpts can contain "###" text).
    if (inFence) {
      if (line.trim() === '```') {
        inFence = false;
        if (pendingDoc && documents.length < MAX_DOCUMENTS) {
          documents.push({
            name: pendingDoc.name,
            reliability: pendingDoc.reliability,
            excerpt: fenceLines.join('\n').trim().slice(0, MAX_EXCERPT_CHARS),
          });
        }
        pendingDoc = null;
        fenceLines = [];
      } else {
        fenceLines.push(line);
      }
      continue;
    }

    if (line.startsWith('### ')) {
      flushPassage();
      pendingDoc = null;
      const classified = classifyHeading(line.slice(4).trim());
      section = classified.section;
      entityType = classified.entityType ?? '';
      continue;
    }
    if (line.startsWith('## ')) {
      flushPassage();
      section = 'other';
      continue;
    }

    if (section === 'entity') {
      const m = line.match(ENTITY_LINE);
      if (m && m[1].trim() && entities.length < MAX_ENTITIES) {
        entities.push({ name: m[1].trim(), type: entityType, detail: m[2]?.trim() || undefined });
      }
      continue;
    }

    if (section === 'relationships') {
      const m = line.match(RELATIONSHIP_LINE);
      if (m && relationships.length < MAX_RELATIONSHIPS) {
        relationships.push({
          source: m[1].trim(),
          relType: m[2].trim(),
          target: m[3].trim(),
          confidence: m[4]?.trim() || undefined,
        });
      }
      continue;
    }

    if (section === 'documents') {
      const heading = line.match(DOCUMENT_HEADING);
      if (heading) {
        pendingDoc = { name: heading[1].trim(), reliability: heading[2].trim() || 'unrated' };
        continue;
      }
      if (line.trim() === '```') {
        inFence = true;
        fenceLines = [];
      }
      continue;
    }

    if (section === 'passages') {
      const marker = line.match(PASSAGE_HEADING);
      if (marker) {
        flushPassage();
        pendingPassage = {
          documentId: marker[2].trim(),
          similarity: Number.parseFloat(marker[1]),
          text: [],
        };
        continue;
      }
      if (pendingPassage) pendingPassage.text.push(line);
    }
  }

  flushPassage();
  // An unterminated fence (context truncated at the token budget) still yields
  // a usable excerpt — better a partial citation than a dropped one.
  if (inFence && pendingDoc && documents.length < MAX_DOCUMENTS) {
    documents.push({
      name: pendingDoc.name,
      reliability: pendingDoc.reliability,
      excerpt: fenceLines.join('\n').trim().slice(0, MAX_EXCERPT_CHARS),
    });
  }

  return { entities, relationships, documents, passages };
}

/**
 * Build the grounding record for one `/api/query` response. Returns null when
 * the payload carries no grounding at all (e.g. a non-RAG task result), so
 * callers can simply omit the citations affordance.
 */
export function parseGrounding(data: unknown): AssistantGrounding | null {
  if (!data || typeof data !== 'object') return null;
  const d = data as Record<string, unknown>;

  const context = typeof d.context === 'string' ? d.context : '';
  const parsed = context
    ? parseRagContext(context)
    : { entities: [], relationships: [], documents: [], passages: [] };

  const grounding: AssistantGrounding = {
    retrievalMode: toText(d.retrieval_mode),
    model: toText(d.model) && d.model !== 'none' ? toText(d.model) : null,
    tokensUsed: toCount(d.tokens_used),
    nodeCount: toCount(d.context_nodes),
    edgeCount: toCount(d.context_edges),
    vectorCount: toCount(d.vector_results),
    ...parsed,
    hasDetail:
      parsed.entities.length > 0 ||
      parsed.relationships.length > 0 ||
      parsed.documents.length > 0 ||
      parsed.passages.length > 0,
  };

  const hasCounts =
    grounding.nodeCount !== null || grounding.edgeCount !== null || grounding.vectorCount !== null;
  if (!grounding.hasDetail && !hasCounts && !grounding.retrievalMode) return null;
  return grounding;
}

/** Short "Sources · 12 entities · 8 links" style summary for the disclosure. */
export function groundingSummary(g: AssistantGrounding): string {
  const parts: string[] = [];
  if (g.entities.length) parts.push(`${g.entities.length} ${g.entities.length === 1 ? 'entity' : 'entities'}`);
  if (g.relationships.length) parts.push(`${g.relationships.length} ${g.relationships.length === 1 ? 'link' : 'links'}`);
  if (g.documents.length) parts.push(`${g.documents.length} ${g.documents.length === 1 ? 'doc' : 'docs'}`);
  if (g.passages.length) parts.push(`${g.passages.length} ${g.passages.length === 1 ? 'passage' : 'passages'}`);
  if (parts.length === 0) {
    if (g.nodeCount) parts.push(`${g.nodeCount} nodes`);
    if (g.edgeCount) parts.push(`${g.edgeCount} edges`);
  }
  return parts.length ? parts.join(' · ') : 'retrieval detail';
}
