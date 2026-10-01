'use client';
import { formatRelType, type GraphEdge } from '../types';

interface EdgeOverviewProps {
  graphEdges: GraphEdge[];
  showLowSignalRel: boolean;
  toggleLowSignalRel: () => void;
}

type RelCount = { count: number; avgConf: number; totalConf: number };

/** The Statistics tab's edge overview: edges per relationship type and their average confidence. */
export default function EdgeOverview({ graphEdges, showLowSignalRel, toggleLowSignalRel }: EdgeOverviewProps) {
  // Aggregate edges by relationship type
  const relCounts: Record<string, RelCount> = {};
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
  const renderRow = ([rt, data]: [string, RelCount]) => (
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
    <div className="flex-1 overflow-y-auto p-3">
      <h4 className="text-xs font-semibold text-gray-400 mb-2">Edge Overview</h4>
      <div className="space-y-1">
        {typed.map(renderRow)}
        {typed.length === 0 && noise.length === 0 && <p className="text-xs text-gray-500">No edges in graph.</p>}
        {noise.length > 0 && (
          <div className={typed.length > 0 ? 'pt-1' : ''}>
            <button
              onClick={toggleLowSignalRel}
              className="w-full flex items-center justify-between text-[10px] text-gray-500 hover:text-gray-300 px-1 py-1"
            >
              <span>{showLowSignalRel ? '▾' : '▸'} Low-signal (Associated With)</span>
              <span>{noise[0][1].count}</span>
            </button>
            {showLowSignalRel && noise.map(renderRow)}
          </div>
        )}
      </div>
    </div>
  );
}
