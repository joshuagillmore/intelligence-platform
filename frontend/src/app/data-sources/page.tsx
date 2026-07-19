/* eslint-disable @typescript-eslint/no-explicit-any */
'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/Sidebar';
import LoadingSpinner from '@/components/LoadingSpinner';
import TopicMindMap from '@/components/TopicMindMap';
import MindMapControls from '@/components/MindMapControls';
import type { LayoutMode, ClusteringMethod, Granularity } from '@/components/MindMapControls';
import HighlightedExcerpt from '@/components/HighlightedExcerpt';
import { useRouter } from 'next/navigation';
import { useProject } from '@/lib/ProjectContext';
import { topicsApi, queryApi } from '@/lib/api';
import { getErrorMessage } from '@/lib/errorMessages';
import Markdown from '@/components/Markdown';

/* -- Types ------------------------------------------------------------ */

interface TreeNode {
  name: string;
  id: string;
  entity_type?: string;
  count?: number;
  children?: TreeNode[];
}

interface RelevantExcerpt {
  text: string;
  score: number;
  matched_keywords: string[];
}

interface SourceDocument {
  id: string;
  name: string;
  content?: string;
  reliability?: string;
  relevant_excerpts?: RelevantExcerpt[];
  keyword_matches?: Record<string, number>;
  relevance_score?: number;
}

interface ConnectedEntity {
  id: string;
  name: string;
  entity_type: string;
  rel_type: string;
  confidence?: number;
}

interface DocumentExcerpt {
  name: string;
  content: string;
}

interface EntityContext {
  entity: { id: string; name: string; entity_type: string; properties?: Record<string, unknown> };
  connected_entities?: ConnectedEntity[];
  source_documents?: SourceDocument[];
  document_excerpts?: DocumentExcerpt[];
  keywords?: string[];
}

interface CrossReference {
  doc_id: string;
  doc_name: string;
  topic_ids: string[];
}

interface ConversationMessage {
  role: 'user' | 'assistant';
  content: string;
}

/* -- Helpers ---------------------------------------------------------- */

const reliabilityColor = (r?: string) => {
  if (!r) return 'bg-gray-800 text-gray-400 border-gray-600';
  const letter = r.charAt(0).toUpperCase();
  switch (letter) {
    case 'A': return 'bg-green-900/40 text-green-300 border-green-700/50';
    case 'B': return 'bg-emerald-900/40 text-emerald-300 border-emerald-700/50';
    case 'C': return 'bg-yellow-900/40 text-yellow-300 border-yellow-700/50';
    case 'D': return 'bg-orange-900/40 text-orange-300 border-orange-700/50';
    case 'E': return 'bg-red-900/40 text-red-300 border-red-700/50';
    case 'F': return 'bg-gray-900/40 text-gray-300 border-gray-700/50';
    default: return 'bg-gray-800 text-gray-400 border-gray-600';
  }
};

const entityTypeColor = (type: string) => {
  const t = type?.toLowerCase() || '';
  if (t.includes('person') || t.includes('people')) return 'bg-purple-900/40 text-purple-300 border-purple-700/50';
  if (t.includes('org')) return 'bg-blue-900/40 text-blue-300 border-blue-700/50';
  if (t.includes('location') || t.includes('place') || t.includes('geo')) return 'bg-green-900/40 text-green-300 border-green-700/50';
  if (t.includes('event')) return 'bg-yellow-900/40 text-yellow-300 border-yellow-700/50';
  if (t.includes('threat') || t.includes('malware') || t.includes('vulnerability')) return 'bg-red-900/40 text-red-300 border-red-700/50';
  return 'bg-gray-900/40 text-gray-300 border-gray-700/50';
};

function getStoredLayout(): LayoutMode {
  if (typeof window === 'undefined') return 'radial';
  return (localStorage.getItem('mindmap-layout') as LayoutMode) || 'radial';
}

/* -- Component -------------------------------------------------------- */

