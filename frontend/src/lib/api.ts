import axios, { type AxiosRequestConfig } from 'axios';
import { createSummaryStreamParser, type SummaryStreamEvent } from './sse';
import type { AttackMapResult } from './attackMapping';
import type { BodyOf, ClientPath, Model, QueryOf, ResponseOf } from './apiTypes';

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

/** Keys that belong to one analyst's session. */
const SESSION_KEYS = ['auth_token', 'auth_user', 'auth_role', 'activeProject'];
/** Per-project assistant threads (see `AssistantContext`): RAG answers and
 *  verbatim source-document excerpts. */
const ASSISTANT_THREAD_PREFIX = 'assistant_thread:';

/**
 * Forget everything the current analyst's session left in this browser: the
 * token and identity, the selected project, and every assistant thread. Called
 * on sign-out, on a 401, and before storing a new login, because workstations
 * are shared and none of it may carry over to the next analyst. Per-browser
 * display preferences (layout choices) are kept.
 */
export function clearSession(): void {
  if (typeof window === 'undefined') return;
  try {
    const storage = window.localStorage;
    const threads: string[] = [];
    for (let i = 0; i < storage.length; i++) {
      const key = storage.key(i);
      if (key && key.startsWith(ASSISTANT_THREAD_PREFIX)) threads.push(key);
    }
    for (const key of [...SESSION_KEYS, ...threads]) storage.removeItem(key);
  } catch {
    /* storage unavailable (private mode, blocked site data): nothing to clear */
  }
}

/** A 401 means the session is over: clear it and send the analyst to log in. */
function handleUnauthorized(): void {
  if (typeof window === 'undefined') return;
  clearSession();
  // Only redirect if not already on login page
  if (!window.location.pathname.includes('/login')) {
    window.location.href = '/login';
  }
}

// Redirect to login on 401
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) handleUnauthorized();
    return Promise.reject(error);
  }
);

/** Whether the signed-in user is an admin, per the role stored at login.
 *  UI gating only: the backend enforces admin on every admin route, this just
 *  keeps analysts from being offered buttons that can only 403. */
export function isAdminSession(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return localStorage.getItem('auth_role') === 'admin';
  } catch {
    return false;
  }
}

/** True for an axios error the backend answered with `status`. */
export function isHttpStatus(error: unknown, status: number): boolean {
  return axios.isAxiosError(error) && error.response?.status === status;
}

/**
 * The body of a route that declares no response schema (no `response_model`
 * on the FastAPI route, so the generated type is `unknown`). As loose as
 * axios' own default, which is what every caller was written against; a
 * route that declares one is typed with `ResponseOf` instead.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Undeclared = any;

/**
 * The axios instance with each URL checked against the generated route list
 * (`ClientPath`): calling a route the backend does not serve for that method
 * is a compile error. Same instance, same interceptors, same runtime.
 */
const http = {
  get: <T = Undeclared>(url: ClientPath<'get'>, config?: AxiosRequestConfig) => api.get<T>(url, config),
  post: <T = Undeclared>(url: ClientPath<'post'>, data?: unknown, config?: AxiosRequestConfig) =>
    api.post<T>(url, data, config),
  put: <T = Undeclared>(url: ClientPath<'put'>, data?: unknown, config?: AxiosRequestConfig) =>
    api.put<T>(url, data, config),
  delete: <T = Undeclared>(url: ClientPath<'delete'>, config?: AxiosRequestConfig) => api.delete<T>(url, config),
};

export type Project = Model<'ProjectResponse'>;

export const projectsApi = {
  /** Same shape as one `ProjectResponse` per project; the list route declares
   *  no schema of its own. */
  list: () => http.get<Project[]>('/projects'),
  create: (data: BodyOf<'/api/projects', 'post'>) =>
    http.post<ResponseOf<'/api/projects', 'post'>>('/projects', data),
  get: (id: string) => http.get<ResponseOf<'/api/projects/{project_id}', 'get'>>(`/projects/${id}`),
  delete: (id: string) => http.delete(`/projects/${id}`),
  batchDelete: (projectIds: string[]) => http.post('/projects/batch-delete', { project_ids: projectIds } satisfies BodyOf<'/api/projects/batch-delete', 'post'>),
  activity: (id: string, limit?: number) => http.get(`/projects/${id}/activity`, { params: { limit } satisfies QueryOf<'/api/projects/{project_id}/activity', 'get'> }),
};

