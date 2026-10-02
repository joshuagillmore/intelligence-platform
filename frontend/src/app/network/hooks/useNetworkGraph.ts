'use client';
import { useCallback, useState } from 'react';
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

  const loadGraph = useCallback(async () => {
    if (!activeProject) return;
    setGraphLoading(true);
    setGraphError(null);
    try {
      const res = await graphApi.full(activeProject.id);
      const nodes = res.data.nodes || [];
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
      // The statistics table's own names for the backend's fields.
      const normalized: GraphStats = {
        total_nodes: raw.nodes,
        total_edges: raw.edges,
        density: raw.density,
        connected_components: raw.components,
        entity_statistics: raw.entities.map(e => ({
          entity: e.name,
          type: e.entity_type,
          degree: e.degree,
          betweenness: e.betweenness,
          eigenvector: e.eigenvector,
          pagerank: e.pagerank,
          closeness: e.closeness,
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
      // Each community lists its members: map every member to its community.
      // The response was read as a flat {entity_id, community} list, which it
      // never is, so the map came back empty and "Select Community" never showed.
      const map: Record<string, number> = {};
      for (const community of res.data) {
        for (const member of community.members) map[member.id] = community.community_id;
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
