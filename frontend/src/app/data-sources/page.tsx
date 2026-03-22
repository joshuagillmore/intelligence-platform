'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/Sidebar';
import LoadingSpinner from '@/components/LoadingSpinner';
import { useRouter } from 'next/navigation';
import { useProject } from '@/lib/ProjectContext';
import { topicsApi, queryApi } from '@/lib/api';
import { getErrorMessage } from '@/lib/errorMessages';

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

interface GeoRegion {
  name: string;
  count: number;
  entities: TopicEntity[];
}

interface ActorGroup {
  name: string;
  entity_type: string;
  count: number;
  entities: TopicEntity[];
}

interface TopicTree {
  by_source_document?: DocumentNode[];
  by_entity_type?: TypeGroup[];
  key_themes?: ThemeNode[];
  geographic_regions?: GeoRegion[];
  actors_organizations?: ActorGroup[];
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
  const router = useRouter();
  const [tree, setTree] = useState<TopicTree>({});
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

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
    setLoadError(null);
    try {
      const res = await topicsApi.tree(activeProject.id);
      const data = res.data;

      // The backend returns a hierarchical tree object
      if (data && typeof data === 'object' && !Array.isArray(data)) {
        // Handle both old format and new 5-branch format
        const sourceDocsBranch = data.by_source_document || data.documents || data['Source Documents'] || [];
        const entityTypeBranch = data.by_entity_type || data.entity_types || data.categories || data['By Entity Type'] || [];
        const themesBranch = data.key_themes || data.themes || data['Thematic Clusters'] || [];
        const geoBranch = data.geographic_regions || data['Geographic Regions'] || [];
        const actorsBranch = data.actors_organizations || data['Actors & Organizations'] || [];
        setTree({
          by_source_document: sourceDocsBranch,
          by_entity_type: entityTypeBranch,
          key_themes: themesBranch,
          geographic_regions: geoBranch,
          actors_organizations: actorsBranch,
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
      setLoadError(getErrorMessage(e));
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
  const geoRegions = tree.geographic_regions || [];
  const actors = tree.actors_organizations || [];
  const hasData = docs.length > 0 || types.length > 0 || themes.length > 0 || geoRegions.length > 0 || actors.length > 0;

  /* ── Render ───────────────────────────────────────────────────── */

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="ml-56 flex-1 flex h-screen overflow-hidden">

        {/* ── Left Panel: Topic Tree ────────────────────────────── */}
        <div className="w-80 flex-none bg-[#161b2a] border-r border-[#1a1f2e] flex flex-col overflow-hidden">
          <div className="p-4 border-b border-[#1a1f2e]">
            <h3 className="text-[10px] font-bold text-[#adc6ff] uppercase tracking-widest mb-3">Topic Explorer</h3>
            <div className="relative">
              <span className="material-symbols-outlined absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500 text-sm">search</span>
              <input className="w-full bg-[#090e1c] border-none text-[11px] py-2 pl-8 pr-3 rounded-sm focus:ring-1 focus:ring-[#adc6ff] placeholder:text-gray-600" placeholder="FILTER TAXONOMY..." />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="p-4"><LoadingSpinner /></div>
            ) : loadError ? (
              <div className="p-4 text-center text-sm">
                <p className="text-red-400 mb-2">{loadError}</p>
                <button onClick={loadTopics} className="text-xs text-accent-blue hover:underline">Retry</button>
              </div>
            ) : !hasData ? (
              <div className="p-4 text-center text-gray-500 text-sm">
                <p className="mb-2">No topics found. Ingest documents to populate.</p>
                <a href="/collections" className="text-accent-blue text-xs hover:underline">Go to Collections to ingest documents</a>
              </div>
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
                          <span
                            className="text-xs text-accent-blue hover:underline truncate flex-1 cursor-pointer"
                            onClick={(e) => { e.stopPropagation(); router.push(`/documents/${doc.id}`); }}
                          >{doc.name}</span>
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

                {/* ── Branch: Key Themes / Thematic Clusters ── */}
                {themes.length > 0 && (
                  <div>
                    <button
                      onClick={() => toggleBranch('themes')}
                      className="w-full text-left px-4 py-2.5 hover:bg-navy-700 transition-colors flex items-center gap-2"
                    >
                      <span className="text-xs text-gray-500">{expandedBranches.has('themes') ? '▼' : '▶'}</span>
                      <span className="text-sm font-semibold text-gray-200">Thematic Clusters</span>
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

                {/* ── Branch: Geographic Regions ─────────────── */}
                {geoRegions.length > 0 && (
                  <div>
                    <button
                      onClick={() => toggleBranch('geo')}
                      className="w-full text-left px-4 py-2.5 hover:bg-navy-700 transition-colors flex items-center gap-2"
                    >
                      <span className="text-xs text-gray-500">{expandedBranches.has('geo') ? '▼' : '▶'}</span>
                      <span className="text-sm font-semibold text-gray-200">Geographic Regions</span>
                      <span className="ml-auto text-xs bg-navy-600 text-gray-400 px-2 py-0.5 rounded-full">{geoRegions.length}</span>
                    </button>
                    {expandedBranches.has('geo') && geoRegions.map(region => (
                      <div key={region.name}>
                        <button
                          onClick={() => toggleNode(`geo-${region.name}`)}
                          className="w-full text-left pl-8 pr-4 py-1.5 hover:bg-navy-700 transition-colors flex items-center gap-2"
                        >
                          <span className="text-xs text-gray-500">
                            {expandedNodes.has(`geo-${region.name}`) ? '▼' : '▶'}
                          </span>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded border ${entityTypeColor('Location')}`}>
                            {region.name}
                          </span>
                          <span className="ml-auto text-xs bg-navy-600 text-gray-400 px-2 py-0.5 rounded-full">
                            {region.count ?? region.entities?.length ?? 0}
                          </span>
                        </button>
                        {expandedNodes.has(`geo-${region.name}`) && region.entities?.map(entity => (
                          <button
                            key={entity.id}
                            onClick={() => selectEntity(entity)}
                            className={`w-full text-left pl-14 pr-4 py-1 text-xs transition-colors flex items-center gap-2 ${
                              selectedEntity?.id === entity.id
                                ? 'bg-accent-blue/20 text-accent-blue'
                                : 'text-gray-400 hover:bg-navy-700 hover:text-gray-200'
                            }`}
                          >
                            <span className="w-1.5 h-1.5 rounded-full bg-green-500/60 flex-none" />
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

                {/* ── Branch: Actors & Organizations ─────────── */}
                {actors.length > 0 && (
                  <div>
                    <button
                      onClick={() => toggleBranch('actors')}
                      className="w-full text-left px-4 py-2.5 hover:bg-navy-700 transition-colors flex items-center gap-2"
                    >
                      <span className="text-xs text-gray-500">{expandedBranches.has('actors') ? '▼' : '▶'}</span>
                      <span className="text-sm font-semibold text-gray-200">Actors &amp; Organizations</span>
                      <span className="ml-auto text-xs bg-navy-600 text-gray-400 px-2 py-0.5 rounded-full">{actors.length}</span>
                    </button>
                    {expandedBranches.has('actors') && actors.map(group => (
                      <div key={group.name}>
                        <button
                          onClick={() => toggleNode(`actor-${group.name}`)}
                          className="w-full text-left pl-8 pr-4 py-1.5 hover:bg-navy-700 transition-colors flex items-center gap-2"
                        >
                          <span className="text-xs text-gray-500">
                            {expandedNodes.has(`actor-${group.name}`) ? '▼' : '▶'}
                          </span>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded border ${entityTypeColor(group.entity_type || 'Organization')}`}>
                            {group.name}
                          </span>
                          <span className="ml-auto text-xs bg-navy-600 text-gray-400 px-2 py-0.5 rounded-full">
                            {group.count ?? group.entities?.length ?? 0}
                          </span>
                        </button>
                        {expandedNodes.has(`actor-${group.name}`) && group.entities?.map(entity => (
                          <button
                            key={entity.id}
                            onClick={() => selectEntity(entity)}
                            className={`w-full text-left pl-14 pr-4 py-1 text-xs transition-colors flex items-center gap-2 ${
                              selectedEntity?.id === entity.id
                                ? 'bg-accent-blue/20 text-accent-blue'
                                : 'text-gray-400 hover:bg-navy-700 hover:text-gray-200'
                            }`}
                          >
                            <span className="w-1.5 h-1.5 rounded-full bg-orange-500/60 flex-none" />
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

              </div>
            )}
          </div>
        </div>

        {/* ── Right Panel: Entity Context ───────────────────────── */}
        <div className="flex-1 overflow-y-auto p-8 relative">
          {!selectedEntity ? (
            <div className="flex items-center justify-center h-full text-gray-500 text-sm">
              <p>Select an entity from the topic tree to view its context.</p>
            </div>
          ) : contextLoading ? (
            <div className="flex items-center justify-center h-full text-gray-500 text-sm">
              <p>Loading entity context...</p>
            </div>
          ) : (
            <div className="space-y-8 max-w-4xl pb-16">

              {/* Entity header */}
              <div>
                <h1 className="text-3xl font-extrabold tracking-tight text-white leading-none mb-2">
                  {entityContext?.entity?.name || selectedEntity.name}
                </h1>
                <div className="flex gap-5 text-[10px] font-medium uppercase tracking-[0.2em] text-gray-500">
                  {entityContext?.source_documents && (
                    <span className="flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#adc6ff]" />
                      {entityContext.source_documents.length} Documents
                    </span>
                  )}
                  {entityContext?.connected_entities && (
                    <span className="flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#ffb95f]" />
                      {entityContext.connected_entities.length} Entities
                    </span>
                  )}
                  <span className="flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                    Active Analysis
                  </span>
                </div>
              </div>

              {/* AI Summary Card */}
              <div className="bg-[#161b2a]/50 rounded-xl p-8 border border-[#adc6ff]/10 relative overflow-hidden group">
                <div className="absolute top-0 right-0 p-6 opacity-5 group-hover:opacity-10 transition-opacity">
                  <span className="material-symbols-outlined text-7xl">auto_awesome</span>
                </div>
                <div className="flex items-center gap-2 mb-5">
                  <span className="material-symbols-outlined text-[#adc6ff] text-sm">auto_awesome</span>
                  <h3 className="font-bold text-[10px] uppercase tracking-widest text-[#adc6ff]">Sentinel AI Summary</h3>
                </div>
                <p className="text-[15px] leading-relaxed text-gray-200/90 max-w-3xl font-medium">
                  Analysis of {entityContext?.entity?.name || selectedEntity.name} ({entityContext?.entity?.entity_type || selectedEntity.entity_type}) reveals{' '}
                  {entityContext?.connected_entities?.length || 0} connected entities across{' '}
                  {entityContext?.source_documents?.length || 0} source documents.
                  {entityContext?.entity?.properties && Object.keys(entityContext.entity.properties).length > 0 && (
                    <> Key attributes include: {Object.entries(entityContext.entity.properties).slice(0, 3).map(([k, v]) => `${k}: ${String(v)}`).join(', ')}.</>
                  )}
                </p>
                <div className="mt-6">
                  <button
                    onClick={() => { if (!queryInput) setQueryInput(`Tell me more about ${selectedEntity.name}`); }}
                    className="bg-[#adc6ff]/10 hover:bg-[#adc6ff]/20 text-[#adc6ff] border border-[#adc6ff]/30 px-5 py-2.5 text-[10px] font-bold uppercase tracking-widest flex items-center gap-2 transition-all rounded-sm"
                  >
                    Ask Follow-up <span className="material-symbols-outlined text-sm">send</span>
                  </button>
                </div>
              </div>

              {/* Suggested Analytic Paths */}
              <div>
                <h3 className="font-bold text-[10px] uppercase tracking-widest text-gray-500/60 mb-5">Suggested Analytic Paths</h3>
                <div className="flex flex-wrap gap-3">
                  {[
                    `What connections exist between ${selectedEntity.name} and known threat infrastructure?`,
                    'Identify temporal patterns in entity activity',
                    'Map related entities to MITRE ATT&CK Matrix',
                  ].map((q, i) => (
                    <button
                      key={i}
                      onClick={() => { setQueryInput(q); }}
                      className="bg-[#252a39] hover:bg-[#343949] text-gray-200 text-[11px] font-medium py-2.5 px-5 rounded-full border border-[#424754]/10 transition-all text-left"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>

              {/* Key Entities & Taxonomy */}
              <div className="grid grid-cols-2 gap-12">
                <div>
                  <h3 className="font-bold text-[10px] uppercase tracking-widest text-gray-500/60 mb-5">Key Entities Detected</h3>
                  <div className="flex flex-wrap gap-2.5">
                    {(entityContext?.connected_entities || []).slice(0, 8).map((ce, i) => (
                      <span key={i} className="flex items-center gap-2 bg-[#2f3444] px-3.5 py-2 rounded-sm border border-[#424754]/20 hover:border-[#adc6ff]/50 cursor-default transition-all">
                        <span className="text-[11px] font-bold text-[#adc6ff]">{ce.name}</span>
                        <span className="text-[8px] font-black bg-[#adc6ff]/20 text-[#adc6ff] px-1.5 rounded-sm">{ce.entity_type}</span>
                      </span>
                    ))}
                  </div>
                </div>
                <div>
                  <h3 className="font-bold text-[10px] uppercase tracking-widest text-gray-500/60 mb-5">Related Taxonomy</h3>
                  <div className="flex flex-wrap gap-2.5">
                    <span className="px-4 py-2 bg-[#090e1c] text-gray-500 text-[10px] font-bold uppercase tracking-widest border border-[#424754]/10 hover:text-[#adc6ff] hover:border-[#adc6ff]/30 transition-all cursor-pointer">
                      {entityContext?.entity?.entity_type || selectedEntity.entity_type} Patterns
                    </span>
                    <span className="px-4 py-2 bg-[#090e1c] text-gray-500 text-[10px] font-bold uppercase tracking-widest border border-[#424754]/10 hover:text-[#adc6ff] hover:border-[#adc6ff]/30 transition-all cursor-pointer">
                      Network Analysis
                    </span>
                  </div>
                </div>
              </div>

              {/* Source Documents */}
              {entityContext?.source_documents && entityContext.source_documents.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-6">
                    <h3 className="font-bold text-[10px] uppercase tracking-widest text-gray-500/60">Primary Sources & Documents</h3>
                    <button className="text-[9px] font-bold text-[#adc6ff] hover:text-white uppercase tracking-widest transition-colors">View All Sources</button>
                  </div>
                  <div className="space-y-4">
                    {entityContext.source_documents.map((doc, i) => (
                      <div key={i} className="bg-[#090e1c] p-5 rounded-sm border border-[#424754]/10 hover:bg-[#161b2a] transition-all cursor-pointer group" onClick={() => router.push(`/documents/${doc.id}`)}>
                        <div className="flex justify-between items-start mb-2.5">
                          <div className="flex-1">
                            <h4 className="text-[15px] font-bold text-white group-hover:text-[#adc6ff] transition-colors mb-1">{doc.name}</h4>
                            <div className="flex items-center gap-4 text-[9px] text-gray-500 font-bold uppercase tracking-widest opacity-80">
                              <span className="flex items-center gap-1.5">
                                <span className="material-symbols-outlined text-[14px]">link</span>
                                Source Document
                              </span>
                            </div>
                          </div>
                          {doc.reliability && (
                            <div className={`text-[9px] font-black px-2.5 py-1 rounded-sm border ${reliabilityColor(doc.reliability)}`}>
                              {doc.reliability} RATING
                            </div>
                          )}
                        </div>
                        {doc.content && (
                          <p className="text-xs text-gray-400/60 line-clamp-2 leading-relaxed font-medium">{doc.content.substring(0, 300)}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Ask about this entity */}
              <div className="bg-[#1a1f2e] border border-[#252a39] rounded-lg p-5">
                <h3 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-3">Ask About This Entity</h3>
                <div className="flex gap-2">
                  <input
                    value={queryInput}
                    onChange={(e) => setQueryInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && askAboutEntity()}
                    placeholder={`Ask about ${selectedEntity.name}...`}
                    className="flex-1 bg-[#090e1c] border border-[#1a1f2e] rounded-sm px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[#adc6ff]"
                  />
                  <button
                    onClick={askAboutEntity}
                    disabled={queryLoading || !queryInput.trim()}
                    className="bg-[#adc6ff] hover:bg-[#4d8eff] text-[#002e6a] px-4 py-2 rounded-sm text-sm font-bold disabled:opacity-50 transition-colors"
                  >
                    {queryLoading ? 'Asking...' : 'Ask'}
                  </button>
                </div>
                {queryResult && (
                  <div className="mt-3 bg-[#090e1c] rounded-sm p-3 text-sm text-gray-300 whitespace-pre-wrap max-h-64 overflow-y-auto border border-[#1a1f2e]">
                    {queryResult}
                  </div>
                )}
              </div>

            </div>
          )}

          {/* Bottom status bar */}
          <div className="absolute bottom-0 left-0 w-full h-12 bg-[#161b2a]/90 backdrop-blur-xl border-t border-[#424754]/10 flex items-center justify-between px-8">
            <div className="flex items-center gap-6">
              <span className="text-[9px] font-bold uppercase text-gray-500/80 tracking-widest flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500 shadow-[0_0_8px_#22c55e]" />
                System Sync: Stable
              </span>
            </div>
            <div className="flex gap-6">
              <button className="text-[9px] font-bold uppercase text-[#adc6ff] hover:text-white transition-colors tracking-widest">Compare Documents</button>
              <button className="text-[9px] font-bold uppercase text-[#adc6ff] hover:text-white transition-colors tracking-widest">Export Selection</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