/** How many rows matched in full, from `X-Total-Count`.
 *
 *  Falls back to the page length when the header is absent, so a caller that
 *  cannot read it under-reports rather than inventing a number. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function totalFrom(res: { headers?: any; data?: unknown }): number {
  const raw = res.headers?.['x-total-count'] ?? res.headers?.['X-Total-Count'];
  const n = Number(raw);
  return Number.isFinite(n) && n >= 0 ? n : (Array.isArray(res.data) ? res.data.length : 0);
}

export const entitiesApi = {
  /** Entities matching the filters. `limit` defaults to 50 on the server, so a
   *  view that means to show everything must say so. Read the true total from
   *  the `X-Total-Count` response header (see `totalFrom`) rather than assuming
   *  the array is complete. */
  search: (projectId: string, query?: string, entityType?: string, limit?: number) =>
    http.get('/entities', { params: { project_id: projectId, query, entity_type: entityType, limit } satisfies QueryOf<'/api/entities', 'get'> }),
  get: (id: string) => http.get(`/entities/${id}`),
  subgraph: (id: string, hops?: number) => http.get(`/subgraph/${id}`, { params: { hops } satisfies QueryOf<'/api/subgraph/{entity_id}', 'get'> }),
  shortestPath: (id1: string, id2: string) => http.get(`/paths/${id1}/${id2}`),
};

// Local context (Overpass) + AOI spatial query around/within a geotarget.
export const geoApiExtra = {
  nearby: (entityId: string, radius?: number) =>
    http.get(`/geo/nearby/${encodeURIComponent(entityId)}`, { params: { radius } satisfies QueryOf<'/api/geo/nearby/{entity_id}', 'get'> }),
  within: (projectId: string, bbox: { minLat: number; minLng: number; maxLat: number; maxLng: number }) =>
    http.get('/geo/within', {
      params: {
        project_id: projectId,
        min_lat: bbox.minLat, min_lng: bbox.minLng, max_lat: bbox.maxLat, max_lng: bbox.maxLng,
      } satisfies QueryOf<'/api/geo/within', 'get'>,
    }),
};

// Cyber-observable enrichment (WHOIS/DNS/GeoIP/certs/KEV/CVSS) — the Investigate
// action. Egress routes through the collection proxy (VPN/Tor), never the LLM path.
export const enrichmentApi = {
  investigate: (entityId: string) => http.post(`/enrichment/entities/${entityId}`),
  getCached: (entityId: string) => http.get(`/enrichment/entities/${entityId}`),
  refresh: (entityId: string, provider: string) =>
    http.post(`/enrichment/entities/${entityId}/refresh`, null, { params: { provider } satisfies QueryOf<'/api/enrichment/entities/{entity_id}/refresh', 'post'> }),
  providers: () => http.get('/enrichment/providers'),
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
  /** The live D3FEND lookup failed or answered in an unexpected shape, so the
   *  empty list means "unknown", not "none"; nothing was cached. */
  degraded?: boolean;
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
  status: () => http.get<AttackStatus>('/attack/status'),
  // Admin action — downloads ~53MB of ATT&CK STIX server-side; can take 30-60s.
  ingest: () => http.post<{ ingested: true; version: string; counts: AttackCounts }>('/attack/ingest'),
  // Re-map the project's TTP entities onto ATT&CK techniques.
  resolve: (projectId: string) =>
    http.post<{ mapped: number }>('/attack/resolve', null, { params: { project_id: projectId } satisfies QueryOf<'/api/attack/resolve', 'post'> }),
  // (Admin) Embed all ATT&CK techniques into pgvector for RAG mapping. One-time,
  // idempotent, and slow (~30-90s for 697 techniques).
  // `embedded: 0` comes with a machine `reason` and a human `detail` saying why
  // (no techniques ingested, no provider, rate-limited) — never read a bare 0
  // as success.
  embed: () => http.post<{ embedded: number; reason?: string; detail?: string }>('/attack/embed'),
  // RAG+LLM map the project's TTP entities that lack an explicit T-code. Slow for
  // many TTPs. Returns mapped/skipped counts with a reason per skip
  // (`skip_reasons`); `remap` also re-checks earlier AI mappings and reports how
  // many it removed (`stale_removed`). 503 "LLM provider unavailable" when no
  // model can run. See `lib/attackMapping` for the wording.
  map: (projectId: string, remap = false) =>
    http.post<AttackMapResult>('/attack/map', null, {
      params: { project_id: projectId, ...(remap ? { remap: true } : {}) } satisfies QueryOf<'/api/attack/map', 'post'>,
    }),
  // Candidate ATT&CK Groups ranked by technique overlap with the project.
  attribution: (projectId: string) =>
    http.get<AttackAttribution>('/attack/attribution', { params: { project_id: projectId } satisfies QueryOf<'/api/attack/attribution', 'get'> }),
  matrix: (projectId: string) =>
    http.get<AttackMatrixData>('/attack/matrix', { params: { project_id: projectId } satisfies QueryOf<'/api/attack/matrix', 'get'> }),
  technique: (techniqueId: string, projectId: string) =>
    http.get<AttackTechniqueDetail>(`/attack/technique/${techniqueId}`, {
      params: { project_id: projectId } satisfies QueryOf<'/api/attack/technique/{tid}', 'get'>,
    }),
  // Downloadable Navigator layer JSON. Fetched via axios so the auth header is
  // sent (Bearer token in localStorage, not a cookie a plain <a> could carry),
  // then turned into a blob download — matching the other exports in the app.
  navigatorLayer: (projectId: string) =>
    http.get('/attack/navigator-layer', { params: { project_id: projectId } satisfies QueryOf<'/api/attack/navigator-layer', 'get'> }),
  // (Phase 3b) D3FEND defensive countermeasures for a technique — a lazy, live
  // MITRE D3FEND lookup, so `countermeasures` may be [] on an outage.
  d3fend: (techniqueId: string) =>
    http.get<AttackD3fendResponse>(`/attack/technique/${techniqueId}/d3fend`),
  // (Phase 3c) Aggregated ATT&CK report for a project: observed techniques by
  // tactic, candidate attribution, key mitigations, CVE-enabled techniques, an
  // optional narrative, and a rendered markdown document.
  report: (projectId: string) =>
    http.get<AttackReport>('/attack/report', { params: { project_id: projectId } satisfies QueryOf<'/api/attack/report', 'get'> }),
};

