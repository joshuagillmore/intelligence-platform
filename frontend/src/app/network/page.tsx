'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/Sidebar';
import GraphVisualization from '@/components/GraphVisualization';
import { useProject } from '@/lib/ProjectContext';
import { entitiesApi, graphApi, queryApi, llmApi, assessApi, notebookApi } from '@/lib/api';

interface Entity {
  id: string;
  name: string;
  entity_type: string;
  properties?: Record<string, unknown>;
  confidence?: number;
}

interface Relationship {
  id?: string;
  source_id: string;
  target_id: string;
  rel_type: string;
  confidence?: number;
  source_name?: string;
  target_name?: string;
}

interface GraphNode {
  id: string;
  name: string;
  entity_type: string;
}

interface GraphEdge {
  source_id: string;
  target_id: string;
  rel_type: string;
  confidence?: number;
  source: string;
  target: string;
}

interface EntityStats {
  entity: string;
  type: string;
  degree: number;
  betweenness: number;
  eigenvector: number;
  pagerank: number;
  closeness: number;
}

interface GraphStats {
  total_nodes: number;
  total_edges: number;
  density: number;
  connected_components: number;
  entity_statistics: EntityStats[];
}

const ENTITY_TYPES = ['All', 'Person', 'Organization', 'Location', 'ThreatActor', 'Document', 'IPAddress', 'Domain', 'Event', 'Hash', 'Vulnerability'];

const TYPE_COLORS: Record<string, string> = {
  Person: 'bg-orange-500',
  Organization: 'bg-blue-500',
  Location: 'bg-green-500',
  ThreatActor: 'bg-red-500',
  Document: 'bg-gray-500',
  IPAddress: 'bg-cyan-500',
  Domain: 'bg-purple-500',
  Event: 'bg-yellow-500',
  Hash: 'bg-pink-500',
  Vulnerability: 'bg-rose-500',
};

type SortKey = 'entity' | 'type' | 'degree' | 'betweenness' | 'eigenvector' | 'pagerank' | 'closeness';

function intensityClass(value: number, max: number): string {
  if (max === 0) return 'text-gray-400';
  const ratio = value / max;
  if (ratio > 0.8) return 'text-blue-300 font-bold';
  if (ratio > 0.6) return 'text-blue-400 font-semibold';
  if (ratio > 0.4) return 'text-blue-400';
  if (ratio > 0.2) return 'text-blue-500';
  return 'text-gray-400';
}

