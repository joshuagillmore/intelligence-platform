'use client';
import GraphVisualization, { type ColorMode, type LayoutMode } from '@/components/GraphVisualization';
import TemporalSlider from '@/components/TemporalSlider';
import TemporalHistogram, { type HistogramData } from '@/components/TemporalHistogram';
import LoadingSpinner from '@/components/LoadingSpinner';
import type { GraphEdge, GraphNode } from '../types';

interface GraphCanvasProps {
  graphLoading: boolean;
  graphError: string | null;
  onRetry: () => void;
  /** Whether the filters left anything to draw. */
  hasNodes: boolean;
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick: (node: GraphNode, event?: MouseEvent) => void;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onEdgeClick: (edge: any) => void;
  selectedNodeId: string | undefined;
  highlightedNodeIds: Set<string>;
  highlightedEdgeKeys: Set<string>;
  layout: LayoutMode;
  colorMode: ColorMode;
  communityMap: Record<string, number>;
  egoHighlightDepth: number;
  projectMissing: boolean;
  projectId: string | undefined;
  // Chronology brush (event dates) and the ingestion-time slider.
  histogram: HistogramData | null;
  histogramLoading: boolean;
  histogramError: string | null;
  eventRange: [string | null, string | null];
  setEventRange: (range: [string | null, string | null]) => void;
  hideUndated: boolean;
  setHideUndated: (hide: boolean) => void;
  setHistogramBucket: (bucket: 'day' | 'month' | 'year') => void;
  graphEdges: GraphEdge[];
  temporalRange: [string | null, string | null];
  setTemporalRange: (range: [string | null, string | null]) => void;
}

/** The d3 graph (or its loading, error and empty states) with the time filters beneath it. */
export default function GraphCanvas({
  graphLoading, graphError, onRetry, hasNodes, nodes, edges, onNodeClick, onEdgeClick, selectedNodeId,
  highlightedNodeIds, highlightedEdgeKeys, layout, colorMode, communityMap, egoHighlightDepth,
  projectMissing, projectId,
  histogram, histogramLoading, histogramError, eventRange, setEventRange, hideUndated, setHideUndated,
  setHistogramBucket, graphEdges, temporalRange, setTemporalRange,
}: GraphCanvasProps) {
  return (
    <div className="flex-1 relative">
      {graphLoading ? (
        <div className="flex items-center justify-center h-full">
          <LoadingSpinner size="lg" />
        </div>
      ) : graphError ? (
        <div className="flex items-center justify-center h-full text-red-400">
          <div className="text-center">
            <p className="mb-2">{graphError}</p>
            <button onClick={onRetry} className="text-xs text-accent-blue hover:underline">Retry</button>
          </div>
        </div>
      ) : hasNodes ? (
        <GraphVisualization
          nodes={nodes}
          edges={edges}
          onNodeClick={onNodeClick}
          onEdgeClick={onEdgeClick as never}
          selectedNodeId={selectedNodeId}
          highlightedNodeIds={highlightedNodeIds}
          highlightedEdgeKeys={highlightedEdgeKeys}
          layout={layout}
          colorMode={colorMode}
          communityMap={communityMap}
          egoHighlightDepth={egoHighlightDepth}
        />
      ) : projectMissing ? (
        <div className="flex flex-col items-center justify-center h-full gap-2 text-center px-6">
          <p className="text-gray-300">
            No project found with the ID <span className="font-mono text-gray-400">{projectId}</span>.
          </p>
          <p className="text-xs text-gray-500 max-w-md">
            It may have been deleted, or this browser is remembering a project from a
            different environment. Pick another project to continue.
          </p>
        </div>
      ) : (
        <div className="flex items-center justify-center h-full text-gray-500">
          <p>No graph data. Ingest documents to populate the knowledge graph.</p>
        </div>
      )}
      {/* Chronology brush — filters the graph by when events
          happened. The slider beside it filters on first_seen /
          last_seen, which are ingestion timestamps, so it answers
          "when did we learn this" rather than "when did it happen";
          the two are kept distinct on purpose. */}
      <TemporalHistogram
        data={histogram}
        loading={histogramLoading}
        error={histogramError}
        value={eventRange}
        onChange={setEventRange}
        hideUndated={hideUndated}
        onHideUndatedChange={setHideUndated}
        onBucketChange={setHistogramBucket}
      />
      <TemporalSlider
        edges={graphEdges}
        value={temporalRange}
        onChange={setTemporalRange}
      />
    </div>
  );
}
