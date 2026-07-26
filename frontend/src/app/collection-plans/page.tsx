'use client';
import { useEffect, useState, useCallback, useRef } from 'react';
import Sidebar from '@/components/Sidebar';
import SelectProjectPrompt from '@/components/SelectProjectPrompt';
import LoadingSpinner from '@/components/LoadingSpinner';
import { useProject } from '@/lib/ProjectContext';
import { collectionPlansApi, pirsApi, CollectionPlan, AcquisitionLogEntry, Pir } from '@/lib/api';
import { getErrorMessage } from '@/lib/errorMessages';
import { humanize } from '@/lib/format';

const STATUS_COLORS: Record<string, string> = {
  DRAFT: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
  ACTIVE: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  PAUSED: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  COMPLETED: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  ARCHIVED: 'bg-gray-600/20 text-gray-500 border-gray-600/30',
};

const SOURCE_TYPE_ICONS: Record<string, string> = {
  file_upload: 'upload_file',
  web_scrape: 'language',
  api_feed: 'api',
  database: 'database',
  rss_feed: 'rss_feed',
  watched_dir: 'folder_open',
};

const SUPPORTED_FILE_EXTENSIONS = ['.csv', '.tsv', '.xlsx', '.xls', '.json', '.jsonl'];

interface DashboardData {
  plan_counts: Record<string, number>;
  total_plans: number;
  source_health: { healthy: number; unhealthy: number; disabled: number; total: number };
  total_records_acquired: number;
  recent_acquisitions: AcquisitionLogEntry[];
}

