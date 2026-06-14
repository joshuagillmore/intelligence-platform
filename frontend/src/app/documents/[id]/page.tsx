'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import api from '@/lib/api';
import { Btn, Tag, Icon } from '@/components/sentinel';
import { PROVENANCE_DEMO } from '@/components/sentinel/mockData';

interface DocSummary {
  summary: string;
  key_facts: string[];
  topics: string[];
  sentiment: string;
}

interface DocEntity {
  id: string;
  name: string;
  entity_type: string;
  relationship: string;
}

interface DocDetail {
  id: string;
  name: string;
  url: string;
  reliability_rating: string;
  content: string;
  entities: DocEntity[];
  entity_count: number;
  summary: DocSummary | null;
}

export default function DocumentDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = (params?.id as string) || '';

  const [doc, setDoc] = useState<DocDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    api.get<DocDetail>(`/documents/${id}`)
      .then((res) => { if (!cancelled) { setDoc(res.data); setError(null); } })
      .catch((e: Error) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [id]);

  if (loading) {
    return (
      <Centered>
        <span style={monoStyle}>FETCHING DOCUMENT…</span>
      </Centered>
    );
  }

  if (error || !doc) {
    return (
      <Centered>
        <div style={{ textAlign: 'center' }}>
          <div style={monoStyle}>NOT FOUND</div>
          <p style={{ marginTop: 8, fontSize: 13, color: 'var(--fg-3)' }}>
            {error || 'This document could not be loaded.'}
          </p>
          <div style={{ marginTop: 16 }}>
            <Btn variant="outline" icon="chevron-left" onClick={() => router.push('/documents')}>
              Back to Documents
            </Btn>
          </div>
        </div>
      </Centered>
    );
  }

  const sentimentTone = (() => {
    const s = (doc.summary?.sentiment || '').toLowerCase();
    if (s === 'positive') return 'signal';
    if (s === 'negative') return 'warn';
    if (s === 'mixed') return 'cite';
    return 'fg-3';
  })();

  return (
    <div style={{ padding: '24px 40px 64px', maxWidth: 1240, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 18 }}>
        <Btn variant="ghost" size="sm" icon="chevron-left" onClick={() => router.push('/documents')}>
          Documents
        </Btn>
      </div>

      <div
        style={{
          padding: '20px 24px',
          background: 'var(--paper-2)',
          border: '1px solid var(--line)',
          borderRadius: 3,
          marginBottom: 22,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h1
              style={{
                margin: 0,
                fontFamily: 'var(--serif)',
                fontSize: 24,
                fontWeight: 500,
                color: 'var(--ink)',
                lineHeight: 1.25,
                wordBreak: 'break-word',
              }}
            >
              {doc.name || 'Untitled document'}
            </h1>
            {doc.url && (
              <a
                href={doc.url}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display: 'inline-block',
                  marginTop: 6,
                  fontFamily: 'var(--mono)',
                  fontSize: 11,
                  color: 'var(--cite)',
                  textDecoration: 'none',
                  wordBreak: 'break-all',
                }}
              >
                {doc.url} ↗
              </a>
            )}
          </div>
          <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
            {doc.reliability_rating && <Tag>{doc.reliability_rating}</Tag>}
            <Tag>{doc.entity_count} entities</Tag>
          </div>
        </div>
      </div>

      {/* Two-column: main content + entity sidebar */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr) 280px',
          gap: 24,
          alignItems: 'flex-start',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 22, minWidth: 0 }}>
          {/* Summary card */}
          {doc.summary && (doc.summary.summary || (doc.summary.key_facts || []).length > 0) && (
            <section
              style={{
                background: 'var(--paper-2)',
                border: '1px solid var(--line)',
                borderRadius: 3,
                padding: 20,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <span style={monoStyle}>LLM SUMMARY</span>
                {doc.summary.sentiment && (
                  <span
                    style={{
                      fontFamily: 'var(--mono)',
                      fontSize: 10,
                      letterSpacing: '0.1em',
                      color: `var(--${sentimentTone})`,
                    }}
                  >
                    SENTIMENT · {doc.summary.sentiment.toUpperCase()}
                  </span>
                )}
              </div>
              {doc.summary.summary && (
                <p
                  style={{
                    margin: '0 0 14px',
                    fontFamily: 'var(--serif)',
                    fontSize: 16,
                    lineHeight: 1.55,
                    color: 'var(--ink)',
                  }}
                >
                  {doc.summary.summary}
                </p>
              )}
              {(doc.summary.key_facts || []).length > 0 && (
                <div style={{ marginTop: 6 }}>
                  <div style={{ ...monoStyle, marginBottom: 6 }}>KEY FACTS</div>
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13.5, lineHeight: 1.55, color: 'var(--fg-2)' }}>
                    {doc.summary.key_facts.map((f, i) => (
                      <li key={i} style={{ marginBottom: 4 }}>{f}</li>
                    ))}
                  </ul>
                </div>
              )}
              {(doc.summary.topics || []).length > 0 && (
                <div style={{ marginTop: 14, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {doc.summary.topics.map((t, i) => (
                    <Tag key={i}>{t}</Tag>
                  ))}
                </div>
              )}
            </section>
          )}

          {/* Content */}
          <section
            style={{
              background: 'var(--paper)',
              border: '1px solid var(--line)',
              borderRadius: 3,
              padding: 24,
            }}
          >
            <div style={{ ...monoStyle, marginBottom: 12 }}>CONTENT · ENTITIES HIGHLIGHTED</div>
            <div
              style={{
                margin: 0,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                fontFamily: 'var(--serif)',
                fontSize: 14.5,
                lineHeight: 1.6,
                color: 'var(--ink)',
              }}
            >
              {doc.content
                ? renderHighlightedContent(doc.content, doc.entities)
                : '(no content)'}
            </div>
          </section>
        </div>

        {/* Entity sidebar */}
        <aside
          style={{
            position: 'sticky',
            top: 96,
            background: 'var(--paper-2)',
            border: '1px solid var(--line)',
            borderRadius: 3,
            padding: 16,
            maxHeight: 'calc(100vh - 140px)',
            overflowY: 'auto',
          }}
        >
          <div style={{ ...monoStyle, marginBottom: 10 }}>EXTRACTED ENTITIES</div>
          {doc.entities.length === 0 ? (
            <p style={{ margin: 0, fontSize: 12, color: 'var(--fg-3)' }}>
              No entities extracted from this document.
            </p>
          ) : (
            <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {doc.entities.slice(0, 50).map((e) => (
                <li
                  key={e.id}
                  style={{
                    padding: '6px 8px',
                    background: 'var(--paper)',
                    border: '1px solid var(--line)',
                    borderRadius: 3,
                    fontSize: 12,
                  }}
                >
                  <div style={{ color: 'var(--ink)', fontWeight: 500 }}>{e.name}</div>
                  <div style={{ ...monoStyle, marginTop: 2, fontSize: 9 }}>
                    {e.entity_type.toUpperCase()} · {e.relationship}
                  </div>
                </li>
              ))}
            </ul>
          )}

          {/* Provenance trail — chain of custody from this doc through the pipeline */}
          <div style={{ marginTop: 22 }}>
            <div style={{ ...monoStyle, marginBottom: 10 }}>PROVENANCE · CHAIN OF CUSTODY</div>
            <ProvenanceTrail />
          </div>
        </aside>
      </div>
    </div>
  );
}

