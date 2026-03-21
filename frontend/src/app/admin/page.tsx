'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/Sidebar';
import { healthApi, projectsApi, type Project } from '@/lib/api';

interface HealthData {
  status: string;
  version?: string;
  uptime?: number;
  [key: string]: unknown;
}

export default function AdminPage() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [projects, setProjects] = useState<Project[]>([]);
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

  useEffect(() => {
    loadHealth();
    loadProjects();
  }, [loadHealth, loadProjects]);

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

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-8">
        <h2 className="text-2xl font-bold mb-6">Administration</h2>

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
                  <span className="text-sm">Status: {health.status}</span>
                </div>
                {Object.entries(health).filter(([k]) => k !== 'status').map(([key, value]) => (
                  <div key={key} className="text-sm">
                    <span className="text-gray-500">{key}:</span>{' '}
                    <span className="text-gray-300">{typeof value === 'object' ? JSON.stringify(value) : String(value)}</span>
                  </div>
                ))}
              </div>
            ) : !error ? (
              <p className="text-gray-500 text-sm">Loading...</p>
            ) : null}
          </div>

          {/* Configuration */}
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-6">
            <h3 className="text-lg font-semibold mb-4">Configuration</h3>
            <div className="space-y-3">
              <div className="text-sm">
                <span className="text-gray-500">API URL:</span>{' '}
                <span className="text-gray-300 font-mono text-xs">http://localhost:8000</span>
              </div>
              <div className="text-sm">
                <span className="text-gray-500">Frontend:</span>{' '}
                <span className="text-gray-300 font-mono text-xs">Next.js 14</span>
              </div>
            </div>
          </div>

          {/* API Key Management */}
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-6 lg:col-span-2">
            <h3 className="text-lg font-semibold mb-4">API Key Management</h3>
            <p className="text-gray-500 text-sm mb-3">Configure API keys for external services.</p>
            <div className="flex gap-3">
              <input
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                type="password"
                placeholder="Enter new API key..."
                className="flex-1 bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-blue max-w-md"
              />
              <button
                className="bg-navy-600 hover:bg-navy-700 text-gray-300 px-4 py-2 rounded text-sm border border-navy-600 cursor-not-allowed opacity-50"
                disabled
              >
                Save (Coming Soon)
              </button>
            </div>
          </div>

          {/* Danger Zone */}
          <div className="bg-navy-800 border border-red-900/50 rounded-lg p-6 lg:col-span-2">
            <h3 className="text-lg font-semibold text-red-400 mb-4">Danger Zone</h3>
            <p className="text-gray-500 text-sm mb-4">Delete projects permanently. This action cannot be undone.</p>
            {projects.length === 0 ? (
              <p className="text-gray-500 text-sm">No projects found.</p>
            ) : (
              <div className="space-y-2">
                {projects.map(project => (
                  <div
                    key={project.id}
                    className="flex items-center justify-between bg-navy-700 rounded p-3"
                  >
                    <div>
                      <span className="text-sm text-gray-200 font-medium">{project.name}</span>
                      <span className="text-xs text-gray-500 ml-3">
                        {project.entity_count} entities, {project.document_count} documents
                      </span>
                    </div>
                    <button
                      onClick={() => deleteProject(project)}
                      className="text-xs bg-red-600/20 hover:bg-red-600/40 text-red-400 hover:text-red-300 px-3 py-1.5 rounded border border-red-600/30 transition-colors"
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
