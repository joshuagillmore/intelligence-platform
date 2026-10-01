'use client';
import { TYPE_COLOR_CLASS as TYPE_COLORS } from '@/lib/entityStyles';
import { formatEntityType, type Entity } from '../types';

interface AssessModalProps {
  multiSelected: Entity[];
  judgment: string;
  setJudgment: (judgment: string) => void;
  probability: number;
  setProbability: (probability: number) => void;
  analyst: string;
  setAnalyst: (analyst: string) => void;
  loading: boolean;
  onSubmit: () => void;
  onGenerate: () => void;
  onCancel: () => void;
}

/** Record an analyst judgment over the multi-selection, or have one generated. */
export function AssessModal({
  multiSelected, judgment, setJudgment, probability, setProbability, analyst, setAnalyst,
  loading, onSubmit, onGenerate, onCancel,
}: AssessModalProps) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-navy-800 border border-navy-600 rounded-lg p-6 w-full max-w-md">
        <h3 className="text-lg font-bold mb-4">Generate Assessment</h3>
        <p className="text-xs text-gray-400 mb-4">
          Assessing {multiSelected.length} entit{multiSelected.length === 1 ? 'y' : 'ies'}:{' '}
          {multiSelected.map(e => e.name).join(', ')}
        </p>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-400 block mb-1">Judgment</label>
            <textarea
              value={judgment}
              onChange={(e) => setJudgment(e.target.value)}
              placeholder="Enter your analyst judgment..."
              className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm h-24 focus:outline-none focus:border-accent-blue"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Probability: {(probability * 100).toFixed(0)}%</label>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={probability}
              onChange={(e) => setProbability(Number(e.target.value))}
              className="w-full accent-accent-blue"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Analyst (optional)</label>
            <input
              value={analyst}
              onChange={(e) => setAnalyst(e.target.value)}
              placeholder="Analyst name..."
              className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-blue"
            />
          </div>
          <div className="flex gap-2 mt-4">
            <button
              onClick={onSubmit}
              disabled={loading || !judgment.trim()}
              className="flex-1 bg-accent-blue hover:bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium disabled:opacity-50 transition-colors"
            >
              {loading ? 'Submitting...' : 'Submit Assessment'}
            </button>
            <button
              onClick={onGenerate}
              disabled={loading}
              className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded text-sm font-medium disabled:opacity-50 transition-colors"
            >
              {loading ? 'Generating...' : 'Generate with AI'}
            </button>
            <button
              onClick={onCancel}
              className="px-4 py-2 bg-navy-600 hover:bg-navy-700 text-gray-300 rounded text-sm transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

interface MergeModalProps {
  multiSelected: Entity[];
  primaryId: string;
  setPrimaryId: (id: string) => void;
  onMerge: () => void;
  onCancel: () => void;
}

/** Merge the multi-selection into one primary entity. */
export function MergeModal({ multiSelected, primaryId, setPrimaryId, onMerge, onCancel }: MergeModalProps) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-navy-800 border border-navy-600 rounded-lg p-6 w-full max-w-md">
        <h3 className="text-lg font-bold mb-4">Merge Entities</h3>
        <p className="text-xs text-gray-400 mb-4">
          Select the primary entity. All other selected entities will be merged into it.
        </p>
        <div className="space-y-2 mb-4">
          {multiSelected.map((e) => (
            <label key={e.id} className="flex items-center gap-2 text-sm cursor-pointer p-2 rounded hover:bg-navy-700">
              <input
                type="radio"
                name="mergePrimary"
                checked={primaryId === e.id}
                onChange={() => setPrimaryId(e.id)}
                className="accent-accent-blue"
              />
              <span className={`w-2 h-2 rounded-full ${TYPE_COLORS[e.entity_type] || 'bg-gray-500'}`} />
              <span className="text-gray-200">{e.name}</span>
              <span className="text-xs text-gray-500">{formatEntityType(e.entity_type)}</span>
              {primaryId === e.id && <span className="text-xs text-accent-blue ml-auto">Primary</span>}
            </label>
          ))}
        </div>
        <div className="flex gap-2">
          <button
            onClick={onMerge}
            disabled={!primaryId}
            className="flex-1 bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded text-sm font-medium disabled:opacity-50 transition-colors"
          >
            Merge
          </button>
          <button
            onClick={onCancel}
            className="px-4 py-2 bg-navy-600 hover:bg-navy-700 text-gray-300 rounded text-sm transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
