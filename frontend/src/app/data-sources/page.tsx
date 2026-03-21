'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/Sidebar';
import { useProject } from '@/lib/ProjectContext';
import { topicsApi, queryApi } from '@/lib/api';

/* ── Types ─────────────────────────────────────────────────────────── */

interface TopicEntity {
  id: string;
  name: string;
  entity_type: string;
  degree?: number;
  properties?: Record<string, unknown>;
}

interface DocumentNode {
  id: string;
  name: string;
  reliability?: string;
  entities: TopicEntity[];
}

interface TypeGroup {
  type: string;
  count: number;
  entities: TopicEntity[];
}

interface ThemeNode {
  entity: TopicEntity;
  degree: number;
  neighbors: TopicEntity[];
}

interface TopicTree {
  by_source_document?: DocumentNode[];
  by_entity_type?: TypeGroup[];
  key_themes?: ThemeNode[];
}

interface ConnectedEntity {
  id: string;
  name: string;
  entity_type: string;
  rel_type: string;
  confidence?: number;
}

interface EntityContext {
  entity: TopicEntity;
  connected_entities?: ConnectedEntity[];
  source_documents?: Array<{ id: string; name: string; content?: string; reliability?: string }>;
}

/* ── Helpers ───────────────────────────────────────────────────────── */

const entityTypeColor = (type: string) => {
  const t = type?.toLowerCase() || '';
  if (t.includes('person') || t.includes('people')) return 'bg-purple-900/40 text-purple-300 border-purple-700/50';
  if (t.includes('org')) return 'bg-blue-900/40 text-blue-300 border-blue-700/50';
  if (t.includes('location') || t.includes('place') || t.includes('geo')) return 'bg-green-900/40 text-green-300 border-green-700/50';
  if (t.includes('event')) return 'bg-yellow-900/40 text-yellow-300 border-yellow-700/50';
  if (t.includes('threat') || t.includes('malware') || t.includes('vulnerability')) return 'bg-red-900/40 text-red-300 border-red-700/50';
  return 'bg-gray-900/40 text-gray-300 border-gray-700/50';
};

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

/* ── Component ─────────────────────────────────────────────────────── */

