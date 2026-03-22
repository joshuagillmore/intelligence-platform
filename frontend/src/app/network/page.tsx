/* eslint-disable @typescript-eslint/no-unused-vars */
'use client';
import { useEffect, useState, useCallback, useMemo, useRef, Suspense } from 'react';
import Sidebar from '@/components/Sidebar';
import GraphVisualization, { LayoutMode, ColorMode } from '@/components/GraphVisualization';
import { useProject } from '@/lib/ProjectContext';
import LoadingSpinner from '@/components/LoadingSpinner';
import { useRouter, useSearchParams } from 'next/navigation';
import { entitiesApi, graphApi, queryApi, llmApi, assessApi, notebookApi, watchlistApi, entityMgmtApi, documentsApi, snapshotsApi } from '@/lib/api';
import { getErrorMessage } from '@/lib/errorMessages';
import { collapseToCommunities } from '@/lib/graphLayout';
import { useNotifications } from '@/components/NotificationProvider';

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

function NetworkPageInner() {
  const { activeProject } = useProject();
  const { addNotification, updateNotification } = useNotifications();
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
  const [islandMetric, setIslandMetric] = useState<'degree' | 'betweenness' | 'eigenvector' | 'pagerank' | 'closeness'>('degree');
  const [filteredGraphNodes, setFilteredGraphNodes] = useState<GraphNode[]>([]);
  const [filteredGraphEdges, setFilteredGraphEdges] = useState<GraphEdge[]>([]);
  const [bottomTab, setBottomTab] = useState<'chat' | 'notebook'>('chat');
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [notes, setNotes] = useState<any[]>([]);
  const [noteTitle, setNoteTitle] = useState('');
  const [noteContent, setNoteContent] = useState('');
  const [noteType, setNoteType] = useState('observation');
  const [noteFormOpen, setNoteFormOpen] = useState(false);
  const [isWatchlisted, setIsWatchlisted] = useState(false);
  const [watchlistLoading, setWatchlistLoading] = useState(false);
  const [typeDropdownOpen, setTypeDropdownOpen] = useState(false);
  const [mergeModalOpen, setMergeModalOpen] = useState(false);
  const [mergePrimaryId, setMergePrimaryId] = useState<string>('');
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState<string | null>(null);
  // Relationship type filter
  const [hiddenRelTypes, setHiddenRelTypes] = useState<Set<string>>(new Set());
  const [relFilterOpen, setRelFilterOpen] = useState(false);
  // Confidence threshold
  const [confidenceThreshold, setConfidenceThreshold] = useState(0);
  // Layout mode
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('force');
  // Color mode and community data
  const [colorMode, setColorMode] = useState<ColorMode>('type');
  const [communityMap, setCommunityMap] = useState<Record<string, number>>({});
  const [collapseCommunities, setCollapseCommunities] = useState(false);
  // Evidence chain: source documents for selected entity
  const [evidenceDocs, setEvidenceDocs] = useState<Array<{ id: string; name: string; reliability_rating: string }>>([]);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  // Snapshots (bins)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [snapshots, setSnapshots] = useState<any[]>([]);
  const [snapshotNameInput, setSnapshotNameInput] = useState('');
  const [snapshotFormOpen, setSnapshotFormOpen] = useState(false);
  const [activeSnapshotId, setActiveSnapshotId] = useState<string | null>(null);
  // Relationship evidence
  const [relEvidenceOpen, setRelEvidenceOpen] = useState<Record<number, boolean>>({});
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [relEvidenceData, setRelEvidenceData] = useState<Record<number, any[]>>({});
  const [relEvidenceLoading, setRelEvidenceLoading] = useState<Record<number, boolean>>({});
  const networkRouter = useRouter();
  const searchParams = useSearchParams();
  const selectParam = searchParams.get('select');
  const graphNodesRef = useRef<GraphNode[]>([]);

  const loadGraph = useCallback(async () => {
    if (!activeProject) return;
    setGraphLoading(true);
    setGraphError(null);
    try {
      const res = await graphApi.full(activeProject.id);
      const nodes = res.data.nodes || [];
      graphNodesRef.current = nodes;
      setGraphNodes(nodes);
      setGraphEdges(res.data.edges || []);
    } catch (e) {
      console.error('Failed to load graph', e);
      setGraphError(getErrorMessage(e));
    } finally {
      setGraphLoading(false);
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
      const raw = res.data;
      // Normalize backend field names to frontend interface
      const normalized: GraphStats = {
        total_nodes: raw.total_nodes ?? raw.nodes ?? 0,
        total_edges: raw.total_edges ?? raw.edges ?? 0,
        density: raw.density ?? 0,
        connected_components: raw.connected_components ?? raw.components ?? 0,
        entity_statistics: (raw.entity_statistics ?? raw.entities ?? []).map((e: Record<string, unknown>) => ({
          entity: (e.entity ?? e.name ?? '') as string,
          type: (e.type ?? e.entity_type ?? '') as string,
          degree: (e.degree ?? 0) as number,
          betweenness: (e.betweenness ?? 0) as number,
          eigenvector: (e.eigenvector ?? 0) as number,
          pagerank: (e.pagerank ?? 0) as number,
          closeness: (e.closeness ?? 0) as number,
        })),
      };
      setStats(normalized);
    } catch (e) {
      console.error('Failed to load statistics', e);
    }
  }, [activeProject]);

  const loadCommunities = useCallback(async () => {
    if (!activeProject) return;
    try {
      const res = await graphApi.communities(activeProject.id);
      const data = res.data;
      const map: Record<string, number> = {};

      const extractFromItem = (item: Record<string, unknown>) => {
        const entityId = item.entity_id || item.id || item.node_id;
        const communityId = item.community ?? item.community_id ?? item.group;
        if (entityId !== undefined && communityId !== undefined) {
          map[String(entityId)] = Number(communityId);
        }
      };

      if (Array.isArray(data)) {
        for (const item of data) {
          extractFromItem(item);
        }
      } else if (data && typeof data === 'object') {
        // Could be { communities: [...] } or { nodes: [...] } or { members: { community_id: [entity_ids] } }
        const arr = data.communities || data.nodes || data.results || [];
        if (Array.isArray(arr) && arr.length > 0) {
          for (const item of arr) {
            // Handle nested format: { id: N, members: [{ id, name }] }
            if (item.members && Array.isArray(item.members)) {
              const cid = item.id ?? item.community_id ?? item.community;
              for (const member of item.members) {
                const eid = member.entity_id || member.id || member.node_id;
                if (eid !== undefined && cid !== undefined) {
                  map[String(eid)] = Number(cid);
                }
              }
            } else {
              extractFromItem(item);
            }
          }
        } else if (!Array.isArray(arr) || arr.length === 0) {
          // Try dict format: { entity_id_or_name: community_number }
          for (const [key, value] of Object.entries(data)) {
            if (key !== 'communities' && key !== 'nodes' && key !== 'results' && typeof value === 'number') {
              map[key] = value;
            }
          }
          // If keys are entity names, map them to IDs via graphNodes
          if (Object.keys(map).length > 0 && graphNodesRef.current.length > 0) {
            const nameToId: Record<string, string> = {};
            for (const n of graphNodesRef.current) {
              nameToId[n.name] = n.id;
            }
            const remapped: Record<string, number> = {};
            for (const [key, val] of Object.entries(map)) {
              if (nameToId[key]) {
                remapped[nameToId[key]] = val;
              } else {
                remapped[key] = val; // already an ID
              }
            }
            setCommunityMap(remapped);
            return;
          }
        }
      }
      setCommunityMap(map);
    } catch (e) {
      console.error('Failed to load communities', e);
    }
  }, [activeProject]);

  const loadSnapshots = useCallback(async () => {
    if (!activeProject) return;
    try {
      const res = await snapshotsApi.list(activeProject.id);
      setSnapshots(res.data.snapshots || []);
    } catch (e) {
      console.error('Failed to load snapshots', e);
    }
  }, [activeProject]);

  async function saveSnapshot() {
    if (!activeProject || !snapshotNameInput.trim() || multiSelected.length === 0) return;
    try {
      await snapshotsApi.create({
        project_id: activeProject.id,
        name: snapshotNameInput.trim(),
        entity_ids: multiSelected.map(e => e.id),
      });
      setSnapshotNameInput('');
      setSnapshotFormOpen(false);
      loadSnapshots();
    } catch {
      console.error('Failed to save snapshot');
    }
  }

  async function loadSnapshotView(snapshotId: string) {
    try {
      const res = await snapshotsApi.get(snapshotId);
      const snap = res.data;
      const snapEntityIds = new Set(snap.entity_ids || []);
      setFilteredGraphNodes(graphNodes.filter(n => snapEntityIds.has(n.id)));
      setFilteredGraphEdges(graphEdges.filter(e => {
        const srcId = e.source_id || e.source;
        const tgtId = e.target_id || e.target;
        return snapEntityIds.has(srcId) && snapEntityIds.has(tgtId);
      }));
      setActiveSnapshotId(snapshotId);
    } catch {
      console.error('Failed to load snapshot');
    }
  }

  function clearSnapshotView() {
    setActiveSnapshotId(null);
    // Re-trigger the filter effect by resetting island threshold
    setIslandThreshold(0);
  }

  async function deleteSnapshot(snapshotId: string) {
    try {
      await snapshotsApi.delete(snapshotId);
      if (activeSnapshotId === snapshotId) clearSnapshotView();
      loadSnapshots();
    } catch {
      console.error('Failed to delete snapshot');
    }
  }

  async function toggleRelEvidence(relIndex: number, rel: Relationship) {
    if (relEvidenceOpen[relIndex]) {
      setRelEvidenceOpen(prev => ({ ...prev, [relIndex]: false }));
      return;
    }
    setRelEvidenceOpen(prev => ({ ...prev, [relIndex]: true }));
    if (relEvidenceData[relIndex]) return; // Already loaded

    if (!activeProject) return;
    setRelEvidenceLoading(prev => ({ ...prev, [relIndex]: true }));
    try {
      const docsRes = await documentsApi.list(activeProject.id);
      const allDocs = docsRes.data.documents || [];
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const passages: any[] = [];
      const sourceName = rel.source_name || '';
      const targetName = rel.target_name || '';
      for (const doc of allDocs) {
        try {
          // Check for source entity
          if (sourceName) {
            const evRes = await documentsApi.evidence(doc.id, sourceName);
            if (evRes.data.count > 0) {
              // Also check if target is mentioned in same passages
              for (const p of evRes.data.passages) {
                if (targetName && p.text.includes(targetName)) {
                  passages.push({ ...p, document_name: doc.name, document_id: doc.id });
                }
              }
            }
          }
        } catch {
          // skip
        }
      }
      setRelEvidenceData(prev => ({ ...prev, [relIndex]: passages }));
    } catch {
      setRelEvidenceData(prev => ({ ...prev, [relIndex]: [] }));
    } finally {
      setRelEvidenceLoading(prev => ({ ...prev, [relIndex]: false }));
    }
  }

  useEffect(() => {
    loadGraph();
    loadEntities();
    loadStatistics();
    loadCommunities();
    loadSnapshots();
  }, [loadGraph, loadEntities, loadStatistics, loadCommunities, loadSnapshots]);

  // Auto-select entity from URL param (e.g., from Cyber "View in Graph")
  useEffect(() => {
    if (selectParam && graphNodes.length > 0) {
      const node = graphNodes.find(n => n.id === selectParam);
      if (node) {
        selectEntity({ id: node.id, name: node.name, entity_type: node.entity_type });
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectParam, graphNodes]);

  // Derive all unique relationship types from graph edges
  const allRelTypes = Array.from(new Set(graphEdges.map(e => e.rel_type).filter(Boolean))).sort();

  function toggleRelType(relType: string) {
    setHiddenRelTypes(prev => {
      const next = new Set(prev);
      if (next.has(relType)) {
        next.delete(relType);
      } else {
        next.add(relType);
      }
      return next;
    });
  }

  // Combined filter: island threshold + relationship type + confidence
  useEffect(() => {
    // First filter edges by relationship type and confidence
    let edges = graphEdges.filter(e => {
      if (hiddenRelTypes.has(e.rel_type)) return false;
      if (confidenceThreshold > 0 && (e.confidence === undefined || e.confidence < confidenceThreshold)) return false;
      return true;
    });

    // Then apply island threshold
    if (islandThreshold > 0) {
      // Build a metric value map for each node
      const metricMap: Record<string, number> = {};

      if (islandMetric === 'degree') {
        // Compute degree from current edges
        for (const node of graphNodes) {
          metricMap[node.id] = 0;
        }
        for (const edge of edges) {
          const srcId = edge.source_id || edge.source;
          const tgtId = edge.target_id || edge.target;
          if (metricMap[srcId] !== undefined) metricMap[srcId]++;
          if (metricMap[tgtId] !== undefined) metricMap[tgtId]++;
        }
      } else {
        // Use pre-computed stats from entity_statistics
        const statsLookup: Record<string, EntityStats> = {};
        if (stats?.entity_statistics) {
          for (const s of stats.entity_statistics) {
            statsLookup[s.entity] = s;
          }
        }
        for (const node of graphNodes) {
          const s = statsLookup[node.name];
          metricMap[node.id] = s ? s[islandMetric] : 0;
        }
      }

      const visibleIds = new Set(graphNodes.filter(n => metricMap[n.id] >= islandThreshold).map(n => n.id));
      setFilteredGraphNodes(graphNodes.filter(n => visibleIds.has(n.id)));
      edges = edges.filter(e => {
        const srcId = e.source_id || e.source;
        const tgtId = e.target_id || e.target;
        return visibleIds.has(srcId) && visibleIds.has(tgtId);
      });
    } else {
      // Still need to filter out orphan nodes if edges were removed
      const connectedIds = new Set<string>();
      for (const edge of edges) {
        connectedIds.add(String(edge.source_id || edge.source));
        connectedIds.add(String(edge.target_id || edge.target));
      }
      // Show all nodes if no edge filtering is active, otherwise show only connected + originally isolated
      if (hiddenRelTypes.size === 0 && confidenceThreshold === 0) {
        setFilteredGraphNodes(graphNodes);
      } else {
        // Show nodes that are connected after filtering, plus nodes that had no edges at all originally
        const originallyConnected = new Set<string>();
        for (const e of graphEdges) {
          originallyConnected.add(String(e.source_id || e.source));
          originallyConnected.add(String(e.target_id || e.target));
        }
        setFilteredGraphNodes(graphNodes.filter(n =>
          connectedIds.has(n.id) || !originallyConnected.has(n.id)
        ));
      }
    }
    setFilteredGraphEdges(edges);
  }, [graphNodes, graphEdges, islandThreshold, islandMetric, hiddenRelTypes, confidenceThreshold, stats]);

  // Community collapse: reduce many nodes into community super-nodes
  const displayData = useMemo(() => {
    if (collapseCommunities && filteredGraphNodes.length > 0) {
      return collapseToCommunities(
        filteredGraphNodes as unknown as Parameters<typeof collapseToCommunities>[0],
        filteredGraphEdges as unknown as Parameters<typeof collapseToCommunities>[1]
      );
    }
    return { nodes: filteredGraphNodes, edges: filteredGraphEdges };
  }, [collapseCommunities, filteredGraphNodes, filteredGraphEdges]);

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
    setTypeDropdownOpen(false);
    setEvidenceDocs([]);
    setRelEvidenceOpen({});
    setRelEvidenceData({});
    setRelEvidenceLoading({});
    checkWatchlistStatus(entity.id);
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
    // Load evidence chain: source documents mentioning this entity
    if (activeProject) {
      setEvidenceLoading(true);
      try {
        const docsRes = await documentsApi.list(activeProject.id);
        const allDocs = docsRes.data.documents || [];
        // Check which documents mention this entity by fetching evidence
        const matched: Array<{ id: string; name: string; reliability_rating: string }> = [];
        for (const doc of allDocs) {
          try {
            const evRes = await documentsApi.evidence(doc.id, entity.name);
            if (evRes.data.count > 0) {
              matched.push({ id: doc.id, name: doc.name, reliability_rating: doc.reliability_rating || '' });
            }
          } catch {
            // skip docs that fail
          }
        }
        setEvidenceDocs(matched);
      } catch {
        setEvidenceDocs([]);
      } finally {
        setEvidenceLoading(false);
      }
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
    const notifId = addNotification({
      type: 'processing',
      title: 'Generating Assessment',
      message: `Analyzing ${selectedEntity.name}...`,
    });
    try {
      const res = await assessApi.generate(selectedEntity.id, {
        entity_id: selectedEntity.id,
        project_id: activeProject.id,
        judgment: '',
        probability: 0.5,
      });
      setAiResult(res.data.assessment || res.data.error || JSON.stringify(res.data));
      updateNotification(notifId, {
        type: 'success',
        title: 'Assessment Ready',
        message: `Assessment for ${selectedEntity.name} complete.`,
      });
    } catch {
      setAiResult('Failed to generate assessment.');
      updateNotification(notifId, {
        type: 'error',
        title: 'Assessment Failed',
        message: `Failed to generate assessment for ${selectedEntity.name}.`,
      });
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

  const ENTITY_TYPE_OPTIONS = ['Person', 'Organization', 'Location', 'IPAddress', 'Domain', 'Hash', 'ThreatActor', 'TTP', 'Vulnerability', 'Malware', 'Campaign'];

  async function checkWatchlistStatus(entityId: string) {
    if (!activeProject) return;
    try {
      const res = await watchlistApi.list(activeProject.id);
      const watchedIds = (res.data || []).map((e: { id: string }) => e.id);
      setIsWatchlisted(watchedIds.includes(entityId));
    } catch {
      setIsWatchlisted(false);
    }
  }

  async function toggleWatchlist() {
    if (!activeProject || !selectedEntity) return;
    setWatchlistLoading(true);
    try {
      if (isWatchlisted) {
        await watchlistApi.remove(activeProject.id, selectedEntity.id);
        setIsWatchlisted(false);
      } else {
        await watchlistApi.add(activeProject.id, selectedEntity.id);
        setIsWatchlisted(true);
      }
    } catch {
      console.error('Failed to toggle watchlist');
    } finally {
      setWatchlistLoading(false);
    }
  }

  async function changeEntityType(newType: string) {
    if (!selectedEntity) return;
    try {
      await entityMgmtApi.updateType(selectedEntity.id, newType);
      setSelectedEntity({ ...selectedEntity, entity_type: newType });
      setTypeDropdownOpen(false);
      loadGraph();
      loadEntities();
    } catch {
      console.error('Failed to update entity type');
    }
  }

  async function mergeEntities() {
    if (!activeProject || multiSelected.length < 2 || !mergePrimaryId) return;
    try {
      const mergeIds = multiSelected.filter(e => e.id !== mergePrimaryId).map(e => e.id);
      await entityMgmtApi.merge(mergePrimaryId, mergeIds, activeProject.id);
      setMergeModalOpen(false);
      setMergePrimaryId('');
      setMultiSelected([]);
      loadGraph();
      loadEntities();
      loadStatistics();
      setAiResult('Entities merged successfully.');
    } catch {
      setAiResult('Failed to merge entities.');
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
    <div className="flex overflow-hidden" style={{ height: 'calc(100vh - 28px)' }}>
      <Sidebar />
      <div className="ml-56 flex-1 flex flex-col overflow-hidden" style={{ height: 'calc(100vh - 28px)' }}>
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
                {multiSelected.length >= 2 && (
                  <button
                    onClick={() => { setMergePrimaryId(multiSelected[0].id); setMergeModalOpen(true); }}
                    className="bg-purple-600 hover:bg-purple-700 text-white px-3 py-1 rounded text-xs font-medium transition-colors"
                  >
                    Merge Entities
                  </button>
                )}
                <button
                  onClick={() => setMultiSelected([])}
                  className="text-gray-500 hover:text-gray-300 text-xs"
                >
                  Clear
                </button>
              </div>
            )}
            <span className="text-sm text-gray-400">{displayData.nodes.length} nodes, {displayData.edges.length} edges{collapseCommunities ? ' (collapsed)' : ''}</span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  const allEntities = filteredGraphNodes.map(n => ({ id: n.id, name: n.name, entity_type: n.entity_type }));
                  setMultiSelected(allEntities);
                }}
                className="text-[10px] px-2 py-0.5 rounded bg-navy-600 text-gray-300 hover:bg-navy-500"
              >
                Select All
              </button>
              {selectedEntity && communityMap[selectedEntity.id] !== undefined && (
                <button
                  onClick={() => {
                    const cid = communityMap[selectedEntity.id];
                    const communityEntities = filteredGraphNodes
                      .filter(n => communityMap[n.id] === cid)
                      .map(n => ({ id: n.id, name: n.name, entity_type: n.entity_type }));
                    setMultiSelected(communityEntities);
                  }}
                  className="text-[10px] px-2 py-0.5 rounded bg-navy-600 text-gray-300 hover:bg-navy-500"
                >
                  Select Community ({filteredGraphNodes.filter(n => communityMap[n.id] === communityMap[selectedEntity.id]).length} members)
                </button>
              )}
              {multiSelected.length > 0 && (
                <>
                  <span className="text-[10px] text-accent-blue font-medium">{multiSelected.length} selected</span>
                  <button
                    onClick={() => setMultiSelected([])}
                    className="text-[10px] px-2 py-0.5 rounded bg-navy-600 text-gray-300 hover:bg-navy-500"
                  >
                    Clear
                  </button>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Toolbar row: filters, layout, coloring */}
        <div className="flex-none px-4 py-1.5 border-b border-navy-600 bg-navy-800/80 flex items-center gap-3 flex-wrap">
          {/* Relationship Filter */}
          <div className="relative">
            <button
              onClick={() => setRelFilterOpen(!relFilterOpen)}
              className="flex items-center gap-1.5 bg-navy-700 hover:bg-navy-600 border border-navy-600 rounded px-2.5 py-1 text-xs text-gray-300 transition-colors"
            >
              <span>Rel Filter</span>
              {hiddenRelTypes.size > 0 && (
                <span className="bg-accent-blue text-white rounded-full px-1.5 text-[10px] font-bold">{hiddenRelTypes.size}</span>
              )}
              <span className="text-gray-500 text-[10px]">{relFilterOpen ? '\u25B2' : '\u25BC'}</span>
            </button>
            {relFilterOpen && (
              <div className="absolute z-20 mt-1 bg-navy-700 border border-navy-600 rounded shadow-lg max-h-56 overflow-y-auto w-56">
                {allRelTypes.length === 0 ? (
                  <p className="text-xs text-gray-500 p-2">No relationships found.</p>
                ) : (
                  <>
                    <div className="flex items-center justify-between px-2 py-1 border-b border-navy-600">
                      <button
                        onClick={() => setHiddenRelTypes(new Set())}
                        className="text-[10px] text-accent-blue hover:underline"
                      >
                        Show All
                      </button>
                      <button
                        onClick={() => setHiddenRelTypes(new Set(allRelTypes))}
                        className="text-[10px] text-gray-400 hover:underline"
                      >
                        Hide All
                      </button>
                    </div>
                    {allRelTypes.map(rt => (
                      <label key={rt} className="flex items-center gap-2 px-2 py-1.5 text-xs hover:bg-navy-600 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={!hiddenRelTypes.has(rt)}
                          onChange={() => toggleRelType(rt)}
                          className="accent-accent-blue rounded"
                        />
                        <span className={hiddenRelTypes.has(rt) ? 'text-gray-500 line-through' : 'text-gray-200'}>{rt}</span>
                      </label>
                    ))}
                  </>
                )}
              </div>
            )}
          </div>

          {/* Active filter chips */}
          {hiddenRelTypes.size > 0 && (
            <div className="flex items-center gap-1 flex-wrap">
              {Array.from(hiddenRelTypes).map(rt => (
                <button
                  key={rt}
                  onClick={() => toggleRelType(rt)}
                  className="flex items-center gap-1 bg-red-900/40 text-red-300 border border-red-800/50 rounded-full px-2 py-0.5 text-[10px] hover:bg-red-900/60 transition-colors"
                >
                  <span>{rt}</span>
                  <span className="font-bold">&times;</span>
                </button>
              ))}
            </div>
          )}

          {/* Divider */}
          <div className="w-px h-5 bg-navy-600" />

          {/* Layout Selector */}
          <div className="flex items-center gap-1.5">
            <label className="text-xs text-gray-400">Layout</label>
            <div className="flex rounded overflow-hidden border border-navy-600">
              {([
                ['force', 'Force-Directed'],
                ['radial', 'Radial'],
                ['hierarchical', 'Hierarchical'],
              ] as [LayoutMode, string][]).map(([mode, label]) => (
                <button
                  key={mode}
                  onClick={() => setLayoutMode(mode)}
                  className={`px-2 py-1 text-[11px] transition-colors ${
                    layoutMode === mode
                      ? 'bg-accent-blue text-white'
                      : 'bg-navy-700 text-gray-400 hover:bg-navy-600 hover:text-gray-200'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Divider */}
          <div className="w-px h-5 bg-navy-600" />

          {/* Color Mode Toggle */}
          <div className="flex items-center gap-1.5">
            <label className="text-xs text-gray-400">Color by</label>
            <div className="flex rounded overflow-hidden border border-navy-600">
              {([
                ['type', 'Type'],
                ['community', 'Community'],
              ] as [ColorMode, string][]).map(([mode, label]) => (
                <button
                  key={mode}
                  onClick={() => setColorMode(mode)}
                  className={`px-2 py-1 text-[11px] transition-colors ${
                    colorMode === mode
                      ? 'bg-accent-blue text-white'
                      : 'bg-navy-700 text-gray-400 hover:bg-navy-600 hover:text-gray-200'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Divider */}
          <div className="w-px h-5 bg-navy-600" />

          {/* Community Collapse Toggle */}
          <button
            onClick={() => setCollapseCommunities(!collapseCommunities)}
            className={`px-3 py-1 rounded text-xs transition-colors ${
              collapseCommunities ? 'bg-accent-blue text-white' : 'bg-navy-700 text-gray-300 border border-navy-600 hover:bg-navy-600'
            }`}
          >
            {collapseCommunities ? 'Expand Communities' : 'Collapse Communities'}
          </button>
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
                {/* Snapshots (Bins) Section */}
                <div className="flex-none border-t border-navy-600">
                  <div className="px-3 py-2 flex items-center justify-between">
                    <h4 className="text-xs font-semibold text-gray-400">Snapshots</h4>
                    {activeSnapshotId && (
                      <button
                        onClick={clearSnapshotView}
                        className="text-[10px] text-accent-blue hover:underline"
                      >
                        Clear Filter
                      </button>
                    )}
                  </div>
                  {multiSelected.length > 0 && (
                    <div className="px-3 pb-2">
                      {snapshotFormOpen ? (
                        <div className="space-y-1.5">
                          <input
                            value={snapshotNameInput}
                            onChange={(e) => setSnapshotNameInput(e.target.value)}
                            placeholder="Snapshot name..."
                            className="w-full bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs focus:outline-none focus:border-accent-blue"
                            onKeyDown={(e) => e.key === 'Enter' && saveSnapshot()}
                          />
                          <div className="flex gap-1">
                            <button
                              onClick={saveSnapshot}
                              disabled={!snapshotNameInput.trim()}
                              className="flex-1 bg-accent-blue hover:bg-blue-600 text-white px-2 py-1 rounded text-[10px] font-medium disabled:opacity-50"
                            >
                              Save ({multiSelected.length} entities)
                            </button>
                            <button
                              onClick={() => setSnapshotFormOpen(false)}
                              className="px-2 py-1 bg-navy-600 hover:bg-navy-700 text-gray-300 rounded text-[10px]"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <button
                          onClick={() => setSnapshotFormOpen(true)}
                          className="w-full bg-navy-700 hover:bg-navy-600 border border-navy-600 text-gray-300 px-2 py-1.5 rounded text-xs transition-colors"
                        >
                          Save Snapshot ({multiSelected.length} selected)
                        </button>
                      )}
                    </div>
                  )}
                  <div className="max-h-40 overflow-y-auto">
                    {snapshots.length === 0 ? (
                      <p className="text-[10px] text-gray-500 px-3 pb-2">No snapshots saved.</p>
                    ) : (
                      snapshots.map((snap) => (
                        <div
                          key={snap.id}
                          className={`flex items-center gap-1.5 px-3 py-1.5 text-xs border-b border-navy-700 hover:bg-navy-700 cursor-pointer transition-colors ${
                            activeSnapshotId === snap.id ? 'bg-navy-700 text-accent-blue' : 'text-gray-300'
                          }`}
                        >
                          <div
                            className="flex-1 min-w-0"
                            onClick={() => loadSnapshotView(snap.id)}
                          >
                            <div className="truncate font-medium">{snap.name}</div>
                            <div className="text-[10px] text-gray-500">
                              {snap.entity_count} entities &middot; {new Date(snap.created_at).toLocaleDateString()}
                            </div>
                          </div>
                          <button
                            onClick={(e) => { e.stopPropagation(); deleteSnapshot(snap.id); }}
                            className="text-red-400 hover:text-red-300 text-[10px] flex-none"
                          >
                            Del
                          </button>
                        </div>
                      ))
                    )}
                  </div>
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
                    {/* Min Confidence */}
                    <div className="bg-navy-700 rounded p-3">
                      <label className="text-xs text-gray-400 font-medium">Min Confidence</label>
                      <input
                        type="range"
                        min={0}
                        max={1}
                        step={0.05}
                        value={confidenceThreshold}
                        onChange={(e) => setConfidenceThreshold(Number(e.target.value))}
                        className="w-full accent-accent-blue mt-2"
                      />
                      <div className="flex justify-between text-xs text-gray-500 mt-1">
                        <span>0</span>
                        <span className="text-accent-blue font-medium">{confidenceThreshold.toFixed(2)}</span>
                        <span>1.00</span>
                      </div>
                    </div>
                    {/* Island Method */}
                    <div className="bg-navy-700 rounded p-3">
                      <div className="flex items-center justify-between mb-2">
                        <label className="text-xs text-gray-400 font-medium">
                          Island Method
                        </label>
                        <select
                          value={islandMetric}
                          onChange={(e) => {
                            setIslandMetric(e.target.value as typeof islandMetric);
                            setIslandThreshold(0);
                          }}
                          className="bg-navy-800 border border-navy-600 rounded px-2 py-0.5 text-xs text-gray-300"
                        >
                          <option value="degree">Degree</option>
                          <option value="betweenness">Betweenness</option>
                          <option value="eigenvector">Eigenvector</option>
                          <option value="pagerank">PageRank</option>
                          <option value="closeness">Closeness</option>
                        </select>
                      </div>
                      <input
                        type="range"
                        min={0}
                        max={islandMetric === 'degree' ? Math.max(maxVals.degree, 1) : Math.max(maxVals[islandMetric], 0.01)}
                        step={islandMetric === 'degree' ? 1 : islandMetric === 'pagerank' ? 0.001 : 0.01}
                        value={islandThreshold}
                        onChange={(e) => setIslandThreshold(Number(e.target.value))}
                        className="w-full accent-accent-blue"
                      />
                      <div className="flex justify-between text-xs text-gray-500 mt-1">
                        <span>0</span>
                        <span className="text-accent-blue font-medium">
                          {islandMetric === 'degree' ? islandThreshold : islandThreshold.toFixed(islandMetric === 'pagerank' ? 3 : 2)}
                        </span>
                        <span>{islandMetric === 'degree' ? maxVals.degree : maxVals[islandMetric].toFixed(islandMetric === 'pagerank' ? 3 : 2)}</span>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">
                        Showing nodes with {islandMetric} &ge; {islandMetric === 'degree' ? islandThreshold : islandThreshold.toFixed(islandMetric === 'pagerank' ? 3 : 2)}
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
                  {graphLoading ? (
                    <div className="flex items-center justify-center h-full">
                      <LoadingSpinner size="lg" />
                    </div>
                  ) : graphError ? (
                    <div className="flex items-center justify-center h-full text-red-400">
                      <div className="text-center">
                        <p className="mb-2">{graphError}</p>
                        <button onClick={loadGraph} className="text-xs text-accent-blue hover:underline">Retry</button>
                      </div>
                    </div>
                  ) : filteredGraphNodes.length > 0 ? (
                    <GraphVisualization
                      nodes={displayData.nodes as GraphNode[]}
                      edges={displayData.edges as GraphEdge[]}
                      onNodeClick={handleNodeClick}
                      selectedNodeId={selectedEntity?.id}
                      layout={layoutMode}
                      colorMode={colorMode}
                      communityMap={communityMap}
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

          {/* Merge modal */}
          {mergeModalOpen && (
            <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
              <div className="bg-navy-800 border border-navy-600 rounded-lg p-6 w-full max-w-md">
                <h3 className="text-lg font-bold mb-4">Merge Entities</h3>
                <p className="text-xs text-gray-400 mb-4">
                  Select the primary entity. All other selected entities will be merged into it.
                </p>
                <div className="space-y-2 mb-4">
                  {multiSelected.map((e) => (
                    <label key={e.id} className="flex items-center gap-2 text-sm cursor-pointer p-2 rounded hover:bg-navy-700">
                      <input
                        type="radio"
                        name="mergePrimary"
                        checked={mergePrimaryId === e.id}
                        onChange={() => setMergePrimaryId(e.id)}
                        className="accent-accent-blue"
                      />
                      <span className={`w-2 h-2 rounded-full ${TYPE_COLORS[e.entity_type] || 'bg-gray-500'}`} />
                      <span className="text-gray-200">{e.name}</span>
                      <span className="text-xs text-gray-500">{e.entity_type}</span>
                      {mergePrimaryId === e.id && <span className="text-xs text-accent-blue ml-auto">Primary</span>}
                    </label>
                  ))}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={mergeEntities}
                    disabled={!mergePrimaryId}
                    className="flex-1 bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded text-sm font-medium disabled:opacity-50 transition-colors"
                  >
                    Merge
                  </button>
                  <button
                    onClick={() => setMergeModalOpen(false)}
                    className="px-4 py-2 bg-navy-600 hover:bg-navy-700 text-gray-300 rounded text-sm transition-colors"
                  >
                    Cancel
                  </button>
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
                      {entityRelationships.map((rel, i) => {
                        const conf = rel.confidence;
                        const confBarColor = conf !== undefined
                          ? conf >= 0.8 ? 'bg-green-500'
                          : conf >= 0.5 ? 'bg-accent-blue'
                          : conf >= 0.3 ? 'bg-yellow-500'
                          : 'bg-red-500'
                          : '';
                        return (
                        <div key={i} className="text-xs bg-navy-700 rounded p-2">
                          <span className="text-accent-blue">{rel.rel_type}</span>
                          {conf !== undefined && (
                            <span className="text-gray-500 ml-2">({(conf * 100).toFixed(0)}%)</span>
                          )}
                          {conf !== undefined && (
                            <div className="w-full bg-navy-800 rounded-full h-1.5 mt-1">
                              <div className={`${confBarColor} h-1.5 rounded-full transition-all`} style={{ width: `${conf * 100}%` }} />
                            </div>
                          )}
                          <div className="text-gray-400 mt-0.5">
                            {rel.source_name || rel.source_id} &rarr; {rel.target_name || rel.target_id}
                          </div>
                          <button
                            onClick={() => toggleRelEvidence(i, rel)}
                            className="text-[10px] text-accent-blue hover:underline mt-1"
                          >
                            {relEvidenceOpen[i] ? 'Hide Evidence' : 'Show Evidence'}
                          </button>
                          {relEvidenceOpen[i] && (
                            <div className="mt-1.5 space-y-1">
                              {relEvidenceLoading[i] ? (
                                <p className="text-[10px] text-gray-500">Loading evidence...</p>
                              ) : relEvidenceData[i] && relEvidenceData[i].length > 0 ? (
                                relEvidenceData[i].map((passage: { text: string; document_name: string; document_id: string }, pi: number) => (
                                  <div key={pi} className="bg-navy-800 rounded p-1.5 text-[10px]">
                                    <div className="text-gray-500 mb-0.5 font-medium">{passage.document_name}</div>
                                    <div className="text-gray-400 leading-relaxed">&ldquo;{passage.text}&rdquo;</div>
                                  </div>
                                ))
                              ) : (
                                <p className="text-[10px] text-gray-500">No co-occurring passages found in source documents.</p>
                              )}
                            </div>
                          )}
                        </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Evidence Chain: Source Documents */}
                <div>
                  <h4 className="text-sm font-semibold text-gray-400 mb-2">Evidence Chain</h4>
                  {evidenceLoading ? (
                    <p className="text-xs text-gray-500">Loading source documents...</p>
                  ) : evidenceDocs.length > 0 ? (
                    <div className="space-y-1">
                      {evidenceDocs.map((doc) => (
                        <div
                          key={doc.id}
                          onClick={() => networkRouter.push(`/documents/${doc.id}`)}
                          className="text-xs bg-navy-700 rounded p-2 cursor-pointer hover:bg-navy-600 transition-colors flex items-center gap-2"
                        >
                          <span className="text-accent-blue hover:underline flex-1 truncate">{doc.name}</span>
                          {doc.reliability_rating && (
                            <span className="text-[10px] px-1 py-0.5 rounded bg-navy-600 text-gray-400 flex-none">
                              {doc.reliability_rating}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-gray-500">No source documents found.</p>
                  )}
                </div>

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

                <div className="space-y-2">
                  <h4 className="text-sm font-semibold text-gray-400">Entity Actions</h4>
                  <button
                    onClick={toggleWatchlist}
                    disabled={watchlistLoading}
                    className={`w-full px-3 py-2 rounded text-xs font-medium transition-colors disabled:opacity-50 ${
                      isWatchlisted
                        ? 'bg-yellow-600 hover:bg-yellow-700 text-white'
                        : 'bg-navy-600 hover:bg-navy-700 text-gray-200 border border-navy-600'
                    }`}
                  >
                    {watchlistLoading ? 'Updating...' : isWatchlisted ? '\u2605 Remove from Watchlist' : '\u2606 Add to Watchlist'}
                  </button>

                  <div className="relative">
                    <button
                      onClick={() => setTypeDropdownOpen(!typeDropdownOpen)}
                      className="w-full bg-navy-600 hover:bg-navy-700 text-gray-200 px-3 py-2 rounded text-xs font-medium border border-navy-600 text-left flex justify-between items-center"
                    >
                      <span>Change Type: {selectedEntity.entity_type}</span>
                      <span className="text-gray-500">{typeDropdownOpen ? '\u25B2' : '\u25BC'}</span>
                    </button>
                    {typeDropdownOpen && (
                      <div className="absolute z-10 mt-1 w-full bg-navy-700 border border-navy-600 rounded shadow-lg max-h-48 overflow-y-auto">
                        {ENTITY_TYPE_OPTIONS.map((t) => (
                          <button
                            key={t}
                            onClick={() => changeEntityType(t)}
                            className={`w-full text-left px-3 py-1.5 text-xs hover:bg-navy-600 transition-colors ${
                              selectedEntity.entity_type === t ? 'text-accent-blue font-medium' : 'text-gray-300'
                            }`}
                          >
                            {t}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
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

export default function NetworkPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-screen"><LoadingSpinner size="lg" /></div>}>
      <NetworkPageInner />
    </Suspense>
  );
}
