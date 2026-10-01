/**
 * Shapes, constants and formatters shared by the network view's hooks and
 * components (split out of `page.tsx`; see `docs/design/plans/2026-09-30-
 * post-review-hardening.md`, WP-F step 5).
 */

export interface Entity {
  id: string;
  name: string;
  entity_type: string;
  properties?: Record<string, unknown>;
  confidence?: number;
}

export interface Relationship {
  id?: string;
  source_id: string;
  target_id: string;
  rel_type: string;
  confidence?: number;
  source_name?: string;
  target_name?: string;
  evidence?: string;
  // Provenance carried on the edge — see components/EvidenceChain.
  source_doc_id?: string;
  admiralty_rating?: string;
  corroboration_count?: number;
  corroboration_agreement?: string;
  method?: string;
}

export interface GraphNode {
  id: string;
  name: string;
  entity_type: string;
  /** When the thing happened, resolved from the source text. Never ingestion time. */
  event_datetime?: string;
  date_precision?: string;
  date_text?: string;
}

export interface GraphEdge {
  source_id: string;
  target_id: string;
  rel_type: string;
  confidence?: number;
  first_seen?: string;
  last_seen?: string;
  source: string;
  target: string;
  // Provenance (contract 4); normalised to text on load, '' when absent.
  evidence?: string;
  method?: string;
  source_doc_id?: string;
  [key: string]: unknown;
}

export interface EntityStats {
  entity: string;
  type: string;
  degree: number;
  betweenness: number;
  eigenvector: number;
  pagerank: number;
  closeness: number;
}

export interface GraphStats {
  total_nodes: number;
  total_edges: number;
  density: number;
  connected_components: number;
  entity_statistics: EntityStats[];
}

export interface StructuralHoleEntry {
  id: string;
  name: string;
  entity_type: string;
  constraint: number;
  effective_size: number;
  degree: number;
  is_broker: boolean;
}

export interface EgoNetworkData {
  center: string;
  hops: number;
  node_count: number;
  edge_count: number;
  nodes: Array<{ id: string; name: string; entity_type: string; hop_distance: number; local_pagerank: number; local_betweenness: number }>;
  edges: Array<{ source_id: string; target_id: string; rel_type: string; confidence: number; weight: number }>;
}

export interface InfluenceStep {
  step: number;
  newly_activated: Array<{ id: string; name: string; entity_type: string }>;
  cumulative_count: number;
}

export interface InfluenceResult {
  seeds: string[];
  steps: InfluenceStep[];
  total_activated: number;
  reach_ratio: number;
  total_nodes: number;
}

export type SortKey = 'entity' | 'type' | 'degree' | 'betweenness' | 'eigenvector' | 'pagerank' | 'closeness';

export type { IslandMetric } from './graphFilters';

export type LeftTab = 'entities' | 'statistics' | 'analysis';

/** The filter settings undo/redo steps through. */
export interface FilterSnapshot {
  hiddenRelTypes: Set<string>;
  confidenceThreshold: number;
  islandThreshold: number;
}

// How many entities the browse panel loads. Higher than the server's default of
// 50 — which is what made the panel group 50 of 5,486 under headings that read
// as totals — but still a page, because this is a scrollable browse list and
// putting 5,486 buttons in the DOM helps nobody. The panel now says which it is.
export const ENTITY_PANEL_LIMIT = 500;

// The entity search waits for typing to pause before it asks the server.
export const SEARCH_DEBOUNCE_MS = 300;

// How many of an entity's source documents the evidence chain lists. The panel
// says when there are more (`total` from GET /entities/{id}/documents).
export const EVIDENCE_DOC_LIMIT = 50;

export const ENTITY_TYPE_OPTIONS = ['Person', 'Organization', 'Location', 'IPAddress', 'Domain', 'Hash', 'ThreatActor', 'TTP', 'Vulnerability', 'Malware', 'Campaign'];

const TYPE_LABELS: Record<string, string> = {
  TTP: 'Tactics, Techniques & Procedures',
  IPAddress: 'IP Address',
  ThreatActor: 'Threat Actor',
  GovernmentAgency: 'Government Agency',
  MilitaryUnit: 'Military Unit',
};
export function formatEntityType(type: string): string {
  return TYPE_LABELS[type] || type;
}

export function formatRelType(rel: string): string {
  return rel.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()).replace(/\bOf\b/g, 'of').replace(/\bOn\b/g, 'on');
}

export function intensityClass(value: number, max: number): string {
  if (max === 0) return 'text-gray-400';
  const ratio = value / max;
  if (ratio > 0.8) return 'text-blue-300 font-bold';
  if (ratio > 0.6) return 'text-blue-400 font-semibold';
  if (ratio > 0.4) return 'text-blue-400';
  if (ratio > 0.2) return 'text-blue-500';
  return 'text-gray-400';
}

/** `{id, name, entity_type}` of a graph node, the shape selection works in. */
export function nodeEntity(n: { id: string; name: string; entity_type: string }): Entity {
  return { id: n.id, name: n.name, entity_type: n.entity_type };
}
