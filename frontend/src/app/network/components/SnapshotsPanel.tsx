'use client';
import { nodeEntity, type Entity, type GraphNode } from '../types';
import type { SnapshotSummary } from '../hooks/useSnapshots';

interface SnapshotsPanelProps {
  snapshots: SnapshotSummary[];
  activeSnapshotId: string | null;
  snapshotFormOpen: boolean;
  setSnapshotFormOpen: (open: boolean) => void;
  snapshotNameInput: string;
  setSnapshotNameInput: (name: string) => void;
  onSave: () => void;
  onView: (snapshotId: string) => void;
  onClearView: () => void;
  onDelete: (snapshotId: string) => void;
  // Mass selection helpers
  filteredGraphNodes: GraphNode[];
  selectedEntity: Entity | null;
  communityMap: Record<string, number>;
  multiSelected: Entity[];
  setMultiSelected: (entities: Entity[]) => void;
}

/** Snapshots ("bins") of the multi-selection, and the mass-selection helpers. */
export default function SnapshotsPanel({
  snapshots, activeSnapshotId, snapshotFormOpen, setSnapshotFormOpen, snapshotNameInput, setSnapshotNameInput,
  onSave, onView, onClearView, onDelete,
  filteredGraphNodes, selectedEntity, communityMap, multiSelected, setMultiSelected,
}: SnapshotsPanelProps) {
  return (
    <div className="flex-none border-t border-navy-600">
      <div className="px-3 py-2 flex items-center justify-between">
        <h4 className="text-xs font-semibold text-gray-400">Snapshots / Bins</h4>
        <div className="flex items-center gap-1">
          {activeSnapshotId && (
            <button onClick={onClearView} className="text-[10px] text-accent-blue hover:underline">Clear</button>
          )}
        </div>
      </div>
      {/* Mass selection helpers */}
      <div className="px-3 pb-2 flex flex-wrap gap-1">
        <button
          onClick={() => {
            const allEntities = filteredGraphNodes.map(nodeEntity);
            setMultiSelected(allEntities);
          }}
          className="text-[9px] px-2 py-0.5 rounded bg-navy-600 text-gray-300 hover:bg-navy-500"
        >
          Select All Visible
        </button>
        {selectedEntity && communityMap[selectedEntity.id] !== undefined && (
          <button
            onClick={() => {
              const cid = communityMap[selectedEntity.id];
              const communityEntities = filteredGraphNodes
                .filter(n => communityMap[n.id] === cid)
                .map(nodeEntity);
              setMultiSelected(communityEntities);
            }}
            className="text-[9px] px-2 py-0.5 rounded bg-purple-800 text-gray-300 hover:bg-purple-700"
          >
            Select Community
          </button>
        )}
        {multiSelected.length > 0 && (
          <>
            <span className="text-[9px] text-purple-400 px-1 py-0.5">{multiSelected.length} selected</span>
            <button onClick={() => setMultiSelected([])} className="text-[9px] px-2 py-0.5 rounded bg-navy-600 text-gray-400 hover:bg-navy-500">Clear</button>
          </>
        )}
      </div>
      {multiSelected.length > 0 && (
        <div className="px-3 pb-2">
          {snapshotFormOpen ? (
            <div className="space-y-1.5">
              <input
                value={snapshotNameInput}
                onChange={(e) => setSnapshotNameInput(e.target.value)}
                placeholder="Snapshot name..."
                className="w-full bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs focus:outline-none focus:border-accent-blue"
                onKeyDown={(e) => e.key === 'Enter' && onSave()}
              />
              <div className="flex gap-1">
                <button onClick={onSave} disabled={!snapshotNameInput.trim()}
                  className="flex-1 bg-accent-blue hover:bg-blue-600 text-white px-2 py-1 rounded text-[10px] font-medium disabled:opacity-50">
                  Save ({multiSelected.length} entities)
                </button>
                <button onClick={() => setSnapshotFormOpen(false)}
                  className="px-2 py-1 bg-navy-600 hover:bg-navy-700 text-gray-300 rounded text-[10px]">
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button onClick={() => setSnapshotFormOpen(true)}
              className="w-full bg-navy-700 hover:bg-navy-600 border border-navy-600 text-gray-300 px-2 py-1.5 rounded text-xs transition-colors">
              Save as Snapshot ({multiSelected.length} selected)
            </button>
          )}
        </div>
      )}
      <div className="max-h-40 overflow-y-auto">
        {snapshots.length === 0 ? (
          <p className="text-[10px] text-gray-500 px-3 pb-2">No snapshots saved.</p>
        ) : (
          snapshots.map((snap) => (
            <div key={snap.id}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs border-b border-navy-700 hover:bg-navy-700 cursor-pointer transition-colors ${
                activeSnapshotId === snap.id ? 'bg-navy-700 text-accent-blue' : 'text-gray-300'
              }`}>
              <div className="flex-1 min-w-0" onClick={() => onView(snap.id)}>
                <div className="truncate font-medium">{snap.name}</div>
                <div className="text-[10px] text-gray-500">
                  {snap.entity_count} entities &middot; {new Date(snap.created_at).toLocaleDateString()}
                </div>
              </div>
              <button onClick={(e) => { e.stopPropagation(); onDelete(snap.id); }}
                className="text-red-400 hover:text-red-300 text-[10px] flex-none">Del</button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
