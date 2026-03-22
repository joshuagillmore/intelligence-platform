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
  tree: (projectId: string) => api.get('/topics', { params: { project_id: projectId } }),
  context: (entityId: string, projectId: string) => api.get(`/topics/${entityId}`, { params: { project_id: projectId } }),
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
    const apiKey = process.env.NEXT_PUBLIC_API_KEY || 'dev-api-key-change-in-production';
    const authValue = token ? `Bearer ${token}` : `Bearer ${apiKey}`;
    return axios.get(`${API_BASE}/health`, { headers: { 'Authorization': authValue } });
  },
};

export default api;
