'use client';
import type { ColorMode, LayoutMode } from '@/components/GraphVisualization';

interface GraphToolbarProps {
  // Relationship-type filter
  allRelTypes: string[];
  hiddenRelTypes: Set<string>;
  setHiddenRelTypes: (types: Set<string>) => void;
  toggleRelType: (relType: string) => void;
  relFilterOpen: boolean;
  setRelFilterOpen: (open: boolean) => void;
  // Presentation
  layoutMode: LayoutMode;
  setLayoutMode: (mode: LayoutMode) => void;
  colorMode: ColorMode;
  setColorMode: (mode: ColorMode) => void;
  collapseCommunities: boolean;
  setCollapseCommunities: (collapse: boolean) => void;
  // Filter history
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
}

/** Toolbar row: relationship filter, layout, colouring, community collapse, undo/redo. */
export default function GraphToolbar({
  allRelTypes, hiddenRelTypes, setHiddenRelTypes, toggleRelType, relFilterOpen, setRelFilterOpen,
  layoutMode, setLayoutMode, colorMode, setColorMode, collapseCommunities, setCollapseCommunities,
  canUndo, canRedo, onUndo, onRedo,
}: GraphToolbarProps) {
  return (
    <div className="flex-none px-4 py-1.5 border-b border-navy-600 bg-navy-800/80 hidden md:flex items-center gap-3 flex-wrap">
      {/* Relationship Filter */}
      <div className="relative">
        <button
          onClick={() => setRelFilterOpen(!relFilterOpen)}
          className="flex items-center gap-1.5 bg-navy-700 hover:bg-navy-600 border border-navy-600 rounded px-2.5 py-1 text-xs text-gray-300 transition-colors"
        >
          <span>Rel Filter</span>
          {hiddenRelTypes.size > 0 && (
            <span className="bg-accent-blue text-white rounded-full px-1.5 text-[10px] font-bold">{hiddenRelTypes.size}</span>
          )}
          <span className="text-gray-500 text-[10px]">{relFilterOpen ? '▲' : '▼'}</span>
        </button>
        {relFilterOpen && (
          <div className="absolute z-20 mt-1 bg-navy-700 border border-navy-600 rounded shadow-lg max-h-56 overflow-y-auto w-56">
            {allRelTypes.length === 0 ? (
              <p className="text-xs text-gray-500 p-2">No relationships found.</p>
            ) : (
              <>
                <div className="flex items-center justify-between px-2 py-1 border-b border-navy-600">
                  <button
                    onClick={() => setHiddenRelTypes(new Set())}
                    className="text-[10px] text-accent-blue hover:underline"
                  >
                    Show All
                  </button>
                  <button
                    onClick={() => setHiddenRelTypes(new Set(allRelTypes))}
                    className="text-[10px] text-gray-400 hover:underline"
                  >
                    Hide All
                  </button>
                </div>
                {allRelTypes.map(rt => (
                  <label key={rt} className="flex items-center gap-2 px-2 py-1.5 text-xs hover:bg-navy-600 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={!hiddenRelTypes.has(rt)}
                      onChange={() => toggleRelType(rt)}
                      className="accent-accent-blue rounded"
                    />
                    <span className={hiddenRelTypes.has(rt) ? 'text-gray-500 line-through' : 'text-gray-200'}>{rt}</span>
                  </label>
                ))}
              </>
            )}
          </div>
        )}
      </div>

      {/* Active filter chips */}
      {hiddenRelTypes.size > 0 && (
        <div className="flex items-center gap-1 flex-wrap">
          {Array.from(hiddenRelTypes).map(rt => (
            <button
              key={rt}
              onClick={() => toggleRelType(rt)}
              className="flex items-center gap-1 bg-red-900/40 text-red-300 border border-red-800/50 rounded-full px-2 py-0.5 text-[10px] hover:bg-red-900/60 transition-colors"
            >
              <span>{rt}</span>
              <span className="font-bold">&times;</span>
            </button>
          ))}
        </div>
      )}

      {/* Divider */}
      <div className="w-px h-5 bg-navy-600" />

      {/* Layout Selector */}
      <div className="flex items-center gap-1.5">
        <label className="text-xs text-gray-400">Layout</label>
        <div className="flex rounded overflow-hidden border border-navy-600">
          {([
            ['force', 'Force-Directed'],
            ['radial', 'Radial'],
            ['hierarchical', 'Hierarchical'],
          ] as [LayoutMode, string][]).map(([mode, label]) => (
            <button
              key={mode}
              onClick={() => setLayoutMode(mode)}
              className={`px-2 py-1 text-[11px] transition-colors ${
                layoutMode === mode
                  ? 'bg-accent-blue text-white'
                  : 'bg-navy-700 text-gray-400 hover:bg-navy-600 hover:text-gray-200'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Divider */}
      <div className="w-px h-5 bg-navy-600" />

      {/* Color Mode Toggle */}
      <div className="flex items-center gap-1.5">
        <label className="text-xs text-gray-400">Color by</label>
        <div className="flex rounded overflow-hidden border border-navy-600">
          {([
            ['type', 'Type'],
            ['community', 'Community'],
          ] as [ColorMode, string][]).map(([mode, label]) => (
            <button
              key={mode}
              onClick={() => setColorMode(mode)}
              className={`px-2 py-1 text-[11px] transition-colors ${
                colorMode === mode
                  ? 'bg-accent-blue text-white'
                  : 'bg-navy-700 text-gray-400 hover:bg-navy-600 hover:text-gray-200'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Divider */}
      <div className="w-px h-5 bg-navy-600" />

      {/* Community Collapse Toggle */}
      <button
        onClick={() => setCollapseCommunities(!collapseCommunities)}
        className={`px-3 py-1 rounded text-xs transition-colors ${
          collapseCommunities ? 'bg-accent-blue text-white' : 'bg-navy-700 text-gray-300 border border-navy-600 hover:bg-navy-600'
        }`}
      >
        {collapseCommunities ? 'Expand Communities' : 'Collapse Communities'}
      </button>

      {/* Divider */}
      <div className="w-px h-5 bg-navy-600" />

      {/* Undo/Redo */}
      <div className="flex items-center gap-1">
        <button
          onClick={onUndo}
          disabled={!canUndo}
          className="px-2 py-1 rounded text-xs bg-navy-700 border border-navy-600 text-gray-400 hover:bg-navy-600 disabled:opacity-30 disabled:cursor-not-allowed"
          title="Undo (Ctrl+Z)"
        >
          Undo
        </button>
        <button
          onClick={onRedo}
          disabled={!canRedo}
          className="px-2 py-1 rounded text-xs bg-navy-700 border border-navy-600 text-gray-400 hover:bg-navy-600 disabled:opacity-30 disabled:cursor-not-allowed"
          title="Redo (Ctrl+Shift+Z)"
        >
          Redo
        </button>
      </div>
    </div>
  );
}