export default function DataSourcesPage() {
  const { activeProject } = useProject();
  const [tree, setTree] = useState<TopicTree>({});
  const [loading, setLoading] = useState(false);

  // Expansion state: track which branches + sub-nodes are expanded
  const [expandedBranches, setExpandedBranches] = useState<Set<string>>(new Set());
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());

  // Right panel state
  const [selectedEntity, setSelectedEntity] = useState<TopicEntity | null>(null);
  const [entityContext, setEntityContext] = useState<EntityContext | null>(null);
  const [contextLoading, setContextLoading] = useState(false);
  const [queryInput, setQueryInput] = useState('');
  const [queryResult, setQueryResult] = useState<string | null>(null);
  const [queryLoading, setQueryLoading] = useState(false);

  /* ── Load topic tree ───────────────────────────────────────────── */

  const loadTopics = useCallback(async () => {
    if (!activeProject) return;
    setLoading(true);
    try {
      const res = await topicsApi.tree(activeProject.id);
      const data = res.data;

      // The backend returns a hierarchical tree object
      if (data && typeof data === 'object' && !Array.isArray(data)) {
        setTree({
          by_source_document: data.by_source_document || data.documents || [],
          by_entity_type: data.by_entity_type || data.entity_types || data.categories || [],
          key_themes: data.key_themes || data.themes || [],
        });
      } else if (Array.isArray(data)) {
        // Fallback: flat entity list -- group by type into by_entity_type
        const grouped: Record<string, TopicEntity[]> = {};
        for (const entity of data) {
          const type = entity.entity_type || 'Unknown';
          if (!grouped[type]) grouped[type] = [];
          grouped[type].push(entity);
        }
        setTree({
          by_source_document: [],
          by_entity_type: Object.entries(grouped).map(([type, entities]) => ({
            type,
            count: entities.length,
            entities,
          })),
          key_themes: [],
        });
      } else {
        setTree({});
      }
    } catch (e) {
      console.error('Failed to load topics', e);
      setTree({});
    } finally {
      setLoading(false);
    }
  }, [activeProject]);

  useEffect(() => {
    loadTopics();
  }, [loadTopics]);

  /* ── Handlers ─────────────────────────────────────────────────── */

  function toggleBranch(branch: string) {
    setExpandedBranches(prev => {
      const next = new Set(prev);
      if (next.has(branch)) next.delete(branch);
      else next.add(branch);
      return next;
    });
  }

  function toggleNode(key: string) {
    setExpandedNodes(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function selectEntity(entity: TopicEntity) {
    setSelectedEntity(entity);
    setEntityContext(null);
    setQueryResult(null);
    setContextLoading(true);
    try {
      const res = await topicsApi.context(entity.id, activeProject!.id);
      setEntityContext(res.data);
    } catch (e) {
      console.error('Failed to load entity context', e);
      setEntityContext({ entity, connected_entities: [], source_documents: [] });
    } finally {
      setContextLoading(false);
    }
  }

  async function askAboutEntity() {
    if (!queryInput.trim() || !activeProject || !selectedEntity) return;
    setQueryLoading(true);
    setQueryResult(null);
    try {
      const scopedQuery = `Regarding entity "${selectedEntity.name}" (${selectedEntity.entity_type}): ${queryInput}`;
      const res = await queryApi.rag(activeProject.id, scopedQuery);
      setQueryResult(res.data.answer || res.data.response || JSON.stringify(res.data));
    } catch {
      setQueryResult('Failed to process query.');
    } finally {
      setQueryLoading(false);
    }
  }

  /* ── No project selected ──────────────────────────────────────── */

  if (!activeProject) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="ml-56 flex-1 p-8">
          <h2 className="text-2xl font-bold mb-4">Data Sources</h2>
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 text-center text-gray-500">
            <p>Select a project first.</p>
          </div>
        </main>
      </div>
    );
  }

  /* ── Tree helpers ──────────────────────────────────────────────── */

  const docs = tree.by_source_document || [];
  const types = tree.by_entity_type || [];
  const themes = tree.key_themes || [];
  const hasData = docs.length > 0 || types.length > 0 || themes.length > 0;

  /* ── Render ───────────────────────────────────────────────────── */

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="ml-56 flex-1 flex h-screen overflow-hidden">

        {/* ── Left Panel: Topic Tree ────────────────────────────── */}
        <div className="w-80 flex-none bg-navy-800 border-r border-navy-600 flex flex-col overflow-hidden">
          <div className="p-4 border-b border-navy-600">
            <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">Topic Tree</h3>
          </div>
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="p-4 text-center text-gray-500 text-sm">Loading topics...</div>
            ) : !hasData ? (
              <div className="p-4 text-center text-gray-500 text-sm">No topics found. Ingest documents to populate.</div>
            ) : (
              <div className="py-1">

                {/* ── Branch: By Source Document ──────────────── */}
                {docs.length > 0 && (
                  <div>
                    <button
                      onClick={() => toggleBranch('docs')}
                      className="w-full text-left px-4 py-2.5 hover:bg-navy-700 transition-colors flex items-center gap-2"
                    >
                      <span className="text-xs text-gray-500">{expandedBranches.has('docs') ? '▼' : '▶'}</span>
                      <span className="text-sm font-semibold text-gray-200">By Source Document</span>
                      <span className="ml-auto text-xs bg-navy-600 text-gray-400 px-2 py-0.5 rounded-full">{docs.length}</span>
                    </button>
                    {expandedBranches.has('docs') && docs.map(doc => (
                      <div key={doc.id}>
                        <button
                          onClick={() => toggleNode(`doc-${doc.id}`)}
                          className="w-full text-left pl-8 pr-4 py-1.5 hover:bg-navy-700 transition-colors flex items-center gap-2"
                        >
                          <span className="text-xs text-gray-500">
                            {expandedNodes.has(`doc-${doc.id}`) ? '▼' : '▶'}
                          </span>
                          <span className="text-xs text-gray-300 truncate flex-1">{doc.name}</span>
                          {doc.reliability && (
                            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${reliabilityColor(doc.reliability)}`}>
                              {doc.reliability}
                            </span>
                          )}
                        </button>
                        {expandedNodes.has(`doc-${doc.id}`) && doc.entities?.map(entity => (
                          <button
                            key={entity.id}
                            onClick={() => selectEntity(entity)}
                            className={`w-full text-left pl-14 pr-4 py-1 text-xs transition-colors flex items-center gap-2 ${
                              selectedEntity?.id === entity.id
                                ? 'bg-accent-blue/20 text-accent-blue'
                                : 'text-gray-400 hover:bg-navy-700 hover:text-gray-200'
                            }`}
                          >
                            <span className="w-1.5 h-1.5 rounded-full bg-accent-blue/60 flex-none" />
                            <span className="truncate">{entity.name}</span>
                            <span className={`ml-auto text-[10px] px-1.5 py-0.5 rounded border flex-none ${entityTypeColor(entity.entity_type)}`}>
                              {entity.entity_type}
                            </span>
                          </button>
                        ))}
                      </div>
                    ))}
                  </div>
                )}

                {/* ── Branch: By Entity Type ─────────────────── */}
                {types.length > 0 && (
                  <div>
                    <button
                      onClick={() => toggleBranch('types')}
                      className="w-full text-left px-4 py-2.5 hover:bg-navy-700 transition-colors flex items-center gap-2"
                    >
                      <span className="text-xs text-gray-500">{expandedBranches.has('types') ? '▼' : '▶'}</span>
                      <span className="text-sm font-semibold text-gray-200">By Entity Type</span>
                      <span className="ml-auto text-xs bg-navy-600 text-gray-400 px-2 py-0.5 rounded-full">{types.length}</span>
                    </button>
                    {expandedBranches.has('types') && types.map(group => (
                      <div key={group.type}>
                        <button
                          onClick={() => toggleNode(`type-${group.type}`)}
                          className="w-full text-left pl-8 pr-4 py-1.5 hover:bg-navy-700 transition-colors flex items-center gap-2"
                        >
                          <span className="text-xs text-gray-500">
                            {expandedNodes.has(`type-${group.type}`) ? '▼' : '▶'}
                          </span>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded border ${entityTypeColor(group.type)}`}>
                            {group.type}
                          </span>
                          <span className="ml-auto text-xs bg-navy-600 text-gray-400 px-2 py-0.5 rounded-full">
                            {group.count ?? group.entities?.length ?? 0}
                          </span>
                        </button>
                        {expandedNodes.has(`type-${group.type}`) && group.entities?.map(entity => (
                          <button
                            key={entity.id}
                            onClick={() => selectEntity(entity)}
                            className={`w-full text-left pl-14 pr-4 py-1 text-xs transition-colors flex items-center gap-2 ${
                              selectedEntity?.id === entity.id
                                ? 'bg-accent-blue/20 text-accent-blue'
                                : 'text-gray-400 hover:bg-navy-700 hover:text-gray-200'
                            }`}
                          >
                            <span className="w-1.5 h-1.5 rounded-full bg-accent-blue/60 flex-none" />
                            <span className="truncate">{entity.name}</span>
                          </button>
                        ))}
                      </div>
                    ))}
                  </div>
                )}

                {/* ── Branch: Key Themes ─────────────────────── */}
                {themes.length > 0 && (
                  <div>
                    <button
                      onClick={() => toggleBranch('themes')}
                      className="w-full text-left px-4 py-2.5 hover:bg-navy-700 transition-colors flex items-center gap-2"
                    >
                      <span className="text-xs text-gray-500">{expandedBranches.has('themes') ? '▼' : '▶'}</span>
                      <span className="text-sm font-semibold text-gray-200">Key Themes</span>
                      <span className="ml-auto text-xs bg-navy-600 text-gray-400 px-2 py-0.5 rounded-full">{themes.length}</span>
                    </button>
                    {expandedBranches.has('themes') && themes.map(theme => (
                      <div key={theme.entity.id}>
                        <button
                          onClick={() => toggleNode(`theme-${theme.entity.id}`)}
                          className="w-full text-left pl-8 pr-4 py-1.5 hover:bg-navy-700 transition-colors flex items-center gap-2"
                        >
                          <span className="text-xs text-gray-500">
                            {expandedNodes.has(`theme-${theme.entity.id}`) ? '▼' : '▶'}
                          </span>
                          <span className="text-xs text-gray-200 truncate flex-1">{theme.entity.name}</span>
                          <span className="text-[10px] bg-navy-600 text-gray-400 px-1.5 py-0.5 rounded-full flex-none">
                            {theme.degree} connections
                          </span>
                        </button>
                        {expandedNodes.has(`theme-${theme.entity.id}`) && (
                          <div>
                            {/* The theme entity itself */}
                            <button
                              onClick={() => selectEntity(theme.entity)}
                              className={`w-full text-left pl-14 pr-4 py-1 text-xs transition-colors flex items-center gap-2 ${
                                selectedEntity?.id === theme.entity.id
                                  ? 'bg-accent-blue/20 text-accent-blue'
                                  : 'text-gray-300 hover:bg-navy-700'
                              }`}
                            >
                              <span className="w-1.5 h-1.5 rounded-full bg-accent-blue flex-none" />
                              <span className="truncate font-medium">{theme.entity.name}</span>
                              <span className={`ml-auto text-[10px] px-1.5 py-0.5 rounded border flex-none ${entityTypeColor(theme.entity.entity_type)}`}>
                                {theme.entity.entity_type}
                              </span>
                            </button>
                            {/* Connected neighbors */}
                            {theme.neighbors?.map(nb => (
                              <button
                                key={nb.id}
                                onClick={() => selectEntity(nb)}
                                className={`w-full text-left pl-[4.5rem] pr-4 py-1 text-xs transition-colors flex items-center gap-2 ${
                                  selectedEntity?.id === nb.id
                                    ? 'bg-accent-blue/20 text-accent-blue'
                                    : 'text-gray-500 hover:bg-navy-700 hover:text-gray-300'
                                }`}
                              >
                                <span className="w-1 h-1 rounded-full bg-gray-600 flex-none" />
                                <span className="truncate">{nb.name}</span>
                                <span className={`ml-auto text-[10px] px-1.5 py-0.5 rounded border flex-none ${entityTypeColor(nb.entity_type)}`}>
                                  {nb.entity_type}
                                </span>
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

              </div>
            )}
          </div>
        </div>

        {/* ── Right Panel: Entity Context ───────────────────────── */}
        <div className="flex-1 overflow-y-auto p-6">
          {!selectedEntity ? (
            <div className="flex items-center justify-center h-full text-gray-500 text-sm">
              <p>Select an entity from the topic tree to view its context.</p>
            </div>
          ) : contextLoading ? (
            <div className="flex items-center justify-center h-full text-gray-500 text-sm">
              <p>Loading entity context...</p>
            </div>
          ) : (
            <div className="space-y-6 max-w-4xl">

              {/* Entity header */}
              <div className="bg-navy-800 border border-navy-600 rounded-lg p-5">
                <div className="flex items-center gap-3">
                  <h2 className="text-xl font-bold text-gray-100">
                    {entityContext?.entity?.name || selectedEntity.name}
                  </h2>
                  <span className={`text-xs px-2 py-0.5 rounded border ${entityTypeColor(entityContext?.entity?.entity_type || selectedEntity.entity_type)}`}>
                    {entityContext?.entity?.entity_type || selectedEntity.entity_type}
                  </span>
                </div>
                {entityContext?.entity?.properties && Object.keys(entityContext.entity.properties).length > 0 && (
                  <div className="mt-3 space-y-1">
                    {Object.entries(entityContext.entity.properties).map(([key, value]) => (
                      <div key={key} className="text-xs">
                        <span className="text-gray-500">{key}:</span>{' '}
                        <span className="text-gray-300">{String(value)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Source documents */}
              {entityContext?.source_documents && entityContext.source_documents.length > 0 && (
                <div className="bg-navy-800 border border-navy-600 rounded-lg p-5">
                  <h3 className="text-sm font-semibold text-gray-400 mb-3">
                    Source Documents ({entityContext.source_documents.length})
                  </h3>
                  <div className="space-y-2">
                    {entityContext.source_documents.map((doc, i) => (
                      <div key={i} className="bg-navy-700 rounded p-3">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-sm text-gray-200 font-medium">{doc.name}</span>
                          {doc.reliability && (
                            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${reliabilityColor(doc.reliability)}`}>
                              {doc.reliability}
                            </span>
                          )}
                        </div>
                        {doc.content && (
                          <p className="text-xs text-gray-400 line-clamp-3">{doc.content.substring(0, 300)}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Connected entities */}
              {entityContext?.connected_entities && entityContext.connected_entities.length > 0 && (
                <div className="bg-navy-800 border border-navy-600 rounded-lg p-5">
                  <h3 className="text-sm font-semibold text-gray-400 mb-3">
                    Connected Entities ({entityContext.connected_entities.length})
                  </h3>
                  <div className="space-y-2">
                    {entityContext.connected_entities.map((ce, i) => (
                      <div key={i} className="flex items-center gap-3 bg-navy-700 rounded p-2 text-xs">
                        <span className="text-accent-blue font-medium">{ce.rel_type}</span>
                        <span className="text-gray-300">{ce.name}</span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${entityTypeColor(ce.entity_type)}`}>
                          {ce.entity_type}
                        </span>
                        {ce.confidence !== undefined && (
                          <span className="ml-auto text-gray-500">{(ce.confidence * 100).toFixed(0)}%</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Ask about this entity */}
              <div className="bg-navy-800 border border-navy-600 rounded-lg p-5">
                <h3 className="text-sm font-semibold text-gray-400 mb-3">Ask About This</h3>
                <div className="flex gap-2">
                  <input
                    value={queryInput}
                    onChange={(e) => setQueryInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && askAboutEntity()}
                    placeholder={`Ask about ${selectedEntity.name}...`}
                    className="flex-1 bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-blue"
                  />
                  <button
                    onClick={askAboutEntity}
                    disabled={queryLoading || !queryInput.trim()}
                    className="bg-accent-blue hover:bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium disabled:opacity-50 transition-colors"
                  >
                    {queryLoading ? 'Asking...' : 'Ask'}
                  </button>
                </div>
                {queryResult && (
                  <div className="mt-3 bg-navy-700 rounded p-3 text-sm text-gray-300 whitespace-pre-wrap max-h-64 overflow-y-auto">
                    {queryResult}
                  </div>
                )}
              </div>

            </div>
          )}
        </div>
      </div>
    </div>
  );
}
