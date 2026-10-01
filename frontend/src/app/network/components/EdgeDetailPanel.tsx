'use client';
import { formatRelType, type GraphEdge } from '../types';

interface EdgeDetailPanelProps {
  edge: GraphEdge;
  onOpenDocument: (docId: string) => void;
  onDismiss: () => void;
}

/** A clicked edge: its endpoints, confidence, timestamps and provenance. */
export default function EdgeDetailPanel({ edge, onOpenDocument, onDismiss }: EdgeDetailPanelProps) {
  return (
    <div className="p-4 space-y-4">
      <div>
        <h3 className="font-bold text-lg text-gray-200">Relationship</h3>
        <span className="inline-block mt-1 text-xs px-2 py-0.5 rounded bg-navy-600 text-gray-300">
          {formatRelType(edge.rel_type)}
        </span>
      </div>
      <div className="space-y-2 text-xs">
        <div>
          <span className="text-gray-500">Source:</span>{' '}
          <span className="text-gray-300">{edge.source_id}</span>
        </div>
        <div>
          <span className="text-gray-500">Target:</span>{' '}
          <span className="text-gray-300">{edge.target_id}</span>
        </div>
        {edge.confidence !== undefined && (
          <div>
            <span className="text-gray-500">Confidence:</span>{' '}
            <span className={edge.confidence >= 0.8 ? 'text-green-400' : edge.confidence >= 0.5 ? 'text-yellow-400' : 'text-red-400'}>
              {(edge.confidence * 100).toFixed(0)}%
            </span>
          </div>
        )}
        {edge.first_seen && (
          <div>
            <span className="text-gray-500">First Seen:</span>{' '}
            <span className="text-gray-300">{String(edge.first_seen).slice(0, 10)}</span>
          </div>
        )}
        {edge.last_seen && (
          <div>
            <span className="text-gray-500">Last Seen:</span>{' '}
            <span className="text-gray-300">{String(edge.last_seen).slice(0, 10)}</span>
          </div>
        )}
        {/* source_doc_id, not `source`: d3 replaces an edge's `source`
            with the node object, which printed "[object Object]". */}
        {edge.source_doc_id && (
          <div>
            <span className="text-gray-500">Source Document:</span>{' '}
            <button
              onClick={() => onOpenDocument(edge.source_doc_id as string)}
              className="text-accent-blue hover:underline font-mono break-all text-left"
            >
              {edge.source_doc_id}
            </button>
          </div>
        )}
        {edge.method && (
          <div>
            <span className="text-gray-500">Extraction Method:</span>{' '}
            <span className="text-gray-300">{edge.method}</span>
          </div>
        )}
        <div>
          <span className="text-gray-500">Evidence:</span>
          {edge.evidence ? (
            <div className="mt-1 bg-navy-700 rounded p-1.5 text-gray-300 italic leading-relaxed">
              &ldquo;{edge.evidence}&rdquo;
            </div>
          ) : (
            <div className="mt-1 text-gray-500 italic">No captured evidence — re-run extraction to populate.</div>
          )}
        </div>
      </div>
      <button
        onClick={onDismiss}
        className="text-xs text-gray-500 hover:text-gray-300"
      >
        Dismiss
      </button>
    </div>
  );
}
