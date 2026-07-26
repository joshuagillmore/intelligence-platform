/* eslint-disable @typescript-eslint/no-unused-vars */
'use client';
import { useEffect, useState, useCallback, useMemo, useRef, Suspense } from 'react';
import Sidebar from '@/components/Sidebar';
import GraphVisualization, { LayoutMode, ColorMode } from '@/components/GraphVisualization';
import TemporalSlider from '@/components/TemporalSlider';
import { useProject } from '@/lib/ProjectContext';
import LoadingSpinner from '@/components/LoadingSpinner';
import { useRouter, useSearchParams } from 'next/navigation';
import { entitiesApi, graphApi, queryApi, llmApi, assessApi, analysisApi, watchlistApi, entityMgmtApi, documentsApi, snapshotsApi, entityFields } from '@/lib/api';
import { useAssistant } from '@/lib/AssistantContext';
import { TYPE_COLOR_CLASS as TYPE_COLORS } from '@/lib/entityStyles';
import EnrichmentPanel from '@/components/EnrichmentPanel';
import EvidenceChain from '@/components/EvidenceChain';
import { getErrorMessage } from '@/lib/errorMessages';
import { collapseToCommunities } from '@/lib/graphLayout';
import { useNotifications } from '@/components/NotificationProvider';
import Markdown from '@/components/Markdown';

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
  evidence?: string;
  // Provenance carried on the edge — see components/EvidenceChain.
  source_doc_id?: string;
  admiralty_rating?: string;
  corroboration_count?: number;
  corroboration_agreement?: string;
  method?: string;
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
  first_seen?: string;
  last_seen?: string;
  source: string;
  target: string;
  evidence?: string;
  [key: string]: unknown;
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

const TYPE_LABELS: Record<string, string> = {
  TTP: 'Tactics, Techniques & Procedures',
  IPAddress: 'IP Address',
  ThreatActor: 'Threat Actor',
  GovernmentAgency: 'Government Agency',
  MilitaryUnit: 'Military Unit',
};
function formatEntityType(type: string): string {
  return TYPE_LABELS[type] || type;
}

function formatRelType(rel: string): string {
  return rel.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()).replace(/\bOf\b/g, 'of').replace(/\bOn\b/g, 'on');
}

// TYPE_COLORS imported from '@/lib/entityStyles' (single source of truth)

interface StructuralHoleEntry {
  id: string;
  name: string;
  entity_type: string;
  constraint: number;
  effective_size: number;
  degree: number;
  is_broker: boolean;
}

interface EgoNetworkData {
  center: string;
  hops: number;
  node_count: number;
  edge_count: number;
  nodes: Array<{ id: string; name: string; entity_type: string; hop_distance: number; local_pagerank: number; local_betweenness: number }>;
  edges: Array<{ source_id: string; target_id: string; rel_type: string; confidence: number; weight: number }>;
}

interface InfluenceStep {
  step: number;
  newly_activated: Array<{ id: string; name: string; entity_type: string }>;
  cumulative_count: number;
}

