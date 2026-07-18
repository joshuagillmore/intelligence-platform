'use client';
import { useEffect, useState, useCallback, useRef } from 'react';
import Sidebar from '@/components/Sidebar';
import LoadingSpinner from '@/components/LoadingSpinner';
import { useProject } from '@/lib/ProjectContext';
import { collectionsApi, collectionPlansApi, ingestApi, llmApi, CollectionPlan, CollectionActivityEntry } from '@/lib/api';
import { getErrorMessage } from '@/lib/errorMessages';

interface Collection {
  id: string;
  pir: string;
  refined_pir?: string;
  refinement?: string;
  plan?: PlanItem[];
  status: string;
  project_id: string;
  documents_acquired?: number;
  progress?: number;
  created_at?: string;
  updated_at?: string;
  results?: unknown;
}

interface PlanItem {
  id: number;
  description: string;
  source_type: string;
  status: string;
  approved: boolean;
}

const EXTRACTION_MODES = [
  { value: 'nlp', label: 'NLP' },
  { value: 'llm', label: 'LLM' },
  { value: 'hybrid', label: 'Hybrid' },
];

const SOURCE_TYPE_ICONS: Record<string, string> = {
  web_search: 'data_exploration',
  web_scrape: 'language',
  news: 'newspaper',
  database: 'account_balance',
  document: 'description',
  social_media: 'forum',
  file_upload: 'upload_file',
  api_feed: 'api',
  rss_feed: 'rss_feed',
  watched_dir: 'folder_open',
};

