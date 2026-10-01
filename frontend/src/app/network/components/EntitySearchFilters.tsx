'use client';
import type { Dispatch, SetStateAction } from 'react';
import { TYPE_COLOR_CLASS as TYPE_COLORS } from '@/lib/entityStyles';
import { formatEntityType, type GraphNode } from '../types';

interface EntitySearchFiltersProps {
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  setTypeFilter: (type: string) => void;
  activeTypeFilters: Set<string>;
  setActiveTypeFilters: Dispatch<SetStateAction<Set<string>>>;
  typeFilterOpen: boolean;
  setTypeFilterOpen: (open: boolean) => void;
  graphNodes: GraphNode[];
}

/** The entity search box and the multi-select entity-type filter over the canvas. */
export default function EntitySearchFilters({
  searchQuery, setSearchQuery, setTypeFilter, activeTypeFilters, setActiveTypeFilters,
  typeFilterOpen, setTypeFilterOpen, graphNodes,
}: EntitySearchFiltersProps) {
  return (
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
          <span className="text-gray-500 ml-1">{typeFilterOpen ? '▲' : '▼'}</span>
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
  );
}