interface InfluenceResult {
  seeds: string[];
  steps: InfluenceStep[];
  total_activated: number;
  reach_ratio: number;
  total_nodes: number;
}

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
  const [activeTypeFilters, setActiveTypeFilters] = useState<Set<string>>(new Set());
  const [typeFilterOpen, setTypeFilterOpen] = useState(false);
  // Chat + notebook moved to the shared, app-wide AssistantPanel (see
  // components/AssistantPanel.tsx). This page only feeds it the current
  // multi-selection so new notebook entries stay linked to those entities.
  const { setLinkedEntities } = useAssistant();
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResult, setAiResult] = useState<string | null>(null);
  const [leftTab, setLeftTab] = useState<'entities' | 'statistics' | 'analysis'>('entities');
  const [expandedEntityTypes, setExpandedEntityTypes] = useState<Set<string>>(new Set());
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
  // Relationship evidence (rel.evidence is persisted on the edge — just toggle visibility, no fetch)
  const [relEvidenceOpen, setRelEvidenceOpen] = useState<Record<number, boolean>>({});
  // De-emphasize noise-tier ASSOCIATED_WITH edges in the Edge Overview stats
  const [showLowSignalRel, setShowLowSignalRel] = useState(false);
  const [mobileLeftOpen, setMobileLeftOpen] = useState(false);
  const [mobileRightOpen, setMobileRightOpen] = useState(false);
  // Ego highlight depth for graph selection
  const [egoHighlightDepth, setEgoHighlightDepth] = useState(1);
  // SNA advanced analysis state
  const [structuralHoles, setStructuralHoles] = useState<StructuralHoleEntry[]>([]);
  const [egoNetwork, setEgoNetwork] = useState<EgoNetworkData | null>(null);
  const [egoLoading, setEgoLoading] = useState(false);
  const [egoHops, setEgoHops] = useState(2);
  const [influenceResult, setInfluenceResult] = useState<InfluenceResult | null>(null);
  const [influenceLoading, setInfluenceLoading] = useState(false);
  const [influenceSteps, setInfluenceSteps] = useState(3);
  const [influenceThreshold, setInfluenceThreshold] = useState(0.3);
  // Temporal range filter for graph edges (P0.5)
  const [temporalRange, setTemporalRange] = useState<[string | null, string | null]>([null, null]);
  // Selected edge for detail panel
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  // Undo/redo history stack
  const [undoStack, setUndoStack] = useState<Array<{ hiddenRelTypes: Set<string>; confidenceThreshold: number; islandThreshold: number }>>([]);
  const [redoStack, setRedoStack] = useState<Array<{ hiddenRelTypes: Set<string>; confidenceThreshold: number; islandThreshold: number }>>([]);
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

  const loadStructuralHoles = useCallback(async () => {
    if (!activeProject) return;
    try {
      const res = await graphApi.structuralHoles(activeProject.id, 20);
      setStructuralHoles(res.data || []);
    } catch (e) {
      console.error('Failed to load structural holes', e);
    }
  }, [activeProject]);

  async function loadEgoNetwork(entityId: string) {
    if (!activeProject) return;
    setEgoLoading(true);
    try {
      const res = await graphApi.egoNetwork(entityId, activeProject.id, egoHops);
      setEgoNetwork(res.data);
    } catch (e) {
      console.error('Failed to load ego network', e);
    } finally {
      setEgoLoading(false);
    }
  }

  async function runInfluencePropagation(seedIds: string[]) {
    if (!activeProject || seedIds.length === 0) return;
    setInfluenceLoading(true);
    try {
      const res = await graphApi.influence(activeProject.id, seedIds, influenceSteps, influenceThreshold);
      setInfluenceResult(res.data);
    } catch (e) {
      console.error('Failed to run influence propagation', e);
    } finally {
      setInfluenceLoading(false);
    }
  }

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

  // Relationship evidence is persisted on the edge itself (rel.evidence) — just toggle the
  // collapsible open/closed. No document fetching / client-side co-occurrence search.
  function toggleRelEvidence(relIndex: number) {
    setRelEvidenceOpen(prev => ({ ...prev, [relIndex]: !prev[relIndex] }));
  }

  useEffect(() => {
    loadGraph();
    loadEntities();
    loadStatistics();
    loadCommunities();
    loadSnapshots();
    loadStructuralHoles();
  }, [loadGraph, loadEntities, loadStatistics, loadCommunities, loadSnapshots, loadStructuralHoles]);

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

  // Combined filter: entity type + island threshold + relationship type + confidence + temporal range
  useEffect(() => {
    // Filter nodes by active entity type filters
    let nodes = graphNodes;
    if (activeTypeFilters.size > 0) {
      nodes = graphNodes.filter(n => activeTypeFilters.has(n.entity_type));
    }
    const visibleNodeIds = new Set(nodes.map(n => n.id));

    // Filter edges by relationship type, confidence, temporal range, and visible nodes
    let edges = graphEdges.filter(e => {
      const srcId = e.source_id || e.source;
      const tgtId = e.target_id || e.target;
      if (activeTypeFilters.size > 0 && (!visibleNodeIds.has(String(srcId)) || !visibleNodeIds.has(String(tgtId)))) return false;
      if (hiddenRelTypes.has(e.rel_type)) return false;
      if (confidenceThreshold > 0 && (e.confidence === undefined || e.confidence < confidenceThreshold)) return false;
      const [tStart, tEnd] = temporalRange;
      if (tStart && e.last_seen && e.last_seen < tStart) return false;
      if (tEnd && e.first_seen && e.first_seen > tEnd) return false;
      return true;
    });

    // Then apply island threshold
    if (islandThreshold > 0) {
      const metricMap: Record<string, number> = {};

      if (islandMetric === 'degree') {
        for (const node of nodes) {
          metricMap[node.id] = 0;
        }
        for (const edge of edges) {
          const srcId = edge.source_id || edge.source;
          const tgtId = edge.target_id || edge.target;
          if (metricMap[srcId] !== undefined) metricMap[srcId]++;
          if (metricMap[tgtId] !== undefined) metricMap[tgtId]++;
        }
      } else {
        const statsLookup: Record<string, EntityStats> = {};
        if (stats?.entity_statistics) {
          for (const s of stats.entity_statistics) {
            statsLookup[s.entity] = s;
          }
        }
        for (const node of nodes) {
          const s = statsLookup[node.name];
          metricMap[node.id] = s ? s[islandMetric] : 0;
        }
      }

      const filteredIds = new Set(nodes.filter(n => metricMap[n.id] >= islandThreshold).map(n => n.id));
      setFilteredGraphNodes(nodes.filter(n => filteredIds.has(n.id)));
      edges = edges.filter(e => {
        const srcId = e.source_id || e.source;
        const tgtId = e.target_id || e.target;
        return filteredIds.has(srcId) && filteredIds.has(tgtId);
      });
    } else {
      const connectedIds = new Set<string>();
      for (const edge of edges) {
        connectedIds.add(String(edge.source_id || edge.source));
        connectedIds.add(String(edge.target_id || edge.target));
      }
      if (hiddenRelTypes.size === 0 && confidenceThreshold === 0 && activeTypeFilters.size === 0) {
        setFilteredGraphNodes(graphNodes);
      } else {
        const originallyConnected = new Set<string>();
        for (const e of graphEdges) {
          originallyConnected.add(String(e.source_id || e.source));
          originallyConnected.add(String(e.target_id || e.target));
        }
        setFilteredGraphNodes(nodes.filter(n =>
          connectedIds.has(n.id) || !originallyConnected.has(n.id)
        ));
      }
    }
    setFilteredGraphEdges(edges);
  }, [graphNodes, graphEdges, islandThreshold, islandMetric, hiddenRelTypes, confidenceThreshold, temporalRange, stats, activeTypeFilters]);

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
    setMobileRightOpen(true);
    setAiResult(null);
    setTypeDropdownOpen(false);
    setEvidenceDocs([]);
    setRelEvidenceOpen({});
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
      // The backend returns a 200 {error: ...} envelope on failure; treat it as
      // one instead of rendering the error string as if it were the assessment.
      if (res.data.error) {
        updateNotification(notifId, {
          type: 'error',
          title: 'Assessment Failed',
          message: `Could not assess ${selectedEntity.name} — check LLM configuration.`,
        });
        return;
      }
      setAiResult(res.data.assessment);
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
      // For multiple entities (community/group), generate a community overview
      if (multiSelected.length > 1) {
        const entityNames = multiSelected.map(e => `${e.name} (${e.entity_type})`).join(', ');
        const entityIds = multiSelected.map(e => e.id);

        // Get stats for these entities if available
        const entityStats = stats?.entity_statistics?.filter(s =>
          multiSelected.some(e => e.name === s.entity)
        ) || [];
        const topByPagerank = [...entityStats].sort((a, b) => b.pagerank - a.pagerank).slice(0, 5);
        const topByBetweenness = [...entityStats].sort((a, b) => b.betweenness - a.betweenness).slice(0, 5);

        const statsContext = topByPagerank.length > 0
          ? `\n\nKey nodes by PageRank: ${topByPagerank.map(s => `${s.entity} (PR: ${s.pagerank.toFixed(4)})`).join(', ')}\nKey brokers by Betweenness: ${topByBetweenness.map(s => `${s.entity} (BC: ${s.betweenness.toFixed(4)})`).join(', ')}`
          : '';

        // Use RAG query for community context
        const ragRes = await queryApi.rag(activeProject.id,
          `Provide a comprehensive overview of the following group of entities and their relationships: ${entityNames}`
        );
        const ragContext = ragRes.data?.response || ragRes.data?.context || '';

        const communityPrompt = `Generate a community/group assessment for these ${multiSelected.length} entities:\n${entityNames}\n\n${statsContext}\n\nContext from knowledge graph:\n${ragContext}\n\nProvide:\n1. Community Overview (what binds this group together)\n2. Key Nodes (most influential members based on centrality)\n3. Internal Dynamics (relationship patterns within the group)\n4. External Connections (how this group connects to the broader network)\n5. Intelligence Gaps\n6. Assessment Summary`;

        const llmRes = await llmApi.query(
          [{ role: 'user', content: communityPrompt }],
          'threat_assessment'
        );
        const result = llmRes.data.response || llmRes.data.content || JSON.stringify(llmRes.data);
        setAiResult(result);
      } else {
        // Single entity: use standard assessment
        const entity = multiSelected[0];
        const res = await assessApi.generate(entity.id, {
          entity_id: entity.id,
          project_id: activeProject.id,
          judgment: assessJudgment || undefined,
          probability: assessProbability,
        });
        setAiResult(res.data.assessment || res.data.error || 'No response');
      }
      setAssessModalOpen(false);
      setAssessJudgment('');
      setAssessProbability(0.5);
      setAssessAnalyst('');
    } catch {
      setAiResult('Failed to generate community assessment.');
    } finally {
      setAssessLoading(false);
    }
  }

  async function gapAnalysis() {
    if (!selectedEntity || !activeProject) return;
    setAiLoading(true);
    try {
      // Grounded: the backend measures real coverage holes across the graph and
      // retrieves this entity's subgraph before reasoning — not a bare prompt.
      const res = await analysisApi.gaps({
        project_id: activeProject.id,
        entity_ids: [selectedEntity.id],
      });
      setAiResult(res.data.analysis);
    } catch (e) {
      // Never write the failure into aiResult — it renders as if it were analysis.
      addNotification({
        type: 'error',
        title: 'Gap Analysis Failed',
        message: getErrorMessage(e),
      });
    } finally {
      setAiLoading(false);
    }
  }

  async function competingHypotheses() {
    if (!selectedEntity || !activeProject) return;
    setAiLoading(true);
    try {
      // ACH over the entity's retrieved evidence, scored by the backend.
      const res = await analysisApi.hypotheses({
        project_id: activeProject.id,
        question: `What are the competing explanations for the role of ${selectedEntity.name} in this intelligence picture?`,
        entity_ids: [selectedEntity.id],
      });
      setAiResult(res.data.analysis);
    } catch (e) {
      addNotification({
        type: 'error',
        title: 'Hypothesis Generation Failed',
        message: getErrorMessage(e),
      });
    } finally {
      setAiLoading(false);
    }
  }

  // Keep the shared assistant's Notebook tab linked to whatever is
  // multi-selected here — preserving the entity linking the in-page notebook
  // used to do before it moved into components/AssistantPanel.
  useEffect(() => {
    setLinkedEntities(multiSelected.map(e => ({ id: e.id, name: e.name })));
  }, [multiSelected, setLinkedEntities]);

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

  // Edge click handler for detail panel (P0.4)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function handleEdgeClick(edge: any) {
    setSelectedEdge(edge as GraphEdge);
    setSelectedEntity(null);
  }

  // Undo/redo keyboard shortcuts
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        e.preventDefault();
        if (e.shiftKey) {
          // Redo
          if (redoStack.length > 0) {
            const nextState = redoStack[redoStack.length - 1];
            setRedoStack(prev => prev.slice(0, -1));
            setUndoStack(prev => [...prev, { hiddenRelTypes, confidenceThreshold, islandThreshold }]);
            setHiddenRelTypes(nextState.hiddenRelTypes);
            setConfidenceThreshold(nextState.confidenceThreshold);
            setIslandThreshold(nextState.islandThreshold);
          }
        } else {
          // Undo
          if (undoStack.length > 0) {
            const prevState = undoStack[undoStack.length - 1];
            setUndoStack(prev => prev.slice(0, -1));
            setRedoStack(prev => [...prev, { hiddenRelTypes, confidenceThreshold, islandThreshold }]);
            setHiddenRelTypes(prevState.hiddenRelTypes);
            setConfidenceThreshold(prevState.confidenceThreshold);
            setIslandThreshold(prevState.islandThreshold);
          }
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [undoStack, redoStack, hiddenRelTypes, confidenceThreshold, islandThreshold]);

  // Push to undo stack when filters change
  const prevFiltersRef = useRef({ hiddenRelTypes, confidenceThreshold, islandThreshold });
  useEffect(() => {
    const prev = prevFiltersRef.current;
    if (prev.hiddenRelTypes !== hiddenRelTypes || prev.confidenceThreshold !== confidenceThreshold || prev.islandThreshold !== islandThreshold) {
      setUndoStack(stack => [...stack.slice(-49), { hiddenRelTypes: prev.hiddenRelTypes, confidenceThreshold: prev.confidenceThreshold, islandThreshold: prev.islandThreshold }]);
      setRedoStack([]);
      prevFiltersRef.current = { hiddenRelTypes, confidenceThreshold, islandThreshold };
    }
  }, [hiddenRelTypes, confidenceThreshold, islandThreshold]);

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
        <main className="md:ml-56 flex-1 p-8 pt-14 md:pt-8">
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
      <div className="md:ml-56 flex-1 flex flex-col overflow-hidden pt-14 md:pt-0" style={{ height: 'calc(100vh - 28px)' }}>
        {/* Top bar */}
        <div className="flex-none px-4 py-2 border-b border-navy-600 bg-navy-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button onClick={() => setMobileLeftOpen(true)} className="md:hidden text-gray-400 hover:text-white p-1">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clipRule="evenodd" /></svg>
            </button>
            <h2 className="text-lg font-bold">Network Analysis</h2>
          </div>
          <div className="flex items-center gap-4">
            {selectedEntity && (
              <button onClick={() => setMobileRightOpen(true)} className="md:hidden text-gray-400 hover:text-accent-blue p-1" title="Show details">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" /></svg>
              </button>
            )}
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
              <div className="hidden md:flex items-center gap-2 text-xs">
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
            <span className="text-xs md:text-sm text-gray-400">{displayData.nodes.length} nodes, {displayData.edges.length} edges{collapseCommunities ? ' (collapsed)' : ''}</span>
            <div className="hidden md:flex items-center gap-2">
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
        <div className="flex-none px-4 py-1.5 border-b border-navy-600 bg-navy-800/80 hidden md:flex items-center gap-3 flex-wrap">
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

          {/* Divider */}
          <div className="w-px h-5 bg-navy-600" />

          {/* Undo/Redo */}
          <div className="flex items-center gap-1">
            <button
              onClick={() => {
                if (undoStack.length > 0) {
                  const prevState = undoStack[undoStack.length - 1];
                  setUndoStack(prev => prev.slice(0, -1));
                  setRedoStack(prev => [...prev, { hiddenRelTypes, confidenceThreshold, islandThreshold }]);
                  setHiddenRelTypes(prevState.hiddenRelTypes);
                  setConfidenceThreshold(prevState.confidenceThreshold);
                  setIslandThreshold(prevState.islandThreshold);
                }
              }}
              disabled={undoStack.length === 0}
              className="px-2 py-1 rounded text-xs bg-navy-700 border border-navy-600 text-gray-400 hover:bg-navy-600 disabled:opacity-30 disabled:cursor-not-allowed"
              title="Undo (Ctrl+Z)"
            >
              Undo
            </button>
            <button
              onClick={() => {
                if (redoStack.length > 0) {
                  const nextState = redoStack[redoStack.length - 1];
                  setRedoStack(prev => prev.slice(0, -1));
                  setUndoStack(prev => [...prev, { hiddenRelTypes, confidenceThreshold, islandThreshold }]);
                  setHiddenRelTypes(nextState.hiddenRelTypes);
                  setConfidenceThreshold(nextState.confidenceThreshold);
                  setIslandThreshold(nextState.islandThreshold);
                }
              }}
              disabled={redoStack.length === 0}
              className="px-2 py-1 rounded text-xs bg-navy-700 border border-navy-600 text-gray-400 hover:bg-navy-600 disabled:opacity-30 disabled:cursor-not-allowed"
              title="Redo (Ctrl+Shift+Z)"
            >
              Redo
            </button>
          </div>
        </div>

        {/* Main content area */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left sidebar - Entity list / Statistics */}
          <div className={`${mobileLeftOpen ? 'fixed inset-0 z-40 w-full' : 'hidden'} md:relative md:block md:w-64 flex-none bg-navy-800 border-r border-navy-600 flex flex-col overflow-hidden`}>
            {/* Mobile close button */}
            <button onClick={() => setMobileLeftOpen(false)} className="md:hidden absolute top-2 right-2 z-50 text-gray-400 hover:text-white p-1">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" /></svg>
            </button>
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
              <button
                onClick={() => setLeftTab('analysis')}
                className={`flex-1 py-2 text-xs font-medium transition-colors ${leftTab === 'analysis' ? 'text-accent-blue border-b-2 border-accent-blue' : 'text-gray-400 hover:text-gray-200'}`}
              >
                Analysis
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
                  {/* Multi-select entity type filter */}
                  <div className="relative">
                    <button
                      onClick={() => setTypeFilterOpen(!typeFilterOpen)}
                      className="w-full flex items-center justify-between bg-navy-700 border border-navy-600 rounded px-2 py-1.5 text-xs text-gray-300 hover:border-accent-blue transition-colors"
                    >
                      <span className="truncate">
                        {activeTypeFilters.size === 0 ? 'All Types' : `${activeTypeFilters.size} type${activeTypeFilters.size > 1 ? 's' : ''} selected`}
                      </span>
                      <span className="text-gray-500 ml-1">{typeFilterOpen ? '\u25B2' : '\u25BC'}</span>
                    </button>
                    {typeFilterOpen && (
                      <div className="absolute z-20 mt-1 w-full bg-navy-700 border border-navy-600 rounded shadow-lg max-h-48 overflow-y-auto">
                        <button
                          onClick={() => { setActiveTypeFilters(new Set()); setTypeFilter('All'); }}
                          className={`w-full text-left px-3 py-1.5 text-xs hover:bg-navy-600 transition-colors ${activeTypeFilters.size === 0 ? 'text-accent-blue font-medium' : 'text-gray-300'}`}
                        >
                          All Types
                        </button>
                        {(() => {
                          const graphTypes = Array.from(new Set(graphNodes.map(n => n.entity_type))).sort();
                          return graphTypes.map(t => (
                            <label key={t} className="flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-navy-600 cursor-pointer transition-colors">
                              <input
                                type="checkbox"
                                checked={activeTypeFilters.has(t)}
                                onChange={() => {
                                  setActiveTypeFilters(prev => {
                                    const next = new Set(prev);
                                    if (next.has(t)) next.delete(t); else next.add(t);
                                    return next;
                                  });
                                }}
                                className="accent-accent-blue"
                              />
                              <span className={`w-2 h-2 rounded-full flex-none ${TYPE_COLORS[t] || 'bg-gray-500'}`} />
                              <span className="text-gray-300">{formatEntityType(t)}</span>
                              <span className="ml-auto text-[10px] text-gray-500">
                                {graphNodes.filter(n => n.entity_type === t).length}
                              </span>
                            </label>
                          ));
                        })()}
                      </div>
                    )}
                  </div>
                  {activeTypeFilters.size > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {Array.from(activeTypeFilters).map(t => (
                        <span key={t} className="flex items-center gap-1 bg-navy-600 text-[10px] text-gray-300 px-1.5 py-0.5 rounded">
                          {t}
                          <button onClick={() => setActiveTypeFilters(prev => { const n = new Set(prev); n.delete(t); return n; })} className="text-gray-500 hover:text-white">&times;</button>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                {/* Stats cards + filters (moved from Statistics tab) */}
                {stats && (
                  <div className="p-3 border-b border-navy-600 space-y-2">
                    <div className="grid grid-cols-4 gap-1.5">
                      <div className="bg-navy-700 rounded p-1.5 text-center">
                        <div className="text-sm font-bold text-accent-blue">{stats.total_nodes}</div>
                        <div className="text-[9px] text-gray-500">Nodes</div>
                      </div>
                      <div className="bg-navy-700 rounded p-1.5 text-center">
                        <div className="text-sm font-bold text-accent-blue">{stats.total_edges}</div>
                        <div className="text-[9px] text-gray-500">Edges</div>
                      </div>
                      <div className="bg-navy-700 rounded p-1.5 text-center">
                        <div className="text-sm font-bold text-accent-blue">{typeof stats.density === 'number' ? stats.density.toFixed(3) : stats.density}</div>
                        <div className="text-[9px] text-gray-500">Density</div>
                      </div>
                      <div className="bg-navy-700 rounded p-1.5 text-center">
                        <div className="text-sm font-bold text-accent-blue">{stats.connected_components}</div>
                        <div className="text-[9px] text-gray-500">Comp.</div>
                      </div>
                    </div>
                    {/* Min Confidence */}
                    <div>
                      <div className="flex items-center justify-between">
                        <label className="text-[10px] text-gray-500">Confidence</label>
                        <span className="text-[10px] text-accent-blue font-medium">{confidenceThreshold.toFixed(2)}</span>
                      </div>
                      <input type="range" min={0} max={1} step={0.05} value={confidenceThreshold}
                        onChange={(e) => setConfidenceThreshold(Number(e.target.value))}
                        className="w-full accent-accent-blue h-1" />
                    </div>
                    {/* Island Method */}
                    <div>
                      <div className="flex items-center justify-between">
                        <label className="text-[10px] text-gray-500">Island ({islandMetric})</label>
                        <select value={islandMetric}
                          onChange={(e) => { setIslandMetric(e.target.value as typeof islandMetric); setIslandThreshold(0); }}
                          className="bg-navy-800 border border-navy-600 rounded px-1 py-0.5 text-[10px] text-gray-400">
                          <option value="degree">Degree</option>
                          <option value="betweenness">Between.</option>
                          <option value="eigenvector">Eigen.</option>
                          <option value="pagerank">PageRank</option>
                          <option value="closeness">Close.</option>
                        </select>
                      </div>
                      <input type="range" min={0}
                        max={islandMetric === 'degree' ? Math.max(maxVals.degree, 1) : Math.max(maxVals[islandMetric], 0.01)}
                        step={islandMetric === 'degree' ? 1 : islandMetric === 'pagerank' ? 0.001 : 0.01}
                        value={islandThreshold}
                        onChange={(e) => setIslandThreshold(Number(e.target.value))}
                        className="w-full accent-accent-blue h-1" />
                    </div>
                    {/* Ego Highlight Depth */}
                    <div>
                      <div className="flex items-center justify-between">
                        <label className="text-[10px] text-gray-500">Ego Highlight</label>
                        <span className="text-[10px] text-accent-blue font-medium">{egoHighlightDepth} hop{egoHighlightDepth > 1 ? 's' : ''}</span>
                      </div>
                      <input type="range" min={1} max={4} step={1} value={egoHighlightDepth}
                        onChange={(e) => setEgoHighlightDepth(Number(e.target.value))}
                        className="w-full accent-accent-blue h-1" />
                    </div>
                  </div>
                )}
                <div className="flex-1 overflow-y-auto">
                  {(() => {
                    const grouped: Record<string, typeof entities> = {};
                    entities.forEach(e => {
                      const t = e.entity_type || 'Unknown';
                      if (!grouped[t]) grouped[t] = [];
                      grouped[t].push(e);
                    });
                    const sortedTypes = Object.keys(grouped).sort();

                    if (entities.length === 0) {
                      return <p className="text-xs text-gray-500 p-3">No entities found.</p>;
                    }

                    return sortedTypes.map(type => {
                      const typeEntities = grouped[type];
                      const isExpanded = expandedEntityTypes.has(type);
                      return (
                        <div key={type}>
                          <button
                            onClick={() => setExpandedEntityTypes(prev => {
                              const next = new Set(prev);
                              if (next.has(type)) next.delete(type); else next.add(type);
                              return next;
                            })}
                            className="w-full text-left px-3 py-2 text-xs font-semibold border-b border-navy-700 hover:bg-navy-700 flex items-center gap-2 text-gray-400"
                          >
                            <span className="text-[10px]">{isExpanded ? '\u25BC' : '\u25B6'}</span>
                            <span className={`w-2 h-2 rounded-full flex-none ${TYPE_COLORS[type] || 'bg-gray-500'}`} />
                            <span className="flex-1">{formatEntityType(type)}</span>
                            <span className="text-[10px] text-gray-500 bg-navy-600 px-1.5 py-0.5 rounded-full">{typeEntities.length}</span>
                          </button>
                          {isExpanded && typeEntities.map(entity => (
                            <button
                              key={entity.id}
                              onClick={(e) => {
                                if (e.shiftKey) {
                                  // Shift+click adds to multi-select
                                  setMultiSelected(prev => {
                                    const exists = prev.find(x => x.id === entity.id);
                                    if (exists) return prev.filter(x => x.id !== entity.id);
                                    return [...prev, entity];
                                  });
                                } else {
                                  selectEntity(entity);
                                }
                              }}
                              className={`w-full text-left pl-8 pr-3 py-1.5 text-xs border-b border-navy-700/50 hover:bg-navy-700 transition-colors flex items-center gap-2 ${
                                selectedEntity?.id === entity.id ? 'bg-navy-700 text-accent-blue'
                                : multiSelected.find(x => x.id === entity.id) ? 'bg-navy-700/50 text-purple-400'
                                : 'text-gray-300'
                              }`}
                            >
                              {multiSelected.find(x => x.id === entity.id) && (
                                <span className="w-2 h-2 rounded-full bg-purple-500 flex-none" />
                              )}
                              <span className="truncate">{entity.name}</span>
                            </button>
                          ))}
                        </div>
                      );
                    });
                  })()}
                </div>
                {/* Snapshots (Bins) + Mass Select Section */}
                <div className="flex-none border-t border-navy-600">
                  <div className="px-3 py-2 flex items-center justify-between">
                    <h4 className="text-xs font-semibold text-gray-400">Snapshots / Bins</h4>
                    <div className="flex items-center gap-1">
                      {activeSnapshotId && (
                        <button onClick={clearSnapshotView} className="text-[10px] text-accent-blue hover:underline">Clear</button>
                      )}
                    </div>
                  </div>
                  {/* Mass selection helpers */}
                  <div className="px-3 pb-2 flex flex-wrap gap-1">
                    <button
                      onClick={() => {
                        const allEntities = filteredGraphNodes.map(n => ({ id: n.id, name: n.name, entity_type: n.entity_type }));
                        setMultiSelected(allEntities);
                      }}
                      className="text-[9px] px-2 py-0.5 rounded bg-navy-600 text-gray-300 hover:bg-navy-500"
                    >
                      Select All Visible
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
                        className="text-[9px] px-2 py-0.5 rounded bg-purple-800 text-gray-300 hover:bg-purple-700"
                      >
                        Select Community
                      </button>
                    )}
                    {multiSelected.length > 0 && (
                      <>
                        <span className="text-[9px] text-purple-400 px-1 py-0.5">{multiSelected.length} selected</span>
                        <button onClick={() => setMultiSelected([])} className="text-[9px] px-2 py-0.5 rounded bg-navy-600 text-gray-400 hover:bg-navy-500">Clear</button>
                      </>
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
                            <button onClick={saveSnapshot} disabled={!snapshotNameInput.trim()}
                              className="flex-1 bg-accent-blue hover:bg-blue-600 text-white px-2 py-1 rounded text-[10px] font-medium disabled:opacity-50">
                              Save ({multiSelected.length} entities)
                            </button>
                            <button onClick={() => setSnapshotFormOpen(false)}
                              className="px-2 py-1 bg-navy-600 hover:bg-navy-700 text-gray-300 rounded text-[10px]">
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <button onClick={() => setSnapshotFormOpen(true)}
                          className="w-full bg-navy-700 hover:bg-navy-600 border border-navy-600 text-gray-300 px-2 py-1.5 rounded text-xs transition-colors">
                          Save as Snapshot ({multiSelected.length} selected)
                        </button>
                      )}
                    </div>
                  )}
                  <div className="max-h-40 overflow-y-auto">
                    {snapshots.length === 0 ? (
                      <p className="text-[10px] text-gray-500 px-3 pb-2">No snapshots saved.</p>
                    ) : (
                      snapshots.map((snap) => (
                        <div key={snap.id}
                          className={`flex items-center gap-1.5 px-3 py-1.5 text-xs border-b border-navy-700 hover:bg-navy-700 cursor-pointer transition-colors ${
                            activeSnapshotId === snap.id ? 'bg-navy-700 text-accent-blue' : 'text-gray-300'
                          }`}>
                          <div className="flex-1 min-w-0" onClick={() => loadSnapshotView(snap.id)}>
                            <div className="truncate font-medium">{snap.name}</div>
                            <div className="text-[10px] text-gray-500">
                              {snap.entity_count} entities &middot; {new Date(snap.created_at).toLocaleDateString()}
                            </div>
                          </div>
                          <button onClick={(e) => { e.stopPropagation(); deleteSnapshot(snap.id); }}
                            className="text-red-400 hover:text-red-300 text-[10px] flex-none">Del</button>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </>
            ) : leftTab === 'statistics' ? (
              <div className="flex-1 overflow-y-auto p-3">
                <h4 className="text-xs font-semibold text-gray-400 mb-2">Edge Overview</h4>
                {(() => {
                  // Aggregate edges by relationship type
                  const relCounts: Record<string, { count: number; avgConf: number; totalConf: number }> = {};
                  graphEdges.forEach(e => {
                    const rt = e.rel_type || 'UNKNOWN';
                    if (!relCounts[rt]) relCounts[rt] = { count: 0, avgConf: 0, totalConf: 0 };
                    relCounts[rt].count++;
                    relCounts[rt].totalConf += (e.confidence ?? 0.5);
                  });
                  Object.values(relCounts).forEach(v => { v.avgConf = v.count > 0 ? v.totalConf / v.count : 0; });
                  const entries = Object.entries(relCounts);
                  // ASSOCIATED_WITH is a noise-tier catch-all relation that tends to dominate this
                  // list with little analytic value — de-emphasize it behind a collapsed disclosure.
                  const typed = entries.filter(([rt]) => rt !== 'ASSOCIATED_WITH').sort((a, b) => b[1].count - a[1].count);
                  const noise = entries.filter(([rt]) => rt === 'ASSOCIATED_WITH');
                  const maxCount = entries.length > 0 ? Math.max(...entries.map(([, d]) => d.count)) : 1;
                  const renderRow = ([rt, data]: [string, { count: number; avgConf: number; totalConf: number }]) => (
                    <div key={rt} className="bg-navy-700 rounded p-2">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-gray-300 font-medium">{formatRelType(rt)}</span>
                        <span className="text-gray-500">{data.count}</span>
                      </div>
                      <div className="w-full bg-navy-800 rounded-full h-1.5 mt-1">
                        <div className="bg-accent-blue h-1.5 rounded-full" style={{ width: `${(data.count / maxCount) * 100}%` }} />
                      </div>
                      <div className="text-[10px] text-gray-500 mt-0.5">
                        Avg confidence: {(data.avgConf * 100).toFixed(0)}%
                      </div>
                    </div>
                  );
                  return (
                    <div className="space-y-1">
                      {typed.map(renderRow)}
                      {typed.length === 0 && noise.length === 0 && <p className="text-xs text-gray-500">No edges in graph.</p>}
                      {noise.length > 0 && (
                        <div className={typed.length > 0 ? 'pt-1' : ''}>
                          <button
                            onClick={() => setShowLowSignalRel(v => !v)}
                            className="w-full flex items-center justify-between text-[10px] text-gray-500 hover:text-gray-300 px-1 py-1"
                          >
                            <span>{showLowSignalRel ? '▾' : '▸'} Low-signal (Associated With)</span>
                            <span>{noise[0][1].count}</span>
                          </button>
                          {showLowSignalRel && noise.map(renderRow)}
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>
            ) : leftTab === 'analysis' ? (
              <div className="flex-1 overflow-y-auto p-3 space-y-3">
                {/* Structural Holes / Brokers */}
                <div>
                  <h4 className="text-xs font-semibold text-gray-400 mb-2">Structural Holes (Brokers)</h4>
                  <p className="text-[10px] text-gray-500 mb-2">Low constraint + high effective size = broker bridging groups.</p>
                  {structuralHoles.length > 0 ? (
                    <div className="space-y-1">
                      {structuralHoles.slice(0, 10).map((sh) => (
                        <div
                          key={sh.id}
                          className={`text-xs rounded p-2 cursor-pointer transition-colors ${sh.is_broker ? 'bg-purple-900/40 border border-purple-700/50' : 'bg-navy-700'} hover:bg-navy-600`}
                          onClick={() => selectEntity({ id: sh.id, name: sh.name, entity_type: sh.entity_type })}
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-gray-200 font-medium truncate">{sh.name}</span>
                            {sh.is_broker && <span className="text-[9px] px-1.5 py-0.5 bg-purple-600 text-white rounded">Broker</span>}
                          </div>
                          <div className="flex gap-3 mt-1 text-[10px] text-gray-400">
                            <span>Constraint: <span className={sh.constraint < 0.5 ? 'text-green-400' : 'text-gray-300'}>{sh.constraint.toFixed(3)}</span></span>
                            <span>Eff. Size: <span className={sh.effective_size > 1.5 ? 'text-blue-400' : 'text-gray-300'}>{sh.effective_size.toFixed(2)}</span></span>
                            <span>Deg: {sh.degree}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-[10px] text-gray-500">No data available.</p>
                  )}
                </div>

                {/* Influence Propagation */}
                <div>
                  <h4 className="text-xs font-semibold text-gray-400 mb-2">Influence Propagation</h4>
                  <p className="text-[10px] text-gray-500 mb-2">Simulate how influence spreads from selected entities.</p>
                  <div className="space-y-2">
                    <div className="flex gap-2">
                      <div className="flex-1">
                        <label className="text-[10px] text-gray-500">Steps</label>
                        <input type="number" min={1} max={10} value={influenceSteps} onChange={(e) => setInfluenceSteps(Number(e.target.value))}
                          className="w-full bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs" />
                      </div>
                      <div className="flex-1">
                        <label className="text-[10px] text-gray-500">Threshold</label>
                        <input type="number" min={0} max={1} step={0.1} value={influenceThreshold} onChange={(e) => setInfluenceThreshold(Number(e.target.value))}
                          className="w-full bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs" />
                      </div>
                    </div>
                    <button
                      onClick={() => {
                        const seeds = multiSelected.length > 0 ? multiSelected.map(e => e.id) : selectedEntity ? [selectedEntity.id] : [];
                        if (seeds.length > 0) runInfluencePropagation(seeds);
                      }}
                      disabled={influenceLoading || (!selectedEntity && multiSelected.length === 0)}
                      className="w-full bg-orange-600 hover:bg-orange-700 text-white px-3 py-1.5 rounded text-xs font-medium disabled:opacity-50 transition-colors"
                    >
                      {influenceLoading ? 'Running...' : `Run from ${multiSelected.length > 0 ? multiSelected.length + ' selected' : selectedEntity?.name || 'no entity'}`}
                    </button>
                  </div>

                  {influenceResult && (
                    <div className="mt-2 space-y-1.5">
                      <div className="flex gap-2 text-[10px]">
                        <span className="bg-navy-700 rounded px-2 py-1">
                          Reach: <span className="text-orange-400 font-bold">{(influenceResult.reach_ratio * 100).toFixed(1)}%</span>
                        </span>
                        <span className="bg-navy-700 rounded px-2 py-1">
                          Activated: <span className="text-orange-400 font-bold">{influenceResult.total_activated}</span> / {influenceResult.total_nodes}
                        </span>
                      </div>
                      {influenceResult.steps.map((step) => (
                        <div key={step.step} className="bg-navy-700 rounded p-2">
                          <div className="text-[10px] text-gray-400 mb-1">
                            Step {step.step}: +{step.newly_activated.length} activated ({step.cumulative_count} total)
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {step.newly_activated.slice(0, 8).map((n) => (
                              <span
                                key={n.id}
                                className="text-[9px] px-1.5 py-0.5 bg-navy-600 text-gray-300 rounded cursor-pointer hover:bg-navy-500"
                                onClick={() => selectEntity({ id: n.id, name: n.name, entity_type: n.entity_type })}
                              >
                                {n.name}
                              </span>
                            ))}
                            {step.newly_activated.length > 8 && (
                              <span className="text-[9px] text-gray-500">+{step.newly_activated.length - 8} more</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ) : null}
          </div>

          {/* Center - Graph or Statistics Table */}
          <div className="flex-1 flex flex-col overflow-hidden relative">
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
                      onEdgeClick={handleEdgeClick as never}
                      selectedNodeId={selectedEntity?.id}
                      highlightedNodeIds={highlightedNodeIds}
                      highlightedEdgeKeys={highlightedEdgeKeys}
                      layout={layoutMode}
                      colorMode={colorMode}
                      communityMap={communityMap}
                      egoHighlightDepth={egoHighlightDepth}
                    />
                  ) : (
                    <div className="flex items-center justify-center h-full text-gray-500">
                      <p>No graph data. Ingest documents to populate the knowledge graph.</p>
                    </div>
                  )}
                  {/* Temporal Slider (P0.5) */}
                  <TemporalSlider
                    edges={graphEdges}
                    value={temporalRange}
                    onChange={setTemporalRange}
                  />
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
                      <span className="text-xs text-gray-500">{formatEntityType(e.entity_type)}</span>
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

          {/* Right sidebar - Detail panel. pb-20 leaves the scroll tail clear of
              the fixed StatusBar and the assistant launcher at bottom-right. */}
          <div className={`${mobileRightOpen ? 'fixed inset-x-0 bottom-0 z-40 h-2/3 rounded-t-xl border-t' : 'hidden'} md:relative md:block md:w-80 md:h-auto md:rounded-none flex-none bg-navy-800 border-l border-navy-600 overflow-y-auto pb-20`}>
            {/* Mobile close button */}
            <button onClick={() => setMobileRightOpen(false)} className="md:hidden absolute top-2 right-2 z-50 text-gray-400 hover:text-white p-1">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" /></svg>
            </button>
            {selectedEntity ? (
              <div className="p-4 space-y-4">
                <div>
                  <h3 className="font-bold text-lg">{selectedEntity.name}</h3>
                  <span className={`inline-block mt-1 text-xs px-2 py-0.5 rounded ${TYPE_COLORS[selectedEntity.entity_type] || 'bg-gray-500'} text-white`}>
                    {formatEntityType(selectedEntity.entity_type)}
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

                <EnrichmentPanel
                  entityId={selectedEntity.id}
                  entityType={selectedEntity.entity_type}
                  properties={entityFields(selectedEntity)}
                  onEnriched={() => selectEntity(selectedEntity)}
                />

                {entityRelationships.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-gray-400 mb-2">Relationships ({entityRelationships.length})</h4>
                    <div className="space-y-1">
                      {entityRelationships.map((rel, i) => {
                        // Compute edge weight from graph edges
                        const otherId = rel.source_id === selectedEntity.id ? rel.target_id : rel.source_id;
                        const edgeWeight = graphEdges.filter(e => {
                          const srcId = e.source_id || e.source;
                          const tgtId = e.target_id || e.target;
                          return (srcId === selectedEntity.id && tgtId === otherId) || (tgtId === selectedEntity.id && srcId === otherId);
                        }).length;
                        const conf = rel.confidence;
                        const confDotColor = conf !== undefined
                          ? conf >= 0.8 ? 'bg-green-500'
                          : conf >= 0.5 ? 'bg-accent-blue'
                          : conf >= 0.3 ? 'bg-yellow-500'
                          : 'bg-red-500'
                          : '';
                        return (
                        <div key={i} className="text-xs bg-navy-700 rounded p-2">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-accent-blue truncate">{formatRelType(rel.rel_type)}{edgeWeight > 1 ? ` (${edgeWeight})` : ''}</span>
                            {conf !== undefined && (
                              <span className="inline-flex items-center gap-1 text-gray-500 flex-none">
                                <span className={`w-1.5 h-1.5 rounded-full ${confDotColor}`} />
                                {(conf * 100).toFixed(0)}%
                              </span>
                            )}
                          </div>
                          <div className="text-gray-400 mt-0.5 truncate">
                            {rel.source_name || rel.source_id} &rarr; {rel.target_name || rel.target_id}
                          </div>
                          <button
                            onClick={() => toggleRelEvidence(i)}
                            className="text-[10px] text-accent-blue hover:underline mt-1"
                          >
                            {relEvidenceOpen[i] ? 'Hide Evidence' : 'Show Evidence'}
                          </button>
                          {relEvidenceOpen[i] && (
                            <div className="mt-2">
                              {/* Full provenance: the claim, how sure, how corroborated,
                                  how the source is graded, and the verbatim basis. */}
                              <EvidenceChain
                                relationship={rel}
                                document={
                                  rel.source_doc_id
                                    ? (() => {
                                        // evidenceDocs is already loaded for this entity —
                                        // reuse it rather than re-fetching document names.
                                        const d = evidenceDocs.find(x => x.id === rel.source_doc_id);
                                        return {
                                          id: rel.source_doc_id,
                                          name: d?.name || 'Source document',
                                          reliability: d?.reliability_rating || undefined,
                                        };
                                      })()
                                    : null
                                }
                                onOpenDocument={(id) => networkRouter.push(`/documents/${id}`)}
                              />
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

                {/* Ego Network */}
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold text-gray-400">Ego Network</h4>
                  <div className="flex items-center gap-2">
                    <select
                      value={egoHops}
                      onChange={(e) => setEgoHops(Number(e.target.value))}
                      className="bg-navy-700 border border-navy-600 rounded px-2 py-1.5 text-xs"
                    >
                      <option value={1}>1 hop</option>
                      <option value={2}>2 hops</option>
                      <option value={3}>3 hops</option>
                      <option value={4}>4 hops</option>
                    </select>
                    <button
                      onClick={() => loadEgoNetwork(selectedEntity.id)}
                      disabled={egoLoading}
                      className="flex-1 bg-purple-600 hover:bg-purple-700 text-white px-3 py-1.5 rounded text-xs font-medium disabled:opacity-50 transition-colors"
                    >
                      {egoLoading ? 'Loading...' : 'Extract'}
                    </button>
                  </div>
                  {egoNetwork && egoNetwork.center === selectedEntity.id && (
                    <div className="bg-navy-700 rounded p-2 space-y-1.5">
                      <div className="flex gap-2 text-[10px] text-gray-400">
                        <span>{egoNetwork.node_count} nodes</span>
                        <span>{egoNetwork.edge_count} edges</span>
                        <span>{egoNetwork.hops} hops</span>
                      </div>
                      <div className="space-y-1 max-h-40 overflow-y-auto">
                        {egoNetwork.nodes.filter(n => n.id !== selectedEntity.id).slice(0, 15).map((n) => (
                          <div
                            key={n.id}
                            className="flex items-center justify-between text-[10px] px-1.5 py-1 bg-navy-800 rounded cursor-pointer hover:bg-navy-600"
                            onClick={() => selectEntity({ id: n.id, name: n.name, entity_type: n.entity_type })}
                          >
                            <div className="flex items-center gap-1.5 min-w-0">
                              <span className={`w-1.5 h-1.5 rounded-full flex-none ${n.hop_distance === 1 ? 'bg-blue-400' : n.hop_distance === 2 ? 'bg-blue-600' : 'bg-blue-800'}`} />
                              <span className="text-gray-300 truncate">{n.name}</span>
                            </div>
                            <span className="text-gray-500 flex-none ml-1">h{n.hop_distance} pr:{n.local_pagerank.toFixed(3)}</span>
                          </div>
                        ))}
                        {egoNetwork.nodes.length > 16 && (
                          <p className="text-[10px] text-gray-500 text-center">+{egoNetwork.nodes.length - 16} more</p>
                        )}
                      </div>
                      <button
                        onClick={() => {
                          // Focus the graph on the ego network by filtering
                          const egoIds = new Set(egoNetwork.nodes.map(n => n.id));
                          setFilteredGraphNodes(graphNodes.filter(n => egoIds.has(n.id)));
                          setFilteredGraphEdges(graphEdges.filter(e => {
                            const srcId = e.source_id || e.source;
                            const tgtId = e.target_id || e.target;
                            return egoIds.has(srcId) && egoIds.has(tgtId);
                          }));
                        }}
                        className="w-full bg-navy-600 hover:bg-navy-500 text-gray-300 px-2 py-1 rounded text-[10px] transition-colors"
                      >
                        Focus Graph on Ego Network
                      </button>
                    </div>
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
                  <button
                    onClick={competingHypotheses}
                    disabled={aiLoading}
                    className="w-full bg-navy-600 hover:bg-navy-700 text-gray-200 px-3 py-2 rounded text-xs font-medium disabled:opacity-50 border border-navy-600"
                    title="Analysis of Competing Hypotheses over this entity's retrieved evidence"
                  >
                    Competing Hypotheses (ACH)
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
                    <div className="bg-navy-700 rounded p-3 text-xs max-h-64 overflow-y-auto">
                      <Markdown content={aiResult} />
                    </div>
                  </div>
                )}
              </div>
            ) : selectedEdge ? (
              <div className="p-4 space-y-4">
                <div>
                  <h3 className="font-bold text-lg text-gray-200">Relationship</h3>
                  <span className="inline-block mt-1 text-xs px-2 py-0.5 rounded bg-navy-600 text-gray-300">
                    {formatRelType(selectedEdge.rel_type)}
                  </span>
                </div>
                <div className="space-y-2 text-xs">
                  <div>
                    <span className="text-gray-500">Source:</span>{' '}
                    <span className="text-gray-300">{selectedEdge.source_id}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Target:</span>{' '}
                    <span className="text-gray-300">{selectedEdge.target_id}</span>
                  </div>
                  {selectedEdge.confidence !== undefined && (
                    <div>
                      <span className="text-gray-500">Confidence:</span>{' '}
                      <span className={selectedEdge.confidence >= 0.8 ? 'text-green-400' : selectedEdge.confidence >= 0.5 ? 'text-yellow-400' : 'text-red-400'}>
                        {(selectedEdge.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  )}
                  {selectedEdge.first_seen && (
                    <div>
                      <span className="text-gray-500">First Seen:</span>{' '}
                      <span className="text-gray-300">{String(selectedEdge.first_seen).slice(0, 10)}</span>
                    </div>
                  )}
                  {selectedEdge.last_seen && (
                    <div>
                      <span className="text-gray-500">Last Seen:</span>{' '}
                      <span className="text-gray-300">{String(selectedEdge.last_seen).slice(0, 10)}</span>
                    </div>
                  )}
                  {selectedEdge.source && (
                    <div>
                      <span className="text-gray-500">Source Document:</span>{' '}
                      <span className="text-gray-300">{String(selectedEdge.source)}</span>
                    </div>
                  )}
                  {selectedEdge['method'] != null && (
                    <div>
                      <span className="text-gray-500">Extraction Method:</span>{' '}
                      <span className="text-gray-300">{String(selectedEdge['method'])}</span>
                    </div>
                  )}
                  <div>
                    <span className="text-gray-500">Evidence:</span>
                    {selectedEdge.evidence ? (
                      <div className="mt-1 bg-navy-700 rounded p-1.5 text-gray-300 italic leading-relaxed">
                        &ldquo;{selectedEdge.evidence}&rdquo;
                      </div>
                    ) : (
                      <div className="mt-1 text-gray-500 italic">No captured evidence — re-run extraction to populate.</div>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => setSelectedEdge(null)}
                  className="text-xs text-gray-500 hover:text-gray-300"
                >
                  Dismiss
                </button>
              </div>
            ) : (
              <div className="p-4 text-center text-gray-500 text-sm mt-8">
                <p>Select an entity from the list or click a node/edge in the graph to see details.</p>
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
