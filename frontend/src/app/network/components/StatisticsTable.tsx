'use client';
import { intensityClass, type EntityStats, type SortKey } from '../types';

interface StatisticsTableProps {
  rows: EntityStats[];
  maxVals: Record<string, number>;
  onSort: (key: SortKey) => void;
  sortArrow: (key: SortKey) => string;
}

/** Per-entity centrality table, shown in place of the canvas on the Statistics tab. */
export default function StatisticsTable({ rows, maxVals, onSort, sortArrow }: StatisticsTableProps) {
  return (
    <div className="flex-1 overflow-auto p-4">
      <div className="flex items-center gap-4 mb-4">
        <h3 className="text-sm font-semibold text-gray-400">Entity Statistics</h3>
        <span className="text-xs text-gray-500">{rows.length} entities</span>
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
                  onClick={() => onSort(key)}
                  className="py-2 px-2 text-left text-gray-400 font-medium cursor-pointer hover:text-accent-blue select-none whitespace-nowrap"
                >
                  {label}{sortArrow(key)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
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
  );
}
