'use client';
import { useState } from 'react';
import { entitiesApi } from '@/lib/api';
import type { Entity } from '../types';

/**
 * The two most recently clicked nodes and the shortest path between them,
 * highlighted on the canvas.
 */
export function useShortestPath() {
  const [selectedEntities, setSelectedEntities] = useState<Entity[]>([]);
  const [pathResult, setPathResult] = useState<{ path: string[]; length: number } | null>(null);
  const [pathLoading, setPathLoading] = useState(false);
  const [highlightedNodeIds, setHighlightedNodeIds] = useState<Set<string>>(new Set());
  const [highlightedEdgeKeys, setHighlightedEdgeKeys] = useState<Set<string>>(new Set());

  /** Track a clicked node as a path endpoint: toggle it, keeping the last two. */
  function trackPathEndpoint(entity: Entity) {
    setSelectedEntities(prev => {
      const exists = prev.find(e => e.id === entity.id);
      if (exists) {
        return prev.filter(e => e.id !== entity.id);
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

  return {
    selectedEntities,
    pathResult,
    pathLoading,
    highlightedNodeIds,
    highlightedEdgeKeys,
    trackPathEndpoint,
    findShortestPath,
    clearPath,
  };
}
