import axios, { type AxiosRequestConfig } from 'axios';
import { createSummaryStreamParser, type SummaryStreamEvent } from './sse';
import type { AttackMapResult } from './attackMapping';
import type { BodyOf, ClientPath, Model, QueryOf, ResponseOf } from './apiTypes';

// Use relative URL so it works on both localhost and Railway (same-origin)
const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

/**
 * Sent on every request. The session is an httpOnly cookie the browser
 * attaches by itself, so a cross-site form could otherwise post as the
 * analyst; the backend refuses a cookie-authenticated state-changing request
 * that lacks this header, and a cross-site page cannot add a custom header
 * without a CORS preflight the backend does not grant.
 */
export const CSRF_HEADER = { 'X-Requested-With': 'sentinel' } as const;

/**
 * No token is read or stored here: `POST /api/auth/login` sets the
 * `sentinel_session` cookie (httpOnly, so script cannot read it) and
 * `withCredentials` makes the browser send it even when the API is on another
 * origin (`NEXT_PUBLIC_API_URL`).
 */
const api = axios.create({
  baseURL: `${API_BASE}/api`,
  timeout: 300000,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
    ...CSRF_HEADER,
  },
});

/** Where the bearer token lived before the session moved to a cookie. A
 *  browser that signed in under the old client may still hold a live one, so
 *  it is cleared with the session and on every load (`forgetLegacyToken`). */
const LEGACY_TOKEN_KEY = 'auth_token';
/** The signed-in identity as `/api/auth/me` last reported it: display and UI
 *  gating only, never a credential. */
const USER_KEY = 'auth_user';
const ROLE_KEY = 'auth_role';

/** Keys that belong to one analyst's session. */
const SESSION_KEYS = [LEGACY_TOKEN_KEY, USER_KEY, ROLE_KEY, 'activeProject'];
/** Per-project assistant threads (see `AssistantContext`): RAG answers and
 *  verbatim source-document excerpts. */
const ASSISTANT_THREAD_PREFIX = 'assistant_thread:';

/**
 * Forget everything the current analyst's session left in this browser: the
 * cached identity (and any legacy token), the selected project, and every
 * assistant thread. Called on sign-out, on a 401, and before recording a new
 * login, because workstations are shared and none of it may carry over to the
 * next analyst. Per-browser display preferences (layout choices) are kept.
 * The session cookie itself is httpOnly: only `authApi.logout` (the backend)
 * can clear it.
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

/** Who is signed in, as `GET /api/auth/me` (and the login body) report it. */
export type SessionUser = Model<'SessionUser'>;

/** Record the identity `/api/auth/me` returned, for display and UI gating. */
export function rememberSessionUser(user: SessionUser): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(USER_KEY, user.username);
    localStorage.setItem(ROLE_KEY, user.role);
  } catch {
    /* storage unavailable: the identity is simply not cached */
  }
}

/** The identity `/api/auth/me` last reported in this browser, or null. */
export function cachedSessionUser(): SessionUser | null {
  if (typeof window === 'undefined') return null;
  try {
    const username = localStorage.getItem(USER_KEY);
    return username ? { username, role: localStorage.getItem(ROLE_KEY) || 'analyst' } : null;
  } catch {
    return null;
  }
}

/** Drop a bearer token an older client left in storage. */
export function forgetLegacyToken(): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(LEGACY_TOKEN_KEY);
  } catch {
    /* storage unavailable: nothing to remove */
  }
}

/** Whether the signed-in user is an admin, per the role `/api/auth/me` last
 *  reported. UI gating only: the backend enforces admin on every admin route,
 *  this just keeps analysts from being offered buttons that can only 403. */
export function isAdminSession(): boolean {
  return cachedSessionUser()?.role === 'admin';
}

/** True for an axios error the backend answered with `status`. */
export function isHttpStatus(error: unknown, status: number): boolean {
  return axios.isAxiosError(error) && error.response?.status === status;
}

/**
 * The axios instance with each URL checked against the generated route list
 * (`ClientPath`): calling a route the backend does not serve for that method
 * is a compile error. Same instance, same interceptors, same runtime.
 *
 * Every route declares its response, so every call below names it with
 * `ResponseOf`; a call that names none gets `unknown`, never `any`.
 */
const http = {
  get: <T>(url: ClientPath<'get'>, config?: AxiosRequestConfig) => api.get<T>(url, config),
  post: <T>(url: ClientPath<'post'>, data?: unknown, config?: AxiosRequestConfig) => api.post<T>(url, data, config),
  put: <T>(url: ClientPath<'put'>, data?: unknown, config?: AxiosRequestConfig) => api.put<T>(url, data, config),
  delete: <T>(url: ClientPath<'delete'>, config?: AxiosRequestConfig) => api.delete<T>(url, config),
};

export const authApi = {
  /** Sets the `sentinel_session` cookie. Confirm it took with `me()`. */
  login: (credentials: BodyOf<'/api/auth/login', 'post'>) =>
    http.post<ResponseOf<'/api/auth/login', 'post'>>('/auth/login', credentials),
  /** Who the session cookie belongs to; 401 when there is no session. */
  me: () => http.get<ResponseOf<'/api/auth/me', 'get'>>('/auth/me'),
  /** Clears the session cookie server-side; the only way to, since script
   *  cannot touch an httpOnly cookie. */
  logout: () => http.post<ResponseOf<'/api/auth/logout', 'post'>>('/auth/logout'),
};

export type Project = Model<'ProjectResponse'>;

