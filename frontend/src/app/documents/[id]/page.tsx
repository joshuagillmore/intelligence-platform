'use client';
import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Sidebar from '@/components/Sidebar';
import api from '@/lib/api';

interface Highlight {
  start: number;
  end: number;
  entity_id: string;
  entity_name: string;
  entity_type: string;
}

interface DocData {
  id: string;
  name: string;
  reliability_rating: string;
  content: string;
  entities: Array<{ id: string; name: string; entity_type: string }>;
  highlights: Highlight[];
  entity_count: number;
  summary_json?: string;
}

interface DocSummary {
  summary?: string;
  key_facts?: string[];
  topics?: string[];
  sentiment?: string;
}

function parseSummary(raw?: string): DocSummary | null {
  if (!raw || !raw.trim()) return null;
  try {
    const obj = JSON.parse(raw);
    if (obj && typeof obj === 'object' && (obj.summary || obj.key_facts || obj.topics)) return obj as DocSummary;
  } catch { /* ignore malformed */ }
  return null;
}

const sentimentColor: Record<string, string> = {
  positive: 'bg-green-500/20 text-green-300 border-green-500/30',
  negative: 'bg-red-500/20 text-red-300 border-red-500/30',
  neutral: 'bg-gray-500/20 text-gray-300 border-gray-500/30',
  mixed: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
};

const typeColor: Record<string, string> = {
  Person: '#f97316',
  Organization: '#3b82f6',
  Location: '#22c55e',
  IPAddress: '#06b6d4',
  Domain: '#a855f7',
  Hash: '#ec4899',
  ThreatActor: '#ef4444',
  TTP: '#eab308',
  Vulnerability: '#f43f5e',
};

