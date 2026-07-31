import axios from 'axios';

// Use relative URL so it works on both localhost and Railway (same-origin)
const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

const api = axios.create({
  baseURL: `${API_BASE}/api`,
  timeout: 300000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth interceptor
api.interceptors.request.use((config) => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // No fallback API key — if no token, the request goes unauthenticated
  // and the 401 interceptor below will redirect to login
  return config;
});

// Redirect to login on 401
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && typeof window !== 'undefined') {
      localStorage.removeItem('auth_token');
      localStorage.removeItem('auth_user');
      // Only redirect if not already on login page
      if (!window.location.pathname.includes('/login')) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export interface Project {
  id: string;
  name: string;
  description: string;
  classification_level: string;
  priority: string;
  status: string;
  entity_count: number;
  relationship_count: number;
  document_count: number;
  collection_count?: number;
  created_at?: string;
  updated_at?: string;
}

export const projectsApi = {
  list: () => api.get<Project[]>('/projects'),
  create: (data: { name: string; description?: string; classification_level?: string; priority?: string }) =>
    api.post<Project>('/projects', data),
  get: (id: string) => api.get<Project>(`/projects/${id}`),
  delete: (id: string) => api.delete(`/projects/${id}`),
  batchDelete: (projectIds: string[]) => api.post('/projects/batch-delete', { project_ids: projectIds }),
  activity: (id: string, limit?: number) => api.get(`/projects/${id}/activity`, { params: { limit } }),
};

export const entitiesApi = {
  search: (projectId: string, query?: string, entityType?: string) =>
    api.get('/entities', { params: { project_id: projectId, query, entity_type: entityType } }),
  get: (id: string) => api.get(`/entities/${id}`),
  subgraph: (id: string, hops?: number) => api.get(`/subgraph/${id}`, { params: { hops } }),
  shortestPath: (id1: string, id2: string) => api.get(`/paths/${id1}/${id2}`),
};

// Local context (Overpass) + AOI spatial query around/within a geotarget.
export const geoApiExtra = {
  nearby: (entityId: string, radius?: number) =>
    api.get(`/geo/nearby/${encodeURIComponent(entityId)}`, { params: { radius } }),
  within: (projectId: string, bbox: { minLat: number; minLng: number; maxLat: number; maxLng: number }) =>
    api.get('/geo/within', {
      params: {
        project_id: projectId,
        min_lat: bbox.minLat, min_lng: bbox.minLng, max_lat: bbox.maxLat, max_lng: bbox.maxLng,
      },
    }),
};

// Cyber-observable enrichment (WHOIS/DNS/GeoIP/certs/KEV/CVSS) — the Investigate
// action. Egress routes through the collection proxy (VPN/Tor), never the LLM path.
export const enrichmentApi = {
  investigate: (entityId: string) => api.post(`/enrichment/entities/${entityId}`),
  getCached: (entityId: string) => api.get(`/enrichment/entities/${entityId}`),
  refresh: (entityId: string, provider: string) =>
    api.post(`/enrichment/entities/${entityId}/refresh`, null, { params: { provider } }),
  providers: () => api.get('/enrichment/providers'),
};

// MITRE ATT&CK® integration — data-driven matrix, technique detail, coverage
// resolution against a project's TTP entities, and Navigator layer export.
export interface AttackCounts {
  tactics: number;
  techniques: number;
  groups: number;
  software: number;
  mitigations: number;
}

export interface AttackStatus {
  ingested: boolean;
  version: string | null;
  counts: AttackCounts;
  // Phase 3a weakness-chain (CWE→CAPEC→ATT&CK) ingest state. Optional so the UI
  // degrades cleanly against a backend that predates the vuln-chain plumbing.
  vuln_chain?: { ingested: boolean; cwes: number };
}

// How a project entity was mapped onto an ATT&CK technique: an explicit T-code
// in the TTP name ("tcode", confidence 1.0) or an AI RAG+LLM mapping ("llm",
// with a model-supplied confidence). Present on observed matrix cells and on the
// technique detail's related entities (Phase 2). Optional so the UI degrades
// cleanly against a backend that hasn't populated it yet.
export type AttackMapMethod = 'tcode' | 'llm';

export interface AttackSubtechnique {
  id: string;
  name: string;
  observed_count: number;
  // DISTINCT MAPS_TO methods across the entities mapped to this sub-technique
  // ("tcode" and/or "llm"). Optional so the UI degrades against a pre-Phase-2
  // backend that doesn't emit it. Per-entity confidence lives in the technique
  // detail's related_entities, not here.
  methods?: AttackMapMethod[];
}

export interface AttackTechniqueCell {
  id: string;
  name: string;
  is_subtechnique: false;
  observed_count: number;
  subtechniques: AttackSubtechnique[];
  // Union of this technique's own + all its sub-techniques' MAPS_TO methods
  // (same rollup as observed_count). Show the "AI" marker when it includes "llm".
  methods?: AttackMapMethod[];
}

export interface AttackTactic {
  id: string;
  name: string;
  shortname: string;
  techniques: AttackTechniqueCell[];
}

export interface AttackMatrixData {
  version: string | null;
  ingested: boolean;
  tactics: AttackTactic[];
}

export interface AttackTechniqueDetail {
  id: string;
  name: string;
  description: string;
  is_subtechnique: boolean;
  parent_id: string | null;
  tactics: { id: string; name: string; shortname: string }[];
  platforms: string[];
  detection: string;
  mitigations: { id: string; name: string }[];
  groups: { id: string; name: string }[];
  related_entities: {
    id: string;
    name: string;
    entity_type: string;
    // Per-entity mapping provenance. tcode edges carry confidence 1.0; llm edges
    // the model's 0..1 confidence; legacy edges default method "tcode", null conf.
    method?: AttackMapMethod;
    confidence?: number | null;
  }[];
  // Phase 3a: the project's CVE/Vulnerability entities whose weakness chain
  // (CWE→CAPEC→ATT&CK) could enable this technique. Potential enablement inferred
  // from the CVE's weaknesses — distinct from observed TTPs. May be empty; optional
  // so the UI degrades against a pre-Phase-3a backend that doesn't emit it.
  enabling_cves?: { id: string; name: string }[];
}

// Threat-actor attribution by technique overlap (Phase 2). Ranked ATT&CK Groups
// that share observed techniques with the project — suggestive overlap only, not
// confirmed attribution.
export interface AttackAttributionGroup {
  id: string;
  name: string;
  shared_count: number;
  coverage: number; // shared / observed_total, 0..1
  shared_techniques: { id: string; name: string }[];
}

export interface AttackAttribution {
  observed_total: number;
  groups: AttackAttributionGroup[];
}

// Phase 3b: MITRE D3FEND defensive countermeasures for a technique. Lazy-loaded
// via a live D3FEND lookup, so `countermeasures` may be [] on an outage. Each
// `id` looks like "d3f:SomeTechnique"; `label` is the human-readable name.
// D3FEND is finer-grained defensive coverage that complements ATT&CK's M-codes.
export interface AttackD3fendCountermeasure {
  id: string;          // D3FEND code, e.g. "D3-DI"
  label: string;       // e.g. "Data Inventory"
  name?: string;       // d3f: local name (URL slug), e.g. "DataInventory"
}

export interface AttackD3fendResponse {
  countermeasures: AttackD3fendCountermeasure[];
}

// Phase 3c: aggregated ATT&CK report for a project. Rolls up observed techniques
// by tactic, candidate attribution (suggestive overlap, not confirmed), key
// mitigations, CVE-enabled techniques, an optional LLM narrative, and a rendered
// markdown document. Fields are optional/possibly-empty so the UI degrades
// against a pre-3c backend and against empty projects.
export interface AttackReportObservedTactic {
  tactic_id: string;
  tactic_name: string;
  techniques: { id: string; name: string; observed_count: number; methods?: AttackMapMethod[] }[];
}

export interface AttackReportAttributionEntry {
  id: string;
  name: string;
  shared_count: number;
  coverage: number;
}

export interface AttackReportMitigation {
  id: string;
  name: string;
  technique_count: number;
}

export interface AttackReportCveEnabled {
  technique_id: string;
  technique_name: string;
  cves: { id: string; name: string }[];
}

export interface AttackReport {
  project_id: string;
  observed_by_tactic: AttackReportObservedTactic[];
  attribution: AttackReportAttributionEntry[];
  key_mitigations: AttackReportMitigation[];
  cve_enabled: AttackReportCveEnabled[];
  narrative: string | null;
  markdown: string;
}

export const attackApi = {
  status: () => api.get<AttackStatus>('/attack/status'),
  // Admin action — downloads ~53MB of ATT&CK STIX server-side; can take 30-60s.
  ingest: () => api.post<{ ingested: true; version: string; counts: AttackCounts }>('/attack/ingest'),
  // Re-map the project's TTP entities onto ATT&CK techniques.
  resolve: (projectId: string) =>
    api.post<{ mapped: number }>('/attack/resolve', null, { params: { project_id: projectId } }),
  // (Admin) Embed all ATT&CK techniques into pgvector for RAG mapping. One-time,
  // idempotent, and slow (~30-90s for 697 techniques).
  embed: () => api.post<{ embedded: number }>('/attack/embed'),
  // RAG+LLM map the project's TTP entities that lack an explicit T-code. Slow for
  // many TTPs. Returns how many were mapped vs. skipped.
  map: (projectId: string) =>
    api.post<{ mapped: number; skipped: number }>('/attack/map', null, {
      params: { project_id: projectId },
    }),
  // Candidate ATT&CK Groups ranked by technique overlap with the project.
  attribution: (projectId: string) =>
    api.get<AttackAttribution>('/attack/attribution', { params: { project_id: projectId } }),
  matrix: (projectId: string) =>
    api.get<AttackMatrixData>('/attack/matrix', { params: { project_id: projectId } }),
  technique: (techniqueId: string, projectId: string) =>
    api.get<AttackTechniqueDetail>(`/attack/technique/${techniqueId}`, {
      params: { project_id: projectId },
    }),
  // Downloadable Navigator layer JSON. Fetched via axios so the auth header is
  // sent (Bearer token in localStorage, not a cookie a plain <a> could carry),
  // then turned into a blob download — matching the other exports in the app.
  navigatorLayer: (projectId: string) =>
    api.get('/attack/navigator-layer', { params: { project_id: projectId } }),
  // (Phase 3b) D3FEND defensive countermeasures for a technique — a lazy, live
  // MITRE D3FEND lookup, so `countermeasures` may be [] on an outage.
  d3fend: (techniqueId: string) =>
    api.get<AttackD3fendResponse>(`/attack/technique/${techniqueId}/d3fend`),
  // (Phase 3c) Aggregated ATT&CK report for a project: observed techniques by
  // tactic, candidate attribution, key mitigations, CVE-enabled techniques, an
  // optional narrative, and a rendered markdown document.
  report: (projectId: string) =>
    api.get<AttackReport>('/attack/report', { params: { project_id: projectId } }),
};

export const graphApi = {
  full: (projectId: string) => api.get('/graph', { params: { project_id: projectId } }),
  communities: (projectId: string) => api.get('/communities', { params: { project_id: projectId } }),
  centrality: (projectId: string) => api.get('/graph/centrality', { params: { project_id: projectId } }),
  statistics: (projectId: string) => api.get('/graph/statistics', { params: { project_id: projectId } }),
  structuralHoles: (projectId: string, topN?: number) =>
    api.get('/graph/structural-holes', { params: { project_id: projectId, top_n: topN } }),
  egoNetwork: (entityId: string, projectId: string, hops?: number) =>
    api.get(`/graph/ego-network/${entityId}`, { params: { project_id: projectId, hops } }),
  influence: (projectId: string, seedIds: string[], steps?: number, threshold?: number) =>
    api.post('/graph/influence', { project_id: projectId, seed_ids: seedIds, steps, threshold }),
};

export const queryApi = {
  rag: (projectId: string, query: string) =>
    api.post('/query', { project_id: projectId, query }),
};

export const llmApi = {
  skills: () => api.get('/llm/skills'),
  query: (
    messages: Array<{role: string; content: string}>,
    skillName?: string,
    overrides?: { system_prompt?: string; temperature?: number; max_tokens?: number },
  ) =>
    api.post('/llm/query', { messages, skill_name: skillName, ...(overrides || {}) }),
};

export const ingestApi = {
  text: (projectId: string, content: string, reliabilityRating?: string) => {
    const formData = new FormData();
    formData.append('project_id', projectId);
    formData.append('content', content);
    if (reliabilityRating) formData.append('reliability_rating', reliabilityRating);
    return api.post('/ingest', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
  },
  file: (projectId: string, file: File, reliabilityRating?: string, extractionMode?: string) => {
    const formData = new FormData();
    formData.append('project_id', projectId);
    formData.append('file', file);
    if (reliabilityRating) formData.append('reliability_rating', reliabilityRating);
    if (extractionMode) formData.append('extraction_mode', extractionMode);
    return api.post('/ingest', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
  },
  batch: (projectId: string, files: File[], reliabilityRating?: string, extractionMode?: string) => {
    const formData = new FormData();
    formData.append('project_id', projectId);
    files.forEach(f => formData.append('files', f));
    if (reliabilityRating) formData.append('reliability_rating', reliabilityRating);
    if (extractionMode) formData.append('extraction_mode', extractionMode);
    return api.post('/ingest/batch', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
  },
};

export const collectionsApi = {
  create: (data: { project_id: string; pir: string; refined_pir?: string; refinement?: string; plan?: object[] }) =>
    api.post('/collections', data),
  list: (projectId?: string) => api.get('/collections', { params: projectId ? { project_id: projectId } : {} }),
  get: (id: string) => api.get(`/collections/${id}`),
  update: (id: string, data: { refined_pir?: string; refinement?: string; plan?: object[]; status?: string }) =>
    api.put(`/collections/${id}`, data),
  status: (id: string) => api.get(`/collections/${id}/status`),
  cancel: (id: string) => api.post(`/collections/${id}/cancel`),
  approve: (id: string) => api.post(`/collections/${id}/approve`),
  parsePlan: (planText: string) => api.post('/collections/parse-plan', { plan_text: planText }),
  count: (projectId: string) => api.get(`/collections/count/${projectId}`),
};

// PIRs — Priority Intelligence Requirements, the requirements spine a project's
// collection hangs off. Every plan raised against one carries its pir_id back.
export type PirStatus = 'OPEN' | 'PARTIAL' | 'SATISFIED' | 'ARCHIVED';

export interface PirPlanLink {
  id: string;
  name: string;
  status: string;
  source_count: number;
  records_acquired: number;
  created_at: string;
}

export interface Pir {
  id: string;
  project_id: string;
  title: string;
  text: string;
  refined_text: string;
  eeis: string[];
  priority: string;
  status: PirStatus;
  created_by: string;
  created_at: string;
  updated_at: string;
  plan_count: number;
  plans: PirPlanLink[];
}

export type RequirementStatus = 'pending' | 'satisfied' | 'unmet';

export interface PirRequirementElement {
  ordinal: number;
  text: string;
  status: RequirementStatus;
  attempts: number;
  queries_tried: string[];
  /** What the assessor said is still absent — the analyst-facing gap. */
  missing: string;
  confidence: string;
}

export interface PirRequirements {
  pir_id: string;
  project_id: string;
  total: number;
  counts: Record<RequirementStatus, number>;
  elements: PirRequirementElement[];
}

export const pirsApi = {
  list: (projectId: string, status?: PirStatus) =>
    api.get<Pir[]>('/pirs', { params: { project_id: projectId, status } }),
  get: (id: string) => api.get<Pir>(`/pirs/${id}`),
  create: (data: {
    project_id: string; text: string; title?: string; refined_text?: string;
    eeis?: string[]; priority?: string; status?: PirStatus; created_by?: string;
  }) => api.post<Pir>('/pirs', data),
  update: (id: string, data: {
    title?: string; text?: string; refined_text?: string;
    eeis?: string[]; priority?: string; status?: PirStatus;
  }) => api.put<Pir>(`/pirs/${id}`, data),
  delete: (id: string) => api.delete(`/pirs/${id}`),
  // Per-element collection state. "unmet" means tried and given up on; it is
  // deliberately distinct from "pending", which is still open.
  requirements: (id: string) =>
    api.get<PirRequirements>(`/pirs/${id}/requirements`),
};

// Collection Plans — new managed pipeline
export interface CollectionPlan {
  id: string;
  project_id: string;
  name: string;
  description: string;
  requirement: string;
  pir: string;
  pir_id: string | null;
  refined_pir: string;
  status: string;
  routing_rules: Record<string, unknown>;
  created_by: string;
  assigned_to: string;
  schedule_cron: string;
  next_run_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  sources: CollectionSourceEntry[];
  source_count: number;
}

export interface CollectionSourceEntry {
  id: string;
  plan_id: string;
  name: string;
  source_type: string;
  config: Record<string, unknown>;
  schedule_cron: string;
  enabled: boolean;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_error: string;
  collection_status: string;
  total_records_acquired: number;
  acquisition_count: number;
  next_run_at: string | null;
  created_at: string | null;
}

export interface CollectionActivityEntry {
  id: string;
  plan_id: string;
  source_id: string | null;
  event: string;
  message: string;
  created_at: string;
}

export interface AcquisitionLogEntry {
  id: string;
  source_id: string;
  plan_id: string;
  result: string;
  record_count: number;
  error_message: string;
  source_type: string;
  entities_created: number;
  relationships_created: number;
  document_id: string;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number;
}

export interface DataCatalogEntry {
  id: string;
  plan_id: string;
  source_id: string;
  name: string;
  file_format: string;
  original_filename: string;
  file_size_bytes: number;
  row_count: number;
  column_count: number;
  schema_info: Record<string, unknown>;
  profiling: Record<string, unknown>;
  preview_rows: Record<string, unknown>[];
  ingested_at: string | null;
}

export const collectionPlansApi = {
  // Plans
  create: (data: { project_id: string; name: string; description?: string; requirement?: string; pir?: string; pir_id?: string; routing_rules?: object; created_by?: string }) =>
    api.post<CollectionPlan>('/collection-plans', data),
  list: (projectId?: string, status?: string) =>
    api.get<CollectionPlan[]>('/collection-plans', { params: { project_id: projectId, status } }),
  get: (id: string) => api.get<CollectionPlan>(`/collection-plans/${id}`),
  update: (id: string, data: Partial<CollectionPlan>) =>
    api.put<CollectionPlan>(`/collection-plans/${id}`, data),
  delete: (id: string) => api.delete(`/collection-plans/${id}`),

  // Status transitions
  activate: (id: string) => api.post<CollectionPlan>(`/collection-plans/${id}/activate`),
  pause: (id: string) => api.post<CollectionPlan>(`/collection-plans/${id}/pause`),
  complete: (id: string) => api.post<CollectionPlan>(`/collection-plans/${id}/complete`),
  archive: (id: string) => api.post<CollectionPlan>(`/collection-plans/${id}/archive`),

  // Execution
  executionStatus: (planId: string) =>
    api.get(`/collection-plans/${planId}/execution-status`),

  // Sources
  addSource: (planId: string, data: { name: string; source_type: string; config?: object; schedule_cron?: string; enabled?: boolean }) =>
    api.post<CollectionSourceEntry>(`/collection-plans/${planId}/sources`, data),
  listSources: (planId: string) =>
    api.get<CollectionSourceEntry[]>(`/collection-plans/${planId}/sources`),
  updateSource: (planId: string, sourceId: string, data: Partial<CollectionSourceEntry>) =>
    api.put<CollectionSourceEntry>(`/collection-plans/${planId}/sources/${sourceId}`, data),
  deleteSource: (planId: string, sourceId: string) =>
    api.delete(`/collection-plans/${planId}/sources/${sourceId}`),

  // File upload through pipeline
  uploadFile: (planId: string, sourceId: string, file: File, extractionMode?: string, reliabilityRating?: string) => {
    const formData = new FormData();
    formData.append('file', file);
    if (extractionMode) formData.append('extraction_mode', extractionMode);
    if (reliabilityRating) formData.append('reliability_rating', reliabilityRating);
    return api.post(`/collection-plans/${planId}/sources/${sourceId}/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  // Acquisition log
  acquisitions: (planId: string, limit?: number) =>
    api.get<AcquisitionLogEntry[]>(`/collection-plans/${planId}/acquisitions`, { params: { limit } }),
  sourceAcquisitions: (planId: string, sourceId: string, limit?: number) =>
    api.get<AcquisitionLogEntry[]>(`/collection-plans/${planId}/sources/${sourceId}/acquisitions`, { params: { limit } }),

  // Data catalog
  catalog: (planId: string) =>
    api.get<DataCatalogEntry[]>(`/collection-plans/${planId}/catalog`),
  catalogEntry: (catalogId: string) =>
    api.get<DataCatalogEntry>(`/data-catalog/${catalogId}`),
  catalogPreview: (catalogId: string, offset?: number, limit?: number) =>
    api.get(`/data-catalog/${catalogId}/preview`, { params: { offset, limit } }),

  // Activity log
  activity: (planId: string, since?: string) =>
    api.get<CollectionActivityEntry[]>(`/collection-plans/${planId}/activity`, { params: { since } }),

  // PIR-driven plan creation (unified flow). Pass pir_id to run against an
  // existing requirement; omit it and the backend persists/reuses one from `pir`.
  fromPir: (data: { project_id: string; pir: string; pir_id?: string; extraction_mode?: string; created_by?: string }) =>
    api.post<CollectionPlan & { llm_plan_text?: string }>('/collection-plans/from-pir', data),
  execute: (planId: string, maxResultsPerSource?: number) =>
    api.post<CollectionPlan & { execution_status: string; message: string }>(
      `/collection-plans/${planId}/execute`,
      maxResultsPerSource != null ? { max_results_per_source: maxResultsPerSource } : undefined,
    ),

  // Dashboard
  dashboard: (projectId: string) => api.get('/collection-dashboard', { params: { project_id: projectId } }),

  // Connector types
  connectorTypes: () => api.get('/connector-types'),
};

export const assessApi = {
  assess: (entityId: string, projectId: string, judgment: string, probability: number) =>
    api.post(`/entities/${entityId}/assess`, { entity_id: entityId, project_id: projectId, judgment, probability }),
  create: (entityId: string, data: { entity_id: string; project_id: string; judgment: string; probability: number; analyst?: string; methodology?: string }) =>
    api.post(`/entities/${entityId}/assess`, data),
  multi: (data: { entity_ids: string[]; project_id: string; judgment?: string; probability?: number }) =>
    api.post('/assess/multi', data),
  generate: (entityId: string, data: { entity_id: string; project_id: string; judgment?: string; probability?: number }) =>
    api.post('/assess/generate', { ...data, entity_id: entityId }),
};

// ── Structured analytic techniques (/api/analysis/*) ──────────────────────
// Grounded runners for the three tradecraft skills. Each retrieves real project
// evidence (graph subgraph, source documents, measured coverage) before
// prompting, and returns a deterministic result when no LLM is configured —
// so the UI must always render `analysis` and check `model !== 'none'`.

export interface SourceEvaluationItem {
  document_id: string;
  name: string;
  current_rating: string;
  admiralty_rating: string;
  entity_count: number;
  corroborating_documents: number;
}

export interface SourceEvaluationResult {
  analysis: string;
  model: string;
  tokens_used: number;
  documents_evaluated: number;
  evaluations: SourceEvaluationItem[];
  ratings_applied: number;
}

export interface Hypothesis {
  id: string;
  statement: string;
  probability: number;
  probability_label: string;
}

export interface HypothesesResult {
  question: string;
  analysis: string;
  hypotheses: Hypothesis[];
  model: string;
  tokens_used: number;
  retrieval_mode: string;
  context_nodes: number;
  context_edges: number;
  vector_hits: number;
  focus_entities: string[];
  assessment_id?: string;
}

export interface StructuralGap {
  kind: string;
  title: string;
  detail: string;
  priority: string;
  count: number;
  examples: string[];
}

export interface GapAnalysisResult {
  analysis: string;
  model: string;
  tokens_used: number;
  retrieval_mode: string;
  coverage: {
    entities: number;
    relationships: number;
    documents: number;
    isolated: number;
    single_link: number;
    unsourced: number;
    unrated_documents: number;
    locations: number;
    ungeocoded_locations: number;
  };
  structural_gaps: StructuralGap[];
  context_nodes: number;
  context_edges: number;
  focus_entities: string[];
}

export const analysisApi = {
  sourceEvaluation: (data: {
    project_id: string;
    document_ids?: string[];
    limit?: number;
    apply_ratings?: boolean;
  }) => api.post<SourceEvaluationResult>('/analysis/source-evaluation', data),
  hypotheses: (data: {
    project_id: string;
    question: string;
    entity_ids?: string[];
    max_hops?: number;
    use_vector?: boolean;
    save_assessment?: boolean;
  }) => api.post<HypothesesResult>('/analysis/hypotheses', data),
  gaps: (data: {
    project_id: string;
    entity_ids?: string[];
    focus?: string;
    max_hops?: number;
  }) => api.post<GapAnalysisResult>('/analysis/gaps', data),
};

export const topicsApi = {
  tree: (projectId: string, method?: string, granularity?: string) =>
    api.get('/topics', { params: { project_id: projectId, method, granularity } }),
  context: (entityId: string, projectId: string) => api.get(`/topics/${entityId}`, { params: { project_id: projectId } }),
  summarizeUrl: (entityId: string) => `${API_BASE}/api/topics/${entityId}/summarize`,

  // Node editing
  updateNode: (nodeId: string, data: { project_id: string; name?: string; description?: string; parent_id?: string }) =>
    api.put(`/topics/${nodeId}`, data),
  addChild: (nodeId: string, data: { project_id: string; name: string; description?: string }) =>
    api.post(`/topics/${nodeId}/children`, data),
  deleteNode: (nodeId: string, projectId: string) =>
    api.delete(`/topics/${nodeId}`, { params: { project_id: projectId } }),

  // Export
  exportMindmap: (projectId: string, format: string = 'json') =>
    api.get('/export/mindmap', { params: { project_id: projectId, format } }),
};

export const reportsApi = {
  save: (data: { project_id: string; title: string; content: string; report_type: string; entity_ids?: string[] }) =>
    api.post('/reports', data),
  // Grounded generation: retrieves real graph + document evidence for the selected
  // entities via the Graph-RAG pipeline before drafting, instead of a bare LLM call.
  generate: (data: {
    project_id: string;
    report_type: string;
    skill_name: string;
    entity_ids: string[];
    include_evidence?: boolean;
    probability_assessments?: boolean;
  }) => api.post('/reports/generate', data),
  list: (projectId: string) => api.get('/reports', { params: { project_id: projectId } }),
  get: (id: string) => api.get(`/reports/${id}`),
  delete: (id: string) => api.delete(`/reports/${id}`),
};

export const timelineApi = {
  get: (projectId: string) => api.get('/timeline', { params: { project_id: projectId } }),
  /** Event-date distribution for the network view's brush filter. */
  histogram: (projectId: string, bucket: 'day' | 'month' | 'year' = 'month') =>
    api.get('/timeline/histogram', { params: { project_id: projectId, bucket } }),
};

export const notebookApi = {
  create: (data: { project_id: string; title: string; content: string; entity_ids?: string[]; note_type?: string }) =>
    api.post('/notebook', data),
  list: (projectId: string) => api.get('/notebook', { params: { project_id: projectId } }),
  get: (id: string) => api.get(`/notebook/${id}`),
  delete: (id: string) => api.delete(`/notebook/${id}`),
};

export const geoApi = {
  locations: (projectId: string) => api.get('/geo/locations', { params: { project_id: projectId } }),
  entityTimeline: (entityId: string, projectId: string) =>
    api.get('/geo/entity-timeline', { params: { entity_id: entityId, project_id: projectId } }),
};

export const searchApi = {
  search: (projectId: string, query: string) =>
    api.get('/search', { params: { project_id: projectId, q: query } }),
  /**
   * Meaning-based retrieval over document chunks (pgvector). Returns passages
   * with a similarity score rather than name matches, so it finds material
   * that never uses the query's words.
   */
  semantic: (projectId: string, query: string) =>
    api.post('/search/semantic', { project_id: projectId, query }),
};

export const exportApi = {
  graph: (projectId: string) => api.get('/export/graph', { params: { project_id: projectId } }),
  entities: (projectId: string) => api.get('/export/entities', { params: { project_id: projectId } }),
  report: (reportId: string) => api.get(`/export/report/${reportId}`),
  stix: (projectId: string) => api.get('/export/stix', { params: { project_id: projectId } }),
};

export const adminApi = {
  config: () => api.get('/admin/config'),
  getProxy: () => api.get('/admin/proxy'),
  updateProxy: (data: { mode: 'direct' | 'vpn' | 'tor'; proxy_url?: string; tor_port?: number }) =>
    api.put('/admin/proxy', data),
  // Collection egress VPN (gluetun sidecar, docker compose --profile vpn)
  getVpnStatus: () => api.get('/admin/vpn/status'),
  setVpnStatus: (action: 'start' | 'stop') => api.put('/admin/vpn/status', { action }),
  listModels: () => api.get('/admin/llm/models'),
  selectModel: (provider: string, model: string) =>
    api.put('/admin/llm/select', { provider, model }),
  // API Key management
  listApiKeys: () => api.get('/admin/api-keys'),
  addApiKey: (provider: string, label: string, apiKey: string) =>
    api.post('/admin/api-keys', { provider, label, api_key: apiKey }),
  activateApiKey: (keyId: string, provider: string) =>
    api.put('/admin/api-keys/activate', { key_id: keyId, provider }),
  deleteApiKey: (keyId: string) =>
    api.delete(`/admin/api-keys/${keyId}`),
  // Cyber enrichment: auto-enrich toggle + provider inventory
  getEnrichmentConfig: () => api.get('/admin/enrichment'),
  setEnrichmentConfig: (autoEnabled: boolean) =>
    api.put('/admin/enrichment', { auto_enabled: autoEnabled }),
  listEnrichmentProviders: () => api.get('/enrichment/providers'),
};

export const watchlistApi = {
  add: (projectId: string, entityId: string) =>
    api.post('/watchlist/add', { project_id: projectId, entity_id: entityId }),
  remove: (projectId: string, entityId: string) =>
    api.post('/watchlist/remove', { project_id: projectId, entity_id: entityId }),
  list: (projectId: string) => api.get('/watchlist', { params: { project_id: projectId } }),
};

export const entityMgmtApi = {
  merge: (primaryId: string, mergeIds: string[], projectId: string) =>
    api.post('/entities/merge', { primary_id: primaryId, merge_ids: mergeIds, project_id: projectId }),
  updateType: (entityId: string, entityType: string) =>
    api.put(`/entities/${entityId}/type`, { entity_type: entityType }),
};

export const personasApi = {
  list: () => api.get('/personas'),
  create: (data: { id: string; name: string; description: string; skills: string[]; temperature?: number }) =>
    api.post('/personas', data),
  activate: (id: string) => api.post(`/personas/${id}/activate`),
  delete: (id: string) => api.delete(`/personas/${id}`),
  active: () => api.get('/personas/active'),
};

export const snapshotsApi = {
  create: (data: { project_id: string; name: string; entity_ids: string[]; description?: string }) =>
    api.post('/snapshots', data),
  list: (projectId: string) => api.get('/snapshots', { params: { project_id: projectId } }),
  get: (id: string) => api.get(`/snapshots/${id}`),
  delete: (id: string) => api.delete(`/snapshots/${id}`),
};

export const documentsApi = {
  list: (projectId: string) => api.get('/documents', { params: { project_id: projectId } }),
  get: (docId: string) => api.get(`/documents/${docId}`),
  evidence: (docId: string, entityName: string) =>
    api.get(`/documents/${docId}/evidence`, { params: { entity_name: entityName } }),
};

export const healthApi = {
  check: () => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
    // SECURITY: only use token if available, don't fall back to hardcoded keys
    const headers: Record<string, string> = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    return axios.get(`${API_BASE}/health`, { headers });
  },
};

/**
 * Return an entity's field bag regardless of how the route shaped it.
 *
 * The entity routes flatten node fields onto the object (`asn`, `geolocation`,
 * `enriched`, …) while a few others (geo) nest them under `properties`. Code
 * that read `entity.properties.x` therefore got `undefined` for everything on
 * the flattened shape — which is why enriched observables rendered as
 * un-enriched and the "Enriched" stat sat at 0%.
 *
 * Prefer this over touching `.properties` directly.
 */
export function entityFields(entity: unknown): Record<string, unknown> {
  if (!entity || typeof entity !== 'object') return {};
  const e = entity as Record<string, unknown>;
  const nested =
    e.properties && typeof e.properties === 'object' && !Array.isArray(e.properties)
      ? (e.properties as Record<string, unknown>)
      : {};
  // Nested wins: where a route supplies both, `properties` is the explicit one.
  return { ...e, ...nested };
}

export default api;
