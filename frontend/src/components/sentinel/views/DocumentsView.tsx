'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useProject } from '@/lib/ProjectContext';
import { documentsApi } from '@/lib/api';
import { Icon, Tag } from '@/components/sentinel';

// ============================================================================
// Types
// ============================================================================

type DocKind = 'PDF' | 'HTML' | 'CSV' | 'JSON' | 'TXT' | 'OTHER';
type Reliability = 'A' | 'B' | 'C';
type FilterKind = 'ALL' | 'PDF' | 'HTML' | 'CSV' | 'JSON' | 'TXT';

interface RawDoc {
  id?: string | number;
  title?: string;
  filename?: string;
  name?: string;
  source?: string;
  source_name?: string;
  reliability?: string;
  reliability_rating?: string;
  date?: string;
  created_at?: string;
  uploaded_at?: string;
  ingested_at?: string;
  pages?: number;
  page_count?: number;
  kind?: string;
  file_format?: string;
  format?: string;
  mime_type?: string;
}

interface DocRow {
  id: string;
  title: string;
  kind: DocKind;
  source: string;
  reliability: Reliability;
  date: string | null;
  pages: number | null;
  ingested: string | null;
}

const FILTER_OPTIONS: FilterKind[] = ['ALL', 'PDF', 'HTML', 'CSV', 'JSON', 'TXT'];

// ============================================================================
// Page wrapper
// ============================================================================

