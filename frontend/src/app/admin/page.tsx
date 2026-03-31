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
  llm_model: string;
  extraction_mode: string;
  chunk_size: number;
  chunk_overlap: number;
  neo4j_uri: string;
}

interface ProxyConfig {
  mode: string;
  proxy_url?: string;
  tor_port?: number;
}

interface ModelInfo {
  provider: string;
  model: string;
  params: string;
  quantization: string;
  size_gb: number;
  configured?: boolean;
}

interface StoredApiKey {
  id: string;
  provider: string;
  label: string;
  key_preview: string;
  is_active: boolean;
  created_at: string | null;
}

const PROVIDERS = [
  { value: 'anthropic', label: 'Anthropic (Claude)', color: 'text-amber-400' },
  { value: 'openai', label: 'OpenAI', color: 'text-green-400' },
  { value: 'cohere', label: 'Cohere', color: 'text-rose-400' },
] as const;

export default function AdminPage() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [config, setConfig] = useState<AdminConfig | null>(null);
  const [proxy, setProxy] = useState<ProxyConfig>({ mode: 'direct' });
  const [proxyLoading, setProxyLoading] = useState(false);
  const [proxySaving, setProxySaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelSwitching, setModelSwitching] = useState(false);

  // API Key management state
  const [storedKeys, setStoredKeys] = useState<StoredApiKey[]>([]);
  const [keysLoading, setKeysLoading] = useState(false);
  const [newKeyProvider, setNewKeyProvider] = useState('anthropic');
  const [newKeyLabel, setNewKeyLabel] = useState('');
  const [newKeyValue, setNewKeyValue] = useState('');
  const [addingKey, setAddingKey] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);

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

  const loadProxy = useCallback(async () => {
    setProxyLoading(true);
    try {
      const res = await adminApi.getProxy();
      setProxy(res.data || { mode: 'direct' });
    } catch {
      setProxy({ mode: 'direct' });
    } finally {
      setProxyLoading(false);
    }
  }, []);

  const loadModels = useCallback(async () => {
    setModelsLoading(true);
    try {
      const res = await adminApi.listModels();
      setModels(res.data.models || []);
    } catch {
      setModels([]);
    } finally {
      setModelsLoading(false);
    }
  }, []);

  const loadKeys = useCallback(async () => {
    setKeysLoading(true);
    try {
      const res = await adminApi.listApiKeys();
      setStoredKeys(res.data.keys || []);
    } catch {
      setStoredKeys([]);
    } finally {
      setKeysLoading(false);
    }
  }, []);

  async function addKey() {
    if (!newKeyValue.trim() || !newKeyLabel.trim()) return;
    setAddingKey(true);
    try {
      await adminApi.addApiKey(newKeyProvider, newKeyLabel.trim(), newKeyValue.trim());
      setNewKeyLabel('');
      setNewKeyValue('');
      setShowAddForm(false);
      setToast(`API key added for ${newKeyProvider}.`);
      loadKeys();
      loadModels();
    } catch {
      setToast('Failed to add API key.');
    } finally {
      setAddingKey(false);
    }
  }

  async function activateKey(keyId: string, provider: string) {
    try {
      await adminApi.activateApiKey(keyId, provider);
      setToast(`Activated key for ${provider}.`);
      loadKeys();
      loadModels();
    } catch {
      setToast('Failed to activate key.');
    }
  }

  async function deleteKey(keyId: string) {
    if (!confirm('Delete this API key? This cannot be undone.')) return;
    try {
      await adminApi.deleteApiKey(keyId);
      setToast('API key deleted.');
      loadKeys();
      loadModels();
    } catch {
      setToast('Failed to delete key.');
    }
  }

  async function switchModel(provider: string, model: string) {
    setModelSwitching(true);
    try {
      await adminApi.selectModel(provider, model);
      setToast(`Switched to ${provider}/${model}`);
      loadConfig();
    } catch {
      setToast('Failed to switch model.');
    } finally {
      setModelSwitching(false);
    }
  }

  async function saveProxy() {
    setProxySaving(true);
    try {
      await adminApi.updateProxy(proxy);
      setToast('Proxy configuration saved.');
    } catch {
      setToast('Failed to save proxy configuration.');
    } finally {
      setProxySaving(false);
    }
  }

  useEffect(() => {
    loadHealth();
    loadProjects();
    loadConfig();
    loadProxy();
    loadModels();
    loadKeys();
  }, [loadHealth, loadProjects, loadConfig, loadProxy, loadModels, loadKeys]);

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
                onClick={() => { loadConfig(); loadModels(); }}
                className="text-xs text-accent-blue hover:text-blue-400"
              >
                Refresh
              </button>
            </div>
            {config ? (
              <div className="space-y-3">
                {/* Active model display */}
                <div className="bg-navy-700 rounded p-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-gray-400">Active Model</span>
                    <span className="text-sm font-medium px-2 py-0.5 rounded bg-green-600/20 text-green-400">
                      {config.llm_provider}
                    </span>
                  </div>
                  {config.llm_model && (
                    <div className="text-xs text-gray-500 font-mono">{config.llm_model}</div>
                  )}
                </div>

                {/* Model selector */}
                <div>
                  <label className="text-xs text-gray-400 block mb-2">Available Models</label>
                  {modelsLoading ? (
                    <p className="text-gray-500 text-sm">Scanning providers...</p>
                  ) : models.length === 0 ? (
                    <p className="text-gray-500 text-sm">No models found.</p>
                  ) : (
                    <div className="space-y-1.5 max-h-64 overflow-y-auto">
                      {models.map((m) => {
                        const isActive = config.llm_provider === m.provider && config.llm_model === m.model;
                        const isConfigured = m.configured !== false;
                        const providerColors: Record<string, string> = {
                          ollama: 'bg-purple-600/20 text-purple-400',
                          anthropic: 'bg-amber-600/20 text-amber-400',
                          openai: 'bg-green-600/20 text-green-400',
                          cohere: 'bg-rose-600/20 text-rose-400',
                        };
                        const dotColors: Record<string, string> = {
                          ollama: 'bg-purple-400',
                          anthropic: 'bg-amber-400',
                          openai: 'bg-green-400',
                          cohere: 'bg-rose-400',
                        };
                        return (
                          <button
                            key={`${m.provider}:${m.model}`}
                            onClick={() => !isActive && isConfigured && switchModel(m.provider, m.model)}
                            disabled={isActive || modelSwitching || !isConfigured}
                            className={`w-full text-left rounded p-2.5 border transition-colors ${
                              isActive
                                ? 'bg-accent-blue/10 border-accent-blue/40 cursor-default'
                                : !isConfigured
                                  ? 'bg-navy-700/50 border-navy-600/50 opacity-50 cursor-not-allowed'
                                  : 'bg-navy-700 border-navy-600 hover:border-accent-blue/30 hover:bg-navy-600'
                            } disabled:opacity-60`}
                          >
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2 min-w-0">
                                <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                                  isActive ? 'bg-green-400' : (dotColors[m.provider] || 'bg-blue-400')
                                }`} />
                                <span className="text-sm text-gray-200 truncate">{m.model}</span>
                              </div>
                              <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                                {m.params && <span className="text-[10px] text-gray-500">{m.params}</span>}
                                {m.size_gb > 0 && <span className="text-[10px] text-gray-500">{m.size_gb}GB</span>}
                                {!isConfigured && (
                                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-600/20 text-red-400">
                                    no key
                                  </span>
                                )}
                                <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                                  providerColors[m.provider] || 'bg-blue-600/20 text-blue-400'
                                }`}>{m.provider}</span>
                              </div>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Other config */}
                <div className="flex items-center justify-between bg-navy-700 rounded p-3">
                  <span className="text-sm text-gray-400">Extraction Mode</span>
                  <span className="text-sm text-gray-300 font-mono">{config.extraction_mode}</span>
                </div>
                <div className="flex items-center justify-between bg-navy-700 rounded p-3">
                  <span className="text-sm text-gray-400">Chunk Size / Overlap</span>
                  <span className="text-sm text-gray-300 font-mono">{config.chunk_size} / {config.chunk_overlap}</span>
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
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">API Key Management</h3>
              <button
                onClick={() => setShowAddForm(!showAddForm)}
                className="text-xs bg-accent-blue hover:bg-blue-600 text-white px-3 py-1.5 rounded transition-colors"
              >
                {showAddForm ? 'Cancel' : '+ Add Key'}
              </button>
            </div>
            <p className="text-gray-500 text-sm mb-3">
              Manage API keys for LLM providers. Add multiple keys per provider and select which one to use.
            </p>

            {/* Add key form */}
            {showAddForm && (
              <div className="bg-navy-700 rounded-lg p-4 mb-4 space-y-3 border border-navy-500">
                <div>
                  <label className="text-xs text-gray-400 block mb-1">Provider</label>
                  <select
                    value={newKeyProvider}
                    onChange={(e) => setNewKeyProvider(e.target.value)}
                    className="w-full bg-navy-800 border border-navy-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-blue"
                  >
                    {PROVIDERS.map(p => (
                      <option key={p.value} value={p.value}>{p.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-gray-400 block mb-1">Label</label>
                  <input
                    value={newKeyLabel}
                    onChange={(e) => setNewKeyLabel(e.target.value)}
                    placeholder="e.g. Personal, Team, Production..."
                    className="w-full bg-navy-800 border border-navy-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-blue"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-400 block mb-1">API Key</label>
                  <input
                    value={newKeyValue}
                    onChange={(e) => setNewKeyValue(e.target.value)}
                    type="password"
                    placeholder="sk-..."
                    className="w-full bg-navy-800 border border-navy-600 rounded px-3 py-2 text-sm font-mono focus:outline-none focus:border-accent-blue"
                  />
                </div>
                <button
                  onClick={addKey}
                  disabled={addingKey || !newKeyValue.trim() || !newKeyLabel.trim()}
                  className="w-full bg-accent-blue hover:bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium transition-colors disabled:opacity-50"
                >
                  {addingKey ? 'Adding...' : 'Save API Key'}
                </button>
              </div>
            )}

            {/* Stored keys list grouped by provider */}
            {keysLoading ? (
              <p className="text-gray-500 text-sm">Loading keys...</p>
            ) : storedKeys.length === 0 ? (
              <div className="text-center py-6">
                <p className="text-gray-500 text-sm">No API keys configured.</p>
                <p className="text-gray-600 text-xs mt-1">Add a key to enable cloud LLM providers.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {PROVIDERS.map(provider => {
                  const providerKeys = storedKeys.filter(k => k.provider === provider.value);
                  if (providerKeys.length === 0) return null;
                  return (
                    <div key={provider.value}>
                      <div className="flex items-center gap-2 mb-2">
                        <span className={`text-xs font-semibold uppercase tracking-wider ${provider.color}`}>
                          {provider.label}
                        </span>
                        <span className="text-[10px] text-gray-600">
                          ({providerKeys.length} key{providerKeys.length !== 1 ? 's' : ''})
                        </span>
                      </div>
                      <div className="space-y-1.5">
                        {providerKeys.map(k => (
                          <div
                            key={k.id}
                            className={`flex items-center justify-between rounded p-2.5 border transition-colors ${
                              k.is_active
                                ? 'bg-accent-blue/10 border-accent-blue/40'
                                : 'bg-navy-700 border-navy-600'
                            }`}
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                                k.is_active ? 'bg-green-400' : 'bg-gray-600'
                              }`} />
                              <div className="min-w-0">
                                <span className="text-sm text-gray-200 block truncate">{k.label}</span>
                                <span className="text-[10px] text-gray-500 font-mono">{k.key_preview}</span>
                              </div>
                            </div>
                            <div className="flex items-center gap-1.5 flex-shrink-0 ml-2">
                              {k.is_active ? (
                                <span className="text-[10px] px-2 py-0.5 rounded bg-green-600/20 text-green-400">
                                  active
                                </span>
                              ) : (
                                <button
                                  onClick={() => activateKey(k.id, k.provider)}
                                  className="text-[10px] px-2 py-0.5 rounded bg-navy-600 hover:bg-accent-blue/30 text-gray-400 hover:text-gray-200 border border-navy-500 transition-colors"
                                >
                                  activate
                                </button>
                              )}
                              <button
                                onClick={() => deleteKey(k.id)}
                                className="text-[10px] px-2 py-0.5 rounded bg-red-600/10 hover:bg-red-600/30 text-red-400 border border-red-600/20 transition-colors"
                              >
                                delete
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Proxy Configuration */}
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-6">
            <h3 className="text-lg font-semibold mb-4">Proxy Configuration</h3>
            <p className="text-gray-500 text-sm mb-3">Configure network proxy for external API calls and collection tasks.</p>
            {proxyLoading ? (
              <p className="text-gray-500 text-sm">Loading proxy configuration...</p>
            ) : (
              <div className="space-y-4">
                <div>
                  <label className="text-xs text-gray-400 block mb-1">Proxy Mode</label>
                  <select
                    value={proxy.mode}
                    onChange={(e) => setProxy(prev => ({ ...prev, mode: e.target.value }))}
                    className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-blue"
                  >
                    <option value="direct">Direct (No Proxy)</option>
                    <option value="proxy">HTTP/SOCKS Proxy</option>
                    <option value="tor">Tor Network</option>
                  </select>
                </div>

                {proxy.mode === 'proxy' && (
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">Proxy URL</label>
                    <input
                      value={proxy.proxy_url || ''}
                      onChange={(e) => setProxy(prev => ({ ...prev, proxy_url: e.target.value }))}
                      placeholder="socks5://127.0.0.1:1080 or http://proxy:8080"
                      className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-blue"
                    />
                  </div>
                )}

                {proxy.mode === 'tor' && (
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">Tor SOCKS Port</label>
                    <input
                      type="number"
                      value={proxy.tor_port || 9050}
                      onChange={(e) => setProxy(prev => ({ ...prev, tor_port: parseInt(e.target.value) || 9050 }))}
                      className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-blue"
                    />
                  </div>
                )}

                <button
                  onClick={saveProxy}
                  disabled={proxySaving}
                  className="bg-accent-blue hover:bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium transition-colors disabled:opacity-50"
                >
                  {proxySaving ? 'Saving...' : 'Save Proxy Settings'}
                </button>
              </div>
            )}
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
