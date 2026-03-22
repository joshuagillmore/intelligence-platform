import { create, useStore } from 'zustand';
import { temporal, TemporalState } from 'zundo';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface GraphNode {
  id: string;
  name: string;
  entity_type: string;
  entity_category?: string;
  community_id?: number;
  pagerank?: number;
  degree?: number;
  members?: string[];
  isCommunity?: boolean;
  [key: string]: unknown;
}

export interface GraphEdge {
  source_id: string;
  target_id: string;
  rel_type: string;
  confidence?: number;
  weight?: number;
  first_seen?: string;
  last_seen?: string;
  [key: string]: unknown;
}

export interface EntityRef {
  id: string;
  name: string;
  entity_type: string;
}

export interface EntityStats {
  entity: string;
  type: string;
  degree: number;
  betweenness: number;
  eigenvector: number;
  pagerank: number;
  closeness: number;
}

export type IslandMetric =
  | 'degree'
  | 'betweenness'
  | 'eigenvector'
  | 'pagerank'
  | 'closeness';
export type LayoutMode = 'force' | 'radial' | 'hierarchical';
export type ColorMode = 'type' | 'community';

// ---------------------------------------------------------------------------
// State shape
// ---------------------------------------------------------------------------

/** All data properties (no actions). */
interface GraphStateData {
  // Graph data (core)
  graphNodes: GraphNode[];
  graphEdges: GraphEdge[];
  filteredGraphNodes: GraphNode[];
  filteredGraphEdges: GraphEdge[];
  graphLoading: boolean;
  graphError: string | null;

  // Selection
  selectedEntityId: string | null;
  selectedEntities: EntityRef[]; // for path finding (max 2)
  multiSelected: EntityRef[]; // shift+click multi-select

  // Filtering
  hiddenRelTypes: string[]; // stored as array for serialisation; exposed via Set-like helpers
  confidenceThreshold: number;
  islandThreshold: number;
  islandMetric: IslandMetric;

  // Layout & Display
  layoutMode: LayoutMode;
  colorMode: ColorMode;
  communityMap: Record<string, number>;
  collapseCommunities: boolean;
  nodePositions: Record<string, { x: number; y: number }>;

  // Temporal range (P0.5)
  temporalRange: [string | null, string | null];

  // Path highlighting
  highlightedNodeIds: string[]; // stored as array; Set-like access via helpers
  highlightedEdgeKeys: string[];
  pathResult: { path: string[]; length: number } | null;
}

/** Action signatures. */
interface GraphStateActions {
  setGraphData: (nodes: GraphNode[], edges: GraphEdge[]) => void;
  setGraphLoading: (loading: boolean) => void;
  setGraphError: (error: string | null) => void;

  selectEntity: (id: string | null) => void;
  toggleMultiSelect: (entity: EntityRef) => void;
  addToSelectedEntities: (entity: EntityRef) => void;
  clearPath: () => void;
  setHighlightedPath: (
    nodeIds: Set<string> | string[],
    edgeKeys: Set<string> | string[],
    result: { path: string[]; length: number },
  ) => void;

  toggleRelType: (relType: string) => void;
  setConfidenceThreshold: (value: number) => void;
  setIslandThreshold: (value: number) => void;
  setIslandMetric: (metric: IslandMetric) => void;

  setLayoutMode: (mode: LayoutMode) => void;
  setColorMode: (mode: ColorMode) => void;
  setCommunityMap: (map: Record<string, number>) => void;
  setCollapseCommunities: (value: boolean) => void;

  setTemporalRange: (range: [string | null, string | null]) => void;

  updateNodePositions: (
    positions: Record<string, { x: number; y: number }>,
  ) => void;

  applyFilters: (stats?: { entity_statistics?: EntityStats[] }) => void;
  resetFilters: () => void;
}

export type GraphState = GraphStateData & GraphStateActions;

// ---------------------------------------------------------------------------
// Convenience Set-like accessors (pure functions, no store dependency)
// ---------------------------------------------------------------------------

