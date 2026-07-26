'use client';
import { useMemo } from 'react';
import HighlightedExcerpt from '@/components/HighlightedExcerpt';

/**
 * The provenance behind a single graph claim: what was asserted, how sure the
 * system is, the verbatim sentence it came from, how many sources agree, and
 * how the source is graded.
 *
 * This is the app's differentiator made visible. It renders only what the data
 * actually contains — an ungraded source is shown as ungraded rather than
 * given a flattering default, and a single-source claim is never dressed up as
 * corroborated.
 */

export interface EvidenceRelationship {
  rel_type: string;
  source_name?: string;
  target_name?: string;
  confidence?: number;
  evidence?: string;
  admiralty_rating?: string;
  corroboration_count?: number;
  corroboration_agreement?: string;
  method?: string;
  source?: string;
}

interface Props {
  relationship: EvidenceRelationship;
  /** Resolved source document, when the excerpt could be traced to one. */
  document?: { id: string; name: string; reliability?: string } | null;
  /** Terms to highlight inside the excerpt — usually the entity names. */
  highlight?: string[];
  onOpenDocument?: (documentId: string) => void;
  className?: string;
}

/** IC-style probability wording for a confidence value. */
export function probabilityLabel(confidence: number): string {
  if (confidence >= 0.9) return 'Almost certain';
  if (confidence >= 0.75) return 'Highly likely';
  if (confidence >= 0.55) return 'Likely';
  if (confidence >= 0.45) return 'Roughly even chance';
  if (confidence >= 0.25) return 'Unlikely';
  return 'Remote';
}

function confidenceColour(confidence: number): string {
  if (confidence >= 0.75) return '#4ade80';
  if (confidence >= 0.45) return '#facc15';
  return '#fb923c';
}

/** How strongly the sources agree — CONFLICT is the one that must stand out. */
function agreementStyle(agreement?: string): { label: string; colour: string } | null {
  switch ((agreement || '').toUpperCase()) {
    case 'CONFLICT': return { label: 'Sources conflict', colour: '#f87171' };
    case 'PARTIAL': return { label: 'Partial agreement', colour: '#facc15' };
    case 'AGREE': return { label: 'Sources agree', colour: '#4ade80' };
    default: return null;
  }
}

export default function EvidenceChain({
  relationship: r,
  document: doc,
  highlight,
  onOpenDocument,
  className = '',
}: Props) {
  const confidence = typeof r.confidence === 'number' ? r.confidence : null;
  const corroboration = r.corroboration_count ?? 0;
  const agreement = agreementStyle(r.corroboration_agreement);

  const terms = useMemo(() => {
    if (highlight?.length) return highlight;
    return [r.source_name, r.target_name].filter(Boolean) as string[];
  }, [highlight, r.source_name, r.target_name]);

  return (
    <div className={`rounded-lg border border-navy-600 bg-navy-800 overflow-hidden ${className}`}>
      {/* 1 — The claim */}
      <div className="px-4 py-3 border-b border-navy-700">
        <div className="text-[9.5px] uppercase tracking-[0.14em] text-gray-500 font-bold mb-1.5">
          Claim
        </div>
        <div className="flex items-baseline gap-2 flex-wrap">
          <span className="text-sm text-gray-100 font-medium">{r.source_name || 'Entity'}</span>
          <span className="text-[11px] font-mono font-semibold text-accent-periwinkle tracking-wide">
            {r.rel_type}
          </span>
          <span className="text-sm text-gray-100 font-medium">{r.target_name || 'Entity'}</span>
        </div>
      </div>

      {/* 2 — How sure, and on what basis */}
      <div className="px-4 py-3 border-b border-navy-700 flex flex-wrap items-center gap-x-5 gap-y-2">
        {confidence !== null && (
          <div>
            <div className="text-[9.5px] uppercase tracking-[0.14em] text-gray-500 font-bold mb-1">
              Confidence
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold" style={{ color: confidenceColour(confidence) }}>
                {probabilityLabel(confidence)}
              </span>
              <span className="text-[11px] font-mono text-gray-400 tabular-nums">
                {Math.round(confidence * 100)}%
              </span>
            </div>
          </div>
        )}

        <div>
          <div className="text-[9.5px] uppercase tracking-[0.14em] text-gray-500 font-bold mb-1">
            Corroboration
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-200">
              {corroboration <= 1 ? 'Single source' : `${corroboration} sources`}
            </span>
            {agreement && corroboration > 1 && (
              <span className="text-[10px] font-semibold" style={{ color: agreement.colour }}>
                {agreement.label}
              </span>
            )}
          </div>
        </div>

        <div>
          <div className="text-[9.5px] uppercase tracking-[0.14em] text-gray-500 font-bold mb-1">
            Source grade
          </div>
          {r.admiralty_rating || doc?.reliability ? (
            <span className="text-sm font-mono text-gray-200">
              {r.admiralty_rating || doc?.reliability}
            </span>
          ) : (
            // Never invent a grade. An ungraded source is a finding in itself —
            // the source-evaluation technique exists to fill this in.
            <span className="text-sm text-gray-500 italic">Ungraded</span>
          )}
        </div>

        {r.method && (
          <div>
            <div className="text-[9.5px] uppercase tracking-[0.14em] text-gray-500 font-bold mb-1">
              Method
            </div>
            <span className="text-sm text-gray-400 font-mono">{r.method}</span>
          </div>
        )}
      </div>

      {/* 3 — The verbatim basis */}
      <div className="px-4 py-3">
        <div className="text-[9.5px] uppercase tracking-[0.14em] text-gray-500 font-bold mb-1.5">
          Basis
        </div>
        {r.evidence ? (
          <blockquote className="border-l-2 border-accent-periwinkle/40 pl-3">
            <HighlightedExcerpt
              text={r.evidence}
              keywords={terms}
              className="text-xs text-gray-300 leading-relaxed italic"
              maxLength={420}
            />
          </blockquote>
        ) : (
          <p className="text-xs text-gray-500 italic">
            No source sentence was captured for this relationship.
          </p>
        )}

        {/* 4 — Where it came from */}
        {doc && (
          <button
            onClick={() => onOpenDocument?.(doc.id)}
            disabled={!onOpenDocument}
            className="mt-3 inline-flex items-center gap-2 text-[11px] text-gray-400
                       hover:text-accent-periwinkle disabled:hover:text-gray-400 transition-colors"
          >
            <span className="material-symbols-outlined text-[13px]">description</span>
            <span className="truncate max-w-[22rem]">{doc.name}</span>
            {doc.reliability && (
              <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-navy-700 text-gray-400">
                {doc.reliability}
              </span>
            )}
            {onOpenDocument && <span aria-hidden>→</span>}
          </button>
        )}
      </div>
    </div>
  );
}
