'use client';
import type { Dispatch, SetStateAction } from 'react';
import { TYPE_COLOR_CLASS as TYPE_COLORS } from '@/lib/entityStyles';
import { formatEntityType, type Entity } from '../types';

interface EntityListProps {
  entities: Entity[];
  entityTotal: number;
  expandedEntityTypes: Set<string>;
  setExpandedEntityTypes: Dispatch<SetStateAction<Set<string>>>;
  selectedEntity: Entity | null;
  multiSelected: Entity[];
  /** Shift+click: add to or remove from the multi-selection. */
  toggleMultiSelected: (entity: Entity) => void;
  selectEntity: (entity: Entity) => void;
}

/** The browse list: loaded entities grouped under collapsible type headings. */
export default function EntityList({
  entities, entityTotal, expandedEntityTypes, setExpandedEntityTypes, selectedEntity, multiSelected,
  toggleMultiSelected, selectEntity,
}: EntityListProps) {
  const grouped: Record<string, Entity[]> = {};
  entities.forEach(e => {
    const t = e.entity_type || 'Unknown';
    if (!grouped[t]) grouped[t] = [];
    grouped[t].push(e);
  });
  const sortedTypes = Object.keys(grouped).sort();

  if (entities.length === 0) {
    return (
      <div className="flex-1 overflow-y-auto">
        <p className="text-xs text-gray-500 p-3">No entities found.</p>
      </div>
    );
  }

  const truncated = entityTotal > entities.length;

  return (
    <div className="flex-1 overflow-y-auto">
      {/* Say so when this is a page rather than the whole set — the per-type
          counts below are counts of what loaded. */}
      {truncated ? (
        <p key="__truncated" className="text-[10px] text-amber-400/80 px-3 py-2 border-b border-navy-700">
          Showing {entities.length.toLocaleString()} of {entityTotal.toLocaleString()} entities.
          {' '}Search or filter by type to narrow.
        </p>
      ) : null}
      {sortedTypes.map(type => {
        const typeEntities = grouped[type];
        const isExpanded = expandedEntityTypes.has(type);
        return (
          <div key={type}>
            <button
              onClick={() => setExpandedEntityTypes(prev => {
                const next = new Set(prev);
                if (next.has(type)) next.delete(type); else next.add(type);
                return next;
              })}
              className="w-full text-left px-3 py-2 text-xs font-semibold border-b border-navy-700 hover:bg-navy-700 flex items-center gap-2 text-gray-400"
            >
              <span className="text-[10px]">{isExpanded ? '▼' : '▶'}</span>
              <span className={`w-2 h-2 rounded-full flex-none ${TYPE_COLORS[type] || 'bg-gray-500'}`} />
              <span className="flex-1">{formatEntityType(type)}</span>
              <span className="text-[10px] text-gray-500 bg-navy-600 px-1.5 py-0.5 rounded-full">{typeEntities.length}</span>
            </button>
            {isExpanded && typeEntities.map(entity => (
              <button
                key={entity.id}
                onClick={(e) => {
                  if (e.shiftKey) {
                    // Shift+click adds to multi-select
                    toggleMultiSelected(entity);
                  } else {
                    selectEntity(entity);
                  }
                }}
                className={`w-full text-left pl-8 pr-3 py-1.5 text-xs border-b border-navy-700/50 hover:bg-navy-700 transition-colors flex items-center gap-2 ${
                  selectedEntity?.id === entity.id ? 'bg-navy-700 text-accent-blue'
                  : multiSelected.find(x => x.id === entity.id) ? 'bg-navy-700/50 text-purple-400'
                  : 'text-gray-300'
                }`}
              >
                {multiSelected.find(x => x.id === entity.id) && (
                  <span className="w-2 h-2 rounded-full bg-purple-500 flex-none" />
                )}
                <span className="truncate">{entity.name}</span>
              </button>
            ))}
          </div>
        );
      })}
    </div>
  );
}