export default function DocumentViewer() {
  const params = useParams();
  const docId = params.id as string;
  const [doc, setDoc] = useState<DocData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedEntity, setSelectedEntity] = useState<string | null>(null);

  useEffect(() => {
    if (!docId) return;
    setLoading(true);
    api.get(`/documents/${docId}`)
      .then(res => setDoc(res.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [docId]);

  function renderHighlightedContent() {
    if (!doc) return null;
    const { content, highlights } = doc;
    if (!highlights.length) return <pre className="whitespace-pre-wrap text-sm text-gray-300">{content}</pre>;

    // Filter overlapping highlights
    const filtered: Highlight[] = [];
    const used = new Set<number>();
    for (const h of highlights) {
      let overlaps = false;
      for (let i = h.start; i < h.end; i++) {
        if (used.has(i)) { overlaps = true; break; }
      }
      if (!overlaps) {
        filtered.push(h);
        for (let i = h.start; i < h.end; i++) used.add(i);
      }
    }

    // Build parts
    const parts: Array<{ text: string; highlight?: Highlight }> = [];
    let lastEnd = 0;

    for (const h of filtered) {
      if (h.start > lastEnd) {
        parts.push({ text: content.slice(lastEnd, h.start) });
      }
      parts.push({ text: content.slice(h.start, h.end), highlight: h });
      lastEnd = h.end;
    }
    if (lastEnd < content.length) {
      parts.push({ text: content.slice(lastEnd) });
    }

    return (
      <pre className="whitespace-pre-wrap text-sm text-gray-300 leading-relaxed">
        {parts.map((part, i) => {
          if (part.highlight) {
            const color = typeColor[part.highlight.entity_type] || '#9ca3af';
            const isSelected = selectedEntity === part.highlight.entity_id;
            return (
              <span
                key={i}
                onClick={() => setSelectedEntity(part.highlight!.entity_id)}
                className="cursor-pointer rounded px-0.5"
                style={{
                  backgroundColor: `${color}${isSelected ? '40' : '20'}`,
                  borderBottom: `2px solid ${color}`,
                  fontWeight: isSelected ? 600 : 400,
                }}
                title={`${part.highlight.entity_type}: ${part.highlight.entity_name}`}
              >
                {part.text}
              </span>
            );
          }
          return <span key={i}>{part.text}</span>;
        })}
      </pre>
    );
  }

  const reliabilityColor = (r: string) => {
    if (r.startsWith('A')) return 'bg-green-900/30 text-green-400';
    if (r.startsWith('B')) return 'bg-blue-900/30 text-blue-400';
    if (r.startsWith('C')) return 'bg-yellow-900/30 text-yellow-400';
    if (r.startsWith('D')) return 'bg-orange-900/30 text-orange-400';
    return 'bg-red-900/30 text-red-400';
  };

  if (loading) {
    return <div className="flex"><Sidebar /><main className="ml-56 flex-1 p-8"><div className="text-gray-500">Loading document...</div></main></div>;
  }

  if (!doc) {
    return <div className="flex"><Sidebar /><main className="ml-56 flex-1 p-8"><div className="text-red-400">Document not found</div></main></div>;
  }

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6 flex gap-4" style={{ height: 'calc(100vh - 1.75rem)' }}>
        {/* Document content */}
        <div className="flex-1 flex flex-col min-w-0">
          <div className="flex items-center gap-3 mb-4">
            <h2 className="text-xl font-bold truncate">{doc.name}</h2>
            {doc.reliability_rating && (
              <span className={`text-xs px-2 py-0.5 rounded ${reliabilityColor(doc.reliability_rating)}`}>
                {doc.reliability_rating}
              </span>
            )}
            <span className="text-xs text-gray-500">{doc.entity_count} entities</span>
          </div>
          {(() => {
            const s = parseSummary(doc.summary_json);
            if (!s) return null;
            return (
              <div className="mb-4 bg-navy-800 border border-[#adc6ff]/30 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="material-symbols-outlined text-[#adc6ff] text-sm">auto_awesome</span>
                  <h3 className="text-[10px] font-bold uppercase tracking-widest text-[#adc6ff]">AI Summary</h3>
                  {s.sentiment && (
                    <span className={`text-[10px] px-2 py-0.5 rounded-full border ml-auto ${sentimentColor[s.sentiment.toLowerCase()] || sentimentColor.neutral}`}>
                      {s.sentiment}
                    </span>
                  )}
                </div>
                {s.summary && <p className="text-sm text-gray-200/90 leading-relaxed mb-3">{s.summary}</p>}
                {Array.isArray(s.key_facts) && s.key_facts.length > 0 && (
                  <div className="mb-3">
                    <div className="text-[10px] font-bold uppercase tracking-widest text-gray-500 mb-1">Key Facts</div>
                    <ul className="list-disc list-inside space-y-0.5">
                      {s.key_facts.slice(0, 8).map((f, i) => (
                        <li key={i} className="text-xs text-gray-300/90 leading-snug">{f}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {Array.isArray(s.topics) && s.topics.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {s.topics.slice(0, 12).map((t, i) => (
                      <span key={i} className="text-[10px] bg-[#adc6ff]/15 text-[#adc6ff] border border-[#adc6ff]/30 px-2 py-0.5 rounded-full">{t}</span>
                    ))}
                  </div>
                )}
              </div>
            );
          })()}
          <div className="flex-1 bg-navy-800 border border-navy-600 rounded-lg p-6 overflow-y-auto">
            {renderHighlightedContent()}
          </div>
        </div>

        {/* Entity sidebar */}
        <div className="w-72 bg-navy-800 border border-navy-600 rounded-lg p-4 overflow-y-auto">
          <h3 className="text-sm font-semibold text-gray-400 mb-3">Extracted Entities ({doc.entities.length})</h3>
          <div className="space-y-1">
            {doc.entities.map((e) => (
              <div
                key={e.id}
                onClick={() => setSelectedEntity(e.id === selectedEntity ? null : e.id)}
                className={`text-xs p-2 rounded cursor-pointer transition-colors ${
                  selectedEntity === e.id ? 'bg-navy-600 border border-accent-blue' : 'bg-navy-700 hover:bg-navy-600'
                }`}
              >
                <span className="text-gray-200">{e.name}</span>
                <span
                  className="ml-2 px-1 py-0 rounded text-[10px]"
                  style={{
                    backgroundColor: `${typeColor[e.entity_type] || '#6b7280'}20`,
                    color: typeColor[e.entity_type] || '#9ca3af',
                  }}
                >
                  {e.entity_type}
                </span>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