export function DocumentsView() {
  const router = useRouter();
  const { activeProject } = useProject();

  const [rawDocs, setRawDocs] = useState<RawDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterKind>('ALL');
  const [query, setQuery] = useState('');

  useEffect(() => {
    if (!activeProject) {
      setRawDocs([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    documentsApi
      .list(activeProject.id)
      .then((res) => {
        const raw = res.data;
        const list = Array.isArray(raw)
          ? raw
          : (raw as { documents?: unknown[] })?.documents ?? [];
        setRawDocs(Array.isArray(list) ? (list as RawDoc[]) : []);
      })
      .catch(() => setRawDocs([]))
      .finally(() => setLoading(false));
  }, [activeProject]);

  const docs: DocRow[] = useMemo(() => rawDocs.map(normalize), [rawDocs]);

  const filtered: DocRow[] = useMemo(() => {
    const q = query.trim().toLowerCase();
    return docs.filter((d) => {
      if (filter !== 'ALL' && d.kind !== filter) return false;
      if (q && !d.title.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [docs, filter, query]);

  if (!activeProject) {
    return (
      <div style={{ height: '100%', overflow: 'auto', background: 'var(--paper)' }}>
        <div style={{ maxWidth: 720, margin: '120px auto', padding: '0 32px' }}>
          <SectionLabel>DOCUMENTS · NO ACTIVE PROJECT</SectionLabel>
          <h1
            style={{
              margin: '8px 0 0',
              fontFamily: 'var(--serif)',
              fontWeight: 500,
              fontSize: 44,
              letterSpacing: '-0.02em',
              color: 'var(--ink)',
              lineHeight: 1,
            }}
          >
            Pick a project to see its documents<span style={{ color: 'var(--signal)' }}>.</span>
          </h1>
          <p
            style={{
              margin: '14px 0 0',
              fontFamily: 'var(--serif)',
              fontSize: 16,
              lineHeight: 1.55,
              color: 'var(--fg-2)',
            }}
          >
            The catalog scopes to one project at a time. Open a project from the hub, then return here
            to browse ingested PDFs, HTML scrapes, CSVs, and feeds.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ height: '100%', overflow: 'auto', background: 'var(--paper)' }}>
      <div style={{ maxWidth: 1320, margin: '0 auto', padding: '28px 32px 64px' }}>
        <Header
          total={docs.length}
          shown={filtered.length}
          filter={filter}
          onFilter={setFilter}
        />

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            marginTop: 18,
            marginBottom: 18,
          }}
        >
          <SearchInput value={query} onChange={setQuery} />
        </div>

        {loading ? (
          <Loading />
        ) : docs.length === 0 ? (
          <EmptyDocs />
        ) : filtered.length === 0 ? (
          <EmptyRow text="No documents match the current filter." />
        ) : (
          <Table rows={filtered} onSelect={(id) => router.push(`/documents/${id}`)} />
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Header
// ============================================================================

function Header({
  total,
  shown,
  filter,
  onFilter,
}: {
  total: number;
  shown: number;
  filter: FilterKind;
  onFilter: (f: FilterKind) => void;
}) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-end',
        justifyContent: 'space-between',
        gap: 24,
        paddingBottom: 18,
        borderBottom: '1px solid var(--line)',
        flexWrap: 'wrap',
      }}
    >
      <div style={{ minWidth: 0 }}>
        <SectionLabel>CATALOG</SectionLabel>
        <h1
          style={{
            margin: '6px 0 0',
            fontFamily: 'var(--serif)',
            fontWeight: 500,
            fontSize: 42,
            letterSpacing: '-0.02em',
            color: 'var(--ink)',
            lineHeight: 1,
          }}
        >
          Documents
          <span style={{ color: 'var(--signal)' }}>.</span>
          <span
            style={{
              fontFamily: 'var(--mono)',
              fontSize: 18,
              fontWeight: 400,
              color: 'var(--fg-3)',
              marginLeft: 14,
              letterSpacing: '0.05em',
            }}
          >
            {shown === total
              ? total.toLocaleString()
              : `${shown.toLocaleString()} / ${total.toLocaleString()}`}
          </span>
        </h1>
        <p
          style={{
            margin: '12px 0 0',
            fontFamily: 'var(--serif)',
            fontSize: 16,
            lineHeight: 1.5,
            color: 'var(--fg-2)',
            maxWidth: 640,
          }}
        >
          Everything ingested into this project — feeds, scrapes, uploads, and snapshots — with
          source reliability and ingestion provenance.
        </p>
      </div>

      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {FILTER_OPTIONS.map((f) => {
          const active = f === filter;
          return (
            <button
              key={f}
              onClick={() => onFilter(f)}
              style={{
                padding: '6px 10px',
                background: active ? 'var(--ink)' : 'transparent',
                color: active ? 'var(--paper)' : 'var(--fg-2)',
                border: `1px solid ${active ? 'var(--ink)' : 'var(--line)'}`,
                borderRadius: 3,
                cursor: 'pointer',
                fontFamily: 'var(--mono)',
                fontSize: 10.5,
                letterSpacing: '0.12em',
                fontWeight: 600,
                textTransform: 'uppercase',
              }}
            >
              {f}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ============================================================================
// Search input
// ============================================================================

function SearchInput({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div
      style={{
        position: 'relative',
        flex: 1,
        maxWidth: 460,
      }}
    >
      <span
        style={{
          position: 'absolute',
          left: 12,
          top: '50%',
          transform: 'translateY(-50%)',
          color: 'var(--fg-3)',
          display: 'inline-flex',
        }}
      >
        <Icon name="search" size={14} />
      </span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Filter by title…"
        style={{
          width: '100%',
          padding: '9px 12px 9px 34px',
          background: 'var(--paper-2)',
          border: '1px solid var(--line)',
          borderRadius: 3,
          fontFamily: 'var(--sans)',
          fontSize: 13,
          color: 'var(--ink)',
          outline: 'none',
        }}
      />
    </div>
  );
}

// ============================================================================
// Table
// ============================================================================

function Table({
  rows,
  onSelect,
}: {
  rows: DocRow[];
  onSelect: (id: string) => void;
}) {
  const grid = '2.4fr 80px 1.4fr 80px 100px 70px 110px';

  return (
    <div
      style={{
        background: 'var(--paper-2)',
        border: '1px solid var(--line)',
        borderRadius: 3,
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: grid,
          gap: 16,
          padding: '12px 18px',
          background: 'var(--paper)',
          borderBottom: '1px solid var(--line-soft)',
        }}
      >
        {['Title', 'Kind', 'Source', 'Reliability', 'Date', 'Pages', 'Ingested'].map((h, i) => (
          <span
            key={h}
            style={{
              fontFamily: 'var(--mono)',
              fontSize: 9.5,
              letterSpacing: '0.18em',
              color: 'var(--fg-3)',
              fontWeight: 600,
              textTransform: 'uppercase',
              textAlign: i === 5 ? 'right' : 'left',
            }}
          >
            {h}
          </span>
        ))}
      </div>

      {rows.map((d, i) => (
        <Row key={d.id} row={d} grid={grid} first={i === 0} onSelect={onSelect} />
      ))}
    </div>
  );
}

function Row({
  row,
  grid,
  first,
  onSelect,
}: {
  row: DocRow;
  grid: string;
  first: boolean;
  onSelect: (id: string) => void;
}) {
  const [hover, setHover] = useState(false);

  return (
    <button
      onClick={() => onSelect(row.id)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        width: '100%',
        display: 'grid',
        gridTemplateColumns: grid,
        gap: 16,
        padding: '12px 18px',
        alignItems: 'center',
        borderTop: first ? 'none' : '1px solid var(--line-soft)',
        background: hover ? 'var(--paper)' : 'transparent',
        border: 'none',
        cursor: 'pointer',
        textAlign: 'left',
        transition: 'background 0.1s',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
        <span
          style={{
            width: 22,
            height: 22,
            borderRadius: 2,
            background: 'var(--paper)',
            border: '1px solid var(--line)',
            color: 'var(--fg-2)',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <Icon name="doc" size={12} />
        </span>
        <span
          style={{
            fontSize: 13,
            color: 'var(--ink)',
            fontWeight: 500,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {row.title}
        </span>
      </div>

      <Tag>{row.kind}</Tag>

      <span
        style={{
          fontSize: 12,
          color: 'var(--fg-2)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {row.source}
      </span>

      <ReliabilityBadge value={row.reliability} />

      <span
        style={{
          fontFamily: 'var(--mono)',
          fontSize: 11,
          color: 'var(--fg-3)',
          letterSpacing: '0.04em',
        }}
      >
        {row.date ?? '—'}
      </span>

      <span
        style={{
          fontFamily: 'var(--mono)',
          fontSize: 11,
          color: 'var(--fg-3)',
          textAlign: 'right',
        }}
      >
        {row.pages !== null ? row.pages.toLocaleString() : '—'}
      </span>

      <span
        style={{
          fontFamily: 'var(--mono)',
          fontSize: 11,
          color: 'var(--fg-3)',
          letterSpacing: '0.04em',
        }}
      >
        {row.ingested ?? '—'}
      </span>
    </button>
  );
}

// ============================================================================
// Reliability badge
// ============================================================================

function ReliabilityBadge({ value }: { value: Reliability }) {
  const meta: Record<Reliability, { color: string; label: string }> = {
    A: { color: 'var(--live)', label: 'A · reliable' },
    B: { color: 'var(--signal)', label: 'B · usually' },
    C: { color: 'var(--warn)', label: 'C · uncertain' },
  };
  const m = meta[value];
  return (
    <span
      title={m.label}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 24,
        height: 22,
        background: 'transparent',
        color: m.color,
        border: `1px solid ${m.color}`,
        borderRadius: 2,
        fontFamily: 'var(--mono)',
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: '0.04em',
      }}
    >
      {value}
    </span>
  );
}

// ============================================================================
// Empty + loading states
// ============================================================================

function EmptyDocs() {
  return (
    <div
      style={{
        padding: '56px 24px',
        textAlign: 'center',
        background: 'var(--paper-2)',
        border: '1px dashed var(--line)',
        borderRadius: 3,
      }}
    >
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 48,
          height: 48,
          borderRadius: 4,
          background: 'var(--paper)',
          border: '1px solid var(--line)',
          color: 'var(--fg-3)',
          marginBottom: 14,
        }}
      >
        <Icon name="doc" size={22} />
      </span>
      <div
        style={{
          fontFamily: 'var(--serif)',
          fontSize: 19,
          fontWeight: 500,
          color: 'var(--ink)',
          marginBottom: 6,
        }}
      >
        No documents yet.
      </div>
      <p
        style={{
          margin: 0,
          fontSize: 13,
          color: 'var(--fg-3)',
          maxWidth: 420,
          marginInline: 'auto',
          lineHeight: 1.5,
        }}
      >
        Run a collection plan or upload a file to populate this catalog. Ingested documents will
        show their format, source, and reliability rating here.
      </p>
    </div>
  );
}

function EmptyRow({ text }: { text: string }) {
  return (
    <div
      style={{
        padding: '32px 20px',
        textAlign: 'center',
        background: 'var(--paper-2)',
        border: '1px dashed var(--line)',
        borderRadius: 3,
        color: 'var(--fg-3)',
        fontSize: 12.5,
      }}
    >
      {text}
    </div>
  );
}

function Loading() {
  return (
    <div
      style={{
        padding: '32px 20px',
        textAlign: 'center',
        background: 'var(--paper-2)',
        border: '1px solid var(--line)',
        borderRadius: 3,
        fontFamily: 'var(--mono)',
        fontSize: 11,
        color: 'var(--fg-3)',
        letterSpacing: '0.1em',
      }}
    >
      LOADING…
    </div>
  );
}

// ============================================================================
// Shared
// ============================================================================

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontFamily: 'var(--mono)',
        fontSize: 9.5,
        letterSpacing: '0.2em',
        color: 'var(--fg-3)',
        fontWeight: 600,
        textTransform: 'uppercase',
      }}
    >
      {children}
    </div>
  );
}

// ============================================================================
// Normalization
// ============================================================================

function normalize(d: RawDoc): DocRow {
  const id = String(d.id ?? '');
  const title = d.title || d.filename || d.name || 'Untitled document';
  const kind = inferKind(d);
  const source = d.source || d.source_name || '—';
  const reliability = inferReliability(d);
  const date = inferDate(d);
  const pages = inferPages(d);
  const ingested = inferIngested(d);
  return { id, title, kind, source, reliability, date, pages, ingested };
}

function inferKind(d: RawDoc): DocKind {
  const raw = (d.kind || d.file_format || d.format || d.mime_type || '').toString().toUpperCase();
  if (raw.includes('PDF')) return 'PDF';
  if (raw.includes('HTML')) return 'HTML';
  if (raw.includes('CSV')) return 'CSV';
  if (raw.includes('JSON')) return 'JSON';
  if (raw.includes('TXT') || raw.includes('TEXT')) return 'TXT';
  return 'OTHER';
}

function inferReliability(d: RawDoc): Reliability {
  const raw = (d.reliability || d.reliability_rating || '').toString().toUpperCase();
  if (raw.startsWith('A')) return 'A';
  if (raw.startsWith('B')) return 'B';
  if (raw.startsWith('C')) return 'C';
  return 'B';
}

function inferDate(d: RawDoc): string | null {
  const raw = d.date || d.created_at || d.uploaded_at || d.ingested_at;
  if (!raw) return null;
  try {
    const dt = new Date(raw);
    if (isNaN(dt.getTime())) return raw.slice(0, 10);
    return dt.toISOString().slice(0, 10);
  } catch {
    return null;
  }
}

function inferPages(d: RawDoc): number | null {
  if (typeof d.pages === 'number') return d.pages;
  if (typeof d.page_count === 'number') return d.page_count;
  return null;
}

function inferIngested(d: RawDoc): string | null {
  const raw = d.ingested_at || d.uploaded_at || d.created_at;
  if (!raw) return null;
  try {
    const dt = new Date(raw);
    if (isNaN(dt.getTime())) return null;
    const diffMs = Date.now() - dt.getTime();
    const m = Math.floor(diffMs / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    const days = Math.floor(h / 24);
    if (days < 30) return `${days}d ago`;
    return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch {
    return null;
  }
}
