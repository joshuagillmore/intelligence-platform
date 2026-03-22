'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/Sidebar';
import LoadingSpinner from '@/components/LoadingSpinner';
import TopicMindMap from '@/components/TopicMindMap';
import { useRouter } from 'next/navigation';
import { useProject } from '@/lib/ProjectContext';
import { topicsApi, queryApi } from '@/lib/api';
import { getErrorMessage } from '@/lib/errorMessages';

/* -- Types ------------------------------------------------------------ */

interface TreeNode {
  name: string;
  id: string;
  entity_type?: string;
  count?: number;
  children?: TreeNode[];
}

interface SourceDocument {
  id: string;
  name: string;
  content?: string;
  reliability?: string;
}

interface ConnectedEntity {
  id: string;
  name: string;
  entity_type: string;
  rel_type: string;
  confidence?: number;
}

interface EntityContext {
  entity: { id: string; name: string; entity_type: string; properties?: Record<string, unknown> };
  connected_entities?: ConnectedEntity[];
  source_documents?: SourceDocument[];
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

/* -- Component -------------------------------------------------------- */

export default function DataSourcesPage() {
  const { activeProject } = useProject();
  const router = useRouter();

  // Mind map tree data (raw from backend)
  const [topicTree, setTopicTree] = useState<TreeNode>({ name: 'Knowledge Base', id: 'root', children: [] });
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Selected node
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedNodeName, setSelectedNodeName] = useState<string | null>(null);

  // Entity context (documents, connected entities)
  const [entityContext, setEntityContext] = useState<EntityContext | null>(null);
  const [contextLoading, setContextLoading] = useState(false);

  // LLM summary
  const [summary, setSummary] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  // Query input
  const [queryInput, setQueryInput] = useState('');
  const [queryResult, setQueryResult] = useState<string | null>(null);
  const [queryLoading, setQueryLoading] = useState(false);

  /* -- Load topic tree ------------------------------------------------ */

