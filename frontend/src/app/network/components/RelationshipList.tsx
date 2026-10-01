'use client';
import EvidenceChain from '@/components/EvidenceChain';
import { formatRelType, type Entity, type GraphEdge, type Relationship } from '../types';
import type { EvidenceDocument } from '../hooks/useEntitySelection';

interface RelationshipListProps {
  selectedEntity: Entity;
  entityRelationships: Relationship[];
  relationshipsError: string | null;
  onRetry: () => void;
  graphEdges: GraphEdge[];
  relEvidenceOpen: Record<number, boolean>;
  toggleRelEvidence: (relIndex: number) => void;
  evidenceDocs: EvidenceDocument[];
  onOpenDocument: (docId: string) => void;
}

/** The selected entity's relationships, each with its provenance behind "Show Evidence". */
export default function RelationshipList({
  selectedEntity, entityRelationships, relationshipsError, onRetry, graphEdges,
  relEvidenceOpen, toggleRelEvidence, evidenceDocs, onOpenDocument,
}: RelationshipListProps) {
  return (
    <>
      {relationshipsError && (
        <div>
          <h4 className="text-sm font-semibold text-gray-400 mb-2">Relationships</h4>
          <p className="text-xs text-red-400">Could not load relationships: {relationshipsError}</p>
          <button
            onClick={onRetry}
            className="text-[10px] text-accent-blue hover:underline mt-1"
          >
            Retry
          </button>
        </div>
      )}

      {entityRelationships.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-gray-400 mb-2">Relationships ({entityRelationships.length})</h4>
          <div className="space-y-1">
            {entityRelationships.map((rel, i) => {
              // Compute edge weight from graph edges
              const otherId = rel.source_id === selectedEntity.id ? rel.target_id : rel.source_id;
              const edgeWeight = graphEdges.filter(e => {
                const srcId = e.source_id || e.source;
                const tgtId = e.target_id || e.target;
                return (srcId === selectedEntity.id && tgtId === otherId) || (tgtId === selectedEntity.id && srcId === otherId);
              }).length;
              const conf = rel.confidence;
              const confDotColor = conf !== undefined
                ? conf >= 0.8 ? 'bg-green-500'
                : conf >= 0.5 ? 'bg-accent-blue'
                : conf >= 0.3 ? 'bg-yellow-500'
                : 'bg-red-500'
                : '';
              return (
              <div key={i} className="text-xs bg-navy-700 rounded p-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-accent-blue truncate">{formatRelType(rel.rel_type)}{edgeWeight > 1 ? ` (${edgeWeight})` : ''}</span>
                  {conf !== undefined && (
                    <span className="inline-flex items-center gap-1 text-gray-500 flex-none">
                      <span className={`w-1.5 h-1.5 rounded-full ${confDotColor}`} />
                      {(conf * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
                <div className="text-gray-400 mt-0.5 truncate">
                  {rel.source_name || rel.source_id} &rarr; {rel.target_name || rel.target_id}
                </div>
                <button
                  onClick={() => toggleRelEvidence(i)}
                  className="text-[10px] text-accent-blue hover:underline mt-1"
                >
                  {relEvidenceOpen[i] ? 'Hide Evidence' : 'Show Evidence'}
                </button>
                {relEvidenceOpen[i] && (
                  <div className="mt-2">
                    {/* Full provenance: the claim, how sure, how corroborated,
                        how the source is graded, and the verbatim basis. */}
                    <EvidenceChain
                      relationship={rel}
                      document={
                        rel.source_doc_id
                          ? (() => {
                              // evidenceDocs is already loaded for this entity —
                              // reuse it rather than re-fetching document names.
                              const d = evidenceDocs.find(x => x.id === rel.source_doc_id || x.source_doc_id === rel.source_doc_id);
                              return {
                                id: rel.source_doc_id,
                                name: d?.name || 'Source document',
                                reliability: d?.reliability_rating || undefined,
                              };
                            })()
                          : null
                      }
                      onOpenDocument={onOpenDocument}
                    />
                  </div>
                )}
              </div>
              );
            })}
          </div>
        </div>
      )}
    </>
  );
}