export const projectsApi = {
  list: () => http.get<ResponseOf<'/api/projects', 'get'>>('/projects'),
  create: (data: BodyOf<'/api/projects', 'post'>) =>
    http.post<ResponseOf<'/api/projects', 'post'>>('/projects', data),
  get: (id: string) => http.get<ResponseOf<'/api/projects/{project_id}', 'get'>>(`/projects/${id}`),
  delete: (id: string) => http.delete<ResponseOf<'/api/projects/{project_id}', 'delete'>>(`/projects/${id}`),
  batchDelete: (projectIds: string[]) => http.post<ResponseOf<'/api/projects/batch-delete', 'post'>>('/projects/batch-delete', { project_ids: projectIds } satisfies BodyOf<'/api/projects/batch-delete', 'post'>),
  activity: (id: string, limit?: number) => http.get<ResponseOf<'/api/projects/{project_id}/activity', 'get'>>(`/projects/${id}/activity`, { params: { limit } satisfies QueryOf<'/api/projects/{project_id}/activity', 'get'> }),
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

/** An entity row as the entity routes return it: the identity fields every
 *  entity carries, plus the node's own stored properties flattened beside them
 *  (typed `unknown`; read them with `entityFields`). A node written without a
 *  name or type has neither, so both may be missing. */
export type EntityRecord = Model<'EntityProperties'>;

/** One edge touching an entity (`GET /entities/{id}`), its stored properties
 *  spread flat; `direction` and `neighbor_*` are relative to that entity. */
export type EntityRelationship = Model<'RelationshipItem'>;

export const entitiesApi = {
  /** Entities matching the filters. `limit` defaults to 50 on the server, so a
   *  view that means to show everything must say so. Read the true total from
   *  the `X-Total-Count` response header (see `totalFrom`) rather than assuming
   *  the array is complete. */
  search: (projectId: string, query?: string, entityType?: string, limit?: number) =>
    http.get<ResponseOf<'/api/entities', 'get'>>('/entities', { params: { project_id: projectId, query, entity_type: entityType, limit } satisfies QueryOf<'/api/entities', 'get'> }),
  get: (id: string) => http.get<ResponseOf<'/api/entities/{entity_id}', 'get'>>(`/entities/${id}`),
  subgraph: (id: string, hops?: number) =>
    http.get<ResponseOf<'/api/subgraph/{entity_id}', 'get'>>(`/subgraph/${id}`, { params: { hops } satisfies QueryOf<'/api/subgraph/{entity_id}', 'get'> }),
  shortestPath: (id1: string, id2: string) =>
    http.get<ResponseOf<'/api/paths/{entity_id_1}/{entity_id_2}', 'get'>>(`/paths/${id1}/${id2}`),
  /** The documents that mention the entity (its MENTIONS edges), each with
   *  up to three passages, one page at a time. Read the body with
   *  `readEntityDocuments`. */
  documents: (id: string, limit?: number, offset?: number) =>
    http.get<EntityDocumentsPage>(`/entities/${id}/documents`, {
      params: { limit, offset } satisfies QueryOf<'/api/entities/{entity_id}/documents', 'get'>,
    }),
};

/** One document that mentions an entity (contract 6): its MENTIONS count and
 *  up to three passages, each with its character offset. */
export type EntityDocument = Model<'MentioningDocument'>;

/** A page of `GET /entities/{id}/documents`: `count` in this page, `total`
 *  that mention the entity in all. */
export type EntityDocumentsPage = ResponseOf<'/api/entities/{entity_id}/documents', 'get'>;

/**
 * The page in a `GET /entities/{id}/documents` body. Throws on any other
 * shape: an evidence chain that silently reads as "no source documents" when
 * the response was something else is worse than an error.
 */
export function readEntityDocuments(data: unknown): EntityDocumentsPage {
  const body = data && typeof data === 'object' && !Array.isArray(data) ? (data as Record<string, unknown>) : null;
  if (!body || !Array.isArray(body.documents)) throw new Error('Unexpected entity documents response shape.');
  const documents = body.documents
    .filter((d): d is Record<string, unknown> => !!d && typeof d === 'object' && typeof (d as { id?: unknown }).id === 'string')
    .map((d) => ({
      id: d.id as string,
      name: typeof d.name === 'string' && d.name ? d.name : (d.id as string),
      url: typeof d.url === 'string' ? d.url : '',
      source_doc_id: typeof d.source_doc_id === 'string' ? d.source_doc_id : '',
      mention_count: typeof d.mention_count === 'number' ? d.mention_count : 0,
      passages: Array.isArray(d.passages)
        ? d.passages
            .filter((p): p is { text: string; offset?: unknown } => !!p && typeof (p as { text?: unknown }).text === 'string')
            .map((p) => ({ text: p.text, offset: typeof p.offset === 'number' ? p.offset : 0 }))
        : [],
    }));
  const total = typeof body.total === 'number' ? body.total : documents.length;
  return { documents, count: documents.length, total: Math.max(total, documents.length) };
}

// Local context (Overpass) + AOI spatial query around/within a geotarget.
export const geoApiExtra = {
  nearby: (entityId: string, radius?: number) =>
    http.get<ResponseOf<'/api/geo/nearby/{entity_id}', 'get'>>(`/geo/nearby/${encodeURIComponent(entityId)}`, { params: { radius } satisfies QueryOf<'/api/geo/nearby/{entity_id}', 'get'> }),
  within: (projectId: string, bbox: { minLat: number; minLng: number; maxLat: number; maxLng: number }) =>
    http.get<ResponseOf<'/api/geo/within', 'get'>>('/geo/within', {
      params: {
        project_id: projectId,
        min_lat: bbox.minLat, min_lng: bbox.minLng, max_lat: bbox.maxLat, max_lng: bbox.maxLng,
      } satisfies QueryOf<'/api/geo/within', 'get'>,
    }),
};

// Cyber-observable enrichment (WHOIS/DNS/GeoIP/certs/KEV/CVSS) — the Investigate
// action. Egress routes through the collection proxy (VPN/Tor), never the LLM path.
export const enrichmentApi = {
  investigate: (entityId: string) =>
    http.post<ResponseOf<'/api/enrichment/entities/{entity_id}', 'post'>>(`/enrichment/entities/${entityId}`),
  getCached: (entityId: string) =>
    http.get<ResponseOf<'/api/enrichment/entities/{entity_id}', 'get'>>(`/enrichment/entities/${entityId}`),
  refresh: (entityId: string, provider: string) =>
    http.post<ResponseOf<'/api/enrichment/entities/{entity_id}/refresh', 'post'>>(`/enrichment/entities/${entityId}/refresh`, null, { params: { provider } satisfies QueryOf<'/api/enrichment/entities/{entity_id}/refresh', 'post'> }),
  providers: () => http.get<ResponseOf<'/api/enrichment/providers', 'get'>>('/enrichment/providers'),
};

// MITRE ATT&CK® integration — data-driven matrix, technique detail, coverage
// resolution against a project's TTP entities, and Navigator layer export.
export type AttackCounts = Model<'AttackCountsItem'>;

/** Includes the CWE→CAPEC→ATT&CK weakness-chain ingest state (`vuln_chain`). */
export type AttackStatus = ResponseOf<'/api/attack/status', 'get'>;

// How a project entity was mapped onto an ATT&CK technique: an explicit T-code
// in the TTP name ("tcode", confidence 1.0) or an AI RAG+LLM mapping ("llm",
// with a model-supplied confidence). The backend sends these as plain strings
// (`methods` on matrix cells, `method` on a technique's related entities).
export type AttackMapMethod = 'tcode' | 'llm';

export type AttackSubtechnique = Model<'AttackSubtechniqueItem'>;
/** `methods` is this technique's own plus its sub-techniques' (the same rollup
 *  as `observed_count`); show the "AI" marker when it includes "llm". */
export type AttackTechniqueCell = Model<'AttackTechniqueCellItem'>;
export type AttackTactic = Model<'AttackTacticItem'>;
export type AttackMatrixData = ResponseOf<'/api/attack/matrix', 'get'>;
/** `enabling_cves` are the project's CVEs whose weakness chain could enable the
 *  technique: potential enablement, distinct from observed TTPs. */
export type AttackTechniqueDetail = ResponseOf<'/api/attack/technique/{tid}', 'get'>;

// Threat-actor attribution by technique overlap: ranked ATT&CK Groups that
// share observed techniques with the project — suggestive overlap only, not
// confirmed attribution.
export type AttackAttributionGroup = Model<'AttributionGroupItem'>;
export type AttackAttribution = ResponseOf<'/api/attack/attribution', 'get'>;

// MITRE D3FEND defensive countermeasures for a technique, from a live lookup.
// `degraded` means the lookup failed, so an empty list is "unknown", not "none".
export type AttackD3fendCountermeasure = Model<'D3fendCountermeasureItem'>;
export type AttackD3fendResponse = ResponseOf<'/api/attack/technique/{tid}/d3fend', 'get'>;

// The aggregated ATT&CK report for a project: observed techniques by tactic,
// candidate attribution, key mitigations, CVE-enabled techniques, an optional
// model narrative (null when no model was reachable) and rendered markdown.
export type AttackReportObservedTactic = Model<'ObservedTacticItem'>;
export type AttackReportAttributionEntry = Model<'AttributionSummaryItem'>;
export type AttackReportMitigation = Model<'KeyMitigationItem'>;
export type AttackReportCveEnabled = Model<'CveEnabledTechniqueItem'>;
export type AttackReport = ResponseOf<'/api/attack/report', 'get'>;

export const attackApi = {
  status: () => http.get<AttackStatus>('/attack/status'),
  // Admin action — downloads ~53MB of ATT&CK STIX server-side; can take 30-60s.
  ingest: () => http.post<ResponseOf<'/api/attack/ingest', 'post'>>('/attack/ingest'),
  // Re-map the project's TTP entities onto ATT&CK techniques.
  resolve: (projectId: string) =>
    http.post<ResponseOf<'/api/attack/resolve', 'post'>>('/attack/resolve', null, { params: { project_id: projectId } satisfies QueryOf<'/api/attack/resolve', 'post'> }),
  // (Admin) Embed all ATT&CK techniques into pgvector for RAG mapping. One-time,
  // idempotent, and slow (~30-90s for 697 techniques).
  // `embedded: 0` comes with a machine `reason` and a human `detail` saying why
  // (no techniques ingested, no provider, rate-limited) — never read a bare 0
  // as success.
  embed: () => http.post<ResponseOf<'/api/attack/embed', 'post'>>('/attack/embed'),
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
  // Downloadable Navigator layer JSON. Fetched via axios and turned into a blob
  // download, matching the other exports in the app (a plain <a> would carry
  // the session cookie too, but not an API base on another origin).
  navigatorLayer: (projectId: string) =>
    http.get<ResponseOf<'/api/attack/navigator-layer', 'get'>>('/attack/navigator-layer', { params: { project_id: projectId } satisfies QueryOf<'/api/attack/navigator-layer', 'get'> }),
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
  full: (projectId: string) => http.get<ResponseOf<'/api/graph', 'get'>>('/graph', { params: { project_id: projectId } satisfies QueryOf<'/api/graph', 'get'> }),
  communities: (projectId: string) => http.get<ResponseOf<'/api/communities', 'get'>>('/communities', { params: { project_id: projectId } satisfies QueryOf<'/api/communities', 'get'> }),
  centrality: (projectId: string) => http.get<ResponseOf<'/api/graph/centrality', 'get'>>('/graph/centrality', { params: { project_id: projectId } satisfies QueryOf<'/api/graph/centrality', 'get'> }),
  statistics: (projectId: string) => http.get<ResponseOf<'/api/graph/statistics', 'get'>>('/graph/statistics', { params: { project_id: projectId } satisfies QueryOf<'/api/graph/statistics', 'get'> }),
  structuralHoles: (projectId: string, topN?: number) =>
    http.get<ResponseOf<'/api/graph/structural-holes', 'get'>>('/graph/structural-holes', { params: { project_id: projectId, top_n: topN } satisfies QueryOf<'/api/graph/structural-holes', 'get'> }),
  egoNetwork: (entityId: string, projectId: string, hops?: number) =>
    http.get<ResponseOf<'/api/graph/ego-network/{entity_id}', 'get'>>(`/graph/ego-network/${entityId}`, { params: { project_id: projectId, hops } satisfies QueryOf<'/api/graph/ego-network/{entity_id}', 'get'> }),
  influence: (projectId: string, seedIds: string[], steps?: number, threshold?: number) =>
    http.post<ResponseOf<'/api/graph/influence', 'post'>>('/graph/influence', {
      project_id: projectId, seed_ids: seedIds, steps, threshold,
    } satisfies BodyOf<'/api/graph/influence', 'post'>),
};

export const queryApi = {
  rag: (projectId: string, query: string) =>
    http.post<ResponseOf<'/api/query', 'post'>>('/query', { project_id: projectId, query } satisfies BodyOf<'/api/query', 'post'>),
};

export const llmApi = {
  skills: () => http.get<ResponseOf<'/api/llm/skills', 'get'>>('/llm/skills'),
  query: (
    messages: Array<{role: string; content: string}>,
    skillName?: string,
    overrides?: { system_prompt?: string; temperature?: number; max_tokens?: number },
  ) =>
    http.post<ResponseOf<'/api/llm/query', 'post'>>('/llm/query', {
      messages, skill_name: skillName, ...(overrides || {}),
    } satisfies BodyOf<'/api/llm/query', 'post'>),
};

export const ingestApi = {
  text: (projectId: string, content: string, reliabilityRating?: string) => {
    const formData = new FormData();
    formData.append('project_id', projectId);
    formData.append('content', content);
    if (reliabilityRating) formData.append('reliability_rating', reliabilityRating);
    return http.post<ResponseOf<'/api/ingest', 'post'>>('/ingest', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
  },
  file: (projectId: string, file: File, reliabilityRating?: string, extractionMode?: string) => {
    const formData = new FormData();
    formData.append('project_id', projectId);
    formData.append('file', file);
    if (reliabilityRating) formData.append('reliability_rating', reliabilityRating);
    if (extractionMode) formData.append('extraction_mode', extractionMode);
    return http.post<ResponseOf<'/api/ingest', 'post'>>('/ingest', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
  },
  batch: (projectId: string, files: File[], reliabilityRating?: string, extractionMode?: string) => {
    const formData = new FormData();
    formData.append('project_id', projectId);
    files.forEach(f => formData.append('files', f));
    if (reliabilityRating) formData.append('reliability_rating', reliabilityRating);
    if (extractionMode) formData.append('extraction_mode', extractionMode);
    return http.post<ResponseOf<'/api/ingest/batch', 'post'>>('/ingest/batch', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
  },
};

/** A legacy collection (`/collections`): the stored node, its plan decoded. */
export type LegacyCollection = Model<'LegacyCollectionResponse'>;

export const collectionsApi = {
  create: (data: BodyOf<'/api/collections', 'post'>) =>
    http.post<ResponseOf<'/api/collections', 'post'>>('/collections', data),
  list: (projectId?: string) =>
    http.get<ResponseOf<'/api/collections', 'get'>>('/collections', { params: projectId ? { project_id: projectId } : {} }),
  get: (id: string) => http.get<ResponseOf<'/api/collections/{task_id}', 'get'>>(`/collections/${id}`),
  update: (id: string, data: BodyOf<'/api/collections/{task_id}', 'put'>) =>
    http.put<ResponseOf<'/api/collections/{task_id}', 'put'>>(`/collections/${id}`, data),
  status: (id: string) => http.get<ResponseOf<'/api/collections/{task_id}/status', 'get'>>(`/collections/${id}/status`),
  cancel: (id: string) => http.post<ResponseOf<'/api/collections/{task_id}/cancel', 'post'>>(`/collections/${id}/cancel`),
  parsePlan: (planText: string) =>
    http.post<ResponseOf<'/api/collections/parse-plan', 'post'>>('/collections/parse-plan', { plan_text: planText } satisfies BodyOf<'/api/collections/parse-plan', 'post'>),
  count: (projectId: string) =>
    http.get<ResponseOf<'/api/collections/count/{project_id}', 'get'>>(`/collections/count/${projectId}`),
};

// PIRs — Priority Intelligence Requirements, the requirements spine a project's
// collection hangs off. Every plan raised against one carries its pir_id back.
export type PirStatus = 'OPEN' | 'PARTIAL' | 'SATISFIED' | 'ARCHIVED';

export type PirPlanLink = Model<'PirPlanLink'>;

/** `PirResponse` with `status` narrowed: the schema says `str`, the route
 *  only ever stores one of `PirStatus`. */
export type Pir = Omit<Model<'PirResponse'>, 'status'> & { status: PirStatus };

export type RequirementStatus = 'pending' | 'satisfied' | 'unmet';

/** One element's collection state, `status` narrowed as `Pir`'s is: the route
 *  only ever stores a `RequirementStatus`. `missing` is what the assessor said
 *  is still absent — the analyst-facing gap. */
export type PirRequirementElement = Omit<Model<'RequirementElementItem'>, 'status'> & { status: RequirementStatus };

/** Every `RequirementStatus` is always counted, zero or not. */
export type PirRequirements = Omit<ResponseOf<'/api/pirs/{pir_id}/requirements', 'get'>, 'counts' | 'elements'> & {
  counts: Record<RequirementStatus, number>;
  elements: PirRequirementElement[];
};

export const pirsApi = {
  list: (projectId: string, status?: PirStatus) =>
    http.get<Pir[]>('/pirs', { params: { project_id: projectId, status } satisfies QueryOf<'/api/pirs', 'get'> }),
  get: (id: string) => http.get<Pir>(`/pirs/${id}`),
  create: (data: Omit<BodyOf<'/api/pirs', 'post'>, 'status'> & { status?: PirStatus }) =>
    http.post<Pir>('/pirs', data),
  update: (id: string, data: Omit<BodyOf<'/api/pirs/{pir_id}', 'put'>, 'status'> & { status?: PirStatus }) =>
    http.put<Pir>(`/pirs/${id}`, data),
  delete: (id: string) => http.delete<ResponseOf<'/api/pirs/{pir_id}', 'delete'>>(`/pirs/${id}`),
  // Per-element collection state. "unmet" means tried and given up on; it is
  // deliberately distinct from "pending", which is still open.
  requirements: (id: string) =>
    http.get<PirRequirements>(`/pirs/${id}/requirements`),
};

// Collection Plans — new managed pipeline
export type CollectionPlan = Model<'CollectionPlanResponse'>;

/** `POST /collection-plans/from-pir`: the plan, plus `generation_failures` (why
 *  generation produced less than it should have) and `eeis_captured` (zero
 *  means satisfaction cannot be measured and collection cannot re-task). */
export type PlanFromPirResult = ResponseOf<'/api/collection-plans/from-pir', 'post'>;

/** Whether a collection run is actually in flight, from the job table and the
 *  activity trail — distinct from `CollectionPlan.status`, which is a lifecycle
 *  flag an analyst sets by hand. `status` is idle | running | stalled |
 *  completed | failed | cancelled; a queued run, and a cancelled run still
 *  winding down, read `running`, and `job_status` (a `CollectionJobStatus`)
 *  tells them apart. `degraded` is this run's `{subsystem: {reason: count}}`,
 *  the only place they show when a worker process ran it. */
export type PlanExecutionStatus = ResponseOf<'/api/collection-plans/{plan_id}/execution-status', 'get'>;

export type CollectionJobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';

/** `POST /collection-plans/{id}/execute` (202): the plan plus how the run
 *  started. `job_id` is null when nothing could run; `worker_mode` is inline |
 *  worker and `execution_status` started | queued | no_executable_sources. */
export type PlanExecuteResult = ResponseOf<'/api/collection-plans/{plan_id}/execute', 'post'>;

/** `POST /collection-plans/{id}/cancel` (202). `stopping`: the run was
 *  mid-flight and stops before its next source; the plan reads `running`
 *  until it has. */
export type PlanCancelResult = ResponseOf<'/api/collection-plans/{plan_id}/cancel', 'post'>;

export type CollectionSourceEntry = Model<'CollectionSourceResponse'>;
export type CollectionActivityEntry = Model<'CollectionActivityItem'>;
export type AcquisitionLogEntry = Model<'AcquisitionLogItem'>;
export type DataCatalogEntry = Model<'DataCatalogItem'>;

export const collectionPlansApi = {
  // Plans
  create: (data: BodyOf<'/api/collection-plans', 'post'>) =>
    http.post<CollectionPlan>('/collection-plans', data),
  list: (projectId?: string, status?: string) =>
    http.get<CollectionPlan[]>('/collection-plans', { params: { project_id: projectId, status } satisfies QueryOf<'/api/collection-plans', 'get'> }),
  get: (id: string) => http.get<CollectionPlan>(`/collection-plans/${id}`),
  update: (id: string, data: BodyOf<'/api/collection-plans/{plan_id}', 'put'>) =>
    http.put<CollectionPlan>(`/collection-plans/${id}`, data),
  delete: (id: string) => http.delete<ResponseOf<'/api/collection-plans/{plan_id}', 'delete'>>(`/collection-plans/${id}`),

  // Status transitions
  activate: (id: string) => http.post<CollectionPlan>(`/collection-plans/${id}/activate`),
  pause: (id: string) => http.post<CollectionPlan>(`/collection-plans/${id}/pause`),
  complete: (id: string) => http.post<CollectionPlan>(`/collection-plans/${id}/complete`),
  archive: (id: string) => http.post<CollectionPlan>(`/collection-plans/${id}/archive`),

  // Execution
  /** Cancel the plan's live run (queued, running or stalled). 409 when none is
   *  live or it is already stopping. */
  cancel: (planId: string) => http.post<PlanCancelResult>(`/collection-plans/${planId}/cancel`),
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
    http.delete<ResponseOf<'/api/collection-plans/{plan_id}/sources/{source_id}', 'delete'>>(`/collection-plans/${planId}/sources/${sourceId}`),

  // File upload through pipeline
  uploadFile: (planId: string, sourceId: string, file: File, extractionMode?: string, reliabilityRating?: string) => {
    const formData = new FormData();
    formData.append('file', file);
    if (extractionMode) formData.append('extraction_mode', extractionMode);
    if (reliabilityRating) formData.append('reliability_rating', reliabilityRating);
    return http.post<ResponseOf<'/api/collection-plans/{plan_id}/sources/{source_id}/upload', 'post'>>(`/collection-plans/${planId}/sources/${sourceId}/upload`, formData, {
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
    http.get<ResponseOf<'/api/data-catalog/{catalog_id}/preview', 'get'>>(`/data-catalog/${catalogId}/preview`, { params: { offset, limit } satisfies QueryOf<'/api/data-catalog/{catalog_id}/preview', 'get'> }),

  // Activity log
  activity: (planId: string, since?: string) =>
    http.get<CollectionActivityEntry[]>(`/collection-plans/${planId}/activity`, { params: { since } satisfies QueryOf<'/api/collection-plans/{plan_id}/activity', 'get'> }),

  // PIR-driven plan creation (unified flow). Pass pir_id to run against an
  // existing requirement; omit it and the backend persists/reuses one from `pir`.
  fromPir: (data: BodyOf<'/api/collection-plans/from-pir', 'post'>) =>
    http.post<PlanFromPirResult>('/collection-plans/from-pir', data),
  execute: (planId: string, maxResultsPerSource?: number) =>
    http.post<PlanExecuteResult>(
      `/collection-plans/${planId}/execute`,
      maxResultsPerSource != null
        ? ({ max_results_per_source: maxResultsPerSource } satisfies BodyOf<'/api/collection-plans/{plan_id}/execute', 'post'>)
        : undefined,
    ),

  // Dashboard
  dashboard: (projectId: string) => http.get<ResponseOf<'/api/collection-dashboard', 'get'>>('/collection-dashboard', { params: { project_id: projectId } satisfies QueryOf<'/api/collection-dashboard', 'get'> }),

  // Connector types
  connectorTypes: () => http.get<ResponseOf<'/api/connector-types', 'get'>>('/connector-types'),
};

export const assessApi = {
  assess: (entityId: string, projectId: string, judgment: string, probability: number) =>
    http.post<ResponseOf<'/api/entities/{entity_id}/assess', 'post'>>(`/entities/${entityId}/assess`, {
      entity_id: entityId, project_id: projectId, judgment, probability,
    } satisfies BodyOf<'/api/entities/{entity_id}/assess', 'post'>),
  create: (entityId: string, data: BodyOf<'/api/entities/{entity_id}/assess', 'post'>) =>
    http.post<ResponseOf<'/api/entities/{entity_id}/assess', 'post'>>(`/entities/${entityId}/assess`, data),
  multi: (data: BodyOf<'/api/assess/multi', 'post'>) =>
    http.post<ResponseOf<'/api/assess/multi', 'post'>>('/assess/multi', data),
  generate: (entityId: string, data: BodyOf<'/api/assess/generate', 'post'>) =>
    http.post<ResponseOf<'/api/assess/generate', 'post'>>('/assess/generate', { ...data, entity_id: entityId } satisfies BodyOf<'/api/assess/generate', 'post'>),
};

// ── Structured analytic techniques (/api/analysis/*) ──────────────────────
// Grounded runners for the three tradecraft skills. Each retrieves real project
// evidence (graph subgraph, source documents, measured coverage) before
// prompting, and returns a deterministic result when no LLM is configured —
// so the UI must always render `analysis` and check `model !== 'none'`.

export type SourceEvaluationItem = Model<'SourceEvaluationItem'>;
export type SourceEvaluationResult = ResponseOf<'/api/analysis/source-evaluation', 'post'>;
export type Hypothesis = Model<'HypothesisItem'>;
/** `assessment_id` is set when the leading hypothesis was saved as an Assessment. */
export type HypothesesResult = ResponseOf<'/api/analysis/hypotheses', 'post'>;
export type StructuralGap = Model<'StructuralGapItem'>;
export type GapAnalysisResult = ResponseOf<'/api/analysis/gaps', 'post'>;

export const analysisApi = {
  sourceEvaluation: (data: BodyOf<'/api/analysis/source-evaluation', 'post'>) =>
    http.post<SourceEvaluationResult>('/analysis/source-evaluation', data),
  hypotheses: (data: BodyOf<'/api/analysis/hypotheses', 'post'>) =>
    http.post<HypothesesResult>('/analysis/hypotheses', data),
  gaps: (data: BodyOf<'/api/analysis/gaps', 'post'>) =>
    http.post<GapAnalysisResult>('/analysis/gaps', data),
};

/** A topic-tree node. A leaf has only `id`, `name` and `entity_type`; other
 *  kinds carry their own keys (`keywords`, `doc_ids`, `reliability` ...). */
export type TopicNode = Model<'TopicNodeItem'>;
/** `GET /topics/{id}` for a topic cluster or an entity. An unknown entity is a
 *  200 carrying only `{error}`, which `topicsApi.context` also types. */
export type TopicContext = Model<'TopicContextResponse'>;

export const topicsApi = {
  tree: (projectId: string, method?: string, granularity?: string) =>
    http.get<ResponseOf<'/api/topics', 'get'>>('/topics', { params: { project_id: projectId, method, granularity } satisfies QueryOf<'/api/topics', 'get'> }),
  context: (entityId: string, projectId: string) =>
    http.get<ResponseOf<'/api/topics/{entity_id}', 'get'>>(`/topics/${entityId}`, { params: { project_id: projectId } satisfies QueryOf<'/api/topics/{entity_id}', 'get'> }),
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
    // fetch, not axios, to read the stream as it arrives; so it must ask for
    // the session cookie and send the CSRF header itself (this is a POST).
    const response = await fetch(topicsApi.summarizeUrl(entityId), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...CSRF_HEADER },
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
    http.put<ResponseOf<'/api/topics/{node_id}', 'put'>>(`/topics/${nodeId}`, data),
  addChild: (nodeId: string, data: BodyOf<'/api/topics/{node_id}/children', 'post'>) =>
    http.post<ResponseOf<'/api/topics/{node_id}/children', 'post'>>(`/topics/${nodeId}/children`, data),
  deleteNode: (nodeId: string, projectId: string) =>
    http.delete<ResponseOf<'/api/topics/{node_id}', 'delete'>>(`/topics/${nodeId}`, { params: { project_id: projectId } satisfies QueryOf<'/api/topics/{node_id}', 'delete'> }),

  // Export
  exportMindmap: (projectId: string, format: string = 'json') =>
    http.get<ResponseOf<'/api/export/mindmap', 'get'>>('/export/mindmap', { params: { project_id: projectId, format } satisfies QueryOf<'/api/export/mindmap', 'get'> }),
};

/** A saved report: the Report node's stored properties (its title is `name`). */
export type SavedReportRecord = Model<'ReportResponse'>;

export const reportsApi = {
  save: (data: BodyOf<'/api/reports', 'post'>) =>
    http.post<ResponseOf<'/api/reports', 'post'>>('/reports', data),
  // Grounded generation: retrieves real graph + document evidence for the selected
  // entities via the Graph-RAG pipeline before drafting, instead of a bare LLM call.
  // `requirement` (PIR text) or `pir_id` makes the requirement the subject of the
  // product; without one it is only "tell me about these entities". Answers 503
  // "LLM provider unavailable" when no model could draft it.
  generate: (data: BodyOf<'/api/reports/generate', 'post'>) =>
    http.post<ResponseOf<'/api/reports/generate', 'post'>>('/reports/generate', data),
  list: (projectId: string) => http.get<ResponseOf<'/api/reports', 'get'>>('/reports', { params: { project_id: projectId } satisfies QueryOf<'/api/reports', 'get'> }),
  /** 404 unless `id` is a Report in `projectId`. */
  get: (id: string, projectId?: string) =>
    http.get<ResponseOf<'/api/reports/{report_id}', 'get'>>(`/reports/${id}`, { params: { project_id: projectId } satisfies QueryOf<'/api/reports/{report_id}', 'get'> }),
  delete: (id: string) => http.delete<ResponseOf<'/api/reports/{report_id}', 'delete'>>(`/reports/${id}`),
};

export const timelineApi = {
  get: (projectId: string) => http.get<ResponseOf<'/api/timeline', 'get'>>('/timeline', { params: { project_id: projectId } satisfies QueryOf<'/api/timeline', 'get'> }),
  /** Event-date distribution for the network view's brush filter. */
  histogram: (projectId: string, bucket: 'day' | 'month' | 'year' = 'month') =>
    http.get<ResponseOf<'/api/timeline/histogram', 'get'>>('/timeline/histogram', { params: { project_id: projectId, bucket } satisfies QueryOf<'/api/timeline/histogram', 'get'> }),
};

/** A notebook entry: a Report node with `report_type` "notebook_entry". */
export type Note = Model<'NoteResponse'>;

/** The note kinds the notebook route accepts (anything else is a 422). */
export type NoteType = NonNullable<BodyOf<'/api/notebook', 'post'>['note_type']>;

export const notebookApi = {
  create: (data: BodyOf<'/api/notebook', 'post'>) =>
    http.post<ResponseOf<'/api/notebook', 'post'>>('/notebook', data),
  list: (projectId: string) => http.get<ResponseOf<'/api/notebook', 'get'>>('/notebook', { params: { project_id: projectId } satisfies QueryOf<'/api/notebook', 'get'> }),
  get: (id: string) => http.get<ResponseOf<'/api/notebook/{note_id}', 'get'>>(`/notebook/${id}`),
  delete: (id: string) => http.delete<ResponseOf<'/api/notebook/{note_id}', 'delete'>>(`/notebook/${id}`),
};

/** Two places joined through the entities they share; `shared_entities` holds
 *  up to ten names, null for an entity without one. */
export type GeoEdge = Model<'GeoEdgeItem'>;

export const geoApi = {
  locations: (projectId: string) => http.get<ResponseOf<'/api/geo/locations', 'get'>>('/geo/locations', { params: { project_id: projectId } satisfies QueryOf<'/api/geo/locations', 'get'> }),
  entityTimeline: (entityId: string, projectId: string) =>
    http.get<ResponseOf<'/api/geo/entity-timeline', 'get'>>('/geo/entity-timeline', { params: { entity_id: entityId, project_id: projectId } satisfies QueryOf<'/api/geo/entity-timeline', 'get'> }),
};

export const searchApi = {
  search: (projectId: string, query: string) =>
    http.get<ResponseOf<'/api/search', 'get'>>('/search', { params: { project_id: projectId, q: query } satisfies QueryOf<'/api/search', 'get'> }),
  /**
   * Meaning-based retrieval over document chunks (pgvector). Returns passages
   * with a similarity score rather than name matches, so it finds material
   * that never uses the query's words.
   */
  semantic: (projectId: string, query: string) =>
    http.post<ResponseOf<'/api/search/semantic', 'post'>>('/search/semantic', { project_id: projectId, query } satisfies BodyOf<'/api/search/semantic', 'post'>),
};

export const exportApi = {
  graph: (projectId: string) => http.get<ResponseOf<'/api/export/graph', 'get'>>('/export/graph', { params: { project_id: projectId } satisfies QueryOf<'/api/export/graph', 'get'> }),
  entities: (projectId: string) => http.get<ResponseOf<'/api/export/entities', 'get'>>('/export/entities', { params: { project_id: projectId } satisfies QueryOf<'/api/export/entities', 'get'> }),
  report: (reportId: string) => http.get<ResponseOf<'/api/export/report/{report_id}', 'get'>>(`/export/report/${reportId}`),
  stix: (projectId: string) => http.get<ResponseOf<'/api/export/stix', 'get'>>('/export/stix', { params: { project_id: projectId } satisfies QueryOf<'/api/export/stix', 'get'> }),
};

export type AdminConfig = ResponseOf<'/api/admin/config', 'get'>;
/** The VPN sidecar's state; only `reachable` and `running` are known when it
 *  cannot be reached. */
export type VpnStatus = ResponseOf<'/api/admin/vpn/status', 'get'>;
export type LlmModel = Model<'LlmModelItem'>;
export type StoredApiKey = Model<'ApiKeyItem'>;

export const adminApi = {
  config: () => http.get<ResponseOf<'/api/admin/config', 'get'>>('/admin/config'),
  /** Degraded outcomes since the API process started, by subsystem and
   *  reason. Read the body with `readDegraded` (lib/degraded). */
  degraded: () => http.get<ResponseOf<'/api/admin/degraded', 'get'>>('/admin/degraded'),
  getProxy: () => http.get<ResponseOf<'/api/admin/proxy', 'get'>>('/admin/proxy'),
  updateProxy: (data: BodyOf<'/api/admin/proxy', 'put'> & { mode: 'direct' | 'vpn' | 'tor' }) =>
    http.put<ResponseOf<'/api/admin/proxy', 'put'>>('/admin/proxy', data),
  // Collection egress VPN (gluetun sidecar, docker compose --profile vpn)
  getVpnStatus: () => http.get<ResponseOf<'/api/admin/vpn/status', 'get'>>('/admin/vpn/status'),
  setVpnStatus: (action: 'start' | 'stop') =>
    http.put<ResponseOf<'/api/admin/vpn/status', 'put'>>('/admin/vpn/status', { action } satisfies BodyOf<'/api/admin/vpn/status', 'put'>),
  listModels: () => http.get<ResponseOf<'/api/admin/llm/models', 'get'>>('/admin/llm/models'),
  selectModel: (provider: string, model: string) =>
    http.put<ResponseOf<'/api/admin/llm/select', 'put'>>('/admin/llm/select', { provider, model } satisfies BodyOf<'/api/admin/llm/select', 'put'>),
  // API Key management
  listApiKeys: () => http.get<ResponseOf<'/api/admin/api-keys', 'get'>>('/admin/api-keys'),
  addApiKey: (provider: string, label: string, apiKey: string) =>
    http.post<ResponseOf<'/api/admin/api-keys', 'post'>>('/admin/api-keys', { provider, label, api_key: apiKey } satisfies BodyOf<'/api/admin/api-keys', 'post'>),
  activateApiKey: (keyId: string, provider: string) =>
    http.put<ResponseOf<'/api/admin/api-keys/activate', 'put'>>('/admin/api-keys/activate', { key_id: keyId, provider } satisfies BodyOf<'/api/admin/api-keys/activate', 'put'>),
  deleteApiKey: (keyId: string) =>
    http.delete<ResponseOf<'/api/admin/api-keys/{key_id}', 'delete'>>(`/admin/api-keys/${keyId}`),
  // Cyber enrichment: auto-enrich toggle + provider inventory
  getEnrichmentConfig: () => http.get<ResponseOf<'/api/admin/enrichment', 'get'>>('/admin/enrichment'),
  setEnrichmentConfig: (autoEnabled: boolean) =>
    http.put<ResponseOf<'/api/admin/enrichment', 'put'>>('/admin/enrichment', { auto_enabled: autoEnabled } satisfies BodyOf<'/api/admin/enrichment', 'put'>),
  listEnrichmentProviders: () => http.get<ResponseOf<'/api/enrichment/providers', 'get'>>('/enrichment/providers'),
};

export type WatchedEntity = Model<'WatchedEntityItem'>;
export type WatchlistResponse = ResponseOf<'/api/watchlist', 'get'>;

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
    http.post<ResponseOf<'/api/watchlist/add', 'post'>>('/watchlist/add', { project_id: projectId, entity_id: entityId } satisfies BodyOf<'/api/watchlist/add', 'post'>),
  remove: (projectId: string, entityId: string) =>
    http.post<ResponseOf<'/api/watchlist/remove', 'post'>>('/watchlist/remove', { project_id: projectId, entity_id: entityId } satisfies BodyOf<'/api/watchlist/remove', 'post'>),
  /** Read the entities with `readWatchlist`, which refuses any other shape. */
  list: (projectId: string) => http.get<WatchlistResponse>('/watchlist', { params: { project_id: projectId } satisfies QueryOf<'/api/watchlist', 'get'> }),
};

export const entityMgmtApi = {
  merge: (primaryId: string, mergeIds: string[], projectId: string) =>
    http.post<ResponseOf<'/api/entities/merge', 'post'>>('/entities/merge', {
      primary_id: primaryId, merge_ids: mergeIds, project_id: projectId,
    } satisfies BodyOf<'/api/entities/merge', 'post'>),
  updateType: (entityId: string, entityType: string) =>
    http.put<ResponseOf<'/api/entities/{entity_id}/type', 'put'>>(`/entities/${entityId}/type`, { entity_type: entityType } satisfies BodyOf<'/api/entities/{entity_id}/type', 'put'>),
};

export const personasApi = {
  list: () => http.get<ResponseOf<'/api/personas', 'get'>>('/personas'),
  create: (data: BodyOf<'/api/personas', 'post'>) =>
    http.post<ResponseOf<'/api/personas', 'post'>>('/personas', data),
  activate: (id: string) => http.post<ResponseOf<'/api/personas/{persona_id}/activate', 'post'>>(`/personas/${id}/activate`),
  delete: (id: string) => http.delete<ResponseOf<'/api/personas/{persona_id}', 'delete'>>(`/personas/${id}`),
  /** `{}` once the active persona was a custom one that has since been deleted. */
  active: () => http.get<ResponseOf<'/api/personas/active', 'get'>>('/personas/active'),
};

export const snapshotsApi = {
  create: (data: BodyOf<'/api/snapshots', 'post'>) =>
    http.post<ResponseOf<'/api/snapshots', 'post'>>('/snapshots', data),
  list: (projectId: string) => http.get<ResponseOf<'/api/snapshots', 'get'>>('/snapshots', { params: { project_id: projectId } satisfies QueryOf<'/api/snapshots', 'get'> }),
  get: (id: string) => http.get<ResponseOf<'/api/snapshots/{snapshot_id}', 'get'>>(`/snapshots/${id}`),
  delete: (id: string) => http.delete<ResponseOf<'/api/snapshots/{snapshot_id}', 'delete'>>(`/snapshots/${id}`),
};

export type DocumentSummary = Model<'DocumentSummaryItem'>;
export type DocumentDetail = ResponseOf<'/api/documents/{doc_id}', 'get'>;

export const documentsApi = {
  list: (projectId: string) => http.get<ResponseOf<'/api/documents', 'get'>>('/documents', { params: { project_id: projectId } satisfies QueryOf<'/api/documents', 'get'> }),
  get: (docId: string) => http.get<ResponseOf<'/api/documents/{doc_id}', 'get'>>(`/documents/${docId}`),
  evidence: (docId: string, entityName: string) =>
    http.get<ResponseOf<'/api/documents/{doc_id}/evidence', 'get'>>(`/documents/${docId}/evidence`, { params: { entity_name: entityName } satisfies QueryOf<'/api/documents/{doc_id}/evidence', 'get'> }),
};

export const healthApi = {
  // `/health` is public and sits outside `/api`, hence plain axios: no
  // session, and a 401 here must not sign the analyst out.
  check: () =>
    // Polled every 30 s by the sidebar and status bar. Without its own timeout
    // a hung backend left the check pending (and the dot green) for minutes.
    axios.get<ResponseOf<'/health', 'get'>>(`${API_BASE}/health`, { timeout: 5000 }),
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