export default function NetworkPage() {
  const { activeProject } = useProject();
  const [entities, setEntities] = useState<Entity[]>([]);
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphEdges, setGraphEdges] = useState<GraphEdge[]>([]);
  const [selectedEntity, setSelectedEntity] = useState<Entity | null>(null);
  const [entityRelationships, setEntityRelationships] = useState<Relationship[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('All');
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState<Array<{ role: string; content: string }>>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [bottomPanelOpen, setBottomPanelOpen] = useState(true);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResult, setAiResult] = useState<string | null>(null);
  const [leftTab, setLeftTab] = useState<'entities' | 'statistics'>('entities');
  const [stats, setStats] = useState<GraphStats | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>('pagerank');
  const [sortAsc, setSortAsc] = useState(false);
  const [selectedEntities, setSelectedEntities] = useState<Entity[]>([]);
  const [pathResult, setPathResult] = useState<{ path: string[]; length: number } | null>(null);
  const [pathLoading, setPathLoading] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [highlightedNodeIds, setHighlightedNodeIds] = useState<Set<string>>(new Set());
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [highlightedEdgeKeys, setHighlightedEdgeKeys] = useState<Set<string>>(new Set());
  const [multiSelected, setMultiSelected] = useState<Entity[]>([]);
  const [assessModalOpen, setAssessModalOpen] = useState(false);
  const [assessJudgment, setAssessJudgment] = useState('');
  const [assessProbability, setAssessProbability] = useState(0.5);
  const [assessAnalyst, setAssessAnalyst] = useState('');
  const [assessLoading, setAssessLoading] = useState(false);
  const [islandThreshold, setIslandThreshold] = useState(0);
  const [filteredGraphNodes, setFilteredGraphNodes] = useState<GraphNode[]>([]);
  const [filteredGraphEdges, setFilteredGraphEdges] = useState<GraphEdge[]>([]);
  const [bottomTab, setBottomTab] = useState<'chat' | 'notebook'>('chat');
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [notes, setNotes] = useState<any[]>([]);
  const [noteTitle, setNoteTitle] = useState('');
  const [noteContent, setNoteContent] = useState('');
  const [noteType, setNoteType] = useState('observation');
  const [noteFormOpen, setNoteFormOpen] = useState(false);

  const loadGraph = useCallback(async () => {
    if (!activeProject) return;
    try {
      const res = await graphApi.full(activeProject.id);
      setGraphNodes(res.data.nodes || []);
      setGraphEdges(res.data.edges || []);
    } catch (e) {
      console.error('Failed to load graph', e);
    }
  }, [activeProject]);

  const loadEntities = useCallback(async () => {
    if (!activeProject) return;
    try {
      const res = await entitiesApi.search(
        activeProject.id,
        searchQuery || undefined,
        typeFilter === 'All' ? undefined : typeFilter
      );
      setEntities(res.data);
    } catch (e) {
      console.error('Failed to load entities', e);
    }
  }, [activeProject, searchQuery, typeFilter]);

  const loadStatistics = useCallback(async () => {
    if (!activeProject) return;
    try {
      const res = await graphApi.statistics(activeProject.id);
      setStats(res.data);
    } catch (e) {
      console.error('Failed to load statistics', e);
    }
  }, [activeProject]);

  useEffect(() => {
    loadGraph();
    loadEntities();
    loadStatistics();
  }, [loadGraph, loadEntities, loadStatistics]);

  // Island method: filter graph by degree threshold
  useEffect(() => {
    if (islandThreshold === 0) {
      setFilteredGraphNodes(graphNodes);
      setFilteredGraphEdges(graphEdges);
      return;
    }
    // Count degree per node
    const degreeMap: Record<string, number> = {};
    for (const node of graphNodes) {
      degreeMap[node.id] = 0;
    }
    for (const edge of graphEdges) {
      const srcId = edge.source_id || edge.source;
      const tgtId = edge.target_id || edge.target;
      if (degreeMap[srcId] !== undefined) degreeMap[srcId]++;
      if (degreeMap[tgtId] !== undefined) degreeMap[tgtId]++;
    }
    const visibleIds = new Set(graphNodes.filter(n => degreeMap[n.id] >= islandThreshold).map(n => n.id));
    setFilteredGraphNodes(graphNodes.filter(n => visibleIds.has(n.id)));
    setFilteredGraphEdges(graphEdges.filter(e => {
      const srcId = e.source_id || e.source;
      const tgtId = e.target_id || e.target;
      return visibleIds.has(srcId) && visibleIds.has(tgtId);
    }));
  }, [graphNodes, graphEdges, islandThreshold]);

  function handleShiftNodeClick(node: GraphNode, shiftKey: boolean) {
    if (shiftKey) {
      const entity = { id: node.id, name: node.name, entity_type: node.entity_type };
      setMultiSelected(prev => {
        const exists = prev.find(e => e.id === node.id);
        if (exists) return prev.filter(e => e.id !== node.id);
        return [...prev, entity];
      });
    }
  }

  async function submitAssessment() {
    if (!activeProject || !assessJudgment.trim()) return;
    setAssessLoading(true);
    try {
      if (multiSelected.length === 1) {
        await assessApi.create(multiSelected[0].id, {
          entity_id: multiSelected[0].id,
          project_id: activeProject.id,
          judgment: assessJudgment,
          probability: assessProbability,
          analyst: assessAnalyst || undefined,
        });
      } else if (multiSelected.length > 1) {
        await assessApi.multi({
          entity_ids: multiSelected.map(e => e.id),
          project_id: activeProject.id,
          judgment: assessJudgment,
          probability: assessProbability,
        });
      }
      setAssessModalOpen(false);
      setAssessJudgment('');
      setAssessProbability(0.5);
      setAssessAnalyst('');
      setAiResult('Assessment submitted successfully.');
    } catch {
      setAiResult('Failed to submit assessment.');
    } finally {
      setAssessLoading(false);
    }
  }

  async function selectEntity(entity: Entity) {
    setSelectedEntity(entity);
    setAiResult(null);
    try {
      const res = await entitiesApi.get(entity.id);
      if (res.data.relationships) {
        setEntityRelationships(res.data.relationships);
      }
      if (res.data.entity) {
        setSelectedEntity(res.data.entity);
      }
    } catch (e) {
      console.error('Failed to load entity details', e);
    }
  }

  function handleNodeClick(node: GraphNode, event?: MouseEvent) {
    const entity = { id: node.id, name: node.name, entity_type: node.entity_type };
    // Shift+click for multi-select
    if (event?.shiftKey) {
      handleShiftNodeClick(node, true);
      return;
    }
    selectEntity(entity);
    // Track selections for shortest path (toggle: add if not present, remove if already selected)
    setSelectedEntities(prev => {
      const exists = prev.find(e => e.id === node.id);
      if (exists) {
        return prev.filter(e => e.id !== node.id);
      }
      const updated = [...prev, entity];
      if (updated.length > 2) {
        return [updated[1], updated[2]];
      }
      return updated;
    });
  }

  async function findShortestPath() {
    if (selectedEntities.length !== 2) return;
    setPathLoading(true);
    setPathResult(null);
    setHighlightedNodeIds(new Set());
    setHighlightedEdgeKeys(new Set());
    try {
      const res = await entitiesApi.shortestPath(selectedEntities[0].id, selectedEntities[1].id);
      const path = res.data.path || res.data.nodes || [];
      const length = res.data.length ?? res.data.path_length ?? path.length - 1;
      setPathResult({ path, length });
      // Highlight path nodes
      const nodeIds = new Set<string>(path.map((p: string | { id: string }) => typeof p === 'string' ? p : p.id));
      setHighlightedNodeIds(nodeIds);
      // Highlight path edges
      const edgeKeys = new Set<string>();
      const pathIds = Array.from(nodeIds);
      for (let i = 0; i < pathIds.length - 1; i++) {
        edgeKeys.add(`${pathIds[i]}-${pathIds[i + 1]}`);
        edgeKeys.add(`${pathIds[i + 1]}-${pathIds[i]}`);
      }
      setHighlightedEdgeKeys(edgeKeys);
    } catch {
      setPathResult({ path: [], length: -1 });
    } finally {
      setPathLoading(false);
    }
  }

  function clearPath() {
    setSelectedEntities([]);
    setPathResult(null);
    setHighlightedNodeIds(new Set());
    setHighlightedEdgeKeys(new Set());
  }

  async function sendChat() {
    if (!chatInput.trim() || !activeProject) return;
    const userMsg = chatInput.trim();
    setChatInput('');
    setChatMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setChatLoading(true);
    try {
      const res = await queryApi.rag(activeProject.id, userMsg);
      const answer = res.data.answer || res.data.response || JSON.stringify(res.data);
      setChatMessages(prev => [...prev, { role: 'assistant', content: answer }]);
    } catch {
      setChatMessages(prev => [...prev, { role: 'assistant', content: 'Error processing query.' }]);
    } finally {
      setChatLoading(false);
    }
  }

  async function generateAssessment() {
    if (!selectedEntity || !activeProject) return;
    setAiLoading(true);
    try {
      const res = await assessApi.generate(selectedEntity.id, {
        entity_id: selectedEntity.id,
        project_id: activeProject.id,
        judgment: '',
        probability: 0.5,
      });
      setAiResult(res.data.assessment || res.data.error || JSON.stringify(res.data));
    } catch {
      setAiResult('Failed to generate assessment.');
    } finally {
      setAiLoading(false);
    }
  }

  async function generateAssessmentFromModal() {
    if (!activeProject || multiSelected.length === 0) return;
    setAssessLoading(true);
    try {
      const results: string[] = [];
      for (const entity of multiSelected) {
        const res = await assessApi.generate(entity.id, {
          entity_id: entity.id,
          project_id: activeProject.id,
          judgment: assessJudgment || undefined,
          probability: assessProbability,
        });
        results.push(res.data.assessment || res.data.error || 'No response');
      }
      setAssessModalOpen(false);
      setAssessJudgment('');
      setAssessProbability(0.5);
      setAssessAnalyst('');
      setAiResult(results.join('\n\n---\n\n'));
    } catch {
      setAiResult('Failed to generate AI assessment.');
    } finally {
      setAssessLoading(false);
    }
  }

  async function gapAnalysis() {
    if (!selectedEntity || !activeProject) return;
    setAiLoading(true);
    try {
      const res = await llmApi.query(
        [{ role: 'user', content: `Perform a gap analysis for entity "${selectedEntity.name}" (type: ${selectedEntity.entity_type}). Identify missing information, intelligence gaps, and recommended collection priorities.` }],
        'gap_analysis'
      );
      setAiResult(res.data.response || res.data.content || JSON.stringify(res.data));
    } catch {
      setAiResult('Failed to perform gap analysis.');
    } finally {
      setAiLoading(false);
    }
  }

  const loadNotes = useCallback(async () => {
    if (!activeProject) return;
    try {
      const res = await notebookApi.list(activeProject.id);
      setNotes(res.data || []);
    } catch (e) {
      console.error('Failed to load notes', e);
    }
  }, [activeProject]);

  useEffect(() => {
    loadNotes();
  }, [loadNotes]);

  async function createNote() {
    if (!activeProject || !noteTitle.trim() || !noteContent.trim()) return;
    try {
      await notebookApi.create({
        project_id: activeProject.id,
        title: noteTitle,
        content: noteContent,
        entity_ids: multiSelected.map(e => e.id),
        note_type: noteType,
      });
      setNoteTitle('');
      setNoteContent('');
      setNoteType('observation');
      setNoteFormOpen(false);
      loadNotes();
    } catch {
      console.error('Failed to create note');
    }
  }

  async function deleteNote(noteId: string) {
    try {
      await notebookApi.delete(noteId);
      loadNotes();
    } catch {
      console.error('Failed to delete note');
    }
  }

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  function getSortedStats(): EntityStats[] {
    if (!stats?.entity_statistics) return [];
    const arr = [...stats.entity_statistics];
    arr.sort((a, b) => {
      let va: string | number = a[sortKey];
      let vb: string | number = b[sortKey];
      if (typeof va === 'string' && typeof vb === 'string') {
        return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
      }
      va = Number(va); vb = Number(vb);
      return sortAsc ? va - vb : vb - va;
    });
    return arr;
  }

  function getMaxValues(): Record<string, number> {
    if (!stats?.entity_statistics || stats.entity_statistics.length === 0) {
      return { degree: 0, betweenness: 0, eigenvector: 0, pagerank: 0, closeness: 0 };
    }
    const es = stats.entity_statistics;
    return {
      degree: Math.max(...es.map(e => e.degree)),
      betweenness: Math.max(...es.map(e => e.betweenness)),
      eigenvector: Math.max(...es.map(e => e.eigenvector)),
      pagerank: Math.max(...es.map(e => e.pagerank)),
      closeness: Math.max(...es.map(e => e.closeness)),
    };
  }

  if (!activeProject) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="ml-56 flex-1 p-8">
          <h2 className="text-2xl font-bold mb-4">Network Analysis</h2>
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 text-center text-gray-500">
            <p className="text-lg mb-2">No Project Selected</p>
            <p className="text-sm">Go to Projects and select one to begin analysis.</p>
          </div>
        </main>
      </div>
    );
  }

  const sortedStats = getSortedStats();
  const maxVals = getMaxValues();
  const sortArrow = (key: SortKey) => sortKey === key ? (sortAsc ? ' ▲' : ' ▼') : '';

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="ml-56 flex-1 flex flex-col h-screen overflow-hidden">
        {/* Top bar */}
        <div className="flex-none px-4 py-2 border-b border-navy-600 bg-navy-800 flex items-center justify-between">
          <h2 className="text-lg font-bold">Network Analysis</h2>
          <div className="flex items-center gap-4">
            {selectedEntities.length > 0 && (
              <div className="flex items-center gap-2 text-xs">
                <span className="text-gray-400">Path:</span>
                {selectedEntities.map((e, i) => (
                  <span key={e.id}>
                    <span className="text-accent-blue">{e.name}</span>
                    {i < selectedEntities.length - 1 && <span className="text-gray-500 mx-1">&rarr;</span>}
                  </span>
                ))}
                {selectedEntities.length === 2 && (
                  <button
                    onClick={findShortestPath}
                    disabled={pathLoading}
                    className="ml-2 bg-accent-blue hover:bg-blue-600 text-white px-3 py-1 rounded text-xs disabled:opacity-50"
                  >
                    {pathLoading ? 'Finding...' : 'Find Path'}
                  </button>
                )}
                <button onClick={clearPath} className="text-gray-500 hover:text-gray-300 text-xs ml-1">Clear</button>
                {pathResult && pathResult.length >= 0 && (
                  <span className="text-green-400 ml-2">Path length: {pathResult.length}</span>
                )}
                {pathResult && pathResult.length < 0 && (
                  <span className="text-red-400 ml-2">No path found</span>
                )}
              </div>
            )}
            {multiSelected.length > 0 && (
              <div className="flex items-center gap-2 text-xs">
                <span className="text-gray-400">{multiSelected.length} selected</span>
                <button
                  onClick={() => setAssessModalOpen(true)}
                  className="bg-green-600 hover:bg-green-700 text-white px-3 py-1 rounded text-xs font-medium transition-colors"
                >
                  Generate Assessment
                </button>
                <button
                  onClick={() => setMultiSelected([])}
                  className="text-gray-500 hover:text-gray-300 text-xs"
                >
                  Clear
                </button>
              </div>
            )}
            <span className="text-sm text-gray-400">{filteredGraphNodes.length} nodes, {filteredGraphEdges.length} edges</span>
          </div>
        </div>

        {/* Main content area */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left sidebar - Entity list / Statistics */}
          <div className="w-64 flex-none bg-navy-800 border-r border-navy-600 flex flex-col overflow-hidden">
            {/* Tab toggle */}
            <div className="flex border-b border-navy-600">
              <button
                onClick={() => setLeftTab('entities')}
                className={`flex-1 py-2 text-xs font-medium transition-colors ${leftTab === 'entities' ? 'text-accent-blue border-b-2 border-accent-blue' : 'text-gray-400 hover:text-gray-200'}`}
              >
                Entities
              </button>
              <button
                onClick={() => setLeftTab('statistics')}
                className={`flex-1 py-2 text-xs font-medium transition-colors ${leftTab === 'statistics' ? 'text-accent-blue border-b-2 border-accent-blue' : 'text-gray-400 hover:text-gray-200'}`}
              >
                Statistics
              </button>
            </div>

            {leftTab === 'entities' ? (
              <>
                <div className="p-3 border-b border-navy-600 space-y-2">
                  <input
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search entities..."
                    className="w-full bg-navy-700 border border-navy-600 rounded px-2 py-1.5 text-xs focus:outline-none focus:border-accent-blue"
                  />
                  <select
                    value={typeFilter}
                    onChange={(e) => setTypeFilter(e.target.value)}
                    className="w-full bg-navy-700 border border-navy-600 rounded px-2 py-1.5 text-xs focus:outline-none focus:border-accent-blue"
                  >
                    {ENTITY_TYPES.map(t => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
                <div className="flex-1 overflow-y-auto">
                  {entities.map((entity) => (
                    <button
                      key={entity.id}
                      onClick={() => selectEntity(entity)}
                      className={`w-full text-left px-3 py-2 text-sm border-b border-navy-700 hover:bg-navy-700 transition-colors flex items-center gap-2 ${
                        selectedEntity?.id === entity.id ? 'bg-navy-700 text-accent-blue' : 'text-gray-300'
                      }`}
                    >
                      <span className={`w-2 h-2 rounded-full flex-none ${TYPE_COLORS[entity.entity_type] || 'bg-gray-500'}`} />
                      <span className="truncate">{entity.name}</span>
                      <span className="text-xs text-gray-500 flex-none">{entity.entity_type}</span>
                    </button>
                  ))}
                  {entities.length === 0 && (
                    <p className="text-xs text-gray-500 p-3">No entities found.</p>
                  )}
                </div>
              </>
            ) : (
              <div className="flex-1 overflow-y-auto p-3">
                {stats ? (
                  <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-2">
                      <div className="bg-navy-700 rounded p-2 text-center">
                        <div className="text-lg font-bold text-accent-blue">{stats.total_nodes}</div>
                        <div className="text-xs text-gray-400">Nodes</div>
                      </div>
                      <div className="bg-navy-700 rounded p-2 text-center">
                        <div className="text-lg font-bold text-accent-blue">{stats.total_edges}</div>
                        <div className="text-xs text-gray-400">Edges</div>
                      </div>
                      <div className="bg-navy-700 rounded p-2 text-center">
                        <div className="text-lg font-bold text-accent-blue">{typeof stats.density === 'number' ? stats.density.toFixed(4) : stats.density}</div>
                        <div className="text-xs text-gray-400">Density</div>
                      </div>
                      <div className="bg-navy-700 rounded p-2 text-center">
                        <div className="text-lg font-bold text-accent-blue">{stats.connected_components}</div>
                        <div className="text-xs text-gray-400">Components</div>
                      </div>
                    </div>
                    {/* Island Method */}
                    <div className="bg-navy-700 rounded p-3">
                      <label className="text-xs text-gray-400 font-medium block mb-2">
                        Island Method &mdash; Minimum Degree
                      </label>
                      <input
                        type="range"
                        min={0}
                        max={Math.max(maxVals.degree, 1)}
                        value={islandThreshold}
                        onChange={(e) => setIslandThreshold(Number(e.target.value))}
                        className="w-full accent-accent-blue"
                      />
                      <div className="flex justify-between text-xs text-gray-500 mt-1">
                        <span>0</span>
                        <span className="text-accent-blue font-medium">{islandThreshold}</span>
                        <span>{maxVals.degree}</span>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">
                        Showing nodes with degree &ge; {islandThreshold}
                      </p>
                    </div>
                    <p className="text-xs text-gray-500">See full statistics table in expanded view by clicking a column header to sort.</p>
                  </div>
                ) : (
                  <p className="text-xs text-gray-500">Loading statistics...</p>
                )}
              </div>
            )}
          </div>

          {/* Center - Graph or Statistics Table */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {leftTab === 'statistics' && stats?.entity_statistics ? (
              <div className="flex-1 overflow-auto p-4">
                <div className="flex items-center gap-4 mb-4">
                  <h3 className="text-sm font-semibold text-gray-400">Entity Statistics</h3>
                  <span className="text-xs text-gray-500">{sortedStats.length} entities</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-navy-600">
                        {([
                          ['entity', 'Entity'],
                          ['type', 'Type'],
                          ['degree', 'Degree'],
                          ['betweenness', 'Betweenness'],
                          ['eigenvector', 'Eigenvector'],
                          ['pagerank', 'PageRank'],
                          ['closeness', 'Closeness'],
                        ] as [SortKey, string][]).map(([key, label]) => (
                          <th
                            key={key}
                            onClick={() => handleSort(key)}
                            className="py-2 px-2 text-left text-gray-400 font-medium cursor-pointer hover:text-accent-blue select-none whitespace-nowrap"
                          >
                            {label}{sortArrow(key)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {sortedStats.map((row, i) => (
                        <tr key={i} className="border-b border-navy-700 hover:bg-navy-700/50">
                          <td className="py-1.5 px-2 text-gray-200 font-medium truncate max-w-[120px]">{row.entity}</td>
                          <td className="py-1.5 px-2 text-gray-400">{row.type}</td>
                          <td className={`py-1.5 px-2 ${intensityClass(row.degree, maxVals.degree)}`}>{row.degree}</td>
                          <td className={`py-1.5 px-2 ${intensityClass(row.betweenness, maxVals.betweenness)}`}>{row.betweenness.toFixed(4)}</td>
                          <td className={`py-1.5 px-2 ${intensityClass(row.eigenvector, maxVals.eigenvector)}`}>{row.eigenvector.toFixed(4)}</td>
                          <td className={`py-1.5 px-2 ${intensityClass(row.pagerank, maxVals.pagerank)}`}>{row.pagerank.toFixed(4)}</td>
                          <td className={`py-1.5 px-2 ${intensityClass(row.closeness, maxVals.closeness)}`}>{row.closeness.toFixed(4)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <>
                <div className="flex-1 relative">
                  {filteredGraphNodes.length > 0 ? (
                    <GraphVisualization
                      nodes={filteredGraphNodes}
                      edges={filteredGraphEdges}
                      onNodeClick={handleNodeClick}
                      selectedNodeId={selectedEntity?.id}
                    />
                  ) : (
                    <div className="flex items-center justify-center h-full text-gray-500">
                      <p>No graph data. Ingest documents to populate the knowledge graph.</p>
                    </div>
                  )}
                </div>

                {/* Bottom panel with tabs */}
                <div className={`flex-none border-t border-navy-600 bg-navy-800 transition-all ${bottomPanelOpen ? 'h-56' : 'h-8'}`}>
                  <div className="h-8 flex items-center border-b border-navy-600">
                    <button
                      onClick={() => setBottomPanelOpen(!bottomPanelOpen)}
                      className="px-3 h-full text-xs text-gray-400 hover:text-gray-200"
                    >
                      {bottomPanelOpen ? '\u25BC' : '\u25B2'}
                    </button>
                    {bottomPanelOpen && (
                      <div className="flex">
                        <button
                          onClick={() => setBottomTab('chat')}
                          className={`px-4 h-8 text-xs font-medium transition-colors ${bottomTab === 'chat' ? 'text-accent-blue border-b-2 border-accent-blue' : 'text-gray-400 hover:text-gray-200'}`}
                        >
                          RAG Chat
                        </button>
                        <button
                          onClick={() => setBottomTab('notebook')}
                          className={`px-4 h-8 text-xs font-medium transition-colors ${bottomTab === 'notebook' ? 'text-accent-blue border-b-2 border-accent-blue' : 'text-gray-400 hover:text-gray-200'}`}
                        >
                          Notebook
                        </button>
                      </div>
                    )}
                  </div>
                  {bottomPanelOpen && bottomTab === 'chat' && (
                    <div className="flex flex-col" style={{ height: 'calc(100% - 2rem)' }}>
                      <div className="flex-1 overflow-y-auto p-2 space-y-2">
                        {chatMessages.map((msg, i) => (
                          <div key={i} className={`text-xs p-2 rounded ${msg.role === 'user' ? 'bg-navy-700 text-gray-200' : 'bg-navy-600 text-gray-300'}`}>
                            <span className="font-bold text-accent-blue">{msg.role === 'user' ? 'You' : 'AI'}:</span> {msg.content}
                          </div>
                        ))}
                        {chatLoading && <div className="text-xs text-gray-400 p-2">Thinking...</div>}
                      </div>
                      <div className="flex gap-2 p-2 border-t border-navy-600">
                        <input
                          value={chatInput}
                          onChange={(e) => setChatInput(e.target.value)}
                          onKeyDown={(e) => e.key === 'Enter' && sendChat()}
                          placeholder="Ask about the knowledge graph..."
                          className="flex-1 bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs focus:outline-none focus:border-accent-blue"
                        />
                        <button
                          onClick={sendChat}
                          disabled={chatLoading}
                          className="bg-accent-blue hover:bg-blue-600 text-white px-3 py-1 rounded text-xs disabled:opacity-50"
                        >
                          Send
                        </button>
                      </div>
                    </div>
                  )}
                  {bottomPanelOpen && bottomTab === 'notebook' && (
                    <div className="flex flex-col" style={{ height: 'calc(100% - 2rem)' }}>
                      <div className="flex items-center justify-between px-3 py-1 border-b border-navy-600">
                        <span className="text-xs text-gray-400">{notes.length} notes</span>
                        <button
                          onClick={() => setNoteFormOpen(!noteFormOpen)}
                          className="text-xs bg-accent-blue hover:bg-blue-600 text-white px-3 py-1 rounded"
                        >
                          {noteFormOpen ? 'Cancel' : 'New Note'}
                        </button>
                      </div>
                      {noteFormOpen ? (
                        <div className="flex-1 overflow-y-auto p-3 space-y-2">
                          <input
                            value={noteTitle}
                            onChange={(e) => setNoteTitle(e.target.value)}
                            placeholder="Note title..."
                            className="w-full bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs focus:outline-none focus:border-accent-blue"
                          />
                          <textarea
                            value={noteContent}
                            onChange={(e) => setNoteContent(e.target.value)}
                            placeholder="Write your note..."
                            className="w-full bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs h-16 focus:outline-none focus:border-accent-blue resize-none"
                          />
                          <div className="flex items-center gap-2">
                            <select
                              value={noteType}
                              onChange={(e) => setNoteType(e.target.value)}
                              className="bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs focus:outline-none focus:border-accent-blue"
                            >
                              <option value="observation">Observation</option>
                              <option value="hypothesis">Hypothesis</option>
                              <option value="question">Question</option>
                              <option value="conclusion">Conclusion</option>
                            </select>
                            {multiSelected.length > 0 && (
                              <span className="text-xs text-gray-400">Linking {multiSelected.length} selected entities</span>
                            )}
                            <button
                              onClick={createNote}
                              disabled={!noteTitle.trim() || !noteContent.trim()}
                              className="ml-auto bg-green-600 hover:bg-green-700 text-white px-3 py-1 rounded text-xs disabled:opacity-50"
                            >
                              Save Note
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex-1 overflow-y-auto p-2 space-y-2">
                          {notes.length === 0 ? (
                            <p className="text-xs text-gray-500 text-center mt-4">No notebook entries yet.</p>
                          ) : (
                            notes.map((note) => (
                              <div key={note.id} className="bg-navy-700 rounded p-2 text-xs">
                                <div className="flex items-center justify-between mb-1">
                                  <span className="font-medium text-gray-200">{note.name}</span>
                                  <div className="flex items-center gap-2">
                                    <span className="text-xs px-1.5 py-0.5 rounded bg-navy-600 text-gray-400">
                                      {note.note_type || 'note'}
                                    </span>
                                    <button
                                      onClick={() => deleteNote(note.id)}
                                      className="text-red-400 hover:text-red-300 text-xs"
                                    >
                                      Delete
                                    </button>
                                  </div>
                                </div>
                                <p className="text-gray-400 truncate">{note.content || ''}</p>
                              </div>
                            ))
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>

          {/* Assessment modal */}
          {assessModalOpen && (
            <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
              <div className="bg-navy-800 border border-navy-600 rounded-lg p-6 w-full max-w-md">
                <h3 className="text-lg font-bold mb-4">Generate Assessment</h3>
                <p className="text-xs text-gray-400 mb-4">
                  Assessing {multiSelected.length} entit{multiSelected.length === 1 ? 'y' : 'ies'}:{' '}
                  {multiSelected.map(e => e.name).join(', ')}
                </p>
                <div className="space-y-3">
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">Judgment</label>
                    <textarea
                      value={assessJudgment}
                      onChange={(e) => setAssessJudgment(e.target.value)}
                      placeholder="Enter your analyst judgment..."
                      className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm h-24 focus:outline-none focus:border-accent-blue"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">Probability: {(assessProbability * 100).toFixed(0)}%</label>
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={assessProbability}
                      onChange={(e) => setAssessProbability(Number(e.target.value))}
                      className="w-full accent-accent-blue"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">Analyst (optional)</label>
                    <input
                      value={assessAnalyst}
                      onChange={(e) => setAssessAnalyst(e.target.value)}
                      placeholder="Analyst name..."
                      className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-blue"
                    />
                  </div>
                  <div className="flex gap-2 mt-4">
                    <button
                      onClick={submitAssessment}
                      disabled={assessLoading || !assessJudgment.trim()}
                      className="flex-1 bg-accent-blue hover:bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium disabled:opacity-50 transition-colors"
                    >
                      {assessLoading ? 'Submitting...' : 'Submit Assessment'}
                    </button>
                    <button
                      onClick={generateAssessmentFromModal}
                      disabled={assessLoading}
                      className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded text-sm font-medium disabled:opacity-50 transition-colors"
                    >
                      {assessLoading ? 'Generating...' : 'Generate with AI'}
                    </button>
                    <button
                      onClick={() => setAssessModalOpen(false)}
                      className="px-4 py-2 bg-navy-600 hover:bg-navy-700 text-gray-300 rounded text-sm transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Right sidebar - Detail panel */}
          <div className="w-80 flex-none bg-navy-800 border-l border-navy-600 overflow-y-auto">
            {selectedEntity ? (
              <div className="p-4 space-y-4">
                <div>
                  <h3 className="font-bold text-lg">{selectedEntity.name}</h3>
                  <span className={`inline-block mt-1 text-xs px-2 py-0.5 rounded ${TYPE_COLORS[selectedEntity.entity_type] || 'bg-gray-500'} text-white`}>
                    {selectedEntity.entity_type}
                  </span>
                </div>

                {selectedEntity.properties && Object.keys(selectedEntity.properties).length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-gray-400 mb-2">Properties</h4>
                    <div className="space-y-1">
                      {Object.entries(selectedEntity.properties).map(([key, value]) => (
                        <div key={key} className="text-xs">
                          <span className="text-gray-500">{key}:</span>{' '}
                          <span className="text-gray-300">{String(value)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {entityRelationships.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-gray-400 mb-2">Relationships ({entityRelationships.length})</h4>
                    <div className="space-y-1">
                      {entityRelationships.map((rel, i) => (
                        <div key={i} className="text-xs bg-navy-700 rounded p-2">
                          <span className="text-accent-blue">{rel.rel_type}</span>
                          {rel.confidence !== undefined && (
                            <span className="text-gray-500 ml-2">({(rel.confidence * 100).toFixed(0)}%)</span>
                          )}
                          <div className="text-gray-400 mt-0.5">
                            {rel.source_name || rel.source_id} &rarr; {rel.target_name || rel.target_id}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="space-y-2">
                  <h4 className="text-sm font-semibold text-gray-400">AI Actions</h4>
                  <button
                    onClick={generateAssessment}
                    disabled={aiLoading}
                    className="w-full bg-accent-blue hover:bg-blue-600 text-white px-3 py-2 rounded text-xs font-medium disabled:opacity-50"
                  >
                    {aiLoading ? 'Generating...' : 'Generate Assessment'}
                  </button>
                  <button
                    onClick={gapAnalysis}
                    disabled={aiLoading}
                    className="w-full bg-navy-600 hover:bg-navy-700 text-gray-200 px-3 py-2 rounded text-xs font-medium disabled:opacity-50 border border-navy-600"
                  >
                    Gap Analysis
                  </button>
                </div>

                {aiResult && (
                  <div>
                    <h4 className="text-sm font-semibold text-gray-400 mb-2">AI Result</h4>
                    <div className="bg-navy-700 rounded p-3 text-xs text-gray-300 whitespace-pre-wrap max-h-64 overflow-y-auto">
                      {aiResult}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="p-4 text-center text-gray-500 text-sm mt-8">
                <p>Select an entity from the list or click a node in the graph to see details.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
