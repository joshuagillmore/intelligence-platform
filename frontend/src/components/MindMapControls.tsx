'use client';
import { useState, useCallback } from 'react';

export type LayoutMode = 'radial' | 'horizontal';

interface BreadcrumbItem {
  id: string;
  name: string;
}

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
            className="w-full bg-[#090e1c] border border-[#1a1f2e] rounded-sm px-2.5 py-1.5 text-[11px] text-gray-300 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-[#adc6ff]/50"
          />
        </div>

        {/* Zoom controls */}
        <div className="flex items-center gap-0.5 bg-[#1a1f2e] rounded-sm border border-[#252a39]">
          <button
            onClick={onZoomOut}
            className="px-2 py-1.5 text-[11px] text-gray-400 hover:text-white transition-colors"
            title="Zoom out"
          >
            &minus;
          </button>
          <button
            onClick={onZoomReset}
            className="px-2 py-1.5 text-[9px] font-bold text-gray-500 hover:text-white transition-colors uppercase"
            title="Reset zoom"
          >
            Fit
          </button>
          <button
            onClick={onZoomIn}
            className="px-2 py-1.5 text-[11px] text-gray-400 hover:text-white transition-colors"
            title="Zoom in"
          >
            +
          </button>
        </div>

        {/* Layout toggle */}
        <div className="flex items-center gap-0.5 bg-[#1a1f2e] rounded-sm border border-[#252a39]">
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
        <div className="flex items-center gap-0.5 bg-[#1a1f2e] rounded-sm border border-[#252a39]">
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
      </div>
    </div>
  );
}
