import axios from 'axios';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || 'dev-api-key-change-in-production';

const api = axios.create({
  baseURL: `${API_BASE}/api`,
  headers: {
    'Authorization': `Bearer ${API_KEY}`,
    'Content-Type': 'application/json',
  },
});

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
}

export const projectsApi = {
  list: () => api.get<Project[]>('/projects'),
  create: (data: { name: string; description?: string; classification_level?: string; priority?: string }) =>
    api.post<Project>('/projects', data),
  get: (id: string) => api.get<Project>(`/projects/${id}`),
  delete: (id: string) => api.delete(`/projects/${id}`),
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
  create: (data: { project_id: string; pir: string }) => api.post('/collections', data),
  list: () => api.get('/collections'),
  status: (id: string) => api.get(`/collections/${id}/status`),
};

export const assessApi = {
  assess: (entityId: string, projectId: string, judgment: string, probability: number) =>
    api.post(`/entities/${entityId}/assess`, { entity_id: entityId, project_id: projectId, judgment, probability }),
  create: (entityId: string, data: { entity_id: string; project_id: string; judgment: string; probability: number; analyst?: string; methodology?: string }) =>
    api.post(`/entities/${entityId}/assess`, data),
  multi: (data: { entity_ids: string[]; project_id: string; judgment?: string; probability?: number }) =>
    api.post('/assess/multi', data),
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

export const geoApi = {
  locations: (projectId: string) => api.get('/geo/locations', { params: { project_id: projectId } }),
};

export const healthApi = {
  check: () => axios.get(`${API_BASE}/health`, { headers: { 'Authorization': `Bearer ${API_KEY}` } }),
};

export default api;
