/**
 * Pure logic behind the network page, kept out of the 2,500-line component so
 * it can be tested: the filter pipeline that decides what reaches the canvas,
 * the request hygiene that keeps slow responses from overwriting newer ones,
 * and the small formatting rules for edge provenance and entity properties.
 *
 * See docs/code-review-2026-09-30.md, findings P-4, P-5, P-6, P-10, P-11, P-12.
 */
import { useEffect, useState } from 'react';
import { entityFields } from '@/lib/api';

// ─── Filter pipeline ─────────────────────────────────────────────────────────

export type IslandMetric = 'degree' | 'betweenness' | 'eigenvector' | 'pagerank' | 'closeness';

export interface FilterableNode {
  id: string;
  name: string;
  entity_type: string;
  event_datetime?: string;
}

export interface FilterableEdge {
  source_id: string;
  target_id: string;
  rel_type: string;
  confidence?: number;
  first_seen?: string;
  last_seen?: string;
  source?: unknown;
  target?: unknown;
}

export type EntityStatsRow = { entity: string } & Record<Exclude<IslandMetric, 'degree'>, number>;

export interface GraphFilterInput<N extends FilterableNode, E extends FilterableEdge> {
  nodes: N[];
  edges: E[];
  activeTypeFilters: Set<string>;
  /** Histogram brush over event dates, as ISO-prefix bin keys ("2026-03"). */
  eventRange: [string | null, string | null];
  hideUndated: boolean;
  hiddenRelTypes: Set<string>;
  confidenceThreshold: number;
  /** first_seen / last_seen window from the TemporalSlider. */
  temporalRange: [string | null, string | null];
  islandThreshold: number;
  islandMetric: IslandMetric;
  entityStats?: EntityStatsRow[] | null;
  /** The entity ids of the snapshot being viewed, or null for no snapshot. */
  snapshotIds?: Set<string> | null;
}

/** An edge's endpoint ids, whichever of the two key shapes it carries. */
export function edgeEndpoints(e: FilterableEdge): [string, string] {
  return [String(e.source_id || e.source), String(e.target_id || e.target)];
}

/**
 * Drop every edge that has an endpoint outside `nodes`. d3's forceLink throws
 * "node not found" on such an edge, so this is the last step before the canvas.
 */
export function dropDanglingEdges<N extends { id: string }, E extends FilterableEdge>(nodes: N[], edges: E[]): E[] {
  const ids = new Set(nodes.map(n => n.id));
  return edges.filter(e => {
    const [s, t] = edgeEndpoints(e);
    return ids.has(s) && ids.has(t);
  });
}

/**
 * What the graph canvas shows for a given set of filters.
 *
 * Nodes are narrowed by snapshot, entity type and the event-date brush. Edges
 * are narrowed by relationship type, confidence and the first/last-seen window,
 * and only survive when both endpoints are still visible. The island threshold
 * then keeps nodes whose metric clears it. When a relationship, confidence or
 * type filter is on, nodes that lost every edge to it are hidden (a node that
 * never had an edge stays, so isolated findings are not mistaken for filtered).
 */
export function filterGraph<N extends FilterableNode, E extends FilterableEdge>(
  input: GraphFilterInput<N, E>,
): { nodes: N[]; edges: E[] } {
  const {
    activeTypeFilters, eventRange, hideUndated, hiddenRelTypes, confidenceThreshold,
    temporalRange, islandThreshold, islandMetric, entityStats, snapshotIds,
  } = input;

  let nodes = input.nodes;
  if (snapshotIds) {
    nodes = nodes.filter(n => snapshotIds.has(n.id));
  }
  if (activeTypeFilters.size > 0) {
    nodes = nodes.filter(n => activeTypeFilters.has(n.entity_type));
  }

  // Event-date brush. Undated entities stay visible unless explicitly hidden:
  // most of a graph carries no date, so removing them on every selection would
  // empty the view and make the filter look broken.
  const [evStart, evEnd] = eventRange;
  if (evStart && evEnd) {
    nodes = nodes.filter(n => {
      const dt = n.event_datetime;
      if (!dt) return !hideUndated;
      const key = dt.slice(0, evStart.length);
      return key >= evStart && key <= evEnd;
    });
  }

  const visibleNodeIds = new Set(nodes.map(n => n.id));
  const [tStart, tEnd] = temporalRange;

  let edges = input.edges.filter(e => {
    const [srcId, tgtId] = edgeEndpoints(e);
    // Always, not only under a type filter: an edge to a brushed-out node is
    // an edge d3 cannot resolve.
    if (!visibleNodeIds.has(srcId) || !visibleNodeIds.has(tgtId)) return false;
    if (hiddenRelTypes.has(e.rel_type)) return false;
    if (confidenceThreshold > 0 && (e.confidence === undefined || e.confidence < confidenceThreshold)) return false;
    if (tStart && e.last_seen && e.last_seen < tStart) return false;
    if (tEnd && e.first_seen && e.first_seen > tEnd) return false;
    return true;
  });

  if (islandThreshold > 0) {
    const metricMap: Record<string, number> = {};
    if (islandMetric === 'degree') {
      for (const n of nodes) metricMap[n.id] = 0;
      for (const e of edges) {
        const [srcId, tgtId] = edgeEndpoints(e);
        if (metricMap[srcId] !== undefined) metricMap[srcId]++;
        if (metricMap[tgtId] !== undefined) metricMap[tgtId]++;
      }
    } else {
      const statsLookup: Record<string, EntityStatsRow> = {};
      for (const s of entityStats ?? []) statsLookup[s.entity] = s;
      for (const n of nodes) {
        const s = statsLookup[n.name];
        metricMap[n.id] = s ? s[islandMetric] : 0;
      }
    }
    nodes = nodes.filter(n => metricMap[n.id] >= islandThreshold);
  } else if (hiddenRelTypes.size > 0 || confidenceThreshold > 0 || activeTypeFilters.size > 0) {
    const connectedIds = new Set<string>();
    for (const e of edges) {
      const [srcId, tgtId] = edgeEndpoints(e);
      connectedIds.add(srcId);
      connectedIds.add(tgtId);
    }
    const originallyConnected = new Set<string>();
    for (const e of input.edges) {
      const [srcId, tgtId] = edgeEndpoints(e);
      originallyConnected.add(srcId);
      originallyConnected.add(tgtId);
    }
    nodes = nodes.filter(n => connectedIds.has(n.id) || !originallyConnected.has(n.id));
  }

  edges = dropDanglingEdges(nodes, edges);
  return { nodes, edges };
}

