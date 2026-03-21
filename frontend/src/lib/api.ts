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
};

export const graphApi = {
  full: (projectId: string) => api.get('/graph', { params: { project_id: projectId } }),
  communities: (projectId: string) => api.get('/communities', { params: { project_id: projectId } }),
  centrality: (projectId: string) => api.get('/graph/centrality', { params: { project_id: projectId } }),
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
};

export default api;
