'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/Sidebar';
import { healthApi, projectsApi, adminApi, exportApi, type Project } from '@/lib/api';

interface HealthData {
  status: string;
  version?: string;
  uptime?: number;
  [key: string]: unknown;
}

interface AdminConfig {
  llm_provider: string;
  extraction_mode: string;
  chunk_size: number;
  chunk_overlap: number;
  neo4j_uri: string;
}

export default function AdminPage() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [projects, setProjects] = useState<Project[]>([]);
  const [config, setConfig] = useState<AdminConfig | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const loadHealth = useCallback(async () => {
    try {
      const res = await healthApi.check();
      setHealth(res.data);
      setError(null);
    } catch {
      setError('Failed to reach backend API.');
      setHealth(null);
    }
  }, []);

  const loadProjects = useCallback(async () => {
    try {
      const res = await projectsApi.list();
      setProjects(res.data);
    } catch {
      setProjects([]);
    }
  }, []);

  const loadConfig = useCallback(async () => {
    try {
      const res = await adminApi.config();
      setConfig(res.data);
    } catch {
      setConfig(null);
    }
  }, []);

  useEffect(() => {
    loadHealth();
    loadProjects();
    loadConfig();
  }, [loadHealth, loadProjects, loadConfig]);

  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(null), 3000);
      return () => clearTimeout(t);
    }
  }, [toast]);

  async function deleteProject(project: Project) {
    if (!confirm(`Are you sure you want to delete project "${project.name}"? This action cannot be undone.`)) return;
    try {
      await projectsApi.delete(project.id);
      setToast(`Deleted: ${project.name}`);
      loadProjects();
    } catch {
      setToast('Failed to delete project.');
    }
  }

  const totalEntities = projects.reduce((sum, p) => sum + (p.entity_count || 0), 0);
  const totalRelationships = projects.reduce((sum, p) => sum + (p.relationship_count || 0), 0);
  const totalDocuments = projects.reduce((sum, p) => sum + (p.document_count || 0), 0);

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-8">
        <h2 className="text-2xl font-bold mb-6">Administration</h2>

        {/* API Statistics Summary */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-accent-blue">{projects.length}</div>
            <div className="text-xs text-gray-400 mt-1">Projects</div>
          </div>
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-green-400">{totalEntities}</div>
            <div className="text-xs text-gray-400 mt-1">Total Entities</div>
          </div>
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-purple-400">{totalRelationships}</div>
            <div className="text-xs text-gray-400 mt-1">Total Relationships</div>
          </div>
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-amber-400">{totalDocuments}</div>
            <div className="text-xs text-gray-400 mt-1">Total Documents</div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* System Health */}
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">System Health</h3>
              <button
                onClick={loadHealth}
                className="text-xs text-accent-blue hover:text-blue-400"
              >
                Refresh
              </button>
            </div>
            {error && <p className="text-red-400 text-sm mb-3">{error}</p>}
            {health ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <span className={`w-2.5 h-2.5 rounded-full ${health.status === 'healthy' || health.status === 'ok' ? 'bg-green-400' : 'bg-red-400'}`} />
                  <span className="text-sm font-medium">
                    {health.status === 'healthy' || health.status === 'ok' ? 'All Systems Operational' : `Status: ${health.status}`}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2 mt-2">
                  {Object.entries(health).filter(([k]) => k !== 'status').map(([key, value]) => (
                    <div key={key} className="bg-navy-700 rounded p-2">
                      <div className="text-[10px] text-gray-500 uppercase tracking-wider">{key.replace(/_/g, ' ')}</div>
                      <div className="text-sm text-gray-300 mt-0.5 truncate">{typeof value === 'object' ? JSON.stringify(value) : String(value)}</div>
                    </div>
                  ))}
                </div>
              </div>
            ) : !error ? (
              <p className="text-gray-500 text-sm">Loading...</p>
            ) : null}
          </div>

          {/* LLM Configuration */}
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">LLM Configuration</h3>
              <button
                onClick={loadConfig}
                className="text-xs text-accent-blue hover:text-blue-400"
              >
                Refresh
              </button>
            </div>
            {config ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between bg-navy-700 rounded p-3">
                  <span className="text-sm text-gray-400">LLM Provider</span>
                  <span className={`text-sm font-medium px-2 py-0.5 rounded ${
                    config.llm_provider !== 'none' ? 'bg-green-600/20 text-green-400' : 'bg-red-600/20 text-red-400'
                  }`}>
                    {config.llm_provider}
                  </span>
                </div>
                <div className="flex items-center justify-between bg-navy-700 rounded p-3">
                  <span className="text-sm text-gray-400">Extraction Mode</span>
                  <span className="text-sm text-gray-300 font-mono">{config.extraction_mode}</span>
                </div>
                <div className="flex items-center justify-between bg-navy-700 rounded p-3">
                  <span className="text-sm text-gray-400">Chunk Size / Overlap</span>
                  <span className="text-sm text-gray-300 font-mono">{config.chunk_size} / {config.chunk_overlap}</span>
                </div>
                <div className="flex items-center justify-between bg-navy-700 rounded p-3">
                  <span className="text-sm text-gray-400">Neo4j</span>
                  <span className="text-sm text-gray-300 font-mono text-xs truncate ml-2">{config.neo4j_uri}</span>
                </div>
              </div>
            ) : (
              <p className="text-gray-500 text-sm">Loading configuration...</p>
            )}
          </div>

          {/* Data Management / Export */}
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-6">
            <h3 className="text-lg font-semibold mb-4">Data Management</h3>
            <p className="text-gray-500 text-sm mb-4">Export data across all projects.</p>
            <div className="space-y-2">
              {projects.map(project => (
                <div key={project.id} className="bg-navy-700 rounded p-3">
                  <div className="text-sm text-gray-200 font-medium mb-2">{project.name}</div>
                  <div className="flex gap-2 flex-wrap">
                    <button
                      onClick={async () => {
                        try {
                          const res = await exportApi.stix(project.id);
                          const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement('a');
                          a.href = url;
                          a.download = `stix-export-${project.id.substring(0, 8)}.json`;
                          a.click();
                          URL.revokeObjectURL(url);
                          setToast(`STIX bundle exported for ${project.name}.`);
                        } catch {
                          setToast('Failed to export STIX bundle.');
                        }
                      }}
                      className="text-xs bg-navy-600 hover:bg-navy-500 text-gray-300 px-3 py-1.5 rounded border border-navy-500 transition-colors"
                    >
                      STIX 2.1
                    </button>
                    <button
                      onClick={async () => {
                        try {
                          const res = await exportApi.graph(project.id);
                          const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement('a');
                          a.href = url;
                          a.download = `graph-export-${project.id.substring(0, 8)}.json`;
                          a.click();
                          URL.revokeObjectURL(url);
                          setToast(`Graph JSON exported for ${project.name}.`);
                        } catch {
                          setToast('Failed to export graph.');
                        }
                      }}
                      className="text-xs bg-navy-600 hover:bg-navy-500 text-gray-300 px-3 py-1.5 rounded border border-navy-500 transition-colors"
                    >
                      JSON
                    </button>
                    <button
                      onClick={async () => {
                        try {
                          const res = await exportApi.entities(project.id);
                          const csvContent = res.data.csv || '';
                          const blob = new Blob([csvContent], { type: 'text/csv' });
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement('a');
                          a.href = url;
                          a.download = `entities-export-${project.id.substring(0, 8)}.csv`;
                          a.click();
                          URL.revokeObjectURL(url);
                          setToast(`CSV exported for ${project.name}.`);
                        } catch {
                          setToast('Failed to export CSV.');
                        }
                      }}
                      className="text-xs bg-navy-600 hover:bg-navy-500 text-gray-300 px-3 py-1.5 rounded border border-navy-500 transition-colors"
                    >
                      CSV
                    </button>
                  </div>
                </div>
              ))}
              {projects.length === 0 && (
                <p className="text-gray-500 text-sm">No projects available for export.</p>
              )}
            </div>
          </div>

          {/* API Key Management */}
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-6">
            <h3 className="text-lg font-semibold mb-4">API Key Management</h3>
            <p className="text-gray-500 text-sm mb-3">Configure API keys for external services.</p>
            <div className="flex gap-3">
              <input
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                type="password"
                placeholder="Enter new API key..."
                className="flex-1 bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-blue"
              />
              <button
                className="bg-navy-600 hover:bg-navy-700 text-gray-300 px-4 py-2 rounded text-sm border border-navy-600 cursor-not-allowed opacity-50"
                disabled
              >
                Save (Coming Soon)
              </button>
            </div>
          </div>

          {/* Project Management / Danger Zone */}
          <div className="bg-navy-800 border border-red-900/50 rounded-lg p-6 lg:col-span-2">
            <h3 className="text-lg font-semibold text-red-400 mb-4">Project Management</h3>
            <p className="text-gray-500 text-sm mb-4">Manage and delete projects. Deletion is permanent and cannot be undone.</p>
            {projects.length === 0 ? (
              <p className="text-gray-500 text-sm">No projects found.</p>
            ) : (
              <div className="space-y-2">
                {projects.map(project => (
                  <div
                    key={project.id}
                    className="flex items-center justify-between bg-navy-700 rounded p-3"
                  >
                    <div className="flex-1 min-w-0">
                      <span className="text-sm text-gray-200 font-medium">{project.name}</span>
                      <div className="flex gap-4 mt-1">
                        <span className="text-xs text-gray-500">
                          {project.entity_count} entities
                        </span>
                        <span className="text-xs text-gray-500">
                          {project.relationship_count} relationships
                        </span>
                        <span className="text-xs text-gray-500">
                          {project.document_count} documents
                        </span>
                        <span className="text-xs text-gray-500">
                          {project.classification_level}
                        </span>
                      </div>
                    </div>
                    <button
                      onClick={() => deleteProject(project)}
                      className="text-xs bg-red-600/20 hover:bg-red-600/40 text-red-400 hover:text-red-300 px-3 py-1.5 rounded border border-red-600/30 transition-colors ml-4"
                    >
                      Delete Project
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {toast && (
          <div className="fixed bottom-6 right-6 bg-accent-blue text-white px-4 py-2 rounded-lg shadow-lg text-sm animate-pulse">
            {toast}
          </div>
        )}
      </main>
    </div>
  );
}