// ─── Edge provenance (contract 4) ─────────────────────────────────────────────

/** A value as display text: strings as-is, lists joined, anything else empty. */
function asText(value: unknown, sep = '\n'): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return value.map(v => asText(v, sep)).filter(Boolean).join(sep);
  return '';
}

export interface NormalisedEdgeFields {
  source_id: string;
  target_id: string;
  source: string;
  target: string;
  rel_type: string;
  evidence: string;
  method: string;
  source_doc_id: string;
}

/**
 * One `/graph` edge in the shape the page reads. Accepts both `source_id` /
 * `target_id` / `rel_type` and contract 4's `source` / `target` / `type`, and
 * coerces the provenance fields to text so the edge panel can never print
 * "[object Object]".
 */
export function normaliseGraphEdge(raw: Record<string, unknown>): Record<string, unknown> & NormalisedEdgeFields {
  const source_id = asText(raw.source_id ?? raw.source);
  const target_id = asText(raw.target_id ?? raw.target);
  return {
    ...raw,
    source_id,
    target_id,
    source: source_id,
    target: target_id,
    rel_type: asText(raw.rel_type ?? raw.type),
    evidence: asText(raw.evidence),
    method: asText(raw.method),
    source_doc_id: asText(raw.source_doc_id),
  };
}

// ─── Truncation note (contract 3) ─────────────────────────────────────────────

/**
 * What to say when `/graph` returned only part of the project. `total` comes
 * from the statistics endpoint, which counts the same node population.
 */
export function graphTruncationNote(truncated: boolean, shown: number, total: number | null | undefined): string | null {
  if (!truncated) return null;
  if (total && total > shown) {
    return `Showing ${shown.toLocaleString()} of ${total.toLocaleString()} entities`;
  }
  return `Showing ${shown.toLocaleString()} entities; the graph is truncated`;
}

// ─── Entity properties panel ──────────────────────────────────────────────────

// The header already shows id/name/type; project_id is the same on every row
// of the view; `properties` is the nested bag entityFields has already spread;
// a Document's `content` is the whole text.
const PROPERTY_SKIP = new Set(['id', 'name', 'entity_type', 'project_id', 'properties', 'content']);
const PROPERTY_MAX_CHARS = 300;

/**
 * The entity's fields as `[key, text]` rows for the properties panel. Reads
 * through `entityFields`, because the entity routes flatten node fields onto
 * the object and the panel used to look only at `.properties`.
 */
export function displayProperties(entity: unknown): Array<[string, string]> {
  const rows: Array<[string, string]> = [];
  for (const [key, value] of Object.entries(entityFields(entity))) {
    if (PROPERTY_SKIP.has(key) || value === null || value === undefined) continue;
    let text: string;
    if (Array.isArray(value)) text = value.map(v => (typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v))).join(', ');
    else if (typeof value === 'object') text = JSON.stringify(value);
    else text = String(value);
    if (text === '') continue;
    if (text.length > PROPERTY_MAX_CHARS) text = text.slice(0, PROPERTY_MAX_CHARS) + '…';
    rows.push([key, text]);
  }
  return rows;
}

// ─── Request hygiene ──────────────────────────────────────────────────────────

/**
 * Tokens for "is this response still the one we want?". Take a token before a
 * request, and apply the response only if the token is still current.
 */
export function createRequestSequencer() {
  let current = 0;
  return {
    next: (): number => ++current,
    isCurrent: (token: number): boolean => token === current,
  };
}

/**
 * `fn` over `items` with at most `limit` calls in flight, results in input
 * order. Once `shouldContinue` returns false no further item is started (calls
 * already in flight finish, and unstarted slots stay `undefined`). A rejection
 * from `fn` rejects the whole run, so callers that want to skip failures catch
 * inside `fn`.
 */
export async function mapWithConcurrency<T, R>(
  items: T[],
  limit: number,
  fn: (item: T, index: number) => Promise<R>,
  shouldContinue: () => boolean = () => true,
): Promise<Array<R | undefined>> {
  const results: Array<R | undefined> = new Array(items.length);
  let nextIndex = 0;
  async function worker() {
    while (nextIndex < items.length && shouldContinue()) {
      const i = nextIndex++;
      results[i] = await fn(items[i], i);
    }
  }
  const workers = Array.from({ length: Math.min(Math.max(1, limit), items.length) }, worker);
  await Promise.all(workers);
  return results;
}

/** `value`, but only once it has stopped changing for `delayMs`. */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}
