'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/Sidebar';
import { useProject } from '@/lib/ProjectContext';
import { topicsApi, queryApi } from '@/lib/api';

interface TopicEntity {
  id: string;
  name: string;
  entity_type: string;
  properties?: Record<string, unknown>;
}

interface TopicCategory {
  type: string;
  entities: TopicEntity[];
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
  source_documents?: Array<{ id: string; name: string; content?: string }>;
}

export default function DataSourcesPage() {
  const { activeProject } = useProject();
  const [categories, setCategories] = useState<TopicCategory[]>([]);
  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(new Set());
  const [selectedEntity, setSelectedEntity] = useState<TopicEntity | null>(null);
  const [entityContext, setEntityContext] = useState<EntityContext | null>(null);
  const [loading, setLoading] = useState(false);
  const [contextLoading, setContextLoading] = useState(false);
  const [queryInput, setQueryInput] = useState('');
  const [queryResult, setQueryResult] = useState<string | null>(null);
  const [queryLoading, setQueryLoading] = useState(false);

  const loadTopics = useCallback(async () => {
    if (!activeProject) return;
    setLoading(true);
    try {
      const res = await topicsApi.tree(activeProject.id);
      const data = res.data;
      // Expect either an array of categories or a flat entity list
      if (Array.isArray(data)) {
        // If flat array of entities, group by type
        if (data.length > 0 && data[0].entity_type) {
          const grouped: Record<string, TopicEntity[]> = {};
          for (const entity of data) {
            const type = entity.entity_type || 'Unknown';
            if (!grouped[type]) grouped[type] = [];
            grouped[type].push(entity);
          }
          setCategories(Object.entries(grouped).map(([type, entities]) => ({ type, entities })));
        } else {
          setCategories(data);
        }
      } else if (data.categories) {
        setCategories(data.categories);
      } else if (data.topics) {
        // Handle {topics: [...]} format
        const grouped: Record<string, TopicEntity[]> = {};
        for (const entity of data.topics) {
          const type = entity.entity_type || 'Unknown';
          if (!grouped[type]) grouped[type] = [];
          grouped[type].push(entity);
        }
        setCategories(Object.entries(grouped).map(([type, entities]) => ({ type, entities })));
      } else {
        setCategories([]);
      }
    } catch (e) {
      console.error('Failed to load topics', e);
      setCategories([]);
    } finally {
      setLoading(false);
    }
  }, [activeProject]);

  useEffect(() => {
    loadTopics();
  }, [loadTopics]);

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

  function toggleType(type: string) {
    setExpandedTypes(prev => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
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

  if (!activeProject) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="ml-56 flex-1 p-8">
          <h2 className="text-2xl font-bold mb-4">Topic Explorer</h2>
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 text-center text-gray-500">
            <p>Select a project first.</p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="ml-56 flex-1 flex h-screen overflow-hidden">
        {/* Left panel - Topic Tree */}
        <div className="w-72 flex-none bg-navy-800 border-r border-navy-600 flex flex-col overflow-hidden">
          <div className="p-4 border-b border-navy-600">
            <h3 className="text-sm font-semibold text-gray-400">Topic Tree</h3>
          </div>
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="p-4 text-center text-gray-500 text-sm">Loading topics...</div>
            ) : categories.length === 0 ? (
              <div className="p-4 text-center text-gray-500 text-sm">No topics found. Ingest documents to populate.</div>
            ) : (
              <div className="py-1">
                {categories.map(cat => (
                  <div key={cat.type}>
                    <button
                      onClick={() => toggleType(cat.type)}
                      className="w-full text-left px-4 py-2 hover:bg-navy-700 transition-colors flex items-center justify-between"
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-gray-500">{expandedTypes.has(cat.type) ? '▼' : '▶'}</span>
                        <span className="text-sm font-medium text-gray-200">{cat.type}</span>
                      </div>
                      <span className="text-xs bg-navy-600 text-gray-400 px-2 py-0.5 rounded-full">
                        {cat.entities.length}
                      </span>
                    </button>
                    {expandedTypes.has(cat.type) && (
                      <div className="ml-6">
                        {cat.entities.map(entity => (
                          <button
                            key={entity.id}
                            onClick={() => selectEntity(entity)}
                            className={`w-full text-left px-3 py-1.5 text-xs transition-colors flex items-center gap-2 ${
                              selectedEntity?.id === entity.id
                                ? 'bg-accent-blue/20 text-accent-blue'
                                : 'text-gray-300 hover:bg-navy-700'
                            }`}
                          >
                            <span className="w-1.5 h-1.5 rounded-full bg-accent-blue flex-none" />
                            <span className="truncate">{entity.name}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right panel - Entity Context */}
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
                <h2 className="text-xl font-bold text-gray-100">{entityContext?.entity?.name || selectedEntity.name}</h2>
                <span className="inline-block mt-2 text-xs px-2 py-0.5 rounded bg-accent-blue/20 text-accent-blue border border-accent-blue/30">
                  {entityContext?.entity?.entity_type || selectedEntity.entity_type}
                </span>
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
                        <span className="text-gray-500">({ce.entity_type})</span>
                        {ce.confidence !== undefined && (
                          <span className="ml-auto text-gray-500">{(ce.confidence * 100).toFixed(0)}%</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Source documents */}
              {entityContext?.source_documents && entityContext.source_documents.length > 0 && (
                <div className="bg-navy-800 border border-navy-600 rounded-lg p-5">
                  <h3 className="text-sm font-semibold text-gray-400 mb-3">
                    Source Documents ({entityContext.source_documents.length})
                  </h3>
                  <div className="space-y-2">
                    {entityContext.source_documents.map((doc, i) => (
                      <div key={i} className="bg-navy-700 rounded p-3">
                        <div className="text-sm text-gray-200 font-medium mb-1">{doc.name}</div>
                        {doc.content && (
                          <p className="text-xs text-gray-400 line-clamp-3">{doc.content.substring(0, 300)}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Query input */}
              <div className="bg-navy-800 border border-navy-600 rounded-lg p-5">
                <h3 className="text-sm font-semibold text-gray-400 mb-3">Ask about this topic</h3>
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
