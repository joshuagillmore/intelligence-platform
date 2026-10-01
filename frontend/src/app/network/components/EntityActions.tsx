'use client';
import { ENTITY_TYPE_OPTIONS, type Entity } from '../types';

interface EntityActionsProps {
  selectedEntity: Entity;
  isWatchlisted: boolean;
  watchlistLoading: boolean;
  onToggleWatchlist: () => void;
  typeDropdownOpen: boolean;
  setTypeDropdownOpen: (open: boolean) => void;
  onChangeType: (entityType: string) => void;
}

/** Watchlist toggle and entity-type change for the selected entity. */
export default function EntityActions({
  selectedEntity, isWatchlisted, watchlistLoading, onToggleWatchlist, typeDropdownOpen, setTypeDropdownOpen, onChangeType,
}: EntityActionsProps) {
  return (
    <div className="space-y-2">
      <h4 className="text-sm font-semibold text-gray-400">Entity Actions</h4>
      <button
        onClick={onToggleWatchlist}
        disabled={watchlistLoading}
        className={`w-full px-3 py-2 rounded text-xs font-medium transition-colors disabled:opacity-50 ${
          isWatchlisted
            ? 'bg-yellow-600 hover:bg-yellow-700 text-white'
            : 'bg-navy-600 hover:bg-navy-700 text-gray-200 border border-navy-600'
        }`}
      >
        {watchlistLoading ? 'Updating...' : isWatchlisted ? '★ Remove from Watchlist' : '☆ Add to Watchlist'}
      </button>

      <div className="relative">
        <button
          onClick={() => setTypeDropdownOpen(!typeDropdownOpen)}
          className="w-full bg-navy-600 hover:bg-navy-700 text-gray-200 px-3 py-2 rounded text-xs font-medium border border-navy-600 text-left flex justify-between items-center"
        >
          <span>Change Type: {selectedEntity.entity_type}</span>
          <span className="text-gray-500">{typeDropdownOpen ? '▲' : '▼'}</span>
        </button>
        {typeDropdownOpen && (
          <div className="absolute z-10 mt-1 w-full bg-navy-700 border border-navy-600 rounded shadow-lg max-h-48 overflow-y-auto">
            {ENTITY_TYPE_OPTIONS.map((t) => (
              <button
                key={t}
                onClick={() => onChangeType(t)}
                className={`w-full text-left px-3 py-1.5 text-xs hover:bg-navy-600 transition-colors ${
                  selectedEntity.entity_type === t ? 'text-accent-blue font-medium' : 'text-gray-300'
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
