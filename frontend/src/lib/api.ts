import axios from 'axios';

// Use relative URL so it works on both localhost and Railway (same-origin)
const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

const api = axios.create({
  baseURL: `${API_BASE}/api`,
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
  query: (messages: Array<{role: string; content: string}>, skillName?: string) =>
    api.post('/llm/query', { messages, skill_name: skillName }),
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

// Collection Plans — new managed pipeline
export interface CollectionPlan {
  id: string;
  project_id: string;
  name: string;
  description: string;
  requirement: string;
  pir: string;
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
  total_records_acquired: number;
  acquisition_count: number;
  next_run_at: string | null;
  created_at: string | null;
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
  create: (data: { project_id: string; name: string; description?: string; requirement?: string; pir?: string; routing_rules?: object; created_by?: string }) =>
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

  // PIR-driven plan creation (unified flow)
  fromPir: (data: { project_id: string; pir: string; extraction_mode?: string; created_by?: string }) =>
    api.post<CollectionPlan & { llm_plan_text?: string }>('/collection-plans/from-pir', data),
  execute: (planId: string) =>
    api.post<CollectionPlan & { execution_status: string; message: string }>(`/collection-plans/${planId}/execute`),

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
  list: (projectId: string) => api.get('/reports', { params: { project_id: projectId } }),
  get: (id: string) => api.get(`/reports/${id}`),
  delete: (id: string) => api.delete(`/reports/${id}`),
};

export const timelineApi = {
  get: (projectId: string) => api.get('/timeline', { params: { project_id: projectId } }),
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
};

export const searchApi = {
  search: (projectId: string, query: string) =>
    api.get('/search', { params: { project_id: projectId, q: query } }),
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
  updateProxy: (data: { mode: string; proxy_url?: string; tor_port?: number }) =>
    api.put('/admin/proxy', data),
  listModels: () => api.get('/admin/llm/models'),
  selectModel: (provider: string, model: string) =>
    api.put('/admin/llm/select', { provider, model }),
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

export default api;
