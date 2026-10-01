'use client';
import { useCallback, useRef, useState } from 'react';
import { graphApi } from '@/lib/api';
import { getErrorMessage } from '@/lib/errorMessages';
import { normaliseGraphEdge } from '../graphFilters';
import type { GraphEdge, GraphNode, GraphStats, StructuralHoleEntry } from '../types';

/**
 * The project's graph and the project-level analytics read alongside it:
 * statistics, communities and structural holes. Each loader is stable for a
 * given project; the page runs them together when the project changes.
 */
export function useNetworkGraph(activeProject: { id: string } | null) {
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphEdges, setGraphEdges] = useState<GraphEdge[]>([]);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState<string | null>(null);
  // /graph returns a display budget of the most-connected entities and says
  // when that is less than the whole project.
  const [graphTruncated, setGraphTruncated] = useState(false);
  // True when the backend says the selected project id refers to nothing at all
  // — distinct from a project that exists and is empty.
  const [projectMissing, setProjectMissing] = useState(false);
  const [stats, setStats] = useState<GraphStats | null>(null);
  const [communityMap, setCommunityMap] = useState<Record<string, number>>({});
  const [structuralHoles, setStructuralHoles] = useState<StructuralHoleEntry[]>([]);
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
      // One edge shape for the page whichever keys the route sends, with
      // evidence / method / source_doc_id as text for the edge panel.
      setGraphEdges(((res.data.edges || []) as Record<string, unknown>[]).map(normaliseGraphEdge) as unknown as GraphEdge[]);
      setGraphTruncated(res.data.truncated === true);
      // The selected project is remembered in localStorage, so a project that
      // has since been deleted stays selected and every view reports "no data".
      // `project_exists === false` is the backend saying the id refers to
      // nothing at all, which is a different message entirely.
      setProjectMissing(res.data.project_exists === false);
    } catch (e) {
      console.error('Failed to load graph', e);
      setGraphError(getErrorMessage(e));
    } finally {
      setGraphLoading(false);
    }
  }, [activeProject]);

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

  const loadStructuralHoles = useCallback(async () => {
    if (!activeProject) return;
    try {
      const res = await graphApi.structuralHoles(activeProject.id, 20);
      setStructuralHoles(res.data || []);
    } catch (e) {
      console.error('Failed to load structural holes', e);
    }
  }, [activeProject]);

  return {
    graphNodes,
    graphEdges,
    graphLoading,
    graphError,
    graphTruncated,
    projectMissing,
    stats,
    communityMap,
    structuralHoles,
    loadGraph,
    loadStatistics,
    loadCommunities,
    loadStructuralHoles,
  };
}