/** Convert the stored array to a Set for O(1) lookups */
export function hiddenRelTypesSet(state: GraphState): Set<string> {
  return new Set(state.hiddenRelTypes);
}

export function highlightedNodeIdSet(state: GraphState): Set<string> {
  return new Set(state.highlightedNodeIds);
}

export function highlightedEdgeKeySet(state: GraphState): Set<string> {
  return new Set(state.highlightedEdgeKeys);
}

// ---------------------------------------------------------------------------
// Default / initial values
// ---------------------------------------------------------------------------

const initialState: GraphStateData = {
  graphNodes: [],
  graphEdges: [],
  filteredGraphNodes: [],
  filteredGraphEdges: [],
  graphLoading: false,
  graphError: null,

  selectedEntityId: null,
  selectedEntities: [],
  multiSelected: [],

  hiddenRelTypes: [],
  confidenceThreshold: 0,
  islandThreshold: 0,
  islandMetric: 'degree',

  layoutMode: 'force',
  colorMode: 'type',
  communityMap: {},
  collapseCommunities: false,
  nodePositions: {},

  temporalRange: [null, null],

  highlightedNodeIds: [],
  highlightedEdgeKeys: [],
  pathResult: null,
};

// ---------------------------------------------------------------------------
// Internal helper: apply all active filters to raw graph data
// ---------------------------------------------------------------------------