export const graphApi = {
  full: (projectId: string) => http.get('/graph', { params: { project_id: projectId } satisfies QueryOf<'/api/graph', 'get'> }),
  communities: (projectId: string) => http.get('/communities', { params: { project_id: projectId } satisfies QueryOf<'/api/communities', 'get'> }),
  centrality: (projectId: string) => http.get('/graph/centrality', { params: { project_id: projectId } satisfies QueryOf<'/api/graph/centrality', 'get'> }),
  statistics: (projectId: string) => http.get('/graph/statistics', { params: { project_id: projectId } satisfies QueryOf<'/api/graph/statistics', 'get'> }),
  structuralHoles: (projectId: string, topN?: number) =>
    http.get('/graph/structural-holes', { params: { project_id: projectId, top_n: topN } satisfies QueryOf<'/api/graph/structural-holes', 'get'> }),
  egoNetwork: (entityId: string, projectId: string, hops?: number) =>
    http.get(`/graph/ego-network/${entityId}`, { params: { project_id: projectId, hops } satisfies QueryOf<'/api/graph/ego-network/{entity_id}', 'get'> }),
  influence: (projectId: string, seedIds: string[], steps?: number, threshold?: number) =>
    http.post('/graph/influence', {
      project_id: projectId, seed_ids: seedIds, steps, threshold,
    } satisfies BodyOf<'/api/graph/influence', 'post'>),
};

export const queryApi = {
  rag: (projectId: string, query: string) =>
    http.post('/query', { project_id: projectId, query } satisfies BodyOf<'/api/query', 'post'>),
};

export const llmApi = {
  skills: () => http.get<ResponseOf<'/api/llm/skills', 'get'>>('/llm/skills'),
  query: (
    messages: Array<{role: string; content: string}>,
    skillName?: string,
    overrides?: { system_prompt?: string; temperature?: number; max_tokens?: number },
  ) =>
    http.post('/llm/query', {
      messages, skill_name: skillName, ...(overrides || {}),
    } satisfies BodyOf<'/api/llm/query', 'post'>),
};

