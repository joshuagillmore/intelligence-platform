'use client';
import { useState, useCallback } from 'react';

export type LayoutMode = 'radial' | 'horizontal';

interface BreadcrumbItem {
  id: string;
  name: string;
}

export type ClusteringMethod = 'tfidf' | 'semantic';
export type Granularity = 'broad' | 'medium' | 'detailed';

interface MindMapControlsProps {
  layout: LayoutMode;
  onLayoutChange: (mode: LayoutMode) => void;
  onSearch: (query: string) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onZoomReset: () => void;
  onExpandAll: () => void;
  onCollapseAll: () => void;
  breadcrumbs: BreadcrumbItem[];
  onBreadcrumbClick: (item: BreadcrumbItem) => void;
  // New controls
  clusteringMethod?: ClusteringMethod;
  onClusteringMethodChange?: (method: ClusteringMethod) => void;
  granularity?: Granularity;
  onGranularityChange?: (granularity: Granularity) => void;
  onExport?: (format: string) => void;
}

export default function MindMapControls({
  layout,
  onLayoutChange,
  onSearch,
  onZoomIn,
  onZoomOut,
  onZoomReset,
  onExpandAll,
  onCollapseAll,
  breadcrumbs,
  onBreadcrumbClick,
  clusteringMethod,
  onClusteringMethodChange,
  granularity,
  onGranularityChange,
  onExport,
}: MindMapControlsProps) {
  const [searchQuery, setSearchQuery] = useState('');

  const handleSearch = useCallback((value: string) => {
    setSearchQuery(value);
    onSearch(value);
  }, [onSearch]);

  return (
    <div className="flex flex-col gap-2">
      {/* Breadcrumbs */}
      {breadcrumbs.length > 0 && (
        <div className="flex items-center gap-1 text-[10px] text-gray-400 px-1 overflow-x-auto">
          {breadcrumbs.map((item, i) => (
            <span key={item.id} className="flex items-center gap-1 whitespace-nowrap">
              {i > 0 && <span className="text-gray-600">&rsaquo;</span>}
              <button
                onClick={() => onBreadcrumbClick(item)}
                className="hover:text-[#adc6ff] transition-colors"
              >
                {item.name}
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Controls bar */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* Search */}
        <div className="flex-1 min-w-[160px] max-w-[280px]">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="Search topics..."
            className="w-full bg-[#090e1c] border border-navy-800 rounded-sm px-2.5 py-1.5 text-[11px] text-gray-300 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-[#adc6ff]/50"
          />
        </div>

        {/* Zoom controls */}
        <div className="flex items-center gap-0.5 bg-navy-800 rounded-sm border border-[#252a39]">
          <button
            onClick={onZoomOut}
            className="px-2 py-1.5 text-[11px] text-gray-400 hover:text-white transition-colors"
            title="Zoom out"
            aria-label="Zoom out"
          >
            &minus;
          </button>
          <button
            onClick={onZoomReset}
            className="px-2 py-1.5 text-[9px] font-bold text-gray-500 hover:text-white transition-colors uppercase"
            title="Reset zoom"
            aria-label="Reset zoom"
          >
            Fit
          </button>
          <button
            onClick={onZoomIn}
            className="px-2 py-1.5 text-[11px] text-gray-400 hover:text-white transition-colors"
            title="Zoom in"
            aria-label="Zoom in"
          >
            +
          </button>
        </div>

        {/* Layout toggle */}
        <div className="flex items-center gap-0.5 bg-navy-800 rounded-sm border border-[#252a39]">
          <button
            onClick={() => onLayoutChange('radial')}
            className={`px-2.5 py-1.5 text-[9px] font-bold uppercase tracking-wider transition-colors rounded-l-sm ${
              layout === 'radial'
                ? 'bg-[#adc6ff]/15 text-[#adc6ff] border-r border-[#adc6ff]/20'
                : 'text-gray-500 hover:text-gray-300'
            }`}
            title="Radial layout"
          >
            Radial
          </button>
          <button
            onClick={() => onLayoutChange('horizontal')}
            className={`px-2.5 py-1.5 text-[9px] font-bold uppercase tracking-wider transition-colors rounded-r-sm ${
              layout === 'horizontal'
                ? 'bg-[#adc6ff]/15 text-[#adc6ff] border-l border-[#adc6ff]/20'
                : 'text-gray-500 hover:text-gray-300'
            }`}
            title="Horizontal layout"
          >
            Tree
          </button>
        </div>

        {/* Expand/Collapse */}
        <div className="flex items-center gap-0.5 bg-navy-800 rounded-sm border border-[#252a39]">
          <button
            onClick={onExpandAll}
            className="px-2.5 py-1.5 text-[9px] font-bold text-gray-500 hover:text-white transition-colors uppercase tracking-wider"
            title="Expand all nodes"
          >
            Expand
          </button>
          <button
            onClick={onCollapseAll}
            className="px-2.5 py-1.5 text-[9px] font-bold text-gray-500 hover:text-white transition-colors uppercase tracking-wider"
            title="Collapse all nodes"
          >
            Collapse
          </button>
        </div>

        {/* Clustering method toggle */}
        {onClusteringMethodChange && (
          <div className="flex items-center gap-0.5 bg-navy-800 rounded-sm border border-[#252a39]">
            <button
              onClick={() => onClusteringMethodChange('tfidf')}
              className={`px-2.5 py-1.5 text-[9px] font-bold uppercase tracking-wider transition-colors rounded-l-sm ${
                clusteringMethod === 'tfidf'
                  ? 'bg-[#adc6ff]/15 text-[#adc6ff]'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
              title="Keyword-based clustering (TF-IDF)"
            >
              Keywords
            </button>
            <button
              onClick={() => onClusteringMethodChange('semantic')}
              className={`px-2.5 py-1.5 text-[9px] font-bold uppercase tracking-wider transition-colors rounded-r-sm ${
                clusteringMethod === 'semantic'
                  ? 'bg-emerald-500/15 text-emerald-400'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
              title="Semantic embedding-based clustering"
            >
              Semantic
            </button>
          </div>
        )}

        {/* Granularity control */}
        {onGranularityChange && (
          <div className="flex items-center gap-0.5 bg-navy-800 rounded-sm border border-[#252a39]">
            {(['broad', 'medium', 'detailed'] as const).map((g) => (
              <button
                key={g}
                onClick={() => onGranularityChange(g)}
                className={`px-2 py-1.5 text-[9px] font-bold uppercase tracking-wider transition-colors ${
                  granularity === g
                    ? 'bg-[#adc6ff]/15 text-[#adc6ff]'
                    : 'text-gray-500 hover:text-gray-300'
                }`}
                title={`${g} granularity`}
              >
                {g === 'broad' ? '◉' : g === 'medium' ? '◉◉' : '◉◉◉'}
              </button>
            ))}
          </div>
        )}

        {/* Export */}
        {onExport && (
          <div className="flex items-center gap-0.5 bg-navy-800 rounded-sm border border-[#252a39]">
            <button
              onClick={() => onExport('json')}
              className="px-2 py-1.5 text-[9px] font-bold text-gray-500 hover:text-white transition-colors uppercase tracking-wider"
              title="Export as JSON"
            >
              JSON
            </button>
            <button
              onClick={() => onExport('markdown')}
              className="px-2 py-1.5 text-[9px] font-bold text-gray-500 hover:text-white transition-colors uppercase tracking-wider"
              title="Export as Markdown"
            >
              MD
            </button>
            <button
              onClick={() => onExport('mermaid')}
              className="px-2 py-1.5 text-[9px] font-bold text-gray-500 hover:text-white transition-colors uppercase tracking-wider"
              title="Export as Mermaid diagram"
            >
              Mermaid
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