function computeFiltered(
  graphNodes: GraphNode[],
  graphEdges: GraphEdge[],
  hiddenRelTypes: string[],
  confidenceThreshold: number,
  islandThreshold: number,
  islandMetric: IslandMetric,
  temporalRange: [string | null, string | null],
  stats?: { entity_statistics?: EntityStats[] },
): { filteredNodes: GraphNode[]; filteredEdges: GraphEdge[] } {
  const hiddenSet = new Set(hiddenRelTypes);
  const [temporalStart, temporalEnd] = temporalRange;

  // 1. Filter edges by relationship type, confidence, and temporal range
  let edges = graphEdges.filter((e) => {
    if (hiddenSet.has(e.rel_type)) return false;
    if (
      confidenceThreshold > 0 &&
      (e.confidence === undefined || e.confidence < confidenceThreshold)
    )
      return false;
    // Temporal range filter
    if (temporalStart && e.last_seen && e.last_seen < temporalStart)
      return false;
    if (temporalEnd && e.first_seen && e.first_seen > temporalEnd)
      return false;
    return true;
  });

  // 2. Apply island threshold
  let filteredNodes: GraphNode[];

  if (islandThreshold > 0) {
    const metricMap: Record<string, number> = {};

    if (islandMetric === 'degree') {
      // Compute degree from current filtered edges
      for (const node of graphNodes) {
        metricMap[node.id] = 0;
      }
      for (const edge of edges) {
        const srcId = (edge.source_id ||
          (edge as Record<string, unknown>).source) as string;
        const tgtId = (edge.target_id ||
          (edge as Record<string, unknown>).target) as string;
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

    const visibleIds = new Set(
      graphNodes
        .filter((n) => metricMap[n.id] >= islandThreshold)
        .map((n) => n.id),
    );
    filteredNodes = graphNodes.filter((n) => visibleIds.has(n.id));
    edges = edges.filter((e) => {
      const srcId = (e.source_id ||
        (e as Record<string, unknown>).source) as string;
      const tgtId = (e.target_id ||
        (e as Record<string, unknown>).target) as string;
      return visibleIds.has(srcId) && visibleIds.has(tgtId);
    });
  } else {
    // No island threshold — handle orphans correctly
    const connectedIds = new Set<string>();
    for (const edge of edges) {
      connectedIds.add(
        String(edge.source_id || (edge as Record<string, unknown>).source),
      );
      connectedIds.add(
        String(edge.target_id || (edge as Record<string, unknown>).target),
      );
    }

    const hasActiveFilters =
      hiddenSet.size > 0 ||
      confidenceThreshold > 0 ||
      temporalStart !== null ||
      temporalEnd !== null;

    if (!hasActiveFilters) {
      filteredNodes = graphNodes;
    } else {
      // Show nodes that are connected after filtering, plus nodes that had no edges originally
      const originallyConnected = new Set<string>();
      for (const e of graphEdges) {
        originallyConnected.add(
          String(e.source_id || (e as Record<string, unknown>).source),
        );
        originallyConnected.add(
          String(e.target_id || (e as Record<string, unknown>).target),
        );
      }
      filteredNodes = graphNodes.filter(
        (n) => connectedIds.has(n.id) || !originallyConnected.has(n.id),
      );
    }
  }

  return { filteredNodes, filteredEdges: edges };
}

// ---------------------------------------------------------------------------
// The subset of state tracked by zundo for undo/redo.
// Excludes transient state (loading, error) and derived state (filtered*,
// nodePositions) so that only meaningful user actions are undoable.
// ---------------------------------------------------------------------------

type TrackedState = Omit<
  GraphStateData,
  | 'graphLoading'
  | 'graphError'
  | 'filteredGraphNodes'
  | 'filteredGraphEdges'
  | 'nodePositions'
>;

// ---------------------------------------------------------------------------
// Store creation with zundo temporal middleware
// ---------------------------------------------------------------------------

export const useGraphStore = create<GraphState>()(
  temporal(
    (set, get) => ({
      ...initialState,

      // -- Graph data --------------------------------------------------------
      setGraphData: (nodes, edges) => {
        const s = get();
        const { filteredNodes, filteredEdges } = computeFiltered(
          nodes,
          edges,
          s.hiddenRelTypes,
          s.confidenceThreshold,
          s.islandThreshold,
          s.islandMetric,
          s.temporalRange,
        );
        set({
          graphNodes: nodes,
          graphEdges: edges,
          filteredGraphNodes: filteredNodes,
          filteredGraphEdges: filteredEdges,
        });
      },

      setGraphLoading: (loading) => set({ graphLoading: loading }),
      setGraphError: (error) => set({ graphError: error }),

      // -- Selection ---------------------------------------------------------
      selectEntity: (id) => set({ selectedEntityId: id }),

      toggleMultiSelect: (entity) =>
        set((s) => {
          const exists = s.multiSelected.find((e) => e.id === entity.id);
          if (exists) {
            return {
              multiSelected: s.multiSelected.filter(
                (e) => e.id !== entity.id,
              ),
            };
          }
          return { multiSelected: [...s.multiSelected, entity] };
        }),

      addToSelectedEntities: (entity) =>
        set((s) => {
          if (s.selectedEntities.find((e) => e.id === entity.id)) return s;
          const next = [...s.selectedEntities, entity];
          // Keep at most 2 entities for path finding
          return { selectedEntities: next.slice(-2) };
        }),

      clearPath: () =>
        set({
          selectedEntities: [],
          highlightedNodeIds: [],
          highlightedEdgeKeys: [],
          pathResult: null,
        }),

      setHighlightedPath: (nodeIds, edgeKeys, result) =>
        set({
          highlightedNodeIds: Array.isArray(nodeIds)
            ? nodeIds
            : Array.from(nodeIds),
          highlightedEdgeKeys: Array.isArray(edgeKeys)
            ? edgeKeys
            : Array.from(edgeKeys),
          pathResult: result,
        }),

      // -- Filtering ---------------------------------------------------------
      toggleRelType: (relType) =>
        set((s) => {
          const asSet = new Set(s.hiddenRelTypes);
          if (asSet.has(relType)) {
            asSet.delete(relType);
          } else {
            asSet.add(relType);
          }
          return { hiddenRelTypes: Array.from(asSet) };
        }),

      setConfidenceThreshold: (value) => set({ confidenceThreshold: value }),
      setIslandThreshold: (value) => set({ islandThreshold: value }),
      setIslandMetric: (metric) => set({ islandMetric: metric }),

      // -- Layout & Display --------------------------------------------------
      setLayoutMode: (mode) => set({ layoutMode: mode }),
      setColorMode: (mode) => set({ colorMode: mode }),
      setCommunityMap: (map) => set({ communityMap: map }),
      setCollapseCommunities: (value) => set({ collapseCommunities: value }),

      // -- Temporal ----------------------------------------------------------
      setTemporalRange: (range) => set({ temporalRange: range }),

      // -- Node positions ----------------------------------------------------
      updateNodePositions: (positions) =>
        set((s) => ({
          nodePositions: { ...s.nodePositions, ...positions },
        })),

      // -- Filter computation ------------------------------------------------
      applyFilters: (stats) => {
        const s = get();
        const { filteredNodes, filteredEdges } = computeFiltered(
          s.graphNodes,
          s.graphEdges,
          s.hiddenRelTypes,
          s.confidenceThreshold,
          s.islandThreshold,
          s.islandMetric,
          s.temporalRange,
          stats,
        );
        set({
          filteredGraphNodes: filteredNodes,
          filteredGraphEdges: filteredEdges,
        });
      },

      resetFilters: () => {
        const s = get();
        const { filteredNodes, filteredEdges } = computeFiltered(
          s.graphNodes,
          s.graphEdges,
          [],
          0,
          0,
          'degree',
          [null, null],
        );
        set({
          hiddenRelTypes: [],
          confidenceThreshold: 0,
          islandThreshold: 0,
          islandMetric: 'degree',
          temporalRange: [null, null],
          filteredGraphNodes: filteredNodes,
          filteredGraphEdges: filteredEdges,
        });
      },
    }),
    {
      // zundo temporal options — only track meaningful state for undo/redo
      partialize: (state): TrackedState => ({
        graphNodes: state.graphNodes,
        graphEdges: state.graphEdges,
        selectedEntityId: state.selectedEntityId,
        selectedEntities: state.selectedEntities,
        multiSelected: state.multiSelected,
        hiddenRelTypes: state.hiddenRelTypes,
        confidenceThreshold: state.confidenceThreshold,
        islandThreshold: state.islandThreshold,
        islandMetric: state.islandMetric,
        layoutMode: state.layoutMode,
        colorMode: state.colorMode,
        communityMap: state.communityMap,
        collapseCommunities: state.collapseCommunities,
        temporalRange: state.temporalRange,
        highlightedNodeIds: state.highlightedNodeIds,
        highlightedEdgeKeys: state.highlightedEdgeKeys,
        pathResult: state.pathResult,
      }),
      limit: 50, // keep at most 50 undo steps
      equality: (pastState, currentState) =>
        JSON.stringify(pastState) === JSON.stringify(currentState),
    },
  ),
);

// ---------------------------------------------------------------------------
// Convenience hooks for undo/redo
// ---------------------------------------------------------------------------

type TemporalGraphState = TemporalState<TrackedState>;

/**
 * React hook that subscribes to the zundo temporal store and re-renders on
 * changes. Returns `{ undo, redo, clear, canUndo, canRedo }`.
 *
 * Usage:
 *   const { undo, redo, canUndo, canRedo } = useGraphUndo();
 */
export function useGraphUndo() {
  const temporalStoreApi = useGraphStore.temporal;

  const undo = useStore(temporalStoreApi, (s: TemporalGraphState) => s.undo);
  const redo = useStore(temporalStoreApi, (s: TemporalGraphState) => s.redo);
  const clear = useStore(temporalStoreApi, (s: TemporalGraphState) => s.clear);
  const pastStates = useStore(
    temporalStoreApi,
    (s: TemporalGraphState) => s.pastStates,
  );
  const futureStates = useStore(
    temporalStoreApi,
    (s: TemporalGraphState) => s.futureStates,
  );

  return {
    undo,
    redo,
    clear,
    pastStates,
    futureStates,
    canUndo: pastStates.length > 0,
    canRedo: futureStates.length > 0,
  };
}

// Re-export the temporal store for direct (non-React) access
export const getTemporalStore = () => useGraphStore.temporal;
