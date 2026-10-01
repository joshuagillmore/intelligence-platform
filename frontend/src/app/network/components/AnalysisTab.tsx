'use client';
import { nodeEntity, type Entity, type InfluenceResult, type StructuralHoleEntry } from '../types';

interface AnalysisTabProps {
  structuralHoles: StructuralHoleEntry[];
  selectEntity: (entity: Entity) => void;
  selectedEntity: Entity | null;
  multiSelected: Entity[];
  influenceSteps: number;
  setInfluenceSteps: (steps: number) => void;
  influenceThreshold: number;
  setInfluenceThreshold: (threshold: number) => void;
  influenceLoading: boolean;
  influenceResult: InfluenceResult | null;
  runInfluencePropagation: (seedIds: string[]) => void;
}

/** The Analysis tab: structural holes (brokers) and influence propagation. */
export default function AnalysisTab({
  structuralHoles, selectEntity, selectedEntity, multiSelected,
  influenceSteps, setInfluenceSteps, influenceThreshold, setInfluenceThreshold,
  influenceLoading, influenceResult, runInfluencePropagation,
}: AnalysisTabProps) {
  return (
    <div className="flex-1 overflow-y-auto p-3 space-y-3">
      {/* Structural Holes / Brokers */}
      <div>
        <h4 className="text-xs font-semibold text-gray-400 mb-2">Structural Holes (Brokers)</h4>
        <p className="text-[10px] text-gray-500 mb-2">Low constraint + high effective size = broker bridging groups.</p>
        {structuralHoles.length > 0 ? (
          <div className="space-y-1">
            {structuralHoles.slice(0, 10).map((sh) => (
              <div
                key={sh.id}
                className={`text-xs rounded p-2 cursor-pointer transition-colors ${sh.is_broker ? 'bg-purple-900/40 border border-purple-700/50' : 'bg-navy-700'} hover:bg-navy-600`}
                onClick={() => selectEntity(nodeEntity(sh))}
              >
                <div className="flex items-center justify-between">
                  <span className="text-gray-200 font-medium truncate">{sh.name}</span>
                  {sh.is_broker && <span className="text-[9px] px-1.5 py-0.5 bg-purple-600 text-white rounded">Broker</span>}
                </div>
                <div className="flex gap-3 mt-1 text-[10px] text-gray-400">
                  <span>Constraint: <span className={sh.constraint < 0.5 ? 'text-green-400' : 'text-gray-300'}>{sh.constraint.toFixed(3)}</span></span>
                  <span>Eff. Size: <span className={sh.effective_size > 1.5 ? 'text-blue-400' : 'text-gray-300'}>{sh.effective_size.toFixed(2)}</span></span>
                  <span>Deg: {sh.degree}</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-[10px] text-gray-500">No data available.</p>
        )}
      </div>

      {/* Influence Propagation */}
      <div>
        <h4 className="text-xs font-semibold text-gray-400 mb-2">Influence Propagation</h4>
        <p className="text-[10px] text-gray-500 mb-2">Simulate how influence spreads from selected entities.</p>
        <div className="space-y-2">
          <div className="flex gap-2">
            <div className="flex-1">
              <label className="text-[10px] text-gray-500">Steps</label>
              <input type="number" min={1} max={10} value={influenceSteps} onChange={(e) => setInfluenceSteps(Number(e.target.value))}
                className="w-full bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs" />
            </div>
            <div className="flex-1">
              <label className="text-[10px] text-gray-500">Threshold</label>
              <input type="number" min={0} max={1} step={0.1} value={influenceThreshold} onChange={(e) => setInfluenceThreshold(Number(e.target.value))}
                className="w-full bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs" />
            </div>
          </div>
          <button
            onClick={() => {
              const seeds = multiSelected.length > 0 ? multiSelected.map(e => e.id) : selectedEntity ? [selectedEntity.id] : [];
              if (seeds.length > 0) runInfluencePropagation(seeds);
            }}
            disabled={influenceLoading || (!selectedEntity && multiSelected.length === 0)}
            className="w-full bg-orange-600 hover:bg-orange-700 text-white px-3 py-1.5 rounded text-xs font-medium disabled:opacity-50 transition-colors"
          >
            {influenceLoading ? 'Running...' : `Run from ${multiSelected.length > 0 ? multiSelected.length + ' selected' : selectedEntity?.name || 'no entity'}`}
          </button>
        </div>

        {influenceResult && (
          <div className="mt-2 space-y-1.5">
            <div className="flex gap-2 text-[10px]">
              <span className="bg-navy-700 rounded px-2 py-1">
                Reach: <span className="text-orange-400 font-bold">{(influenceResult.reach_ratio * 100).toFixed(1)}%</span>
              </span>
              <span className="bg-navy-700 rounded px-2 py-1">
                Activated: <span className="text-orange-400 font-bold">{influenceResult.total_activated}</span> / {influenceResult.total_nodes}
              </span>
            </div>
            {influenceResult.steps.map((step) => (
              <div key={step.step} className="bg-navy-700 rounded p-2">
                <div className="text-[10px] text-gray-400 mb-1">
                  Step {step.step}: +{step.newly_activated.length} activated ({step.cumulative_count} total)
                </div>
                <div className="flex flex-wrap gap-1">
                  {step.newly_activated.slice(0, 8).map((n) => (
                    <span
                      key={n.id}
                      className="text-[9px] px-1.5 py-0.5 bg-navy-600 text-gray-300 rounded cursor-pointer hover:bg-navy-500"
                      onClick={() => selectEntity(nodeEntity(n))}
                    >
                      {n.name}
                    </span>
                  ))}
                  {step.newly_activated.length > 8 && (
                    <span className="text-[9px] text-gray-500">+{step.newly_activated.length - 8} more</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