export default function CollectionPlansPage() {
  const { activeProject } = useProject();
  const [plans, setPlans] = useState<CollectionPlan[]>([]);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Create plan form. `pir_id` anchors the plan on one of the project's
  // Priority Intelligence Requirements (see /pirs) rather than a free-text copy.
  const [showCreate, setShowCreate] = useState(false);
  const [newPlan, setNewPlan] = useState({ name: '', description: '', requirement: '', pir_id: '' });
  const [creating, setCreating] = useState(false);
  const [pirs, setPirs] = useState<Pir[]>([]);

  // Selected plan detail
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
  const [selectedPlan, setSelectedPlan] = useState<CollectionPlan | null>(null);

  // Add source form
  const [showAddSource, setShowAddSource] = useState(false);
  const [newSource, setNewSource] = useState({ name: '', source_type: 'file_upload' });

  // File upload
  const [uploadingSourceId, setUploadingSourceId] = useState<string | null>(null);
  const [uploadResult, setUploadResult] = useState<Record<string, unknown> | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Acquisition log
  const [acquisitions, setAcquisitions] = useState<AcquisitionLogEntry[]>([]);

  const loadPlans = useCallback(async () => {
    if (!activeProject) return;
    setLoading(true);
    try {
      const [plansRes, dashRes] = await Promise.all([
        collectionPlansApi.list(activeProject.id),
        collectionPlansApi.dashboard(activeProject.id),
      ]);
      setPlans(plansRes.data);
      setDashboard(dashRes.data);
    } catch (e) {
      console.error('Failed to load plans', e);
    } finally {
      setLoading(false);
    }
  }, [activeProject]);

  const loadPirs = useCallback(async () => {
    if (!activeProject) return;
    try {
      const res = await pirsApi.list(activeProject.id);
      setPirs(res.data);
    } catch (e) {
      console.error('Failed to load PIRs', e);
    }
  }, [activeProject]);

  useEffect(() => { loadPlans(); loadPirs(); }, [loadPlans, loadPirs]);

  const loadPlanDetail = useCallback(async (planId: string) => {
    try {
      const [planRes, acqRes] = await Promise.all([
        collectionPlansApi.get(planId),
        collectionPlansApi.acquisitions(planId),
      ]);
      setSelectedPlan(planRes.data);
      setAcquisitions(acqRes.data);
    } catch (e) {
      console.error('Failed to load plan detail', e);
    }
  }, []);

  useEffect(() => {
    if (selectedPlanId) loadPlanDetail(selectedPlanId);
  }, [selectedPlanId, loadPlanDetail]);

  async function createPlan() {
    if (!activeProject || !newPlan.name.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const res = await collectionPlansApi.create({
        project_id: activeProject.id,
        name: newPlan.name.trim(),
        description: newPlan.description,
        requirement: newPlan.requirement,
        // The backend copies the PIR's text onto the plan, so the requirement
        // is stored once and referenced — not retyped per plan.
        pir_id: newPlan.pir_id || undefined,
      });
      setShowCreate(false);
      setNewPlan({ name: '', description: '', requirement: '', pir_id: '' });
      setSelectedPlanId(res.data.id);
      loadPlans();
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setCreating(false);
    }
  }

  async function transitionPlan(planId: string, action: 'activate' | 'pause' | 'complete' | 'archive') {
    try {
      await collectionPlansApi[action](planId);
      loadPlans();
      if (selectedPlanId === planId) loadPlanDetail(planId);
    } catch (e) {
      setError(getErrorMessage(e));
    }
  }

  async function deletePlan(planId: string) {
    const name = plans.find(p => String(p.id) === String(planId))?.name || 'this plan';
    if (!confirm(`Delete "${name}"? Its sources and collection history go with it. This can't be undone.`)) return;
    try {
      await collectionPlansApi.delete(planId);
      if (selectedPlanId === planId) {
        setSelectedPlanId(null);
        setSelectedPlan(null);
      }
      loadPlans();
    } catch (e) {
      setError(getErrorMessage(e));
    }
  }

  async function addSource() {
    if (!selectedPlanId || !newSource.name.trim()) return;
    try {
      await collectionPlansApi.addSource(selectedPlanId, {
        name: newSource.name.trim(),
        source_type: newSource.source_type,
        config: {},
      });
      setShowAddSource(false);
      setNewSource({ name: '', source_type: 'file_upload' });
      loadPlanDetail(selectedPlanId);
    } catch (e) {
      setError(getErrorMessage(e));
    }
  }

  async function deleteSource(sourceId: string) {
    if (!selectedPlanId) return;
    const name = selectedPlan?.sources?.find(s => String(s.id) === String(sourceId))?.name || 'this source';
    if (!confirm(`Remove source "${name}" from this plan? This can't be undone.`)) return;
    try {
      await collectionPlansApi.deleteSource(selectedPlanId, sourceId);
      loadPlanDetail(selectedPlanId);
    } catch (e) {
      setError(getErrorMessage(e));
    }
  }

  async function handleFileUpload(sourceId: string, file: File) {
    if (!selectedPlanId) return;
    setUploading(true);
    setUploadingSourceId(sourceId);
    setUploadResult(null);
    setUploadError(null);
    try {
      const res = await collectionPlansApi.uploadFile(selectedPlanId, sourceId, file);
      setUploadResult(res.data);
      loadPlanDetail(selectedPlanId);
      loadPlans();
    } catch (e) {
      setUploadError(getErrorMessage(e));
    } finally {
      setUploading(false);
    }
  }

  function formatDate(d: string | null) {
    if (!d) return '—';
    return new Date(d).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }

  if (!activeProject) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="md:ml-56 flex-1 p-4 pt-16 pb-24 md:p-8 md:pt-8 md:pb-8">
          <h2 className="text-2xl font-bold mb-4">Collection Plans</h2>
          <SelectProjectPrompt action="manage collection plans for" />
        </main>
      </div>
    );
  }

  return (
    <div className="flex">
      <Sidebar />
      <main className="md:ml-56 flex-1 p-4 pt-16 pb-24 md:p-8 md:pt-8 md:pb-8 overflow-y-auto h-screen">

        {/* Dashboard Summary */}
        {dashboard && (
          <section className="mb-8">
            <h2 className="text-[10px] font-black tracking-[0.2em] text-accent-periwinkle uppercase mb-4 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-accent-periwinkle animate-pulse" />
              Collection Dashboard
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-navy-800 rounded p-4">
                <div className="text-2xl font-bold text-white">{dashboard.total_plans}</div>
                <div className="text-[10px] uppercase tracking-wider text-gray-400">Total Plans</div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {Object.entries(dashboard.plan_counts).map(([status, count]) => (
                    <span key={status} className={`px-1.5 py-0.5 text-[9px] rounded border ${STATUS_COLORS[status] || 'text-gray-400'}`}>
                      {status}: {count}
                    </span>
                  ))}
                </div>
              </div>
              <div className="bg-navy-800 rounded p-4">
                <div className="text-2xl font-bold text-white">{dashboard.source_health.total}</div>
                <div className="text-[10px] uppercase tracking-wider text-gray-400">Sources</div>
                <div className="mt-2 flex gap-2 text-[10px]">
                  <span className="text-emerald-400">{dashboard.source_health.healthy} healthy</span>
                  {dashboard.source_health.unhealthy > 0 && <span className="text-red-400">{dashboard.source_health.unhealthy} errors</span>}
                </div>
              </div>
              <div className="bg-navy-800 rounded p-4">
                <div className="text-2xl font-bold text-white">{dashboard.total_records_acquired.toLocaleString()}</div>
                <div className="text-[10px] uppercase tracking-wider text-gray-400">Records Acquired</div>
              </div>
              <div className="bg-navy-800 rounded p-4">
                <div className="text-2xl font-bold text-white">{dashboard.recent_acquisitions.length}</div>
                <div className="text-[10px] uppercase tracking-wider text-gray-400">Recent Acquisitions</div>
              </div>
            </div>
          </section>
        )}

        <div className="flex flex-col lg:flex-row gap-6">
          {/* Left Panel: Plan List */}
          <div className="lg:w-1/3">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-[10px] font-black tracking-[0.2em] text-accent-periwinkle uppercase flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-accent-periwinkle" />
                Collection Plans
              </h2>
              <button
                onClick={() => setShowCreate(!showCreate)}
                className="bg-accent-periwinkle hover:bg-[#4d8eff] text-[#002e6a] px-3 py-1.5 rounded text-[10px] font-bold uppercase tracking-wider"
              >
                + New Plan
              </button>
            </div>

            {/* Create Plan Form */}
            {showCreate && (
              <div className="bg-navy-800 rounded p-4 mb-4 space-y-3">
                <input
                  value={newPlan.name}
                  onChange={e => setNewPlan(p => ({ ...p, name: e.target.value }))}
                  placeholder="Plan name"
                  className="w-full bg-[#090e1c] border-none text-sm py-2 px-3 rounded focus:ring-1 focus:ring-accent-periwinkle placeholder:text-gray-600"
                />
                {/* Anchor the plan on a tracked PIR — created and managed on the
                    project hub, so the requirement is not retyped here. */}
                <select
                  value={newPlan.pir_id}
                  onChange={e => setNewPlan(p => ({ ...p, pir_id: e.target.value }))}
                  aria-label="Priority Intelligence Requirement"
                  className="w-full bg-[#090e1c] border-none text-sm py-2 px-3 rounded focus:ring-1 focus:ring-accent-periwinkle text-gray-300"
                >
                  <option value="">
                    {pirs.length ? 'Priority Intelligence Requirement (optional)' : 'No PIRs yet — add one on the project hub'}
                  </option>
                  {pirs.map(p => (
                    <option key={p.id} value={p.id}>[{p.status}] {p.title || p.text.slice(0, 60)}</option>
                  ))}
                </select>
                <textarea
                  value={newPlan.requirement}
                  onChange={e => setNewPlan(p => ({ ...p, requirement: e.target.value }))}
                  placeholder="Intelligence requirement — what question does this collection address?"
                  rows={3}
                  className="w-full bg-[#090e1c] border-none text-sm py-2 px-3 rounded focus:ring-1 focus:ring-accent-periwinkle placeholder:text-gray-600 resize-none"
                />
                <input
                  value={newPlan.description}
                  onChange={e => setNewPlan(p => ({ ...p, description: e.target.value }))}
                  placeholder="Description (optional)"
                  className="w-full bg-[#090e1c] border-none text-sm py-2 px-3 rounded focus:ring-1 focus:ring-accent-periwinkle placeholder:text-gray-600"
                />
                <div className="flex gap-2">
                  <button onClick={createPlan} disabled={creating || !newPlan.name.trim()} className="bg-accent-periwinkle hover:bg-[#4d8eff] text-[#002e6a] px-4 py-2 rounded text-[10px] font-bold uppercase disabled:opacity-50">
                    {creating ? 'Creating...' : 'Create'}
                  </button>
                  <button onClick={() => setShowCreate(false)} className="text-gray-400 hover:text-white px-4 py-2 text-[10px] uppercase">
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {error && <p className="text-red-400 text-xs mb-2">{error}</p>}

            {/* Plan List */}
            {loading ? <LoadingSpinner size="sm" /> : (
              <div className="space-y-2">
                {plans.length === 0 && (
                  <div className="bg-navy-800 rounded p-6 text-center text-gray-500 text-sm">
                    No collection plans yet. Create one to start collecting data.
                  </div>
                )}
                {plans.map(plan => (
                  <button
                    key={plan.id}
                    onClick={() => setSelectedPlanId(plan.id)}
                    className={`w-full text-left bg-navy-800 rounded p-3 hover:bg-[#252a39] transition-colors border ${selectedPlanId === plan.id ? 'border-accent-periwinkle/50' : 'border-transparent'}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-white truncate">{plan.name}</div>
                        {plan.requirement && <div className="text-[11px] text-gray-400 mt-0.5 line-clamp-2">{plan.requirement}</div>}
                      </div>
                      <span className={`px-1.5 py-0.5 text-[9px] rounded border whitespace-nowrap ${STATUS_COLORS[plan.status] || 'text-gray-400'}`}>
                        {plan.status}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 mt-2 text-[10px] text-gray-500">
                      <span>{plan.source_count} sources</span>
                      <span>{formatDate(plan.updated_at)}</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Right Panel: Plan Detail */}
          <div className="lg:w-2/3">
            {!selectedPlan ? (
              <div className="bg-navy-800 rounded p-8 text-center text-gray-500 text-sm">
                Select a collection plan to view details, manage sources, and upload data.
              </div>
            ) : (
              <div className="space-y-6">
                {/* Plan Header */}
                <div className="bg-navy-800 rounded p-4">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="text-lg font-bold text-white">{selectedPlan.name}</h3>
                      {/* Which requirement this plan answers to — the spine, visible
                          from the collection side of the cycle too. */}
                      {selectedPlan.pir_id && (
                        <p className="text-[10px] uppercase tracking-widest font-bold mt-1 text-accent-periwinkle">
                          PIR · {pirs.find(p => p.id === selectedPlan.pir_id)?.title || 'linked requirement'}
                          <span className="ml-2 text-gray-500 normal-case tracking-normal font-normal">
                            {pirs.find(p => p.id === selectedPlan.pir_id)?.status || ''}
                          </span>
                        </p>
                      )}
                      {selectedPlan.requirement && (
                        <p className="text-sm text-gray-300 mt-1">{selectedPlan.requirement}</p>
                      )}
                      {selectedPlan.description && (
                        <p className="text-xs text-gray-500 mt-1">{selectedPlan.description}</p>
                      )}
                    </div>
                    <span className={`px-2 py-1 text-[10px] rounded border font-bold ${STATUS_COLORS[selectedPlan.status] || 'text-gray-400'}`}>
                      {selectedPlan.status}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2 mt-4">
                    {selectedPlan.status === 'DRAFT' && (
                      <button onClick={() => transitionPlan(selectedPlan.id, 'activate')} className="bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 px-3 py-1 rounded text-[10px] font-bold uppercase hover:bg-emerald-500/30">
                        Activate
                      </button>
                    )}
                    {selectedPlan.status === 'ACTIVE' && (
                      <button onClick={() => transitionPlan(selectedPlan.id, 'pause')} className="bg-amber-500/20 text-amber-400 border border-amber-500/30 px-3 py-1 rounded text-[10px] font-bold uppercase hover:bg-amber-500/30">
                        Pause
                      </button>
                    )}
                    {selectedPlan.status === 'PAUSED' && (
                      <button onClick={() => transitionPlan(selectedPlan.id, 'activate')} className="bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 px-3 py-1 rounded text-[10px] font-bold uppercase hover:bg-emerald-500/30">
                        Resume
                      </button>
                    )}
                    {(selectedPlan.status === 'ACTIVE' || selectedPlan.status === 'PAUSED') && (
                      <button onClick={() => transitionPlan(selectedPlan.id, 'complete')} className="bg-blue-500/20 text-blue-400 border border-blue-500/30 px-3 py-1 rounded text-[10px] font-bold uppercase hover:bg-blue-500/30">
                        Complete
                      </button>
                    )}
                    {selectedPlan.status === 'COMPLETED' && (
                      <button onClick={() => transitionPlan(selectedPlan.id, 'archive')} className="bg-gray-500/20 text-gray-400 border border-gray-500/30 px-3 py-1 rounded text-[10px] font-bold uppercase hover:bg-gray-500/30">
                        Archive
                      </button>
                    )}
                    <button onClick={() => deletePlan(selectedPlan.id)} className="bg-red-500/10 text-red-400 border border-red-500/20 px-3 py-1 rounded text-[10px] font-bold uppercase hover:bg-red-500/20 ml-auto">
                      Delete
                    </button>
                  </div>
                  <div className="flex gap-4 mt-3 text-[10px] text-gray-500">
                    <span>Created by: {selectedPlan.created_by}</span>
                    <span>Created: {formatDate(selectedPlan.created_at)}</span>
                    <span>Updated: {formatDate(selectedPlan.updated_at)}</span>
                  </div>
                </div>

                {/* Sources */}
                <div className="bg-navy-800 rounded p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-[10px] font-black tracking-[0.2em] text-accent-periwinkle uppercase">
                      Assigned Sources
                    </h4>
                    <button onClick={() => setShowAddSource(!showAddSource)} className="text-accent-periwinkle hover:text-white text-[10px] font-bold uppercase">
                      + Add Source
                    </button>
                  </div>

                  {showAddSource && (
                    <div className="bg-[#090e1c] rounded p-3 mb-3 space-y-2">
                      <input
                        value={newSource.name}
                        onChange={e => setNewSource(s => ({ ...s, name: e.target.value }))}
                        placeholder="Source name (e.g. 'Q1 Financial Report', 'OSINT Feed')"
                        className="w-full bg-navy-800 border-none text-sm py-2 px-3 rounded focus:ring-1 focus:ring-accent-periwinkle placeholder:text-gray-600"
                      />
                      <select
                        value={newSource.source_type}
                        onChange={e => setNewSource(s => ({ ...s, source_type: e.target.value }))}
                        className="w-full bg-navy-800 border-none text-sm py-2 px-3 rounded focus:ring-1 focus:ring-accent-periwinkle text-gray-300"
                      >
                        <option value="file_upload">File Upload (CSV, Excel, JSON)</option>
                        <option value="web_scrape">Web Scrape</option>
                        <option value="api_feed">API Feed</option>
                        <option value="database">Database Query</option>
                        <option value="rss_feed">RSS Feed</option>
                      </select>
                      <div className="flex gap-2">
                        <button onClick={addSource} disabled={!newSource.name.trim()} className="bg-accent-periwinkle text-[#002e6a] px-3 py-1.5 rounded text-[10px] font-bold uppercase disabled:opacity-50">Add</button>
                        <button onClick={() => setShowAddSource(false)} className="text-gray-400 text-[10px] uppercase px-3">Cancel</button>
                      </div>
                    </div>
                  )}

                  {(selectedPlan.sources || []).length === 0 ? (
                    <p className="text-gray-500 text-sm text-center py-4">No sources assigned. Add a source to start collecting data.</p>
                  ) : (
                    <div className="space-y-2">
                      {(selectedPlan.sources || []).map(source => (
                        <div key={source.id} className="bg-[#090e1c] rounded p-3">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span className="material-symbols-outlined text-base text-accent-periwinkle">
                                {SOURCE_TYPE_ICONS[source.source_type] || 'source'}
                              </span>
                              <div>
                                <div className="text-sm font-medium text-white">{source.name}</div>
                                <div className="text-[10px] text-gray-500">{humanize(source.source_type)} · {source.total_records_acquired.toLocaleString()} records · {source.acquisition_count} acquisitions</div>
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              {source.last_error ? (
                                <span className="text-[9px] text-red-400 bg-red-500/10 px-1.5 py-0.5 rounded" title={source.last_error}>ERROR</span>
                              ) : source.last_success_at ? (
                                <span className="text-[9px] text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded">OK</span>
                              ) : null}
                            </div>
                          </div>

                          {/* File upload action for file_upload sources */}
                          {source.source_type === 'file_upload' && (
                            <div className="mt-2 flex items-center gap-2">
                              <input
                                ref={uploadingSourceId === source.id ? fileInputRef : undefined}
                                type="file"
                                accept={SUPPORTED_FILE_EXTENSIONS.join(',')}
                                onChange={e => {
                                  const f = e.target.files?.[0];
                                  if (f) handleFileUpload(source.id, f);
                                }}
                                className="hidden"
                                id={`file-${source.id}`}
                              />
                              <label
                                htmlFor={`file-${source.id}`}
                                className={`cursor-pointer bg-[#252a39] hover:bg-[#313849] text-accent-periwinkle border border-accent-periwinkle/20 px-3 py-1.5 rounded text-[10px] font-bold uppercase transition-colors ${uploading && uploadingSourceId === source.id ? 'opacity-50 pointer-events-none' : ''}`}
                              >
                                {uploading && uploadingSourceId === source.id ? 'Uploading...' : 'Upload File'}
                              </label>
                              <button onClick={() => deleteSource(source.id)} className="text-red-400/50 hover:text-red-400 text-[10px]">
                                <span className="material-symbols-outlined text-sm">delete</span>
                              </button>
                            </div>
                          )}

                          {/* Coverage info */}
                          {source.last_success_at && (
                            <div className="mt-1 text-[10px] text-gray-500">
                              Last success: {formatDate(source.last_success_at)}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Upload Result */}
                {uploadResult && (
                  <div className="bg-[#0a2a0a] border border-emerald-500/20 rounded p-4">
                    <h4 className="text-[10px] font-black tracking-[0.2em] text-emerald-400 uppercase mb-3">
                      Ingestion Result
                    </h4>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                      <div><div className="text-lg font-bold text-white">{(uploadResult as { record_count?: number }).record_count}</div><div className="text-[9px] text-gray-400">Records</div></div>
                      <div><div className="text-lg font-bold text-white">{(uploadResult as { column_count?: number }).column_count}</div><div className="text-[9px] text-gray-400">Columns</div></div>
                      <div><div className="text-lg font-bold text-white">{((uploadResult as { routing_results?: { entities_created?: number } }).routing_results?.entities_created) || 0}</div><div className="text-[9px] text-gray-400">Entities Extracted</div></div>
                      <div><div className="text-lg font-bold text-white">{((uploadResult as { routing_results?: { relationships_created?: number } }).routing_results?.relationships_created) || 0}</div><div className="text-[9px] text-gray-400">Relationships</div></div>
                    </div>

                    {/* Schema Preview */}
                    {(uploadResult as { schema_info?: { columns?: Array<{ name: string; type: string }> } }).schema_info?.columns && (
                      <div className="mb-3">
                        <div className="text-[10px] text-gray-400 uppercase mb-1">Schema</div>
                        <div className="flex flex-wrap gap-1">
                          {((uploadResult as { schema_info: { columns: Array<{ name: string; type: string }> } }).schema_info.columns).map((col: { name: string; type: string }, i: number) => (
                            <span key={i} className="bg-navy-800 text-gray-300 px-2 py-0.5 rounded text-[10px]">
                              {col.name} <span className="text-gray-500">({col.type})</span>
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Data Preview */}
                    {(uploadResult as { preview_rows?: Record<string, unknown>[] }).preview_rows && ((uploadResult as { preview_rows: Record<string, unknown>[] }).preview_rows).length > 0 && (
                      <div>
                        <div className="text-[10px] text-gray-400 uppercase mb-1">Preview (first rows)</div>
                        <div className="overflow-x-auto">
                          <table className="w-full text-[11px]">
                            <thead>
                              <tr className="text-gray-400">
                                {Object.keys((uploadResult as { preview_rows: Record<string, unknown>[] }).preview_rows[0]).filter(k => k !== '_row_number').map(key => (
                                  <th key={key} className="text-left py-1 px-2 font-medium">{key}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {((uploadResult as { preview_rows: Record<string, unknown>[] }).preview_rows).slice(0, 10).map((row: Record<string, unknown>, i: number) => (
                                <tr key={i} className="border-t border-navy-800">
                                  {Object.entries(row).filter(([k]) => k !== '_row_number').map(([k, v]) => (
                                    <td key={k} className="py-1 px-2 text-gray-300 max-w-[200px] truncate">{String(v ?? '')}</td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    <button onClick={() => setUploadResult(null)} className="mt-2 text-gray-400 text-[10px] hover:text-white">Dismiss</button>
                  </div>
                )}

                {uploadError && (
                  <div className="bg-red-500/10 border border-red-500/20 rounded p-3 text-red-400 text-sm">
                    {uploadError}
                    <button onClick={() => setUploadError(null)} className="ml-2 text-red-400/50 hover:text-red-400 text-[10px]">Dismiss</button>
                  </div>
                )}

                {/* Acquisition Log */}
                <div className="bg-navy-800 rounded p-4">
                  <h4 className="text-[10px] font-black tracking-[0.2em] text-accent-periwinkle uppercase mb-3">
                    Acquisition History
                  </h4>
                  {acquisitions.length === 0 ? (
                    <p className="text-gray-500 text-sm text-center py-4">No acquisitions yet.</p>
                  ) : (
                    <div className="space-y-1">
                      {acquisitions.map(acq => (
                        <div key={acq.id} className="flex items-center justify-between py-2 px-2 rounded hover:bg-[#090e1c] text-[11px]">
                          <div className="flex items-center gap-3">
                            <span className={`w-2 h-2 rounded-full ${acq.result === 'SUCCESS' ? 'bg-emerald-400' : acq.result === 'FAILURE' ? 'bg-red-400' : 'bg-amber-400'}`} />
                            <span className="text-gray-300">{humanize(acq.source_type)}</span>
                            <span className="text-gray-500">{acq.record_count} records</span>
                            {acq.entities_created > 0 && <span className="text-gray-500">{acq.entities_created} entities</span>}
                          </div>
                          <div className="flex items-center gap-3 text-gray-500">
                            <span>{acq.duration_ms}ms</span>
                            <span>{formatDate(acq.started_at)}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
