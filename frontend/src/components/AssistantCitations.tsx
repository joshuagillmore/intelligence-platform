'use client';
/**
 * Citations panel for a Graph-RAG answer.
 *
 * Everything shown here comes from the real `/api/query` payload — the counts
 * it reports and the retrieval `context` it actually handed the model (parsed
 * in `lib/assistantGrounding.ts`). Nothing is inferred or synthesised: if the
 * response carries no context, only the counts render.
 */
import { useId, useState } from 'react';
import { groundingSummary, type AssistantGrounding } from '@/lib/assistantGrounding';

function MetaLine({ g }: { g: AssistantGrounding }) {
  const bits: string[] = [];
  if (g.retrievalMode) bits.push(`${g.retrievalMode} retrieval`);
  if (g.nodeCount !== null) bits.push(`${g.nodeCount} nodes`);
  if (g.edgeCount !== null) bits.push(`${g.edgeCount} edges`);
  if (g.vectorCount) bits.push(`${g.vectorCount} vector hits`);
  if (g.model) bits.push(g.model);
  if (g.tokensUsed) bits.push(`${g.tokensUsed.toLocaleString()} tokens`);
  if (bits.length === 0) return null;
  return <p className="text-[10px] font-mono text-gray-500 leading-relaxed">{bits.join(' · ')}</p>;
}

function Group({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  if (count === 0) return null;
  return (
    <div className="mt-2">
      <h4 className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 mb-1">
        {title} ({count})
      </h4>
      {children}
    </div>
  );
}

export default function AssistantCitations({ grounding }: { grounding: AssistantGrounding }) {
  const [expanded, setExpanded] = useState(false);
  const regionId = useId();

  return (
    <div className="mt-1.5">
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        aria-expanded={expanded}
        aria-controls={regionId}
        className="text-[10px] px-2 py-0.5 rounded bg-navy-700 text-gray-400 hover:text-gray-200 hover:bg-navy-600 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-blue"
      >
        {expanded ? 'Hide sources' : `Sources · ${groundingSummary(grounding)}`}
      </button>

      {expanded && (
        <div
          id={regionId}
          className="mt-1.5 rounded-md border border-navy-600 bg-navy-900 p-2 max-h-56 overflow-y-auto"
        >
          <MetaLine g={grounding} />

          {!grounding.hasDetail && (
            <p className="text-[10px] text-gray-500 mt-1">
              The API returned retrieval counts but no context text for this answer.
            </p>
          )}

          <Group title="Entities in context" count={grounding.entities.length}>
            <div className="flex flex-wrap gap-1">
              {grounding.entities.map((e, i) => (
                <span
                  key={`${e.name}-${i}`}
                  title={e.detail ? `${e.type} — ${e.detail}` : e.type}
                  className="text-[10px] px-1.5 py-0.5 rounded bg-navy-800 border border-navy-600 text-gray-300"
                >
                  {e.name}
                  {e.type && <span className="text-gray-500"> · {e.type}</span>}
                </span>
              ))}
            </div>
          </Group>

          <Group title="Relationships" count={grounding.relationships.length}>
            <ul className="space-y-0.5">
              {grounding.relationships.map((r, i) => (
                <li key={`${r.source}-${r.relType}-${r.target}-${i}`} className="text-[10px] font-mono text-gray-400 break-words">
                  {r.source} <span className="text-accent-cyan">--[{r.relType}]--&gt;</span> {r.target}
                  {r.confidence && <span className="text-gray-600"> ({r.confidence})</span>}
                </li>
              ))}
            </ul>
          </Group>

          <Group title="Source documents" count={grounding.documents.length}>
            <ul className="space-y-1.5">
              {grounding.documents.map((d, i) => (
                <li key={`${d.name}-${i}`} className="rounded bg-navy-800 p-1.5">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-[10px] font-medium text-gray-200 break-all">{d.name}</span>
                    <span className="text-[9px] px-1 py-px rounded bg-navy-700 text-gray-400 shrink-0">
                      reliability: {d.reliability}
                    </span>
                  </div>
                  {d.excerpt && (
                    <p className="mt-1 text-[10px] text-gray-500 leading-snug line-clamp-4 whitespace-pre-wrap break-words">
                      {d.excerpt}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </Group>

          <Group title="Semantic passages" count={grounding.passages.length}>
            <ul className="space-y-1.5">
              {grounding.passages.map((p, i) => (
                <li key={`${p.documentId}-${i}`} className="rounded bg-navy-800 p-1.5">
                  <div className="text-[9px] font-mono text-gray-500 break-all">
                    doc {p.documentId} · similarity {p.similarity.toFixed(3)}
                  </div>
                  <p className="mt-0.5 text-[10px] text-gray-500 leading-snug line-clamp-4 whitespace-pre-wrap break-words">
                    {p.text}
                  </p>
                </li>
              ))}
            </ul>
          </Group>
        </div>
      )}
    </div>
  );
}