export const ingestApi = {
  text: (projectId: string, content: string, reliabilityRating?: string) => {
    const formData = new FormData();
    formData.append('project_id', projectId);
    formData.append('content', content);
    if (reliabilityRating) formData.append('reliability_rating', reliabilityRating);
    return http.post('/ingest', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
  },
  file: (projectId: string, file: File, reliabilityRating?: string, extractionMode?: string) => {
    const formData = new FormData();
    formData.append('project_id', projectId);
    formData.append('file', file);
    if (reliabilityRating) formData.append('reliability_rating', reliabilityRating);
    if (extractionMode) formData.append('extraction_mode', extractionMode);
    return http.post('/ingest', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
  },
  batch: (projectId: string, files: File[], reliabilityRating?: string, extractionMode?: string) => {
    const formData = new FormData();
    formData.append('project_id', projectId);
    files.forEach(f => formData.append('files', f));
    if (reliabilityRating) formData.append('reliability_rating', reliabilityRating);
    if (extractionMode) formData.append('extraction_mode', extractionMode);
    return http.post('/ingest/batch', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
  },
};

export const collectionsApi = {
  create: (data: BodyOf<'/api/collections', 'post'>) =>
    http.post('/collections', data),
  list: (projectId?: string) => http.get('/collections', { params: projectId ? { project_id: projectId } : {} }),
  get: (id: string) => http.get(`/collections/${id}`),
  update: (id: string, data: BodyOf<'/api/collections/{task_id}', 'put'>) =>
    http.put(`/collections/${id}`, data),
  status: (id: string) => http.get(`/collections/${id}/status`),
  cancel: (id: string) => http.post(`/collections/${id}/cancel`),
  parsePlan: (planText: string) => http.post('/collections/parse-plan', { plan_text: planText } satisfies BodyOf<'/api/collections/parse-plan', 'post'>),
  count: (projectId: string) => http.get(`/collections/count/${projectId}`),
};

// PIRs — Priority Intelligence Requirements, the requirements spine a project's
// collection hangs off. Every plan raised against one carries its pir_id back.
export type PirStatus = 'OPEN' | 'PARTIAL' | 'SATISFIED' | 'ARCHIVED';

export type PirPlanLink = Model<'PirPlanLink'>;

/** `PirResponse` with `status` narrowed: the schema says `str`, the route
 *  only ever stores one of `PirStatus`. */
export type Pir = Omit<Model<'PirResponse'>, 'status'> & { status: PirStatus };

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
    http.get<Pir[]>('/pirs', { params: { project_id: projectId, status } satisfies QueryOf<'/api/pirs', 'get'> }),
  get: (id: string) => http.get<Pir>(`/pirs/${id}`),
  create: (data: Omit<BodyOf<'/api/pirs', 'post'>, 'status'> & { status?: PirStatus }) =>
    http.post<Pir>('/pirs', data),
  update: (id: string, data: Omit<BodyOf<'/api/pirs/{pir_id}', 'put'>, 'status'> & { status?: PirStatus }) =>
    http.put<Pir>(`/pirs/${id}`, data),
  delete: (id: string) => http.delete(`/pirs/${id}`),
  // Per-element collection state. "unmet" means tried and given up on; it is
  // deliberately distinct from "pending", which is still open.
  requirements: (id: string) =>
    http.get<PirRequirements>(`/pirs/${id}/requirements`),
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
  /** Why generation produced less than it should have, as recorded by the
   *  backend. Present on the from-pir response; absent on plain plan reads. */
  generation_failures?: string[];
  /** Essential elements captured onto the requirement. Zero means satisfaction
   *  cannot be measured and collection cannot re-task against the gaps. */
  eeis_captured?: number;
}

/** Whether a collection run is actually in flight, from the activity trail —
 *  distinct from `CollectionPlan.status`, which is a lifecycle flag an analyst
 *  sets by hand and says nothing about whether work is happening now. */
export interface PlanExecutionStatus {
  plan_id: string;
  /** idle | running | stalled | completed | failed | error */
  status: string;
  message?: string;
  last_event?: string;
  sources_succeeded?: number;
  sources_failed?: number;
  updated_at?: string;
  /** How long the plan has been silent. `stalled` means past the backend's
   *  threshold, i.e. presumed dead rather than merely slow. */
  seconds_since_last_event?: number;
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
  create: (data: BodyOf<'/api/collection-plans', 'post'>) =>
    http.post<CollectionPlan>('/collection-plans', data),
  list: (projectId?: string, status?: string) =>
    http.get<CollectionPlan[]>('/collection-plans', { params: { project_id: projectId, status } satisfies QueryOf<'/api/collection-plans', 'get'> }),
  get: (id: string) => http.get<CollectionPlan>(`/collection-plans/${id}`),
  update: (id: string, data: BodyOf<'/api/collection-plans/{plan_id}', 'put'>) =>
    http.put<CollectionPlan>(`/collection-plans/${id}`, data),
  delete: (id: string) => http.delete(`/collection-plans/${id}`),

  // Status transitions
  activate: (id: string) => http.post<CollectionPlan>(`/collection-plans/${id}/activate`),
  pause: (id: string) => http.post<CollectionPlan>(`/collection-plans/${id}/pause`),
  complete: (id: string) => http.post<CollectionPlan>(`/collection-plans/${id}/complete`),
  archive: (id: string) => http.post<CollectionPlan>(`/collection-plans/${id}/archive`),

  // Execution
  executionStatus: (planId: string) =>
    http.get<PlanExecutionStatus>(`/collection-plans/${planId}/execution-status`),

  // Sources
  addSource: (planId: string, data: BodyOf<'/api/collection-plans/{plan_id}/sources', 'post'>) =>
    http.post<CollectionSourceEntry>(`/collection-plans/${planId}/sources`, data),
  listSources: (planId: string) =>
    http.get<CollectionSourceEntry[]>(`/collection-plans/${planId}/sources`),
  updateSource: (planId: string, sourceId: string, data: BodyOf<'/api/collection-plans/{plan_id}/sources/{source_id}', 'put'>) =>
    http.put<CollectionSourceEntry>(`/collection-plans/${planId}/sources/${sourceId}`, data),
  deleteSource: (planId: string, sourceId: string) =>
    http.delete(`/collection-plans/${planId}/sources/${sourceId}`),

  // File upload through pipeline
  uploadFile: (planId: string, sourceId: string, file: File, extractionMode?: string, reliabilityRating?: string) => {
    const formData = new FormData();
    formData.append('file', file);
    if (extractionMode) formData.append('extraction_mode', extractionMode);
    if (reliabilityRating) formData.append('reliability_rating', reliabilityRating);
    return http.post(`/collection-plans/${planId}/sources/${sourceId}/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  // Acquisition log
  acquisitions: (planId: string, limit?: number) =>
    http.get<AcquisitionLogEntry[]>(`/collection-plans/${planId}/acquisitions`, { params: { limit } satisfies QueryOf<'/api/collection-plans/{plan_id}/acquisitions', 'get'> }),
  sourceAcquisitions: (planId: string, sourceId: string, limit?: number) =>
    http.get<AcquisitionLogEntry[]>(`/collection-plans/${planId}/sources/${sourceId}/acquisitions`, { params: { limit } satisfies QueryOf<'/api/collection-plans/{plan_id}/sources/{source_id}/acquisitions', 'get'> }),

  // Data catalog
  catalog: (planId: string) =>
    http.get<DataCatalogEntry[]>(`/collection-plans/${planId}/catalog`),
  catalogEntry: (catalogId: string) =>
    http.get<DataCatalogEntry>(`/data-catalog/${catalogId}`),
  catalogPreview: (catalogId: string, offset?: number, limit?: number) =>
    http.get(`/data-catalog/${catalogId}/preview`, { params: { offset, limit } satisfies QueryOf<'/api/data-catalog/{catalog_id}/preview', 'get'> }),

  // Activity log
  activity: (planId: string, since?: string) =>
    http.get<CollectionActivityEntry[]>(`/collection-plans/${planId}/activity`, { params: { since } satisfies QueryOf<'/api/collection-plans/{plan_id}/activity', 'get'> }),

  // PIR-driven plan creation (unified flow). Pass pir_id to run against an
  // existing requirement; omit it and the backend persists/reuses one from `pir`.
  fromPir: (data: BodyOf<'/api/collection-plans/from-pir', 'post'>) =>
    http.post<CollectionPlan & { llm_plan_text?: string }>('/collection-plans/from-pir', data),
  execute: (planId: string, maxResultsPerSource?: number) =>
    http.post<CollectionPlan & { execution_status: string; message: string }>(
      `/collection-plans/${planId}/execute`,
      maxResultsPerSource != null
        ? ({ max_results_per_source: maxResultsPerSource } satisfies BodyOf<'/api/collection-plans/{plan_id}/execute', 'post'>)
        : undefined,
    ),

  // Dashboard
  dashboard: (projectId: string) => http.get('/collection-dashboard', { params: { project_id: projectId } satisfies QueryOf<'/api/collection-dashboard', 'get'> }),

  // Connector types
  connectorTypes: () => http.get('/connector-types'),
};

export const assessApi = {
  assess: (entityId: string, projectId: string, judgment: string, probability: number) =>
    http.post(`/entities/${entityId}/assess`, {
      entity_id: entityId, project_id: projectId, judgment, probability,
    } satisfies BodyOf<'/api/entities/{entity_id}/assess', 'post'>),
  create: (entityId: string, data: BodyOf<'/api/entities/{entity_id}/assess', 'post'>) =>
    http.post(`/entities/${entityId}/assess`, data),
  multi: (data: BodyOf<'/api/assess/multi', 'post'>) =>
    http.post('/assess/multi', data),
  generate: (entityId: string, data: BodyOf<'/api/assess/generate', 'post'>) =>
    http.post('/assess/generate', { ...data, entity_id: entityId } satisfies BodyOf<'/api/assess/generate', 'post'>),
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
  sourceEvaluation: (data: BodyOf<'/api/analysis/source-evaluation', 'post'>) =>
    http.post<SourceEvaluationResult>('/analysis/source-evaluation', data),
  hypotheses: (data: BodyOf<'/api/analysis/hypotheses', 'post'>) =>
    http.post<HypothesesResult>('/analysis/hypotheses', data),
  gaps: (data: BodyOf<'/api/analysis/gaps', 'post'>) =>
    http.post<GapAnalysisResult>('/analysis/gaps', data),
};

export const topicsApi = {
  tree: (projectId: string, method?: string, granularity?: string) =>
    http.get('/topics', { params: { project_id: projectId, method, granularity } satisfies QueryOf<'/api/topics', 'get'> }),
  context: (entityId: string, projectId: string) => http.get(`/topics/${entityId}`, { params: { project_id: projectId } satisfies QueryOf<'/api/topics/{entity_id}', 'get'> }),
  summarizeUrl: (entityId: string) => `${API_BASE}/api/topics/${entityId}/summarize`,
  /** Stream an LLM summary of a topic node (server-sent events; see `lib/sse`).
   *  `onText` receives the text so far as events arrive. Resolves with the full
   *  summary only once the stream says `[DONE]`; rejects on an HTTP error, an
   *  `{"error"}` event, a malformed payload, or a stream that stops early, so a
   *  failure can never be mistaken for (or cached as) a summary. */
  streamSummary: async (
    entityId: string,
    body: BodyOf<'/api/topics/{entity_id}/summarize', 'post'>,
    onText?: (textSoFar: string) => void,
  ): Promise<string> => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
    const response = await fetch(topicsApi.summarizeUrl(entityId), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    });
    if (response.status === 401) handleUnauthorized();
    if (!response.ok) throw new Error(`Summary request failed (${response.status}).`);
    const reader = response.body?.getReader();
    if (!reader) throw new Error('The summary response had no body.');

    const decoder = new TextDecoder();
    const parser = createSummaryStreamParser();
    let text = '';
    let finished = false;
    const apply = (events: SummaryStreamEvent[]) => {
      for (const event of events) {
        if (event.type === 'error') throw new Error(event.message);
        if (event.type === 'done') {
          finished = true;
          return;
        }
        text += event.text;
        onText?.(text);
      }
    };
    try {
      while (!finished) {
        const { done, value } = await reader.read();
        if (done) {
          apply(parser.push(decoder.decode()));
          apply(parser.end());
          break;
        }
        apply(parser.push(decoder.decode(value, { stream: true })));
      }
    } finally {
      reader.cancel().catch(() => undefined);
    }
    if (!finished) throw new Error('The summary stream ended before it finished.');
    return text;
  },

  // Node editing
  updateNode: (nodeId: string, data: BodyOf<'/api/topics/{node_id}', 'put'>) =>
    http.put(`/topics/${nodeId}`, data),
  addChild: (nodeId: string, data: BodyOf<'/api/topics/{node_id}/children', 'post'>) =>
    http.post(`/topics/${nodeId}/children`, data),
  deleteNode: (nodeId: string, projectId: string) =>
    http.delete(`/topics/${nodeId}`, { params: { project_id: projectId } satisfies QueryOf<'/api/topics/{node_id}', 'delete'> }),

  // Export
  exportMindmap: (projectId: string, format: string = 'json') =>
    http.get('/export/mindmap', { params: { project_id: projectId, format } satisfies QueryOf<'/api/export/mindmap', 'get'> }),
};

export const reportsApi = {
  save: (data: BodyOf<'/api/reports', 'post'>) =>
    http.post('/reports', data),
  // Grounded generation: retrieves real graph + document evidence for the selected
  // entities via the Graph-RAG pipeline before drafting, instead of a bare LLM call.
  // `requirement` (PIR text) or `pir_id` makes the requirement the subject of the
  // product; without one it is only "tell me about these entities". Answers 503
  // "LLM provider unavailable" when no model could draft it.
  generate: (data: BodyOf<'/api/reports/generate', 'post'>) => http.post('/reports/generate', data),
  list: (projectId: string) => http.get('/reports', { params: { project_id: projectId } satisfies QueryOf<'/api/reports', 'get'> }),
  get: (id: string) => http.get(`/reports/${id}`),
  delete: (id: string) => http.delete(`/reports/${id}`),
};

export const timelineApi = {
  get: (projectId: string) => http.get('/timeline', { params: { project_id: projectId } satisfies QueryOf<'/api/timeline', 'get'> }),
  /** Event-date distribution for the network view's brush filter. */
  histogram: (projectId: string, bucket: 'day' | 'month' | 'year' = 'month') =>
    http.get('/timeline/histogram', { params: { project_id: projectId, bucket } satisfies QueryOf<'/api/timeline/histogram', 'get'> }),
};

/** The note kinds the notebook route accepts (anything else is a 422). */
export type NoteType = NonNullable<BodyOf<'/api/notebook', 'post'>['note_type']>;

export const notebookApi = {
  create: (data: BodyOf<'/api/notebook', 'post'>) =>
    http.post('/notebook', data),
  list: (projectId: string) => http.get('/notebook', { params: { project_id: projectId } satisfies QueryOf<'/api/notebook', 'get'> }),
  get: (id: string) => http.get(`/notebook/${id}`),
  delete: (id: string) => http.delete(`/notebook/${id}`),
};

export const geoApi = {
  locations: (projectId: string) => http.get('/geo/locations', { params: { project_id: projectId } satisfies QueryOf<'/api/geo/locations', 'get'> }),
  entityTimeline: (entityId: string, projectId: string) =>
    http.get('/geo/entity-timeline', { params: { entity_id: entityId, project_id: projectId } satisfies QueryOf<'/api/geo/entity-timeline', 'get'> }),
};

export const searchApi = {
  search: (projectId: string, query: string) =>
    http.get('/search', { params: { project_id: projectId, q: query } satisfies QueryOf<'/api/search', 'get'> }),
  /**
   * Meaning-based retrieval over document chunks (pgvector). Returns passages
   * with a similarity score rather than name matches, so it finds material
   * that never uses the query's words.
   */
  semantic: (projectId: string, query: string) =>
    http.post('/search/semantic', { project_id: projectId, query } satisfies BodyOf<'/api/search/semantic', 'post'>),
};

export const exportApi = {
  graph: (projectId: string) => http.get('/export/graph', { params: { project_id: projectId } satisfies QueryOf<'/api/export/graph', 'get'> }),
  entities: (projectId: string) => http.get('/export/entities', { params: { project_id: projectId } satisfies QueryOf<'/api/export/entities', 'get'> }),
  report: (reportId: string) => http.get(`/export/report/${reportId}`),
  stix: (projectId: string) => http.get('/export/stix', { params: { project_id: projectId } satisfies QueryOf<'/api/export/stix', 'get'> }),
};

export const adminApi = {
  config: () => http.get('/admin/config'),
  getProxy: () => http.get('/admin/proxy'),
  updateProxy: (data: BodyOf<'/api/admin/proxy', 'put'> & { mode: 'direct' | 'vpn' | 'tor' }) =>
    http.put('/admin/proxy', data),
  // Collection egress VPN (gluetun sidecar, docker compose --profile vpn)
  getVpnStatus: () => http.get('/admin/vpn/status'),
  setVpnStatus: (action: 'start' | 'stop') => http.put('/admin/vpn/status', { action } satisfies BodyOf<'/api/admin/vpn/status', 'put'>),
  listModels: () => http.get('/admin/llm/models'),
  selectModel: (provider: string, model: string) =>
    http.put('/admin/llm/select', { provider, model } satisfies BodyOf<'/api/admin/llm/select', 'put'>),
  // API Key management
  listApiKeys: () => http.get('/admin/api-keys'),
  addApiKey: (provider: string, label: string, apiKey: string) =>
    http.post('/admin/api-keys', { provider, label, api_key: apiKey } satisfies BodyOf<'/api/admin/api-keys', 'post'>),
  activateApiKey: (keyId: string, provider: string) =>
    http.put('/admin/api-keys/activate', { key_id: keyId, provider } satisfies BodyOf<'/api/admin/api-keys/activate', 'put'>),
  deleteApiKey: (keyId: string) =>
    http.delete(`/admin/api-keys/${keyId}`),
  // Cyber enrichment: auto-enrich toggle + provider inventory
  getEnrichmentConfig: () => http.get('/admin/enrichment'),
  setEnrichmentConfig: (autoEnabled: boolean) =>
    http.put('/admin/enrichment', { auto_enabled: autoEnabled } satisfies BodyOf<'/api/admin/enrichment', 'put'>),
  listEnrichmentProviders: () => http.get('/enrichment/providers'),
};

export interface WatchedEntity {
  id: string;
  name: string;
  entity_type: string;
  relationship_count?: number;
}

export interface WatchlistResponse {
  watched_entities: WatchedEntity[];
  count: number;
}

/**
 * The watched entities in a `GET /watchlist` body (`{watched_entities, count}`).
 *
 * Throws on any other shape: consumers used to guess (`entities`, `watchlist`,
 * a bare array, `.items`), found nothing, and showed an always-empty watchlist
 * and a badge stuck at 0. A wrong shape is an error to show, not an empty list.
 */
export function readWatchlist(data: unknown): WatchedEntity[] {
  const rows =
    data && typeof data === 'object' && !Array.isArray(data)
      ? (data as { watched_entities?: unknown }).watched_entities
      : undefined;
  if (!Array.isArray(rows)) throw new Error('Unexpected watchlist response shape.');
  return rows.filter(
    (r): r is WatchedEntity => !!r && typeof r === 'object' && typeof (r as WatchedEntity).id === 'string',
  );
}

export const watchlistApi = {
  add: (projectId: string, entityId: string) =>
    http.post('/watchlist/add', { project_id: projectId, entity_id: entityId } satisfies BodyOf<'/api/watchlist/add', 'post'>),
  remove: (projectId: string, entityId: string) =>
    http.post('/watchlist/remove', { project_id: projectId, entity_id: entityId } satisfies BodyOf<'/api/watchlist/remove', 'post'>),
  /** The body is a `WatchlistResponse`; read it with `readWatchlist`. Left
   *  untyped so existing callers that index it loosely still compile. */
  list: (projectId: string) => http.get('/watchlist', { params: { project_id: projectId } satisfies QueryOf<'/api/watchlist', 'get'> }),
};

export const entityMgmtApi = {
  merge: (primaryId: string, mergeIds: string[], projectId: string) =>
    http.post('/entities/merge', {
      primary_id: primaryId, merge_ids: mergeIds, project_id: projectId,
    } satisfies BodyOf<'/api/entities/merge', 'post'>),
  updateType: (entityId: string, entityType: string) =>
    http.put(`/entities/${entityId}/type`, { entity_type: entityType } satisfies BodyOf<'/api/entities/{entity_id}/type', 'put'>),
};

export const personasApi = {
  list: () => http.get('/personas'),
  create: (data: BodyOf<'/api/personas', 'post'>) =>
    http.post('/personas', data),
  activate: (id: string) => http.post(`/personas/${id}/activate`),
  delete: (id: string) => http.delete(`/personas/${id}`),
  active: () => http.get('/personas/active'),
};

export const snapshotsApi = {
  create: (data: BodyOf<'/api/snapshots', 'post'>) =>
    http.post('/snapshots', data),
  list: (projectId: string) => http.get('/snapshots', { params: { project_id: projectId } satisfies QueryOf<'/api/snapshots', 'get'> }),
  get: (id: string) => http.get(`/snapshots/${id}`),
  delete: (id: string) => http.delete(`/snapshots/${id}`),
};

export const documentsApi = {
  list: (projectId: string) => http.get('/documents', { params: { project_id: projectId } satisfies QueryOf<'/api/documents', 'get'> }),
  get: (docId: string) => http.get(`/documents/${docId}`),
  evidence: (docId: string, entityName: string) =>
    http.get(`/documents/${docId}/evidence`, { params: { entity_name: entityName } satisfies QueryOf<'/api/documents/{doc_id}/evidence', 'get'> }),
};

export const healthApi = {
  check: () => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
    // SECURITY: only use token if available, don't fall back to hardcoded keys
    const headers: Record<string, string> = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    // Polled every 30 s by the sidebar and status bar. Without its own timeout
    // a hung backend left the check pending (and the dot green) for minutes.
    return axios.get<ResponseOf<'/health', 'get'>>(`${API_BASE}/health`, { headers, timeout: 5000 });
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

/** Keys that identify an entity rather than describe it. */
const IDENTITY_KEYS = new Set(['id', 'name', 'entity_type', 'project_id', 'properties']);

/**
 * The entity's descriptive fields as `[key, value]` pairs for a properties
 * panel, from either the flattened or the nested shape (see `entityFields`),
 * without identity keys or empty values. Listing `entity.properties` directly
 * showed nothing for flattened entities.
 */
export function entityPropertyEntries(entity: unknown): Array<[string, unknown]> {
  return Object.entries(entityFields(entity)).filter(
    ([k, v]) => !IDENTITY_KEYS.has(k) && v !== null && v !== undefined && v !== '',
  );
}

export default api;
