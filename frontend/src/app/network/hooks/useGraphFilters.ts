'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { collapseToCommunities } from '@/lib/graphLayout';
import { filterGraph } from '../graphFilters';
import type { FilterSnapshot, GraphEdge, GraphNode, GraphStats, IslandMetric } from '../types';

interface GraphFilterSources {
  graphNodes: GraphNode[];
  graphEdges: GraphEdge[];
  stats: GraphStats | null;
  /** The viewed snapshot's entity ids, or null when no snapshot is viewed. */
  activeSnapshotIds: Set<string> | null;
}

/**
 * Every filter over the graph canvas, the filtered (and optionally
 * community-collapsed) result, and the hand-rolled undo/redo over the
 * relationship-type, confidence and island filters (Ctrl+Z / Ctrl+Shift+Z).
 */
export function useGraphFilters({ graphNodes, graphEdges, stats, activeSnapshotIds }: GraphFilterSources) {
  const [activeTypeFilters, setActiveTypeFilters] = useState<Set<string>>(new Set());
  const [islandThreshold, setIslandThreshold] = useState(0);
  const [islandMetric, setIslandMetric] = useState<IslandMetric>('degree');
  const [filteredGraphNodes, setFilteredGraphNodes] = useState<GraphNode[]>([]);
  const [filteredGraphEdges, setFilteredGraphEdges] = useState<GraphEdge[]>([]);
  // Relationship type filter
  const [hiddenRelTypes, setHiddenRelTypes] = useState<Set<string>>(new Set());
  // Confidence threshold
  const [confidenceThreshold, setConfidenceThreshold] = useState(0);
  const [collapseCommunities, setCollapseCommunities] = useState(false);
  // Temporal range filter for graph edges (P0.5)
  const [temporalRange, setTemporalRange] = useState<[string | null, string | null]>([null, null]);
  // Event-date filter, driven by the histogram brush below the canvas. Keys are
  // histogram bin keys ("2026-03"), compared as ISO prefixes — ISO dates sort
  // lexicographically, so no date parsing is needed to test membership.
  const [eventRange, setEventRange] = useState<[string | null, string | null]>([null, null]);
  const [hideUndated, setHideUndated] = useState(false);
  // Undo/redo history stack
  const [undoStack, setUndoStack] = useState<FilterSnapshot[]>([]);
  const [redoStack, setRedoStack] = useState<FilterSnapshot[]>([]);

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

  // Combined filter: snapshot + entity type + event-date brush + relationship
  // type + confidence + temporal range + island threshold. The logic lives in
  // graphFilters.filterGraph; it always applies the brushed node set and never
  // returns an edge whose endpoint is hidden (d3 cannot resolve one).
  useEffect(() => {
    const { nodes, edges } = filterGraph({
      nodes: graphNodes,
      edges: graphEdges,
      activeTypeFilters,
      eventRange,
      hideUndated,
      hiddenRelTypes,
      confidenceThreshold,
      temporalRange,
      islandThreshold,
      islandMetric,
      entityStats: stats?.entity_statistics ?? null,
      snapshotIds: activeSnapshotIds,
    });
    setFilteredGraphNodes(nodes);
    setFilteredGraphEdges(edges);
  }, [graphNodes, graphEdges, islandThreshold, islandMetric, hiddenRelTypes, confidenceThreshold, temporalRange, eventRange, hideUndated, stats, activeTypeFilters, activeSnapshotIds]);

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

  function undo() {
    if (undoStack.length > 0) {
      const prevState = undoStack[undoStack.length - 1];
      setUndoStack(prev => prev.slice(0, -1));
      setRedoStack(prev => [...prev, { hiddenRelTypes, confidenceThreshold, islandThreshold }]);
      setHiddenRelTypes(prevState.hiddenRelTypes);
      setConfidenceThreshold(prevState.confidenceThreshold);
      setIslandThreshold(prevState.islandThreshold);
    }
  }

  function redo() {
    if (redoStack.length > 0) {
      const nextState = redoStack[redoStack.length - 1];
      setRedoStack(prev => prev.slice(0, -1));
      setUndoStack(prev => [...prev, { hiddenRelTypes, confidenceThreshold, islandThreshold }]);
      setHiddenRelTypes(nextState.hiddenRelTypes);
      setConfidenceThreshold(nextState.confidenceThreshold);
      setIslandThreshold(nextState.islandThreshold);
    }
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

  return {
    activeTypeFilters, setActiveTypeFilters,
    islandThreshold, setIslandThreshold,
    islandMetric, setIslandMetric,
    hiddenRelTypes, setHiddenRelTypes, toggleRelType, allRelTypes,
    confidenceThreshold, setConfidenceThreshold,
    collapseCommunities, setCollapseCommunities,
    temporalRange, setTemporalRange,
    eventRange, setEventRange,
    hideUndated, setHideUndated,
    filteredGraphNodes, setFilteredGraphNodes,
    filteredGraphEdges, setFilteredGraphEdges,
    displayData,
    canUndo: undoStack.length > 0,
    canRedo: redoStack.length > 0,
    undo,
    redo,
  };
}
