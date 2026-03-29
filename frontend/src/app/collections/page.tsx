'use client';
import { useEffect, useState, useCallback, useRef } from 'react';
import Sidebar from '@/components/Sidebar';
import LoadingSpinner from '@/components/LoadingSpinner';
import { useProject } from '@/lib/ProjectContext';
import { collectionsApi, collectionPlansApi, ingestApi, llmApi, CollectionPlan } from '@/lib/api';
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

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
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

  // PIR Assistant state
  const [assistantMessages, setAssistantMessages] = useState<ChatMessage[]>([]);
  const [assistantLoading, setAssistantLoading] = useState(false);
  const [assistantError, setAssistantError] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Structured plan state
  const [planItems, setPlanItems] = useState<PlanItem[]>([]);
  const [planParsing, setPlanParsing] = useState(false);

  // Current active collection being built
  const [activeCollectionId, setActiveCollectionId] = useState<string | null>(null);

  // Unified collection plan state
  const [activePlan, setActivePlan] = useState<CollectionPlan | null>(null);
  const [plans, setPlans] = useState<CollectionPlan[]>([]);
  const [plansLoading, setPlansLoading] = useState(false);

  // Expanded collection cards
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

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
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [assistantMessages]);

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

  function toggleExpanded(id: string) {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function refinePirWithAI() {
    if (!pir.trim() || !activeProject) return;
    const userMsg: ChatMessage = { role: 'user', content: pir.trim() };
    setAssistantMessages(prev => [...prev, userMsg]);
    setPir('');
    if (pirTextareaRef.current) pirTextareaRef.current.style.height = 'auto';
    setAssistantLoading(true);
    setAssistantError(null);
    setPlanItems([]);

    // Create a collection record if we don't have one yet
    let collId = activeCollectionId;
    if (!collId) {
      try {
        const createRes = await collectionsApi.create({
          project_id: activeProject.id,
          pir: pir.trim(),
        });
        collId = createRes.data.id;
        setActiveCollectionId(collId);
      } catch (e) {
        console.error('Failed to create collection', e);
      }
    }

    try {
      const refineResponse = await llmApi.query(
        [{ role: 'user', content: `As an intelligence analyst mentor, help me refine this Priority Intelligence Requirement (PIR). Do NOT answer the question. Instead:

1. ASSESS the PIR: Is it specific enough? Measurable? Time-bounded?
2. IDENTIFY hidden assumptions in the PIR
3. BREAK DOWN into 3-5 more specific sub-questions (Essential Elements of Information)
4. SUGGEST which structured analytic techniques would help (ACH, Key Assumptions Check, etc.)
5. PROPOSE a refined version of the PIR that is more actionable

PIR: ${pir.trim()}` }],
        undefined
      );
      const answer = refineResponse.data?.response || refineResponse.data?.answer || refineResponse.data?.content || JSON.stringify(refineResponse.data);
      const aiMsg: ChatMessage = { role: 'assistant', content: answer };
      setAssistantMessages(prev => [...prev, aiMsg]);

      // Save refinement to collection
      if (collId) {
        try {
          await collectionsApi.update(collId, {
            refined_pir: pir.trim(),
            refinement: answer,
          });
        } catch (e) {
          console.error('Failed to save refinement', e);
        }
      }
    } catch (e) {
      setAssistantError(getErrorMessage(e));
    } finally {
      setAssistantLoading(false);
    }
  }

  async function generateCollectionPlan() {
    if (!pir.trim() || !activeProject) return;
    const pirText = pir.trim();
    const userMsg: ChatMessage = { role: 'user', content: pirText };
    setAssistantMessages(prev => [...prev, userMsg]);
    setPir('');
    if (pirTextareaRef.current) pirTextareaRef.current.style.height = 'auto';
    setAssistantLoading(true);
    setAssistantError(null);
    setPlanItems([]);
    setPlanParsing(true);

    try {
      // Try the unified from-pir endpoint first (LLM refines PIR + generates plan server-side)
      const res = await collectionPlansApi.fromPir({
        project_id: activeProject.id,
        pir: pirText,
        extraction_mode: extractionMode,
      });
      const plan = res.data;
      setActivePlan(plan);

      const llmText = (plan as Record<string, unknown>).llm_plan_text as string || '';
      const hasSources = (plan.sources || []).length > 0;

      if (hasSources && llmText) {
        // Backend LLM worked — show plan text and sources
        const aiMsg: ChatMessage = { role: 'assistant', content: llmText };
        setAssistantMessages(prev => [...prev, aiMsg]);

        const items: PlanItem[] = (plan.sources || []).map((src, i) => ({
          id: i + 1,
          description: src.name,
          source_type: src.source_type,
          status: 'pending',
          approved: true,
        }));
        setPlanItems(items);

        if (plan.refined_pir && plan.refined_pir !== pirText) {
          const refineMsg: ChatMessage = { role: 'assistant', content: `**Refined PIR:** ${plan.refined_pir}` };
          setAssistantMessages(prev => [...prev, refineMsg]);
        }
      } else {
        // Backend LLM unavailable — fall back to client-side LLM call
        const llmRes = await llmApi.query(
          [{ role: 'user', content: pirText }],
          'collection_planning'
        );
        const answer = llmRes.data?.response || llmRes.data?.answer || llmRes.data?.content || JSON.stringify(llmRes.data);
        const aiMsg: ChatMessage = { role: 'assistant', content: answer };
        setAssistantMessages(prev => [...prev, aiMsg]);

        // Parse the plan text into items
        const planRes = await collectionsApi.parsePlan(answer);
        const items: PlanItem[] = (planRes.data.items || []).map((item: PlanItem) => ({
          ...item,
          approved: true,
        }));
        setPlanItems(items);

        // Update the plan with the LLM-generated description
        if (plan.id) {
          try {
            await collectionPlansApi.update(String(plan.id), {
              description: answer,
              refined_pir: pirText,
            } as Partial<CollectionPlan>);
          } catch { /* non-fatal */ }

          // Create sources from parsed items
          for (const item of items) {
            try {
              await collectionPlansApi.addSource(String(plan.id), {
                name: item.description,
                source_type: item.source_type === 'news' ? 'rss_feed'
                  : item.source_type === 'document' ? 'file_upload'
                  : item.source_type === 'social_media' ? 'web_scrape'
                  : item.source_type === 'web_search' ? 'web_scrape'
                  : item.source_type in ['file_upload', 'web_scrape', 'api_feed', 'database', 'rss_feed']
                    ? item.source_type : 'file_upload',
              });
            } catch { /* source type may not be registered */ }
          }

          // Reload the plan to get updated sources
          try {
            const updated = await collectionPlansApi.get(String(plan.id));
            setActivePlan(updated.data);
          } catch { /* non-fatal */ }
        }
      }
    } catch (e) {
      setAssistantError(getErrorMessage(e));
    } finally {
      setAssistantLoading(false);
      setPlanParsing(false);
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

  async function acceptPlan() {
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

        // Execute the plan — activates and triggers acquisition pipeline
        await collectionPlansApi.execute(String(activePlan.id));
      } else if (activeCollectionId) {
        // Legacy fallback
        await collectionsApi.update(activeCollectionId, {
          plan: planItems.filter(i => i.approved),
          status: 'APPROVED',
        });
      }
      setPir('');
      setAssistantMessages([]);
      setPlanItems([]);
      setActiveCollectionId(null);
      setActivePlan(null);
      loadCollections();
      loadPlans();
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  async function createCollection() {
    if (!pir.trim() || !activeProject) return;
    setLoading(true);
    setError(null);
    try {
      await collectionsApi.create({ project_id: activeProject.id, pir: pir.trim() });
      setPir('');
      setAssistantMessages([]);
      setPlanItems([]);
      setActiveCollectionId(null);
      loadCollections();
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

        {/* Section 1: Collection Initiation (Chat Interface) */}
        <section className="max-w-5xl mx-auto">
          <h2 className="text-[10px] font-black tracking-[0.2em] text-[#adc6ff] uppercase mb-4 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#adc6ff] animate-pulse" />
            Collection Initiation
          </h2>

          <div className="bg-[#1a1f2e] rounded p-1">
            <div className="bg-[#090e1c] rounded p-6 space-y-6">
              {/* Chat History */}
              {assistantMessages.length > 0 && (
                <div className="space-y-4 max-h-80 overflow-y-auto">
                  {assistantMessages.map((msg, i) => (
                    msg.role === 'user' ? (
                      <div key={i} className="flex gap-4 max-w-2xl">
                        <div className="w-8 h-8 flex-shrink-0 bg-[#304671] rounded flex items-center justify-center">
                          <span className="material-symbols-outlined text-sm text-[#9fb5e7]">person</span>
                        </div>
                        <div className="bg-[#252a39] p-4 rounded-xl rounded-tl-none border-l-2 border-[#4d8eff]">
                          <p className="text-sm text-gray-200 leading-relaxed italic">&ldquo;{msg.content}&rdquo;</p>
                        </div>
                      </div>
                    ) : (
                      <div key={i} className="flex gap-4 max-w-2xl ml-auto flex-row-reverse">
                        <div className="w-8 h-8 flex-shrink-0 bg-[#df7412] rounded flex items-center justify-center">
                          <span className="material-symbols-outlined text-sm text-[#461f00]">smart_toy</span>
                        </div>
                        <div className="bg-[#2f3444] p-4 rounded-xl rounded-tr-none border-r-2 border-[#ffb786]">
                          <p className="text-sm text-gray-200 leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                        </div>
                      </div>
                    )
                  ))}
                  {assistantLoading && (
                    <div className="flex gap-4 max-w-2xl ml-auto flex-row-reverse">
                      <div className="w-8 h-8 flex-shrink-0 bg-[#df7412] rounded flex items-center justify-center">
                        <span className="material-symbols-outlined text-sm text-[#461f00]">smart_toy</span>
                      </div>
                      <div className="bg-[#2f3444] p-4 rounded-xl rounded-tr-none border-r-2 border-[#ffb786]">
                        <LoadingSpinner size="sm" />
                      </div>
                    </div>
                  )}
                  <div ref={chatEndRef} />
                </div>
              )}

              {assistantError && <p className="text-red-400 text-xs">{assistantError}</p>}

              {/* Input Area */}
              <div className="relative mt-4">
                <textarea
                  ref={pirTextareaRef}
                  value={pir}
                  onChange={(e) => {
                    setPir(e.target.value);
                    const ta = e.target;
                    ta.style.height = 'auto';
                    ta.style.height = `${ta.scrollHeight}px`;
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      if (pir.trim()) createCollection();
                    }
                  }}
                  rows={1}
                  className="w-full bg-[#1a1f2e] border-none focus:ring-1 focus:ring-[#adc6ff] text-sm py-4 pl-4 pr-4 md:pl-6 md:pr-48 rounded font-medium placeholder:text-gray-600 placeholder:italic transition-all resize-none overflow-hidden"
                  placeholder="Enter your Priority Intelligence Requirement..."
                />
                <div className="relative mt-2 flex gap-2 md:absolute md:mt-0 md:right-2 md:top-2 md:bottom-2">
                  <button
                    onClick={refinePirWithAI}
                    disabled={assistantLoading || !pir.trim()}
                    className="bg-[#252a39] hover:bg-[#2f3444] text-[#adc6ff] border border-[#adc6ff]/30 px-3 py-2 md:py-0 rounded text-[10px] font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed uppercase tracking-wider"
                    title={!pir.trim() ? 'Enter a PIR first' : 'Refine your PIR with AI'}
                  >
                    Refine
                  </button>
                  <button
                    onClick={generateCollectionPlan}
                    disabled={assistantLoading || !pir.trim()}
                    className="bg-[#252a39] hover:bg-[#2f3444] text-emerald-400 border border-emerald-500/30 px-3 rounded text-[10px] font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed uppercase tracking-wider"
                    title={!pir.trim() ? 'Enter a PIR first' : 'Generate a collection plan'}
                  >
                    Plan
                  </button>
                  <button
                    onClick={createCollection}
                    disabled={loading || !pir.trim()}
                    className="bg-[#adc6ff] hover:bg-[#4d8eff] text-[#002e6a] px-4 py-2 md:py-0 rounded text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    title={!pir.trim() ? 'Enter a PIR first' : 'Execute collection'}
                  >
                    EXECUTE
                    <span className="material-symbols-outlined text-xs">send</span>
                  </button>
                </div>
              </div>
              {error && <p className="text-red-400 text-xs mt-2">{error}</p>}
              {!pir.trim() && !error && (
                <p className="text-gray-500 text-[10px] mt-2 italic">Enter a Priority Intelligence Requirement above to begin.</p>
              )}
            </div>
          </div>
        </section>

        {/* Section 2: Collection Plan Review */}
        {(planItems.length > 0 || planParsing) && (
          <section className="max-w-5xl mx-auto">
            <div className="flex justify-between items-end mb-4">
              <h2 className="text-[10px] font-black tracking-[0.2em] text-[#adc6ff] uppercase flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-[#ffb786]" />
                Strategic Plan Review
              </h2>
              <span className="text-[10px] font-mono text-gray-500 uppercase tracking-tighter">
                Queue: {String(planItems.length).padStart(2, '0')} tasks pending validation
              </span>
            </div>

            {planParsing ? (
              <div className="flex items-center gap-2 text-xs text-gray-400 p-4">
                <LoadingSpinner size="sm" /> Parsing plan...
              </div>
            ) : (
              <div className="bg-[#161b2a] rounded overflow-x-auto">
                <table className="w-full text-left border-separate border-spacing-y-1 min-w-[600px]">
                  <thead className="bg-[#2f3444]">
                    <tr>
                      <th className="px-6 py-3 text-[10px] font-bold text-gray-400 tracking-widest uppercase">Source Type</th>
                      <th className="px-6 py-3 text-[10px] font-bold text-gray-400 tracking-widest uppercase">Description</th>
                      <th className="px-6 py-3 text-[10px] font-bold text-gray-400 tracking-widest uppercase">Status</th>
                      <th className="px-6 py-3 text-[10px] font-bold text-gray-400 tracking-widest uppercase text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {planItems.map(item => (
                      <tr key={item.id} className="bg-[#1a1f2e] hover:bg-[#343949] transition-colors group">
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-2">
                            <span className="material-symbols-outlined text-xs text-[#adc6ff]">
                              {SOURCE_TYPE_ICONS[item.source_type] || 'description'}
                            </span>
                            <span className="text-xs font-semibold capitalize">{item.source_type.replace('_', ' ')}</span>
                          </div>
                        </td>
                        <td className="px-6 py-4">
                          <span className="text-[11px] text-gray-400">{item.description}</span>
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-2">
                            <span className={`w-1.5 h-1.5 rounded-full ${item.approved ? 'bg-green-400' : 'bg-[#ffb786]'}`} />
                            <span className={`text-[10px] font-bold uppercase ${item.approved ? 'text-green-400' : 'text-[#ffb786]'}`}>
                              {item.approved ? 'Approved' : 'Pending Approval'}
                            </span>
                          </div>
                        </td>
                        <td className="px-6 py-4 text-right">
                          <div className="flex justify-end gap-2 opacity-40 group-hover:opacity-100 transition-opacity">
                            <button onClick={() => togglePlanItem(item.id)} className="p-1 hover:text-green-400 transition-colors">
                              <span className="material-symbols-outlined text-sm">{item.approved ? 'close' : 'check'}</span>
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="p-4 md:p-6 bg-[#161b2a] flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                  <div className="flex gap-4">
                    <div className="flex flex-col">
                      <span className="text-[10px] text-gray-500 uppercase tracking-widest font-bold">Approved Items</span>
                      <span className="text-xs font-mono text-[#adc6ff]">{planItems.filter(i => i.approved).length} of {planItems.length}</span>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button onClick={approveAllPlanItems} className="bg-[#252a39] border border-green-500/30 text-green-400 px-4 py-2 rounded text-[10px] font-bold tracking-widest uppercase hover:bg-green-900/20 transition-all">
                      Approve All
                    </button>
                    <button onClick={rejectAllPlanItems} className="bg-[#252a39] border border-red-500/30 text-red-400 px-4 py-2 rounded text-[10px] font-bold tracking-widest uppercase hover:bg-red-900/20 transition-all">
                      Reject All
                    </button>
                    <button
                      onClick={acceptPlan}
                      disabled={loading || planItems.filter(i => i.approved).length === 0}
                      className="bg-gradient-to-br from-[#adc6ff] to-[#4d8eff] text-[#002e6a] px-8 py-2 rounded text-xs font-black tracking-widest uppercase hover:opacity-90 active:scale-95 transition-all disabled:opacity-50 shadow-[0_0_8px_rgba(173,198,255,0.3)]"
                    >
                      {loading ? 'Creating...' : 'Approve & Execute'}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </section>
        )}

        {/* Section 3: Active Streams */}
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

        {/* Section 4: Active Collection Plans */}
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
                    <div className="p-4 cursor-pointer hover:bg-[#1e2436] transition-colors" onClick={() => toggleExpanded(String(plan.id))}>
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
                              {plan.sources.map(src => (
                                <div key={src.id} className="flex items-center gap-3 bg-[#1a1f2e] rounded px-3 py-2">
                                  <span className="material-symbols-outlined text-xs text-[#adc6ff]">
                                    {SOURCE_TYPE_ICONS[src.source_type] || 'description'}
                                  </span>
                                  <span className="text-xs text-gray-300 capitalize flex-none">{src.source_type.replace('_', ' ')}</span>
                                  <span className="text-[11px] text-gray-400 flex-1">{src.name}</span>
                                  <span className="text-[10px] text-gray-500">{src.total_records_acquired || 0} records</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {plan.status === 'DRAFT' && (
                          <div className="flex gap-2 pt-2">
                            <button
                              onClick={async () => { await collectionPlansApi.execute(String(plan.id)); loadPlans(); }}
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