  const loadTopics = useCallback(async () => {
    if (!activeProject) return;
    setLoading(true);
    setLoadError(null);
    try {
      const res = await topicsApi.tree(activeProject.id);
      const data = res.data;

      if (data && typeof data === 'object' && !Array.isArray(data) && data.children) {
        // Backend returns tree structure directly
        setTopicTree(data);
      } else if (Array.isArray(data)) {
        // Fallback: flat entity list -- group by type
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
  }, [activeProject]);

  useEffect(() => {
    loadTopics();
  }, [loadTopics]);

  /* -- Handle node click ---------------------------------------------- */

  const handleTopicClick = useCallback(async (node: TreeNode) => {
    if (!activeProject) return;

    setSelectedNodeId(node.id);
    setSelectedNodeName(node.name);
    setEntityContext(null);
    setSummary(null);
    setQueryResult(null);

    // Skip fetching context for branch/root nodes
    if (node.id === 'root' || node.id.startsWith('branch-')) return;

    // Fetch entity context
    setContextLoading(true);
    try {
      const res = await topicsApi.context(node.id, activeProject.id);
      setEntityContext(res.data);
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

    // Fetch LLM summary
    setSummaryLoading(true);
    try {
      const res = await queryApi.rag(
        activeProject.id,
        `Provide a comprehensive intelligence summary about "${node.name}". What do we know from our sources?`
      );
      setSummary(res.data.answer || res.data.response || JSON.stringify(res.data));
    } catch {
      setSummary('Unable to generate summary at this time.');
    } finally {
      setSummaryLoading(false);
    }
  }, [activeProject]);

  /* -- Ask about selected topic --------------------------------------- */

  async function askAboutTopic() {
    if (!queryInput.trim() || !activeProject || !selectedNodeName) return;
    setQueryLoading(true);
    setQueryResult(null);
    try {
      const scopedQuery = `Regarding "${selectedNodeName}": ${queryInput}`;
      const res = await queryApi.rag(activeProject.id, scopedQuery);
      setQueryResult(res.data.answer || res.data.response || JSON.stringify(res.data));
    } catch {
      setQueryResult('Failed to process query.');
    } finally {
      setQueryLoading(false);
    }
  }

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

  const documents = entityContext?.source_documents || [];
  const connectedEntities = entityContext?.connected_entities || [];
  const isLeafSelected = selectedNodeId && !selectedNodeId.startsWith('branch-') && selectedNodeId !== 'root';

  return (
    <div className="flex">
      <Sidebar />
      <main className="md:ml-56 flex-1 flex flex-col pt-16 pb-24 md:pt-0 md:pb-0" style={{ height: 'calc(100vh - 28px)' }}>

        {/* -- Mind Map ------------------------------------------------- */}
        <div className="flex-none p-4 pb-0">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-[10px] font-bold text-[#adc6ff] uppercase tracking-widest">Topic Mind Map</h3>
            <button
              onClick={loadTopics}
              className="text-[9px] font-bold text-[#adc6ff] hover:text-white uppercase tracking-widest transition-colors"
            >
              Refresh
            </button>
          </div>
          {loading ? (
            <div className="flex items-center justify-center bg-[#0a0f1c] rounded-lg border border-[#1a1f2e]" style={{ height: '350px' }}>
              <LoadingSpinner />
            </div>
          ) : loadError ? (
            <div className="flex items-center justify-center bg-[#0a0f1c] rounded-lg border border-[#1a1f2e]" style={{ height: '350px' }}>
              <div className="text-center">
                <p className="text-red-400 text-sm mb-2">{loadError}</p>
                <button onClick={loadTopics} className="text-xs text-[#adc6ff] hover:underline">Retry</button>
              </div>
            </div>
          ) : topicTree.children && topicTree.children.length > 0 ? (
            <TopicMindMap
              data={topicTree}
              onNodeClick={handleTopicClick}
              selectedNodeId={selectedNodeId}
            />
          ) : (
            <div className="flex items-center justify-center bg-[#0a0f1c] rounded-lg border border-[#1a1f2e]" style={{ height: '350px' }}>
              <div className="text-center text-gray-500 text-sm">
                <p className="mb-2">No topics found. Ingest documents to populate.</p>
                <a href="/collections" className="text-[#adc6ff] text-xs hover:underline">Go to Collections to ingest documents</a>
              </div>
            </div>
          )}
        </div>

        {/* -- Document Corpus + LLM Summary --------------------------- */}
        <div className="flex-1 flex flex-col md:flex-row gap-4 p-4 min-h-0 overflow-auto md:overflow-hidden">

          {/* Left: Documents */}
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
                    Documents for &ldquo;{selectedNodeName}&rdquo;
                  </h3>
                  <span className="text-[10px] bg-[#1a1f2e] text-gray-400 px-2 py-0.5 rounded-full">
                    {documents.length} source{documents.length !== 1 ? 's' : ''}
                  </span>
                </div>

                {documents.length === 0 ? (
                  <p className="text-gray-500 text-sm">No source documents found for this entity.</p>
                ) : (
                  <div className="space-y-3">
                    {documents.map((doc, i) => (
                      <div
                        key={i}
                        className="bg-[#090e1c] p-4 rounded-sm border border-[#1a1f2e] hover:bg-[#161b2a] transition-all cursor-pointer group"
                        onClick={() => router.push(`/documents/${doc.id}`)}
                      >
                        <div className="flex justify-between items-start mb-2">
                          <h4 className="text-sm font-bold text-white group-hover:text-[#adc6ff] transition-colors flex-1">
                            {doc.name}
                          </h4>
                          {doc.reliability && (
                            <span className={`text-[9px] font-black px-2 py-0.5 rounded-sm border ml-2 flex-none ${reliabilityColor(doc.reliability)}`}>
                              {doc.reliability}
                            </span>
                          )}
                        </div>
                        {doc.content && (
                          <p className="text-xs text-gray-400/60 line-clamp-3 leading-relaxed">
                            {doc.content.substring(0, 300)}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* Connected entities */}
                {connectedEntities.length > 0 && (
                  <div className="mt-6">
                    <h3 className="font-bold text-[10px] uppercase tracking-widest text-gray-500 mb-3">
                      Connected Entities
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {connectedEntities.slice(0, 12).map((ce, i) => (
                        <span
                          key={i}
                          className="flex items-center gap-1.5 bg-[#2f3444] px-2.5 py-1.5 rounded-sm border border-[#424754]/20 text-xs"
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

          {/* Right: LLM Summary + Query */}
          <div className="w-full md:w-1/2 overflow-y-auto bg-[#0d1220] rounded-lg border border-[#1a1f2e] p-4 flex flex-col">
            {!isLeafSelected ? (
              <div className="flex items-center justify-center h-full text-gray-500 text-sm">
                <p>Select a topic to see its intelligence summary.</p>
              </div>
            ) : (
              <div className="flex flex-col h-full">
                {/* AI Summary */}
                <div className="bg-[#161b2a]/50 rounded-xl p-6 border border-[#adc6ff]/10 relative overflow-hidden mb-4">
                  <div className="absolute top-0 right-0 p-4 opacity-5">
                    <span className="material-symbols-outlined text-6xl">auto_awesome</span>
                  </div>
                  <div className="flex items-center gap-2 mb-4">
                    <span className="material-symbols-outlined text-[#adc6ff] text-sm">auto_awesome</span>
                    <h3 className="font-bold text-[10px] uppercase tracking-widest text-[#adc6ff]">
                      Intelligence Summary: {selectedNodeName}
                    </h3>
                  </div>
                  {summaryLoading ? (
                    <div className="flex items-center gap-3 py-4">
                      <LoadingSpinner />
                      <span className="text-sm text-gray-400">Generating intelligence summary...</span>
                    </div>
                  ) : summary ? (
                    <p className="text-[13px] leading-relaxed text-gray-200/90 whitespace-pre-wrap">
                      {summary}
                    </p>
                  ) : (
                    <p className="text-sm text-gray-500">Summary will appear here once generated.</p>
                  )}
                </div>

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
                  {queryResult && (
                    <div className="mt-3 bg-[#090e1c] rounded-sm p-3 text-sm text-gray-300 whitespace-pre-wrap max-h-48 overflow-y-auto border border-[#1a1f2e]">
                      {queryResult}
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