export default function CollectionsPage() {
  const { activeProject } = useProject();
  const [pir, setPir] = useState('');
  const [collections, setCollections] = useState<Collection[]>([]);
  const [collectionsLoading, setCollectionsLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadContent, setUploadContent] = useState('');
  const [uploadReliability, setUploadReliability] = useState('C3');
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);

  // Step state
  const [step1Open, setStep1Open] = useState(true);
  const [step2Open, setStep2Open] = useState(false);
  const [step3Open, setStep3Open] = useState(false);

  // Refine state
  const [refineLoading, setRefineLoading] = useState(false);
  const [refineError, setRefineError] = useState<string | null>(null);
  const [refinedPir, setRefinedPir] = useState<string | null>(null);
  const [refineAnalysis, setRefineAnalysis] = useState<string | null>(null);

  // Plan state
  const [planLoading, setPlanLoading] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const [planItems, setPlanItems] = useState<PlanItem[]>([]);
  const [activePlan, setActivePlan] = useState<CollectionPlan | null>(null);
  const [plans, setPlans] = useState<CollectionPlan[]>([]);
  const [, setPlansLoading] = useState(false);

  // Expanded collection cards
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  // Activity log
  const [activityLogs, setActivityLogs] = useState<Record<string, CollectionActivityEntry[]>>({});

  // File upload state
  const [fileUploadOpen, setFileUploadOpen] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [fileReliability, setFileReliability] = useState('C3');
  const [extractionMode, setExtractionMode] = useState('hybrid');
  const [fileUploading, setFileUploading] = useState(false);
  const [fileUploadMsg, setFileUploadMsg] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pirTextareaRef = useRef<HTMLTextAreaElement>(null);

  const loadCollections = useCallback(async () => {
    if (!activeProject) return;
    setCollectionsLoading(true);
    try {
      const res = await collectionsApi.list(activeProject.id);
      setCollections(res.data);
    } catch (e) {
      console.error('Failed to load collections', e);
    } finally {
      setCollectionsLoading(false);
    }
  }, [activeProject]);

  const loadPlans = useCallback(async () => {
    if (!activeProject) return;
    setPlansLoading(true);
    try {
      const res = await collectionPlansApi.list(activeProject.id);
      setPlans(res.data);
    } catch (e) {
      console.error('Failed to load plans', e);
    } finally {
      setPlansLoading(false);
    }
  }, [activeProject]);

  useEffect(() => {
    loadCollections();
    loadPlans();
  }, [loadCollections, loadPlans]);

  useEffect(() => {
    const activeTasks = collections.filter(c => {
      const s = c.status?.toUpperCase();
      return s === 'PENDING' || s === 'STARTED' || s === 'PROGRESS' || s === 'RUNNING';
    });
    if (activeTasks.length === 0) return;
    const interval = setInterval(async () => {
      for (const task of activeTasks) {
        try {
          const res = await collectionsApi.status(task.id);
          setCollections(prev => prev.map(c => c.id === task.id ? { ...c, ...res.data } : c));
        } catch { /* ignore polling errors */ }
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [collections]);

  // Poll active plans for status updates
  useEffect(() => {
    const activePlans = plans.filter(p => p.status === 'ACTIVE');
    if (activePlans.length === 0) return;
    const interval = setInterval(async () => {
      loadPlans();
      for (const p of activePlans) {
        try {
          const res = await collectionPlansApi.activity(String(p.id));
          setActivityLogs(prev => ({ ...prev, [String(p.id)]: res.data }));
        } catch { /* ignore */ }
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [plans, loadPlans]);

  // Fetch activity when expanding a plan
  async function loadActivity(planId: string) {
    try {
      const res = await collectionPlansApi.activity(planId);
      setActivityLogs(prev => ({ ...prev, [planId]: res.data }));
    } catch { /* ignore */ }
  }

  function toggleExpanded(id: string) {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function resetWorkflow() {
    setPir('');
    setRefinedPir(null);
    setRefineAnalysis(null);
    setRefineError(null);
    setPlanItems([]);
    setActivePlan(null);
    setPlanError(null);
    setError(null);
    setStep1Open(true);
    setStep2Open(false);
    setStep3Open(false);
  }

  // ---- STEP 1: Refine PIR ----
  async function refinePir() {
    const pirText = pir.trim();
    if (!pirText || !activeProject) return;
    setRefineLoading(true);
    setRefineError(null);
    setRefinedPir(null);
    setRefineAnalysis(null);

    try {
      const res = await llmApi.query(
        [{ role: 'user', content: `As an intelligence analyst mentor, help me refine this Priority Intelligence Requirement (PIR). Do NOT answer the question. Instead:

1. ASSESS the PIR: Is it specific enough? Measurable? Time-bounded?
2. IDENTIFY hidden assumptions in the PIR
3. BREAK DOWN into 3-5 more specific sub-questions (Essential Elements of Information)
4. SUGGEST which structured analytic techniques would help (ACH, Key Assumptions Check, etc.)
5. PROPOSE a refined version of the PIR that is more actionable

PIR: ${pirText}` }],
        undefined
      );
      const answer = res.data?.response || res.data?.answer || res.data?.content || JSON.stringify(res.data);
      setRefineAnalysis(answer);

      // Try to extract refined PIR from the response
      const refinedMatch = answer.match(/(?:refined|revised|improved|proposed)\s*(?:PIR|version)[:\s]*[""]?([^""]+)[""]?/i);
      if (refinedMatch) {
        setRefinedPir(refinedMatch[1].trim());
      }

      // Auto-open step 2
      setStep1Open(false);
      setStep2Open(true);
    } catch (e) {
      setRefineError(getErrorMessage(e));
    } finally {
      setRefineLoading(false);
    }
  }

  // ---- STEP 2: Generate Plan ----
  async function generatePlan() {
    const pirText = refinedPir || pir.trim();
    if (!pirText || !activeProject) return;
    setPlanLoading(true);
    setPlanError(null);
    setPlanItems([]);
    setActivePlan(null);

    try {
      const res = await collectionPlansApi.fromPir({
        project_id: activeProject.id,
        pir: pirText,
        extraction_mode: extractionMode,
      });
      const plan = res.data;
      setActivePlan(plan);

      // Convert plan sources to plan items for approval UI
      const items: PlanItem[] = (plan.sources || []).map((src, i) => ({
        id: i + 1,
        description: src.name,
        source_type: src.source_type,
        status: 'pending',
        approved: true,
      }));
      setPlanItems(items);

      if (plan.refined_pir && !refinedPir) {
        setRefinedPir(plan.refined_pir);
      }
      if (plan.description && !refineAnalysis) {
        setRefineAnalysis(plan.description);
      }

      // Auto-open step 3 if sources were generated
      if (items.length > 0) {
        setStep2Open(false);
        setStep3Open(true);
      }
    } catch (e) {
      setPlanError(getErrorMessage(e));
    } finally {
      setPlanLoading(false);
    }
  }

  function togglePlanItem(itemId: number) {
    setPlanItems(prev => prev.map(item =>
      item.id === itemId ? { ...item, approved: !item.approved } : item
    ));
  }

  function approveAllPlanItems() {
    setPlanItems(prev => prev.map(item => ({ ...item, approved: true })));
  }

  function rejectAllPlanItems() {
    setPlanItems(prev => prev.map(item => ({ ...item, approved: false })));
  }

  // ---- STEP 3: Execute ----
  async function executePlan() {
    if (!activeProject) return;
    setLoading(true);
    setError(null);
    try {
      if (activePlan) {
        // Remove rejected sources before executing
        const rejectedItems = planItems.filter(item => !item.approved);
        for (const item of rejectedItems) {
          const matchingSource = (activePlan.sources || []).find(s => s.name === item.description);
          if (matchingSource) {
            try {
              await collectionPlansApi.deleteSource(String(activePlan.id), String(matchingSource.id));
            } catch { /* source may not exist */ }
          }
        }
        await collectionPlansApi.execute(String(activePlan.id));
      }
      resetWorkflow();
      loadCollections();
      loadPlans();
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  async function uploadDocument() {
    if (!uploadContent.trim() || !activeProject) return;
    setUploading(true);
    setUploadMsg(null);
    try {
      const res = await ingestApi.text(activeProject.id, uploadContent.trim(), uploadReliability);
      const d = res.data;
      const entityCount = d?.entities_created ?? d?.entity_count ?? 0;
      const relCount = d?.relationships_created ?? 0;
      setUploadContent('');
      setUploadMsg(`Document ingested successfully. ${entityCount} entities created, ${relCount} relationships found.`);
      loadCollections();
    } catch (e) {
      setUploadMsg(getErrorMessage(e));
    } finally {
      setUploading(false);
    }
  }

  function handleFileDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const droppedFiles = Array.from(e.dataTransfer.files).filter(f =>
      f.name.endsWith('.pdf') || f.name.endsWith('.txt') || f.name.endsWith('.md')
    );
    if (droppedFiles.length > 0) {
      setSelectedFiles(prev => [...prev, ...droppedFiles]);
    }
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files) {
      setSelectedFiles(prev => [...prev, ...Array.from(e.target.files!)]);
    }
  }

  function removeFile(index: number) {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
  }

  async function uploadFiles() {
    if (selectedFiles.length === 0 || !activeProject) return;
    setFileUploading(true);
    setFileUploadMsg(null);
    try {
      if (selectedFiles.length === 1) {
        const res = await ingestApi.file(activeProject.id, selectedFiles[0], fileReliability, extractionMode);
        const d = res.data;
        setFileUploadMsg(`"${d?.document_name}" ingested. ${d?.entities_created ?? 0} entities created, ${d?.relationships_created ?? 0} relationships, ${d?.chunks ?? 0} chunks.`);
      } else {
        const res = await ingestApi.batch(activeProject.id, selectedFiles, fileReliability, extractionMode);
        const d = res.data;
        setFileUploadMsg(`${d?.documents_processed ?? selectedFiles.length} files ingested. ${d?.total_entities_created ?? 0} entities, ${d?.total_relationships_created ?? 0} relationships.`);
      }
      setSelectedFiles([]);
      if (fileInputRef.current) fileInputRef.current.value = '';
      loadCollections();
    } catch (e) {
      setFileUploadMsg(getErrorMessage(e));
    } finally {
      setFileUploading(false);
    }
  }

  // Derive active streams from collections
  const activeStreams = collections.filter(c => {
    const s = c.status?.toUpperCase();
    return s === 'PENDING' || s === 'STARTED' || s === 'PROGRESS' || s === 'RUNNING';
  });

  const completedCollections = collections.filter(c => {
    const s = c.status?.toUpperCase();
    return s !== 'PENDING' && s !== 'STARTED' && s !== 'PROGRESS' && s !== 'RUNNING';
  });

  // Workflow has started if we have a PIR or any step result
  const workflowActive = pir.trim() || refinedPir || refineAnalysis || activePlan || planItems.length > 0;

  if (!activeProject) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="md:ml-56 flex-1 p-4 pt-16 pb-24 md:p-8 md:pt-8 md:pb-8">
          <h2 className="text-2xl font-bold mb-4">Collections</h2>
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 text-center text-gray-500">
            <p>Select a project first.</p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="flex">
      <Sidebar />
      <main className="md:ml-56 flex-1 p-4 pt-16 pb-24 md:p-8 md:pt-8 md:pb-8 overflow-y-auto h-screen space-y-8">

        {/* Collection Pipeline */}
        <section className="max-w-5xl mx-auto">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-[10px] font-black tracking-[0.2em] text-[#adc6ff] uppercase flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-[#adc6ff] animate-pulse" />
              Collection Pipeline
            </h2>
            {workflowActive && (
              <button onClick={resetWorkflow} className="text-[10px] text-gray-500 hover:text-gray-300 uppercase tracking-wider font-bold transition-colors">
                Reset
              </button>
            )}
          </div>

          <div className="space-y-2">

            {/* ──── STEP 1: REFINE PIR ──── */}
            <div className="bg-[#1a1f2e] border border-[#252a39] rounded overflow-hidden">
              <button
                onClick={() => setStep1Open(!step1Open)}
                className="w-full flex items-center justify-between p-4 text-left hover:bg-[#1e2436] transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-black ${
                    refinedPir || refineAnalysis ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' :
                    refineLoading ? 'bg-[#adc6ff]/20 text-[#adc6ff] border border-[#adc6ff]/30 animate-pulse' :
                    'bg-[#252a39] text-gray-400 border border-[#353a49]'
                  }`}>
                    {refinedPir || refineAnalysis ? <span className="material-symbols-outlined text-xs">check</span> : '1'}
                  </span>
                  <div>
                    <span className="text-[10px] font-bold text-gray-300 uppercase tracking-widest">Refine PIR</span>
                    <p className="text-[10px] text-gray-500 mt-0.5">Enter your intelligence requirement and refine it with AI</p>
                  </div>
                </div>
                <span className="material-symbols-outlined text-sm text-gray-500">
                  {step1Open ? 'expand_less' : 'expand_more'}
                </span>
              </button>

              {step1Open && (
                <div className="border-t border-[#252a39] p-4 md:p-6 space-y-4 bg-[#0d1220]">
                  {/* PIR Input */}
                  <div>
                    <textarea
                      ref={pirTextareaRef}
                      value={pir}
                      onChange={(e) => {
                        setPir(e.target.value);
                        const ta = e.target;
                        ta.style.height = 'auto';
                        ta.style.height = `${ta.scrollHeight}px`;
                      }}
                      rows={2}
                      className="w-full bg-[#1a1f2e] border border-[#353a49] focus:ring-1 focus:ring-[#adc6ff] focus:border-[#adc6ff] text-sm py-3 px-4 rounded font-medium placeholder:text-gray-600 placeholder:italic transition-all resize-none"
                      placeholder="Enter your Priority Intelligence Requirement..."
                    />
                  </div>

                  {/* Refine button */}
                  <div className="flex items-center gap-3">
                    <button
                      onClick={refinePir}
                      disabled={refineLoading || !pir.trim()}
                      className="bg-[#adc6ff] hover:bg-[#4d8eff] text-[#002e6a] px-6 py-2 rounded text-[10px] font-black tracking-widest uppercase transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                      {refineLoading ? (
                        <><LoadingSpinner size="sm" /> Refining...</>
                      ) : (
                        <><span className="material-symbols-outlined text-xs">auto_fix_high</span> Refine with AI</>
                      )}
                    </button>
                    <button
                      onClick={() => { setStep1Open(false); setStep2Open(true); }}
                      disabled={!pir.trim()}
                      className="text-[10px] text-gray-400 hover:text-gray-200 uppercase tracking-wider font-bold transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                      Skip to Plan &rarr;
                    </button>
                  </div>

                  {refineError && <p className="text-red-400 text-xs">{refineError}</p>}

                  {/* Refinement Result */}
                  {refineAnalysis && (
                    <div className="space-y-3">
                      {refinedPir !== null && (
                        <div className="bg-[#1a1f2e] border-l-2 border-emerald-500 rounded p-4">
                          <span className="text-[10px] text-emerald-400 uppercase tracking-widest font-bold block mb-1">
                            Refined PIR <span className="text-gray-500 normal-case font-normal">· editable</span>
                          </span>
                          <textarea
                            value={refinedPir}
                            onChange={(e) => setRefinedPir(e.target.value)}
                            rows={3}
                            className="w-full bg-transparent text-sm text-gray-200 resize-y focus:outline-none focus:ring-1 focus:ring-emerald-500/40 rounded px-1 py-0.5"
                            placeholder="Refined PIR (edit to adjust before generating the plan)"
                          />
                        </div>
                      )}
                      <div className="bg-[#1a1f2e] rounded p-4 max-h-60 overflow-y-auto">
                        <span className="text-[10px] text-gray-500 uppercase tracking-widest font-bold block mb-2">Analysis</span>
                        <p className="text-xs text-gray-400 whitespace-pre-wrap leading-relaxed">{refineAnalysis}</p>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* ──── STEP 2: GENERATE PLAN ──── */}
            <div className={`bg-[#1a1f2e] border border-[#252a39] rounded overflow-hidden transition-opacity ${
              !pir.trim() && !refinedPir ? 'opacity-40 pointer-events-none' : ''
            }`}>
              <button
                onClick={() => setStep2Open(!step2Open)}
                disabled={!pir.trim() && !refinedPir}
                className="w-full flex items-center justify-between p-4 text-left hover:bg-[#1e2436] transition-colors disabled:cursor-not-allowed"
              >
                <div className="flex items-center gap-3">
                  <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-black ${
                    activePlan ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' :
                    planLoading ? 'bg-[#adc6ff]/20 text-[#adc6ff] border border-[#adc6ff]/30 animate-pulse' :
                    'bg-[#252a39] text-gray-400 border border-[#353a49]'
                  }`}>
                    {activePlan ? <span className="material-symbols-outlined text-xs">check</span> : '2'}
                  </span>
                  <div>
                    <span className="text-[10px] font-bold text-gray-300 uppercase tracking-widest">Generate Collection Plan</span>
                    <p className="text-[10px] text-gray-500 mt-0.5">AI generates sources and collection strategy</p>
                  </div>
                </div>
                <span className="material-symbols-outlined text-sm text-gray-500">
                  {step2Open ? 'expand_less' : 'expand_more'}
                </span>
              </button>

              {step2Open && (
                <div className="border-t border-[#252a39] p-4 md:p-6 space-y-4 bg-[#0d1220]">
                  {/* Show what PIR will be used */}
                  <div className="bg-[#1a1f2e] rounded p-3">
                    <span className="text-[10px] text-gray-500 uppercase tracking-widest font-bold block mb-1">PIR to Plan</span>
                    <p className="text-sm text-gray-300">{refinedPir || pir.trim()}</p>
                    {refinedPir && refinedPir !== pir.trim() && (
                      <p className="text-[10px] text-gray-500 mt-1 italic">Using refined version</p>
                    )}
                  </div>

                  <div className="flex items-center gap-3">
                    <button
                      onClick={generatePlan}
                      disabled={planLoading}
                      className="bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 border border-emerald-500/30 px-6 py-2 rounded text-[10px] font-black tracking-widest uppercase transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                      {planLoading ? (
                        <><LoadingSpinner size="sm" /> Generating Plan...</>
                      ) : (
                        <><span className="material-symbols-outlined text-xs">account_tree</span> Generate Plan</>
                      )}
                    </button>
                  </div>

                  {planError && <p className="text-red-400 text-xs">{planError}</p>}

                  {/* Plan Result - show sources table if plan returned but with no sources */}
                  {activePlan && planItems.length === 0 && (
                    <div className="bg-amber-500/10 border border-amber-500/20 rounded p-4">
                      <p className="text-xs text-amber-400">Plan was created but no collection sources were generated. The LLM may have been rate-limited. Try generating again.</p>
                    </div>
                  )}

                  {activePlan && planItems.length > 0 && (
                    <div className="bg-[#161b2a] rounded overflow-x-auto">
                      <table className="w-full text-left border-separate border-spacing-y-1 min-w-[500px]">
                        <thead className="bg-[#2f3444]">
                          <tr>
                            <th className="px-4 py-2 text-[10px] font-bold text-gray-400 tracking-widest uppercase">Source</th>
                            <th className="px-4 py-2 text-[10px] font-bold text-gray-400 tracking-widest uppercase">Description</th>
                            <th className="px-4 py-2 text-[10px] font-bold text-gray-400 tracking-widest uppercase text-right">Include</th>
                          </tr>
                        </thead>
                        <tbody>
                          {planItems.map(item => (
                            <tr key={item.id} className="bg-[#1a1f2e] hover:bg-[#343949] transition-colors group">
                              <td className="px-4 py-3">
                                <div className="flex items-center gap-2">
                                  <span className="material-symbols-outlined text-xs text-[#adc6ff]">
                                    {SOURCE_TYPE_ICONS[item.source_type] || 'description'}
                                  </span>
                                  <span className="text-xs font-semibold capitalize">{item.source_type.replace('_', ' ')}</span>
                                </div>
                              </td>
                              <td className="px-4 py-3">
                                <span className="text-[11px] text-gray-400">{item.description}</span>
                              </td>
                              <td className="px-4 py-3 text-right">
                                <button onClick={() => togglePlanItem(item.id)} className="transition-colors">
                                  <span className={`material-symbols-outlined text-sm ${item.approved ? 'text-emerald-400' : 'text-gray-600'}`}>
                                    {item.approved ? 'check_circle' : 'radio_button_unchecked'}
                                  </span>
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <div className="px-4 py-3 flex justify-between items-center border-t border-[#252a39]">
                        <span className="text-[10px] text-gray-500 font-mono">
                          {planItems.filter(i => i.approved).length}/{planItems.length} selected
                        </span>
                        <div className="flex gap-2">
                          <button onClick={approveAllPlanItems} className="text-[10px] text-emerald-400 hover:text-emerald-300 font-bold uppercase tracking-wider transition-colors">
                            All
                          </button>
                          <span className="text-gray-600">|</span>
                          <button onClick={rejectAllPlanItems} className="text-[10px] text-gray-400 hover:text-gray-300 font-bold uppercase tracking-wider transition-colors">
                            None
                          </button>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Analysis from plan if available */}
                  {activePlan?.description && (
                    <div className="bg-[#1a1f2e] rounded p-4 max-h-40 overflow-y-auto">
                      <span className="text-[10px] text-gray-500 uppercase tracking-widest font-bold block mb-2">Plan Analysis</span>
                      <p className="text-xs text-gray-400 whitespace-pre-wrap leading-relaxed">{activePlan.description}</p>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* ──── STEP 3: EXECUTE ──── */}
            <div className={`bg-[#1a1f2e] border border-[#252a39] rounded overflow-hidden transition-opacity ${
              !activePlan ? 'opacity-40 pointer-events-none' : ''
            }`}>
              <button
                onClick={() => setStep3Open(!step3Open)}
                disabled={!activePlan}
                className="w-full flex items-center justify-between p-4 text-left hover:bg-[#1e2436] transition-colors disabled:cursor-not-allowed"
              >
                <div className="flex items-center gap-3">
                  <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-black ${
                    'bg-[#252a39] text-gray-400 border border-[#353a49]'
                  }`}>
                    3
                  </span>
                  <div>
                    <span className="text-[10px] font-bold text-gray-300 uppercase tracking-widest">Approve & Execute</span>
                    <p className="text-[10px] text-gray-500 mt-0.5">Review and launch the collection plan</p>
                  </div>
                </div>
                <span className="material-symbols-outlined text-sm text-gray-500">
                  {step3Open ? 'expand_less' : 'expand_more'}
                </span>
              </button>

              {step3Open && activePlan && (
                <div className="border-t border-[#252a39] p-4 md:p-6 space-y-4 bg-[#0d1220]">
                  {/* Summary */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="bg-[#1a1f2e] rounded p-3">
                      <span className="text-[10px] text-gray-500 uppercase tracking-widest font-bold block mb-1">PIR</span>
                      <p className="text-xs text-gray-300">{activePlan.refined_pir || activePlan.pir || pir}</p>
                    </div>
                    <div className="bg-[#1a1f2e] rounded p-3">
                      <span className="text-[10px] text-gray-500 uppercase tracking-widest font-bold block mb-1">Sources</span>
                      <p className="text-lg font-black text-[#adc6ff]">{planItems.filter(i => i.approved).length}</p>
                      <p className="text-[10px] text-gray-500">of {planItems.length} approved</p>
                    </div>
                    <div className="bg-[#1a1f2e] rounded p-3">
                      <span className="text-[10px] text-gray-500 uppercase tracking-widest font-bold block mb-1">Status</span>
                      <p className="text-xs text-amber-400 font-bold uppercase">Awaiting Approval</p>
                    </div>
                  </div>

                  {error && <p className="text-red-400 text-xs">{error}</p>}

                  <div className="flex gap-3">
                    <button
                      onClick={executePlan}
                      disabled={loading || planItems.filter(i => i.approved).length === 0}
                      className="bg-gradient-to-br from-[#adc6ff] to-[#4d8eff] text-[#002e6a] px-8 py-2.5 rounded text-xs font-black tracking-widest uppercase hover:opacity-90 active:scale-95 transition-all disabled:opacity-50 shadow-[0_0_8px_rgba(173,198,255,0.3)] flex items-center gap-2"
                    >
                      {loading ? (
                        <><LoadingSpinner size="sm" /> Executing...</>
                      ) : (
                        <><span className="material-symbols-outlined text-sm">rocket_launch</span> Approve & Execute</>
                      )}
                    </button>
                    <button
                      onClick={resetWorkflow}
                      className="bg-red-500/10 border border-red-500/20 text-red-400 px-4 py-2 rounded text-[10px] font-bold uppercase tracking-wider hover:bg-red-900/20 transition-all"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>

          </div>
        </section>

        {/* Active Streams */}
        {activeStreams.length > 0 && (
          <section className="max-w-5xl mx-auto">
            <h2 className="text-[10px] font-black tracking-[0.2em] text-[#adc6ff] uppercase mb-4 flex items-center gap-2">
              <span className="material-symbols-outlined text-sm">sync</span>
              Active Streams
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {activeStreams.map((col) => {
                const progress = col.progress != null
                  ? Math.round(col.progress * 100)
                  : col.status?.toUpperCase() === 'STARTED' ? 5
                  : col.status?.toUpperCase() === 'PENDING' ? 0
                  : 10;
                return (
                  <div key={col.id} className="bg-[#1a1f2e] p-6 rounded relative overflow-hidden group">
                    <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                      <span className="material-symbols-outlined text-6xl">lan</span>
                    </div>
                    <div className="relative z-10 flex flex-col h-full justify-between gap-6">
                      <div className="flex justify-between items-start">
                        <div>
                          <h3 className="text-sm font-bold text-gray-200">{col.pir.substring(0, 60)}{col.pir.length > 60 ? '...' : ''}</h3>
                          <p className="text-[10px] text-gray-500 font-mono mt-1">ID: {col.id.substring(0, 16)}</p>
                        </div>
                        <span className="text-xs font-black text-[#adc6ff]">{progress}%</span>
                      </div>
                      <div>
                        <div className="w-full h-1.5 bg-[#2f3444] rounded-full overflow-hidden mb-3">
                          <div
                            className="h-full bg-gradient-to-r from-[#adc6ff] to-[#4d8eff] relative shadow-[0_0_8px_rgba(173,198,255,0.3)]"
                            style={{ width: `${progress}%` }}
                          >
                            <div className="absolute right-0 top-0 bottom-0 w-1 bg-white/40 blur-[2px]" />
                          </div>
                        </div>
                        <div className="flex justify-between text-[10px] font-bold tracking-widest uppercase">
                          <span className="text-gray-400">{col.status}</span>
                          <span className="text-[#ffb786]">Processing...</span>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* Collection Plans */}
        {plans.length > 0 && (
          <section className="max-w-5xl mx-auto">
            <h2 className="text-[10px] font-black tracking-[0.2em] text-[#adc6ff] uppercase mb-4 flex items-center gap-2">
              <span className="material-symbols-outlined text-sm">assignment</span>
              Collection Plans
              <span className="text-gray-500 font-mono ml-2">({plans.length})</span>
            </h2>
            <div className="space-y-2">
              {plans.map(plan => {
                const statusColor = plan.status === 'ACTIVE' ? 'bg-emerald-500/20 text-emerald-400'
                  : plan.status === 'COMPLETED' ? 'bg-blue-500/20 text-blue-400'
                  : plan.status === 'DRAFT' ? 'bg-gray-500/20 text-gray-400'
                  : plan.status === 'PAUSED' ? 'bg-amber-500/20 text-amber-400'
                  : 'bg-gray-600/20 text-gray-500';
                const isExpanded = expandedIds.has(String(plan.id));
                return (
                  <div key={plan.id} className="bg-[#1a1f2e] border border-[#252a39] rounded overflow-hidden">
                    <div className="p-4 cursor-pointer hover:bg-[#1e2436] transition-colors" onClick={() => { toggleExpanded(String(plan.id)); loadActivity(String(plan.id)); }}>
                      <div className="flex items-start justify-between">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-gray-300 truncate">{plan.pir || plan.name}</p>
                          {plan.refined_pir && plan.refined_pir !== plan.pir && (
                            <p className="text-[10px] text-[#adc6ff] mt-1 truncate">Refined: {plan.refined_pir}</p>
                          )}
                          <div className="flex items-center gap-3 mt-2">
                            <span className="text-[10px] text-gray-500 font-mono">{plan.created_at ? new Date(plan.created_at).toLocaleString() : ''}</span>
                            <span className="text-[10px] text-gray-500">{plan.source_count || 0} sources</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 ml-3 flex-none">
                          <span className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-wider ${statusColor}`}>
                            {plan.status}
                          </span>
                          <span className="material-symbols-outlined text-sm text-gray-500">
                            {isExpanded ? 'expand_less' : 'expand_more'}
                          </span>
                        </div>
                      </div>
                    </div>

                    {isExpanded && (
                      <div className="border-t border-[#252a39] p-4 space-y-3 bg-[#0d1220]">
                        {plan.description && (
                          <div>
                            <span className="text-[10px] text-gray-500 uppercase tracking-widest font-bold block mb-1">Analysis</span>
                            <p className="text-xs text-gray-400 whitespace-pre-wrap max-h-40 overflow-y-auto">{plan.description}</p>
                          </div>
                        )}
                        {plan.sources && plan.sources.length > 0 && (
                          <div>
                            <span className="text-[10px] text-gray-500 uppercase tracking-widest font-bold block mb-1">Sources ({plan.sources.length})</span>
                            <div className="space-y-1">
                              {plan.sources.map(src => {
                                const cs = src.collection_status || 'pending';
                                const statusIcon = cs === 'succeeded' ? 'check_circle'
                                  : cs === 'failed' ? 'error'
                                  : cs === 'collecting' ? 'sync'
                                  : cs === 'queued' ? 'schedule'
                                  : cs === 'awaiting_upload' ? 'upload_file'
                                  : 'radio_button_unchecked';
                                const statusColor = cs === 'succeeded' ? 'text-emerald-400'
                                  : cs === 'failed' ? 'text-red-400'
                                  : cs === 'collecting' ? 'text-[#adc6ff] animate-spin'
                                  : cs === 'queued' ? 'text-amber-400'
                                  : cs === 'awaiting_upload' ? 'text-orange-400'
                                  : 'text-gray-500';
                                return (
                                  <div key={src.id} className="flex items-center gap-3 bg-[#1a1f2e] rounded px-3 py-2">
                                    <span className="material-symbols-outlined text-xs text-[#adc6ff]">
                                      {SOURCE_TYPE_ICONS[src.source_type] || 'description'}
                                    </span>
                                    <span className="text-xs text-gray-300 capitalize flex-none w-20">{src.source_type.replace('_', ' ')}</span>
                                    <span className="text-[11px] text-gray-400 flex-1 truncate">{src.name}</span>
                                    <div className="flex items-center gap-1.5 flex-none">
                                      <span className={`material-symbols-outlined text-xs ${statusColor}`}>{statusIcon}</span>
                                      <span className={`text-[10px] font-bold uppercase ${statusColor.replace(' animate-spin', '')}`}>
                                        {cs.replace('_', ' ')}
                                      </span>
                                    </div>
                                    {src.total_records_acquired > 0 && (
                                      <span className="text-[10px] text-gray-500 flex-none">{src.total_records_acquired} rec</span>
                                    )}
                                    {cs === 'failed' && src.last_error && (
                                      <span className="text-[10px] text-red-400/70 truncate max-w-[150px]" title={src.last_error}>{src.last_error}</span>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        {/* Activity Log */}
                        {activityLogs[String(plan.id)] && activityLogs[String(plan.id)].length > 0 && (
                          <div>
                            <span className="text-[10px] text-gray-500 uppercase tracking-widest font-bold block mb-1">Activity Log</span>
                            <div className="bg-[#1a1f2e] rounded p-3 max-h-40 overflow-y-auto space-y-1 font-mono">
                              {activityLogs[String(plan.id)].map(a => {
                                const eventColor = a.event.includes('failed') ? 'text-red-400'
                                  : a.event.includes('fetched') || a.event.includes('succeeded') || a.event.includes('completed') ? 'text-emerald-400'
                                  : a.event.includes('fetching') || a.event.includes('collecting') ? 'text-[#adc6ff]'
                                  : a.event.includes('started') ? 'text-amber-400'
                                  : 'text-gray-500';
                                return (
                                  <div key={a.id} className="flex items-start gap-2 text-[10px]">
                                    <span className="text-gray-600 flex-none whitespace-nowrap">
                                      {new Date(a.created_at).toLocaleTimeString()}
                                    </span>
                                    <span className={`${eventColor} flex-none uppercase font-bold w-24`}>
                                      {({ url_fetching: 'fetching', url_fetched: 'fetched', url_failed: 'failed' }[a.event])
                                        || a.event.replace('source_', '').replace('plan_', '')}
                                    </span>
                                    <span className="text-gray-400">{a.message}</span>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        {plan.status === 'DRAFT' && (
                          <div className="flex gap-2 pt-2">
                            <button
                              onClick={async () => { await collectionPlansApi.execute(String(plan.id)); loadPlans(); loadActivity(String(plan.id)); }}
                              className="bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 px-4 py-2 rounded text-[10px] font-bold uppercase tracking-wider hover:bg-emerald-900/30 transition-all"
                            >
                              Approve & Execute
                            </button>
                            <button
                              onClick={async () => { await collectionPlansApi.delete(String(plan.id)); loadPlans(); }}
                              className="bg-red-500/10 border border-red-500/20 text-red-400 px-4 py-2 rounded text-[10px] font-bold uppercase tracking-wider hover:bg-red-900/20 transition-all"
                            >
                              Delete
                            </button>
                          </div>
                        )}
                        <div className="flex items-center gap-4 text-[10px] text-gray-500 font-mono pt-2 border-t border-[#252a39]">
                          <span>ID: {plan.id}</span>
                          {plan.updated_at && <span>Updated: {new Date(plan.updated_at).toLocaleString()}</span>}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* File Upload Section */}
        <section className="max-w-5xl mx-auto">
          <div className="bg-navy-800 border border-navy-600 rounded-lg">
            <button
              onClick={() => setFileUploadOpen(!fileUploadOpen)}
              className="w-full flex items-center justify-between p-4 text-left"
            >
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-sm text-gray-400">upload_file</span>
                <h3 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">File Upload (PDF, TXT, MD)</h3>
              </div>
              <span className="text-gray-500 text-xs">{fileUploadOpen ? '\u25B2' : '\u25BC'}</span>
            </button>
            {fileUploadOpen && (
              <div className="px-6 pb-6">
                <div
                  onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={handleFileDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
                    dragOver
                      ? 'border-[#adc6ff] bg-[#adc6ff]/10'
                      : 'border-navy-600 hover:border-navy-500 hover:bg-navy-700/50'
                  }`}
                >
                  <span className="material-symbols-outlined text-3xl text-gray-400 mb-2 block">cloud_upload</span>
                  <p className="text-sm text-gray-400">Drag and drop files here, or click to browse</p>
                  <p className="text-xs text-gray-500 mt-1">Accepted: PDF, TXT, MD</p>
                  <input ref={fileInputRef} type="file" multiple accept=".pdf,.txt,.md" onChange={handleFileSelect} className="hidden" />
                </div>

                {selectedFiles.length > 0 && (
                  <div className="mt-3 space-y-1">
                    {selectedFiles.map((file, i) => (
                      <div key={i} className="flex items-center justify-between bg-navy-700 rounded px-3 py-2 text-xs">
                        <span className="text-gray-300 truncate flex-1">{file.name}</span>
                        <span className="text-gray-500 mx-2">{(file.size / 1024).toFixed(1)} KB</span>
                        <button onClick={() => removeFile(i)} className="text-red-400 hover:text-red-300 ml-2">x</button>
                      </div>
                    ))}
                  </div>
                )}

                <div className="flex items-center gap-4 mt-3 flex-wrap">
                  <div className="flex items-center gap-2">
                    <label className="text-xs text-gray-400">Reliability:</label>
                    <select value={fileReliability} onChange={(e) => setFileReliability(e.target.value)}
                      className="bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs focus:outline-none focus:border-[#adc6ff]">
                      <option value="A1">A1 - Reliable, Confirmed</option>
                      <option value="B2">B2 - Usually Reliable, Probably True</option>
                      <option value="C3">C3 - Fairly Reliable, Possibly True</option>
                      <option value="D4">D4 - Not Usually Reliable, Doubtful</option>
                      <option value="E5">E5 - Unreliable, Improbable</option>
                      <option value="F6">F6 - Cannot Be Judged</option>
                    </select>
                  </div>
                  <div className="flex items-center gap-2">
                    <label className="text-xs text-gray-400">Extraction Mode:</label>
                    <select value={extractionMode} onChange={(e) => setExtractionMode(e.target.value)}
                      className="bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs focus:outline-none focus:border-[#adc6ff]">
                      {EXTRACTION_MODES.map(m => (<option key={m.value} value={m.value}>{m.label}</option>))}
                    </select>
                  </div>
                  <button onClick={uploadFiles} disabled={fileUploading || selectedFiles.length === 0}
                    className="bg-[#adc6ff] hover:bg-[#4d8eff] text-[#002e6a] px-4 py-2 rounded text-sm font-bold disabled:opacity-50 transition-colors">
                    {fileUploading ? 'Uploading...' : `Upload ${selectedFiles.length > 0 ? `(${selectedFiles.length})` : ''}`}
                  </button>
                </div>
                {fileUploadMsg && (
                  <p className={`text-xs mt-2 ${fileUploadMsg.includes('ingested') || fileUploadMsg.includes('success') ? 'text-green-400' : 'text-red-400'}`}>
                    {fileUploadMsg}
                  </p>
                )}
              </div>
            )}
          </div>
        </section>

        {/* Manual Text Upload */}
        <section className="max-w-5xl mx-auto">
          <div className="bg-navy-800 border border-navy-600 rounded-lg">
            <button onClick={() => setUploadOpen(!uploadOpen)} className="w-full flex items-center justify-between p-4 text-left">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-sm text-gray-400">edit_note</span>
                <h3 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Manual Text Upload</h3>
              </div>
              <span className="text-gray-500 text-xs">{uploadOpen ? '\u25B2' : '\u25BC'}</span>
            </button>
            {uploadOpen && (
              <div className="px-6 pb-6">
                <textarea value={uploadContent} onChange={(e) => setUploadContent(e.target.value)}
                  placeholder="Paste document text here for ingestion and entity extraction..."
                  className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm h-40 focus:outline-none focus:border-[#adc6ff] resize-none font-mono" />
                <div className="flex items-center gap-4 mt-3">
                  <div className="flex items-center gap-2">
                    <label className="text-xs text-gray-400">Reliability:</label>
                    <select value={uploadReliability} onChange={(e) => setUploadReliability(e.target.value)}
                      className="bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs focus:outline-none focus:border-[#adc6ff]">
                      <option value="A1">A1 - Reliable, Confirmed</option>
                      <option value="C3">C3 - Fairly Reliable, Possibly True</option>
                      <option value="F6">F6 - Cannot Be Judged</option>
                    </select>
                  </div>
                  <button onClick={uploadDocument} disabled={uploading || !uploadContent.trim()}
                    className="bg-[#adc6ff] hover:bg-[#4d8eff] text-[#002e6a] px-4 py-2 rounded text-sm font-bold disabled:opacity-50 transition-colors">
                    {uploading ? 'Uploading...' : 'Upload Document'}
                  </button>
                </div>
                {uploadMsg && (
                  <p className={`text-xs mt-2 ${uploadMsg.includes('success') ? 'text-green-400' : 'text-red-400'}`}>{uploadMsg}</p>
                )}
              </div>
            )}
          </div>
        </section>

        {/* Collection History */}
        <section className="max-w-5xl mx-auto pb-12">
          <h2 className="text-[10px] font-black tracking-[0.2em] text-[#adc6ff] uppercase mb-4 flex items-center gap-2">
            <span className="material-symbols-outlined text-sm">history</span>
            Collection History
            <span className="text-gray-500 font-mono ml-2">({collections.length})</span>
          </h2>
          {collectionsLoading ? (
            <LoadingSpinner />
          ) : completedCollections.length === 0 ? (
            <div className="bg-[#1a1f2e] border border-[#252a39] rounded p-8 text-center text-gray-500 text-sm">
              No collection history yet. Create a PIR above to get started.
            </div>
          ) : (
            <div className="space-y-2">
              {completedCollections.map((col) => {
                const isExpanded = expandedIds.has(col.id);
                const statusColor = col.status?.toUpperCase() === 'SUCCESS' || col.status?.toUpperCase() === 'COMPLETED'
                  ? 'bg-green-900/30 text-green-400'
                  : col.status?.toUpperCase() === 'APPROVED'
                  ? 'bg-blue-900/30 text-blue-400'
                  : col.status?.toUpperCase() === 'REVOKED'
                  ? 'bg-red-900/30 text-red-400'
                  : 'bg-gray-900/30 text-gray-400';

                return (
                  <div key={col.id} className="bg-[#1a1f2e] border border-[#252a39] rounded overflow-hidden">
                    <div
                      className="p-4 cursor-pointer hover:bg-[#1e2436] transition-colors"
                      onClick={() => toggleExpanded(col.id)}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-gray-300 truncate">{col.pir}</p>
                          {col.refined_pir && (
                            <p className="text-[10px] text-[#adc6ff] mt-1 truncate">Refined: {col.refined_pir}</p>
                          )}
                          <div className="flex items-center gap-3 mt-2">
                            {col.created_at && (
                              <span className="text-[10px] text-gray-500 font-mono">{new Date(col.created_at).toLocaleString()}</span>
                            )}
                            {col.plan && col.plan.length > 0 && (
                              <span className="text-[10px] text-gray-500">{col.plan.length} plan items</span>
                            )}
                            {(col.documents_acquired ?? 0) > 0 && (
                              <span className="text-[10px] text-gray-500">{col.documents_acquired} docs</span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-2 ml-3 flex-none">
                          <span className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-wider ${statusColor}`}>
                            {col.status}
                          </span>
                          <span className="material-symbols-outlined text-sm text-gray-500">
                            {isExpanded ? 'expand_less' : 'expand_more'}
                          </span>
                        </div>
                      </div>
                    </div>

                    {isExpanded && (
                      <div className="border-t border-[#252a39] p-4 space-y-4 bg-[#0d1220]">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                          <div>
                            <span className="text-[10px] text-gray-500 uppercase tracking-widest font-bold block mb-1">PIR</span>
                            <p className="text-gray-300 whitespace-pre-wrap">{col.pir}</p>
                          </div>
                          {col.refined_pir && (
                            <div>
                              <span className="text-[10px] text-gray-500 uppercase tracking-widest font-bold block mb-1">Refined PIR</span>
                              <p className="text-gray-300 whitespace-pre-wrap">{col.refined_pir}</p>
                            </div>
                          )}
                        </div>

                        {col.refinement && (
                          <div>
                            <span className="text-[10px] text-gray-500 uppercase tracking-widest font-bold block mb-1">LLM Refinement</span>
                            <div className="bg-[#1a1f2e] rounded p-3 max-h-60 overflow-y-auto">
                              <p className="text-xs text-gray-400 whitespace-pre-wrap leading-relaxed">{col.refinement}</p>
                            </div>
                          </div>
                        )}

                        {col.plan && col.plan.length > 0 && (
                          <div>
                            <span className="text-[10px] text-gray-500 uppercase tracking-widest font-bold block mb-1">Collection Plan</span>
                            <div className="space-y-1">
                              {col.plan.map((item, i) => (
                                <div key={i} className="flex items-center gap-3 bg-[#1a1f2e] rounded px-3 py-2">
                                  <span className="material-symbols-outlined text-xs text-[#adc6ff]">
                                    {SOURCE_TYPE_ICONS[item.source_type] || 'description'}
                                  </span>
                                  <span className="text-xs text-gray-300 capitalize flex-none">{(item.source_type || '').replace('_', ' ')}</span>
                                  <span className="text-[11px] text-gray-400 flex-1">{item.description}</span>
                                  <span className={`text-[10px] font-bold uppercase ${item.approved ? 'text-green-400' : 'text-gray-500'}`}>
                                    {item.approved ? 'approved' : 'rejected'}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        <div className="flex items-center gap-4 text-[10px] text-gray-500 font-mono pt-2 border-t border-[#252a39]">
                          <span>ID: {col.id}</span>
                          {col.updated_at && <span>Updated: {new Date(col.updated_at).toLocaleString()}</span>}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
