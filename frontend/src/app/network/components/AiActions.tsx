'use client';
import Markdown from '@/components/Markdown';

interface AiActionsProps {
  aiLoading: boolean;
  onGenerateAssessment: () => void;
  onGapAnalysis: () => void;
  onCompetingHypotheses: () => void;
}

/** AI actions over the selected entity. */
export function AiActions({ aiLoading, onGenerateAssessment, onGapAnalysis, onCompetingHypotheses }: AiActionsProps) {
  return (
    <div className="space-y-2">
      <h4 className="text-sm font-semibold text-gray-400">AI Actions</h4>
      <button
        onClick={onGenerateAssessment}
        disabled={aiLoading}
        className="w-full bg-accent-blue hover:bg-blue-600 text-white px-3 py-2 rounded text-xs font-medium disabled:opacity-50"
      >
        {aiLoading ? 'Generating...' : 'Generate Assessment'}
      </button>
      <button
        onClick={onGapAnalysis}
        disabled={aiLoading}
        className="w-full bg-navy-600 hover:bg-navy-700 text-gray-200 px-3 py-2 rounded text-xs font-medium disabled:opacity-50 border border-navy-600"
      >
        Gap Analysis
      </button>
      <button
        onClick={onCompetingHypotheses}
        disabled={aiLoading}
        className="w-full bg-navy-600 hover:bg-navy-700 text-gray-200 px-3 py-2 rounded text-xs font-medium disabled:opacity-50 border border-navy-600"
        title="Analysis of Competing Hypotheses over this entity's retrieved evidence"
      >
        Competing Hypotheses (ACH)
      </button>
    </div>
  );
}

/** What the last AI action (or merge, or assessment) produced, rendered as analysis. */
export function AiResult({ result }: { result: string | null }) {
  if (!result) return null;
  return (
    <div>
      <h4 className="text-sm font-semibold text-gray-400 mb-2">AI Result</h4>
      <div className="bg-navy-700 rounded p-3 text-xs max-h-64 overflow-y-auto">
        <Markdown content={result} />
      </div>
    </div>
  );
}
