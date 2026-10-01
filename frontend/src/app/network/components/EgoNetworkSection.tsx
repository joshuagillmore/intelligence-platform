'use client';
import { nodeEntity, type EgoNetworkData, type Entity } from '../types';

interface EgoNetworkSectionProps {
  selectedEntity: Entity;
  egoHops: number;
  setEgoHops: (hops: number) => void;
  egoLoading: boolean;
  egoNetwork: EgoNetworkData | null;
  onExtract: (entityId: string) => void;
  selectEntity: (entity: Entity) => void;
  /** Restrict the canvas to the ego network's nodes. */
  onFocus: (ego: EgoNetworkData) => void;
}

/** Extract the selected entity's ego network and focus the canvas on it. */
export default function EgoNetworkSection({
  selectedEntity, egoHops, setEgoHops, egoLoading, egoNetwork, onExtract, selectEntity, onFocus,
}: EgoNetworkSectionProps) {
  return (
    <div className="space-y-2">
      <h4 className="text-sm font-semibold text-gray-400">Ego Network</h4>
      <div className="flex items-center gap-2">
        <select
          value={egoHops}
          onChange={(e) => setEgoHops(Number(e.target.value))}
          className="bg-navy-700 border border-navy-600 rounded px-2 py-1.5 text-xs"
        >
          <option value={1}>1 hop</option>
          <option value={2}>2 hops</option>
          <option value={3}>3 hops</option>
          <option value={4}>4 hops</option>
        </select>
        <button
          onClick={() => onExtract(selectedEntity.id)}
          disabled={egoLoading}
          className="flex-1 bg-purple-600 hover:bg-purple-700 text-white px-3 py-1.5 rounded text-xs font-medium disabled:opacity-50 transition-colors"
        >
          {egoLoading ? 'Loading...' : 'Extract'}
        </button>
      </div>
      {egoNetwork && egoNetwork.center === selectedEntity.id && (
        <div className="bg-navy-700 rounded p-2 space-y-1.5">
          <div className="flex gap-2 text-[10px] text-gray-400">
            <span>{egoNetwork.node_count} nodes</span>
            <span>{egoNetwork.edge_count} edges</span>
            <span>{egoNetwork.hops} hops</span>
          </div>
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {egoNetwork.nodes.filter(n => n.id !== selectedEntity.id).slice(0, 15).map((n) => (
              <div
                key={n.id}
                className="flex items-center justify-between text-[10px] px-1.5 py-1 bg-navy-800 rounded cursor-pointer hover:bg-navy-600"
                onClick={() => selectEntity(nodeEntity(n))}
              >
                <div className="flex items-center gap-1.5 min-w-0">
                  <span className={`w-1.5 h-1.5 rounded-full flex-none ${n.hop_distance === 1 ? 'bg-blue-400' : n.hop_distance === 2 ? 'bg-blue-600' : 'bg-blue-800'}`} />
                  <span className="text-gray-300 truncate">{n.name}</span>
                </div>
                <span className="text-gray-500 flex-none ml-1">h{n.hop_distance} pr:{n.local_pagerank.toFixed(3)}</span>
              </div>
            ))}
            {egoNetwork.nodes.length > 16 && (
              <p className="text-[10px] text-gray-500 text-center">+{egoNetwork.nodes.length - 16} more</p>
            )}
          </div>
          <button
            onClick={() => onFocus(egoNetwork)}
            className="w-full bg-navy-600 hover:bg-navy-500 text-gray-300 px-2 py-1 rounded text-[10px] transition-colors"
          >
            Focus Graph on Ego Network
          </button>
        </div>
      )}
    </div>
  );
}