export default function DataSourcesPage() {
  const { activeProject } = useProject();
  const router = useRouter();
  // Mind map tree data
  const [topicTree, setTopicTree] = useState<TreeNode>({ name: 'Knowledge Base', id: 'root', children: [] });
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [crossReferences, setCrossReferences] = useState<CrossReference[]>([]);

  // Layout
  const [layout, setLayout] = useState<LayoutMode>('radial');
  const [searchQuery, setSearchQuery] = useState('');
  const [breadcrumbs, setBreadcrumbs] = useState<{ id: string; name: string }[]>([]);
  const [focusMode, setFocusMode] = useState(false);

  // Selected node
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedNodeName, setSelectedNodeName] = useState<string | null>(null);

  // Entity context
  const [entityContext, setEntityContext] = useState<EntityContext | null>(null);
  const [contextLoading, setContextLoading] = useState(false);

  // LLM summary (progressive)
  const [summary, setSummary] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryCache, setSummaryCache] = useState<Record<string, string>>({});

  // Keywords
  const [keywords, setKeywords] = useState<string[]>([]);

  // Conversation history per topic
  const [conversation, setConversation] = useState<ConversationMessage[]>([]);

  // Query input
  const [queryInput, setQueryInput] = useState('');
  const [queryLoading, setQueryLoading] = useState(false);

  // Expanded documents
  const [expandedDocs, setExpandedDocs] = useState<Set<string>>(new Set());

  // Clustering controls
  const [clusteringMethod, setClusteringMethod] = useState<ClusteringMethod>('tfidf');
  const [granularity, setGranularity] = useState<Granularity>('medium');

  // Load stored layout preference
  useEffect(() => {
    setLayout(getStoredLayout());
  }, []);

  /* -- Load topic tree ------------------------------------------------ */

  const loadTopics = useCallback(async () => {
    if (!activeProject) return;
    setLoading(true);
    setLoadError(null);
    try {
      const res = await topicsApi.tree(activeProject.id, clusteringMethod, granularity);
      const data = res.data;

      if (data && typeof data === 'object' && !Array.isArray(data) && data.children) {
        setTopicTree(data);
        setCrossReferences(data.cross_references || []);
      } else if (Array.isArray(data)) {
        const grouped: Record<string, TreeNode[]> = {};
        for (const entity of data) {
          const type = entity.entity_type || 'Unknown';
          if (!grouped[type]) grouped[type] = [];
          grouped[type].push({ name: entity.name, id: entity.id, entity_type: entity.entity_type });
        }
        setTopicTree({
          name: 'Knowledge Base',
          id: 'root',
          children: Object.entries(grouped).map(([type, entities]) => ({
            name: type,
            id: `branch-${type.toLowerCase().replace(/\s+/g, '-')}`,
            count: entities.length,
            children: entities,
          })),
        });
      } else {
        setTopicTree({ name: 'Knowledge Base', id: 'root', children: [] });
      }
    } catch (e) {
      console.error('Failed to load topics', e);
      setLoadError(getErrorMessage(e));
      setTopicTree({ name: 'Knowledge Base', id: 'root', children: [] });
    } finally {
      setLoading(false);
    }
  }, [activeProject, clusteringMethod, granularity]);

  useEffect(() => {
    loadTopics();
  }, [loadTopics]);

  /* -- Auto-generate summary ------------------------------------------ */

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const generateSummary = useCallback(async (nodeId: string, nodeName: string, _ctx: EntityContext | null) => {
    if (!activeProject || !nodeName) return;

    // Check cache first
    if (summaryCache[nodeId]) {
      setSummary(summaryCache[nodeId]);
      return;
    }

    setSummaryLoading(true);
    setSummary(null);
    try {
      const url = topicsApi.summarizeUrl(nodeId);
      const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ project_id: activeProject.id, level: 'topic' }),
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let fullText = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        // Parse SSE events
        for (const line of chunk.split('\n')) {
          if (line.startsWith('data: ')) {
            const payload = line.slice(6);
            if (payload === '[DONE]') break;
            fullText += payload;
            setSummary(fullText);
          }
        }
      }

      if (fullText) {
        setSummaryCache((prev: Record<string, string>) => ({ ...prev, [nodeId]: fullText }));
        setConversation([{ role: 'assistant', content: fullText }]);
      } else {
        setSummary('No summary content returned.');
      }
    } catch {
      setSummary('Unable to generate summary at this time.');
    } finally {
      setSummaryLoading(false);
    }
  }, [activeProject, summaryCache]);

  /* -- Handle node click ---------------------------------------------- */

  const handleTopicClick = useCallback(async (node: TreeNode) => {
    if (!activeProject) return;

    setSelectedNodeId(node.id);
    setSelectedNodeName(node.name);
    setEntityContext(null);
    setQueryInput('');
    setKeywords([]);
    setExpandedDocs(new Set());
    setConversation([]);

    // Check summary cache
    if (summaryCache[node.id]) {
      setSummary(summaryCache[node.id]);
    } else {
      setSummary(null);
    }

    const isGroupingNode = node.id === 'root' || node.id.startsWith('branch-')
      || node.id.startsWith('type-') || node.id.startsWith('cat-')
      || node.id.startsWith('geo-') || node.id.startsWith('actors-')
      || node.id.startsWith('theme-') || node.entity_type === 'sub_category'
      || node.entity_type === 'category' || node.entity_type === 'region';
    if (isGroupingNode) return;

    setContextLoading(true);
    try {
      const res = await topicsApi.context(node.id, activeProject.id);
      const data = res.data;
      if (data.documents && !data.source_documents) {
        data.source_documents = data.documents;
      }
      setEntityContext(data);
      setKeywords(data.keywords || []);

      // Summary is now generated on-demand via button, not auto-generated
    } catch (e) {
      console.error('Failed to load entity context', e);
      setEntityContext({
        entity: { id: node.id, name: node.name, entity_type: node.entity_type || 'Unknown' },
        connected_entities: [],
        source_documents: [],
      });
    } finally {
      setContextLoading(false);
    }
  }, [activeProject, summaryCache]);

  /* -- Ask about selected topic --------------------------------------- */

  async function askAboutTopic() {
    if (!queryInput.trim() || !activeProject || !selectedNodeName) return;
    setQueryLoading(true);
    const userMessage = queryInput;
    setQueryInput('');

    // Add user message to conversation
    setConversation((prev: ConversationMessage[]) => [...prev, { role: 'user', content: userMessage }]);

    try {
      const scopedQuery = `Regarding "${selectedNodeName}": ${userMessage}`;
      const res = await queryApi.rag(activeProject.id, scopedQuery);
      const answer = res.data.answer || res.data.response || JSON.stringify(res.data);
      setConversation((prev: ConversationMessage[]) => [...prev, { role: 'assistant', content: answer }]);
    } catch {
      setConversation((prev: ConversationMessage[]) => [...prev, { role: 'assistant', content: 'Failed to process query.' }]);
    } finally {
      setQueryLoading(false);
    }
  }

  /* -- Layout controls ------------------------------------------------ */

  const handleLayoutChange = useCallback((mode: LayoutMode) => {
    setLayout(mode);
    localStorage.setItem('mindmap-layout', mode);
  }, []);

  const handleZoomIn = useCallback(() => {
    const el = document.querySelector('[data-mindmap-svg]') as any;
    el?.__zoomIn?.();
  }, []);

  const handleZoomOut = useCallback(() => {
    const el = document.querySelector('[data-mindmap-svg]') as any;
    el?.__zoomOut?.();
  }, []);

  const handleZoomReset = useCallback(() => {
    const el = document.querySelector('[data-mindmap-svg]') as any;
    el?.__zoomReset?.();
  }, []);

  const [treeCollapsed, setTreeCollapsed] = useState(false);
  const collapseTree = (node: TreeNode, depth: number): TreeNode =>
    depth <= 0
      ? { ...node, children: [] }
      : { ...node, children: (node.children || []).map((c) => collapseTree(c, depth - 1)) };

  const handleExpandAll = useCallback(() => {
    setTreeCollapsed(false);
  }, []);

  const handleCollapseAll = useCallback(() => {
    setTreeCollapsed(true);
  }, []);

  const handleBreadcrumbClick = useCallback((item: { id: string; name: string }) => {
    handleTopicClick({ id: item.id, name: item.name } as TreeNode);
  }, [handleTopicClick]);

  const toggleDocExpanded = useCallback((docId: string) => {
    setExpandedDocs((prev: Set<string>) => {
      const next = new Set(prev);
      if (next.has(docId)) next.delete(docId);
      else next.add(docId);
      return next;
    });
  }, []);

  /* -- No project selected -------------------------------------------- */

  if (!activeProject) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="md:ml-56 flex-1 p-4 pt-16 pb-24 md:p-8 md:pt-8 md:pb-8">
          <h2 className="text-2xl font-bold mb-4">Data Sources</h2>
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 text-center text-gray-500">
            <p>Select a project first.</p>
          </div>
        </main>
      </div>
    );
  }

  /* -- Render --------------------------------------------------------- */

  const rawDocs = entityContext?.source_documents || [];
  const documents = rawDocs.map((doc: any) => ({
    ...doc,
    reliability: doc.reliability || doc.reliability_rating || '',
    content: doc.content || doc.content_preview || '',
  }));
  const connectedEntities = entityContext?.connected_entities || [];
  const isLeafSelected = selectedNodeId && !selectedNodeId.startsWith('branch-') && selectedNodeId !== 'root'
    && !selectedNodeId.startsWith('type-') && !selectedNodeId.startsWith('cat-')
    && !selectedNodeId.startsWith('geo-') && !selectedNodeId.startsWith('actors-')
    && !selectedNodeId.startsWith('theme-');

  return (
    <div className="flex">
      <Sidebar />
      <main className="md:ml-56 flex-1 flex flex-col pt-16 pb-24 md:pt-0 md:pb-0" style={{ height: 'calc(100vh - 28px)' }}>

        {/* -- Mind Map Section ----------------------------------------- */}
        <div className={`flex flex-col ${focusMode ? 'flex-1' : ''}`} style={focusMode ? {} : { height: '60%', minHeight: '300px' }}>
          {/* Header + Controls */}
          <div className="flex-none px-4 pt-4 pb-2">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-[10px] font-bold text-[#adc6ff] uppercase tracking-widest">Topic Mind Map</h3>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setFocusMode(!focusMode)}
                  className="text-[9px] font-bold text-gray-500 hover:text-[#adc6ff] uppercase tracking-widest transition-colors"
                >
                  {focusMode ? 'Exit Focus' : 'Focus'}
                </button>
                <button
                  onClick={loadTopics}
                  className="text-[9px] font-bold text-[#adc6ff] hover:text-white uppercase tracking-widest transition-colors"
                >
                  Refresh
                </button>
              </div>
            </div>
            <MindMapControls
              layout={layout}
              onLayoutChange={handleLayoutChange}
              onSearch={setSearchQuery}
              onZoomIn={handleZoomIn}
              onZoomOut={handleZoomOut}
              onZoomReset={handleZoomReset}
              onExpandAll={handleExpandAll}
              onCollapseAll={handleCollapseAll}
              breadcrumbs={breadcrumbs}
              onBreadcrumbClick={handleBreadcrumbClick}
              clusteringMethod={clusteringMethod}
              onClusteringMethodChange={setClusteringMethod}
              granularity={granularity}
              onGranularityChange={setGranularity}
              onExport={async (format) => {
                if (!activeProject) return;
                try {
                  const res = await topicsApi.exportMindmap(activeProject.id, format);
                  const content = format === 'json' ? JSON.stringify(res.data, null, 2) : (res.data?.content || JSON.stringify(res.data));
                  const blob = new Blob([content], { type: 'text/plain' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `mindmap.${format === 'mermaid' ? 'mmd' : format === 'markdown' ? 'md' : 'json'}`;
                  a.click();
                  URL.revokeObjectURL(url);
                } catch (e) { console.error('Export failed', e); }
              }}
            />
          </div>

          {/* Map */}
          <div className="flex-1 px-4 pb-2 min-h-0">
            {loading ? (
              <div className="flex items-center justify-center bg-[#0a0f1c] rounded-lg border border-[#1a1f2e] h-full">
                <LoadingSpinner />
              </div>
            ) : loadError ? (
              <div className="flex items-center justify-center bg-[#0a0f1c] rounded-lg border border-[#1a1f2e] h-full">
                <div className="text-center">
                  <p className="text-red-400 text-sm mb-2">{loadError}</p>
                  <button onClick={loadTopics} className="text-xs text-[#adc6ff] hover:underline">Retry</button>
                </div>
              </div>
            ) : topicTree.children && topicTree.children.length > 0 ? (
              <TopicMindMap
                data={treeCollapsed ? collapseTree(topicTree, 1) : topicTree}
                onNodeClick={handleTopicClick}
                selectedNodeId={selectedNodeId}
                layout={layout}
                searchQuery={searchQuery}
                crossReferences={crossReferences}
                onBreadcrumbsChange={setBreadcrumbs}
              />
            ) : (
              <div className="flex items-center justify-center bg-[#0a0f1c] rounded-lg border border-[#1a1f2e] h-full">
                <div className="text-center text-gray-500 text-sm">
                  <p className="mb-2">No topics found. Ingest documents to populate.</p>
                  <a href="/collections" className="text-[#adc6ff] text-xs hover:underline">Go to Collections to ingest documents</a>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* -- Document Corpus + LLM Summary (bottom panels) ----------- */}
        {!focusMode && (
          <div className="flex-1 flex flex-col md:flex-row gap-4 p-4 pt-2 min-h-0 overflow-auto md:overflow-hidden">

            {/* Left: Documents (evidence-centric) */}
            <div className="w-full md:w-1/2 overflow-y-auto bg-[#0d1220] rounded-lg border border-[#1a1f2e] p-4">
              {!isLeafSelected ? (
                <div className="flex items-center justify-center h-full text-gray-500 text-sm">
                  <p>Click a topic node above to view associated documents.</p>
                </div>
              ) : contextLoading ? (
                <div className="flex items-center justify-center h-full">
                  <LoadingSpinner />
                </div>
              ) : (
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="font-bold text-[10px] uppercase tracking-widest text-gray-500">
                      {selectedNodeId?.startsWith('topic-')
                        ? <>Documents in &ldquo;{selectedNodeName}&rdquo;</>
                        : <>Documents for &ldquo;{selectedNodeName}&rdquo;</>
                      }
                    </h3>
                    <span className="text-[10px] bg-[#1a1f2e] text-gray-400 px-2 py-0.5 rounded-full">
                      {documents.length} source{documents.length !== 1 ? 's' : ''}
                    </span>
                  </div>

                  {documents.length === 0 ? (
                    <p className="text-gray-500 text-sm">No source documents found for this entity.</p>
                  ) : (
                    <div className="space-y-3">
                      {documents.map((doc: any, i: number) => {
                        const isExpanded = expandedDocs.has(doc.id);
                        const excerpts: RelevantExcerpt[] = doc.relevant_excerpts || [];
                        const kwMatches: Record<string, number> = doc.keyword_matches || {};
                        const matchCount = Object.values(kwMatches).reduce((a: number, b: number) => a + b, 0);

                        return (
                          <div
                            key={i}
                            className="bg-[#090e1c] rounded-sm border border-[#1a1f2e] hover:bg-[#161b2a] transition-all group"
                          >
                            {/* Document header */}
                            <div
                              className="p-4 cursor-pointer"
                              onClick={() => router.push(`/documents/${doc.id}`)}
                            >
                              <div className="flex justify-between items-start mb-2">
                                <h4 className="text-sm font-bold text-white group-hover:text-[#adc6ff] transition-colors flex-1">
                                  {doc.name}
                                </h4>
                                <div className="flex items-center gap-1.5 flex-none ml-2">
                                  {matchCount > 0 && (
                                    <span className="text-[8px] font-bold bg-purple-900/30 text-purple-300 border border-purple-700/30 px-1.5 py-0.5 rounded-sm">
                                      {matchCount} match{matchCount !== 1 ? 'es' : ''}
                                    </span>
                                  )}
                                  {doc.reliability && (
                                    <span className={`text-[9px] font-black px-2 py-0.5 rounded-sm border ${reliabilityColor(doc.reliability)}`}>
                                      {doc.reliability}
                                    </span>
                                  )}
                                </div>
                              </div>

                              {/* Show relevant excerpts with highlighting instead of first 300 chars */}
                              {excerpts.length > 0 ? (
                                <div className="space-y-1.5">
                                  {excerpts.slice(0, isExpanded ? excerpts.length : 2).map((ex, j) => (
                                    <div key={j} className="text-xs text-gray-400/80 leading-relaxed border-l-2 border-purple-700/30 pl-2">
                                      <HighlightedExcerpt
                                        text={ex.text}
                                        keywords={keywords}
                                        maxLength={isExpanded ? 0 : 200}
                                      />
                                    </div>
                                  ))}
                                </div>
                              ) : doc.content ? (
                                <p className="text-xs text-gray-400/60 line-clamp-3 leading-relaxed">
                                  <HighlightedExcerpt
                                    text={doc.content}
                                    keywords={keywords}
                                    maxLength={300}
                                  />
                                </p>
                              ) : null}
                            </div>

                            {/* Expand/collapse toggle */}
                            {(doc.content || excerpts.length > 2) && (
                              <button
                                onClick={(e) => { e.stopPropagation(); toggleDocExpanded(doc.id); }}
                                className="w-full text-[9px] font-bold text-gray-500 hover:text-[#adc6ff] py-1.5 border-t border-[#1a1f2e]/50 uppercase tracking-widest transition-colors"
                              >
                                {isExpanded ? 'Show Less' : 'Show Full Document'}
                              </button>
                            )}

                            {/* Expanded full document content */}
                            {isExpanded && doc.content && (
                              <div className="px-4 pb-4 text-xs text-gray-400/70 leading-relaxed whitespace-pre-wrap border-t border-[#1a1f2e]/50 pt-3 max-h-64 overflow-y-auto">
                                <HighlightedExcerpt
                                  text={doc.content}
                                  keywords={keywords}
                                  maxLength={0}
                                />
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Connected entities */}
                  {connectedEntities.length > 0 && (
                    <div className="mt-6">
                      <h3 className="font-bold text-[10px] uppercase tracking-widest text-gray-500 mb-3">
                        Connected Entities
                      </h3>
                      <div className="flex flex-wrap gap-2">
                        {connectedEntities.slice(0, 15).map((ce, i) => (
                          <span
                            key={i}
                            className="flex items-center gap-1.5 bg-[#2f3444] px-2.5 py-1.5 rounded-sm border border-[#424754]/20 text-xs cursor-pointer hover:bg-[#3a4050] transition-colors"
                            onClick={() => {
                              // Search mind map for topics containing this entity
                              setSearchQuery(ce.name);
                            }}
                          >
                            <span className="font-bold text-[#adc6ff]">{ce.name}</span>
                            <span className={`text-[8px] font-black px-1 rounded-sm ${entityTypeColor(ce.entity_type)}`}>
                              {ce.entity_type}
                            </span>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Right: LLM Summary + Conversation */}
            <div className="w-full md:w-1/2 overflow-y-auto bg-[#0d1220] rounded-lg border border-[#1a1f2e] p-4 flex flex-col">
              {!isLeafSelected ? (
                <div className="flex items-center justify-center h-full text-gray-500 text-sm">
                  <p>Select a topic to see its intelligence summary.</p>
                </div>
              ) : (
                <div className="flex flex-col h-full">
                  {/* Keywords */}
                  {keywords.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mb-3">
                      {keywords.map((kw, i) => (
                        <span
                          key={i}
                          className="bg-purple-900/30 text-purple-300 border border-purple-700/30 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider"
                        >
                          {kw}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* AI Summary */}
                  <div className="bg-[#161b2a]/50 rounded-xl p-6 border border-[#adc6ff]/10 relative overflow-y-auto mb-4">
                    <div className="absolute top-0 right-0 p-4 opacity-5">
                      <span className="material-symbols-outlined text-6xl">auto_awesome</span>
                    </div>
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-2">
                        <span className="material-symbols-outlined text-[#adc6ff] text-sm">auto_awesome</span>
                        <h3 className="font-bold text-[10px] uppercase tracking-widest text-[#adc6ff]">
                          Intelligence Summary
                        </h3>
                      </div>
                      {!summaryLoading && summary && (
                        <button
                          onClick={() => {
                            // Clear cache and regenerate
                            setSummaryCache((prev: Record<string, string>) => {
                              const next = { ...prev };
                              if (selectedNodeId) delete next[selectedNodeId];
                              return next;
                            });
                            if (selectedNodeId && selectedNodeName) {
                              generateSummary(selectedNodeId, selectedNodeName, entityContext);
                            }
                          }}
                          className="bg-[#adc6ff]/10 hover:bg-[#adc6ff]/20 text-[#adc6ff] px-3 py-1.5 rounded text-[10px] font-bold uppercase tracking-wider transition-colors border border-[#adc6ff]/20"
                        >
                          Regenerate
                        </button>
                      )}
                    </div>
                    {summaryLoading ? (
                      <div className="flex items-center gap-3 py-4">
                        <LoadingSpinner />
                        <span className="text-sm text-gray-400">Generating intelligence summary...</span>
                      </div>
                    ) : summary ? (
                      <Markdown content={summary} className="text-[13px]" />
                    ) : (
                      <div className="flex flex-col items-center gap-3 py-4">
                        <p className="text-sm text-gray-500">Click below to generate an intelligence summary.</p>
                        <button
                          onClick={() => {
                            if (selectedNodeId && selectedNodeName) {
                              generateSummary(selectedNodeId, selectedNodeName, entityContext);
                            }
                          }}
                          className="bg-[#adc6ff]/10 hover:bg-[#adc6ff]/20 text-[#adc6ff] px-4 py-2 rounded text-xs font-bold uppercase tracking-wider transition-colors border border-[#adc6ff]/20 flex items-center gap-2"
                        >
                          <span className="material-symbols-outlined text-sm">auto_awesome</span>
                          Generate Intelligence Summary
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Conversation thread */}
                  {conversation.length > 1 && (
                    <div className="mb-4 space-y-3 max-h-96 overflow-y-auto">
                      {conversation.slice(1).map((msg, i) => (
                        <div
                          key={i}
                          className={`rounded-sm p-3 text-sm ${
                            msg.role === 'user'
                              ? 'bg-[#1a1f2e] text-gray-300 border-l-2 border-[#adc6ff]/40 whitespace-pre-wrap'
                              : 'bg-[#090e1c] text-gray-400 border border-[#1a1f2e]'
                          }`}
                        >
                          <span className="text-[9px] font-bold uppercase tracking-widest text-gray-600 block mb-1">
                            {msg.role === 'user' ? 'You' : 'Analysis'}
                          </span>
                          {msg.role === 'assistant' ? (
                            <Markdown content={msg.content} />
                          ) : (
                            msg.content
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Quick Queries */}
                  <div className="mb-4">
                    <h3 className="font-bold text-[10px] uppercase tracking-widest text-gray-500/60 mb-3">
                      Suggested Queries
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {[
                        `What connections exist for ${selectedNodeName}?`,
                        `Identify temporal patterns related to ${selectedNodeName}`,
                        `What threats are associated with ${selectedNodeName}?`,
                      ].map((q, i) => (
                        <button
                          key={i}
                          onClick={() => setQueryInput(q)}
                          className="bg-[#252a39] hover:bg-[#343949] text-gray-200 text-[10px] font-medium py-2 px-3 rounded-full border border-[#424754]/10 transition-all text-left"
                        >
                          {q}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Ask about this topic */}
                  <div className="mt-auto bg-[#1a1f2e] border border-[#252a39] rounded-lg p-4">
                    <h3 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-2">
                      Ask About This Topic
                    </h3>
                    <div className="flex gap-2">
                      <input
                        value={queryInput}
                        onChange={(e) => setQueryInput(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && askAboutTopic()}
                        placeholder={`Ask about ${selectedNodeName}...`}
                        className="flex-1 bg-[#090e1c] border border-[#1a1f2e] rounded-sm px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[#adc6ff]"
                      />
                      <button
                        onClick={askAboutTopic}
                        disabled={queryLoading || !queryInput.trim()}
                        className="bg-[#adc6ff] hover:bg-[#4d8eff] text-[#002e6a] px-4 py-2 rounded-sm text-sm font-bold disabled:opacity-50 transition-colors"
                      >
                        {queryLoading ? 'Asking...' : 'Ask'}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
