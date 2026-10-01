'use client';
import type { EvidenceDocument } from '../hooks/useEntitySelection';

interface EvidenceDocumentsProps {
  loading: boolean;
  error: string | null;
  documents: EvidenceDocument[];
  /** Documents that mention the entity in all; more than `documents` when paged. */
  total: number;
  onOpenDocument: (docId: string) => void;
}

/** The evidence chain: the source documents that mention the selected entity. */
export default function EvidenceDocuments({ loading, error, documents, total, onOpenDocument }: EvidenceDocumentsProps) {
  return (
    <div>
      <h4 className="text-sm font-semibold text-gray-400 mb-2">Evidence Chain</h4>
      {loading ? (
        <p className="text-xs text-gray-500">Loading source documents...</p>
      ) : error ? (
        <p className="text-xs text-red-400">Could not load source documents: {error}</p>
      ) : documents.length > 0 ? (
        <div className="space-y-1">
          {total > documents.length && (
            <p className="text-[10px] text-gray-500">
              Showing {documents.length} of {total} documents.
            </p>
          )}
          {documents.map((doc) => (
            <div
              key={doc.id}
              onClick={() => onOpenDocument(doc.id)}
              className="text-xs bg-navy-700 rounded p-2 cursor-pointer hover:bg-navy-600 transition-colors"
            >
              <div className="flex items-center gap-2">
                <span className="text-accent-blue hover:underline flex-1 truncate">{doc.name}</span>
                {doc.mention_count > 0 && (
                  <span
                    className="text-[10px] text-gray-500 flex-none"
                    title={`Mentioned ${doc.mention_count} time${doc.mention_count === 1 ? '' : 's'}`}
                  >
                    &times;{doc.mention_count}
                  </span>
                )}
                {doc.reliability_rating && (
                  <span className="text-[10px] px-1 py-0.5 rounded bg-navy-600 text-gray-400 flex-none">
                    {doc.reliability_rating}
                  </span>
                )}
              </div>
              {doc.passages[0] && (
                <p className="mt-1 text-[11px] text-gray-400 italic line-clamp-2" title={doc.passages[0].text}>
                  &ldquo;{doc.passages[0].text}&rdquo;
                </p>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-gray-500">No source documents found.</p>
      )}
    </div>
  );
}
