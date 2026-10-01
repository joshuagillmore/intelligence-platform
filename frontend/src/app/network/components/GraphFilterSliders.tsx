'use client';
import type { GraphStats, IslandMetric } from '../types';

interface GraphFilterSlidersProps {
  stats: GraphStats;
  maxVals: Record<string, number>;
  confidenceThreshold: number;
  setConfidenceThreshold: (value: number) => void;
  islandMetric: IslandMetric;
  setIslandMetric: (metric: IslandMetric) => void;
  islandThreshold: number;
  setIslandThreshold: (value: number) => void;
  egoHighlightDepth: number;
  setEgoHighlightDepth: (depth: number) => void;
}

/** Graph summary cards and the confidence, island and ego-highlight sliders. */
export default function GraphFilterSliders({
  stats, maxVals, confidenceThreshold, setConfidenceThreshold, islandMetric, setIslandMetric,
  islandThreshold, setIslandThreshold, egoHighlightDepth, setEgoHighlightDepth,
}: GraphFilterSlidersProps) {
  return (
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
            onChange={(e) => { setIslandMetric(e.target.value as IslandMetric); setIslandThreshold(0); }}
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
  );
}