// Highlight entity name occurrences in plain document content.
// Builds a regex from the entity names (longest first to prefer multi-word matches)
// and wraps matches in a tinted span. Capped to avoid catastrophic regex perf on huge docs.
function renderHighlightedContent(content: string, entities: DocEntity[]): React.ReactNode[] {
  const names = entities
    .map((e) => (e.name || '').trim())
    .filter((n) => n.length >= 3)
    .sort((a, b) => b.length - a.length)
    .slice(0, 80);
  if (names.length === 0) return [content];
  const escaped = names.map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const re = new RegExp('\\b(' + escaped.join('|') + ')\\b', 'g');
  const out: React.ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  let idx = 0;
  // Hard cap on highlights to bound DOM size.
  const MAX_HL = 400;
  while ((m = re.exec(content)) !== null && idx < MAX_HL) {
    if (m.index > last) out.push(content.slice(last, m.index));
    const matched = m[0];
    const entity = entities.find((e) => e.name === matched);
    out.push(
      <mark
        key={`hl-${idx}`}
        title={entity ? `${entity.entity_type} · ${entity.relationship}` : matched}
        style={{
          background: 'var(--signal-soft)',
          color: 'var(--signal-ink)',
          padding: '0 2px',
          borderRadius: 2,
          fontWeight: 500,
        }}
      >
        {matched}
      </mark>,
    );
    last = m.index + matched.length;
    idx++;
  }
  if (last < content.length) out.push(content.slice(last));
  return out;
}

const STEP_TONE: Record<string, string> = {
  source:       'var(--cite)',
  extraction:   'var(--signal-ink)',
  resolution:   'var(--violet)',
  relationship: 'var(--ink)',
  assessment:   'var(--signal)',
  product:      'var(--live)',
};

function ProvenanceTrail() {
  return (
    <ol style={{ listStyle: 'none', padding: 0, margin: 0, position: 'relative' }}>
      {/* vertical thread */}
      <span
        style={{
          position: 'absolute', left: 9, top: 6, bottom: 6, width: 1,
          background: 'var(--line)',
        }}
      />
      {PROVENANCE_DEMO.map((s) => (
        <li key={s.step} style={{ display: 'flex', gap: 10, padding: '6px 0', position: 'relative' }}>
          <span
            style={{
              width: 18, height: 18, flexShrink: 0, marginTop: 2,
              borderRadius: '50%',
              background: 'var(--paper)',
              border: `1.5px solid ${STEP_TONE[s.step] || 'var(--fg-3)'}`,
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              color: STEP_TONE[s.step] || 'var(--fg-3)',
            }}
          >
            <Icon name="dot" size={6} />
          </span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 9, letterSpacing: '0.12em', color: STEP_TONE[s.step] || 'var(--fg-3)', fontWeight: 600 }}>
              {s.step.toUpperCase()}
            </div>
            <div style={{ fontSize: 12, color: 'var(--ink)', fontWeight: 500, lineHeight: 1.3, marginTop: 1 }}>
              {s.label}
            </div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-3)', marginTop: 1 }}>
              {s.meta}
            </div>
            <div style={{ fontSize: 11.5, color: 'var(--fg-2)', marginTop: 3, lineHeight: 1.4 }}>
              {s.detail}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '60vh',
      }}
    >
      {children}
    </div>
  );
}

const monoStyle: React.CSSProperties = {
  fontFamily: 'var(--mono)',
  fontSize: 10,
  letterSpacing: '0.12em',
  color: 'var(--fg-3)',
  display: 'block',
};
