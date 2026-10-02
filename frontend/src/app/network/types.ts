/**
 * Shapes, constants and formatters shared by the network view's hooks and
 * components (split out of `page.tsx`; see `docs/design/plans/2026-09-30-
 * post-review-hardening.md`, WP-F step 5).
 */
import type { EntityRecord, EntityRelationship } from '@/lib/api';
import type { Model, ResponseOf } from '@/lib/apiTypes';

export interface Entity {
  id: string;
  name: string;
  entity_type: string;
  properties?: Record<string, unknown>;
  confidence?: number;
}

/** One edge touching the selected entity, with the provenance it carries
 *  (see components/EvidenceChain). */
export type Relationship = EntityRelationship;

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

export type StructuralHoleEntry = Model<'StructuralHoleItem'>;

/** `node_count` and `edge_count` are absent when the entity is not in the graph. */
export type EgoNetworkData = ResponseOf<'/api/graph/ego-network/{entity_id}', 'get'>;

export type InfluenceStep = Model<'InfluenceStepItem'>;

/** `total_nodes` is absent when no seed was in the graph. */
export type InfluenceResult = ResponseOf<'/api/graph/influence', 'post'>;

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

/** An `/entities` row as the view's `Entity`. A node stored without a name or
 *  type reads as '' (the view already shows those as blank / "Unknown"). */
export function entityFromRecord(e: EntityRecord): Entity {
  return { ...e, name: e.name ?? '', entity_type: e.entity_type ?? '' };
}

/** `{id, name, entity_type}` of a graph node, the shape selection works in. */
export function nodeEntity(n: { id: string; name: string; entity_type: string }): Entity {
  return { id: n.id, name: n.name, entity_type: n.entity_type };
}
