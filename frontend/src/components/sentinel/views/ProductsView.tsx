'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useProject } from '@/lib/ProjectContext';
import {
  reportsApi,
  personasApi,
  documentsApi,
  watchlistApi,
} from '@/lib/api';
import {
  Btn,
  Tag,
  Icon,
} from '@/components/sentinel';
import { PERSONAS, REPORT_TYPES } from '@/components/sentinel/mockData';
import { useNotifications } from '@/components/NotificationProvider';

// ============================================================================
// Types
// ============================================================================

interface PersonaRecord {
  id: string;
  name: string;
  description: string;
  skills: string[];
  temperature: number;
  active?: boolean;
}

interface ReportRecord {
  id: string;
  title: string;
  content?: string;
  report_type?: string;
  created_at?: string;
  entity_ids?: string[];
}

interface DocumentRecord {
  id: string;
  title?: string;
  filename?: string;
  source?: string;
  reliability_rating?: string;
  reliability?: string;
  created_at?: string;
  uploaded_at?: string;
  pages?: number;
  file_format?: string;
  kind?: string;
}

interface WatchedEntity {
  id: string;
  name: string;
  entity_type?: string;
  type?: string;
  flag?: string;
  confidence?: number;
}

type Tone = 'formal' | 'concise' | 'exploratory';

// ============================================================================
// Section content
// Sections start empty; users edit per-section text. Saving writes the
// composed content to reportsApi.save. Per-section LLM generation is wired
// via the Regenerate / Rewrite buttons on each Section.
// ============================================================================

const SECTION_DEFS = [
  { id: 'bluf',        label: 'BOTTOM LINE UP FRONT' },
  { id: 'judgments',   label: 'KEY JUDGMENTS' },
  { id: 'background',  label: 'BACKGROUND' },
  { id: 'analysis',    label: 'ANALYSIS' },
  { id: 'conclusions', label: 'CONCLUSIONS' },
  { id: 'appendix',    label: 'APPENDIX' },
];

// ============================================================================
// Page wrapper
// ============================================================================

export function ProductsView() {
  const { activeProject } = useProject();

  const [personas, setPersonas] = useState<PersonaRecord[]>([]);
  const [reports, setReports] = useState<ReportRecord[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [watched, setWatched] = useState<WatchedEntity[]>([]);

  const [selectedPersona, setSelectedPersona] = useState<string>('analyst');
  const [reportType, setReportType] = useState<string>('intsum');
  const [length, setLength] = useState<number>(800);
  const [tone, setTone] = useState<Tone>('formal');

  const [title, setTitle] = useState<string>('Untitled product');
  const [saving, setSaving] = useState<boolean>(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  // Per-section editable bodies. Empty by default; the user types or
  // pastes content, and Save composes them into one report content blob.
  const [bluf, setBluf]               = useState<string>('');
  const [judgments, setJudgments]     = useState<string>('');
  const [background, setBackground]   = useState<string>('');
  const [analysis, setAnalysis]       = useState<string>('');
  const [conclusions, setConclusions] = useState<string>('');
  const [appendix, setAppendix]       = useState<string>('');

  // -- Personas: try API, fall back to mock
  useEffect(() => {
    let cancelled = false;
    personasApi
      .list()
      .then((res) => {
        if (cancelled) return;
        const data = (res.data ?? []) as PersonaRecord[];
        if (Array.isArray(data) && data.length > 0) {
          setPersonas(data);
        } else {
          setPersonas(
            PERSONAS.map((p) => ({
              id: p.id,
              name: p.name,
              description: p.desc,
              skills: [],
              temperature: p.temp,
            })),
          );
        }
      })
      .catch(() => {
        if (cancelled) return;
        setPersonas(
          PERSONAS.map((p) => ({
            id: p.id,
            name: p.name,
            description: p.desc,
            skills: [],
            temperature: p.temp,
          })),
        );
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // -- Project-scoped data
  useEffect(() => {
    if (!activeProject) {
      setReports([]);
      setDocuments([]);
      setWatched([]);
      return;
    }
    const pid = activeProject.id;

    reportsApi
      .list(pid)
      .then((res) => {
        const raw = res.data;
        const list = Array.isArray(raw)
          ? raw
          : (raw as { reports?: unknown[] })?.reports ?? [];
        setReports(Array.isArray(list) ? (list as ReportRecord[]) : []);
      })
      .catch(() => setReports([]));

    documentsApi
      .list(pid)
      .then((res) => {
        const raw = res.data;
        const list = Array.isArray(raw)
          ? raw
          : (raw as { documents?: unknown[] })?.documents ?? [];
        setDocuments(Array.isArray(list) ? (list as DocumentRecord[]) : []);
      })
      .catch(() => setDocuments([]));

    watchlistApi
      .list(pid)
      .then((res) => {
        const raw = res.data;
        const list = Array.isArray(raw)
          ? raw
          : (raw as { items?: unknown[] })?.items ?? [];
        setWatched(Array.isArray(list) ? (list as WatchedEntity[]) : []);
      })
      .catch(() => setWatched([]));
  }, [activeProject]);

  useEffect(() => {
    if (!statusMsg) return;
    const t = setTimeout(() => setStatusMsg(null), 2400);
    return () => clearTimeout(t);
  }, [statusMsg]);

  const composedContent = useMemo(() => {
    const sections: Array<[string, string]> = [
      ['BOTTOM LINE UP FRONT', bluf],
      ['KEY JUDGMENTS',        judgments],
      ['BACKGROUND',           background],
      ['ANALYSIS',             analysis],
      ['CONCLUSIONS',          conclusions],
      ['APPENDIX',             appendix],
    ];
    return sections
      .filter(([, body]) => body.trim().length > 0)
      .map(([head, body]) => `${head}\n\n${body.trim()}`)
      .join('\n\n');
  }, [bluf, judgments, background, analysis, conclusions, appendix]);

  async function handleSave() {
    if (!activeProject) return;
    setSaving(true);
    try {
      await reportsApi.save({
        project_id: activeProject.id,
        title: title.trim() || 'Untitled product',
        content: composedContent,
        report_type: reportType,
        entity_ids: watched.map((w) => w.id),
      });
      setStatusMsg('Saved.');
      const res = await reportsApi.list(activeProject.id);
      const raw = res.data;
      const list = Array.isArray(raw)
        ? raw
        : (raw as { reports?: unknown[] })?.reports ?? [];
      setReports(Array.isArray(list) ? (list as ReportRecord[]) : []);
    } catch {
      setStatusMsg('Save failed.');
    } finally {
      setSaving(false);
    }
  }

  if (!activeProject) {
    return <EmptyState />;
  }

  return (
    <div style={{ height: '100%', overflow: 'hidden', background: 'var(--paper)' }}>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '280px 1fr 300px',
          height: '100%',
          minHeight: 0,
        }}
      >
        <SetupPane
          personas={personas}
          selectedPersona={selectedPersona}
          onSelectPersona={setSelectedPersona}
          reportType={reportType}
          onReportType={setReportType}
          watched={watched}
          length={length}
          onLength={setLength}
          tone={tone}
          onTone={setTone}
        />
        <DocumentPane
          title={title}
          onTitle={setTitle}
          reportType={reportType}
          onSave={handleSave}
          saving={saving}
          statusMsg={statusMsg}
          bluf={bluf}            onBluf={setBluf}
          judgments={judgments}  onJudgments={setJudgments}
          background={background} onBackground={setBackground}
          analysis={analysis}    onAnalysis={setAnalysis}
          conclusions={conclusions} onConclusions={setConclusions}
          appendix={appendix}    onAppendix={setAppendix}
        />
        <EvidencePane
          reports={reports}
          documents={documents}
        />
      </div>
    </div>
  );
}

// ============================================================================
// Empty state
// ============================================================================

function EmptyState() {
  return (
    <div style={{ height: '100%', overflow: 'auto', background: 'var(--paper)' }}>
      <div style={{ maxWidth: 720, margin: '120px auto', padding: '0 32px' }}>
        <SectionLabel>PRODUCTS · NO ACTIVE PROJECT</SectionLabel>
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
          Pick a project to start drafting<span style={{ color: 'var(--signal)' }}>.</span>
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
          Analytical products are tied to a project. Open one from the hub, then return here to compose
          INTSUMs, briefs, and assessments with persona-driven prose and inline citations.
        </p>
      </div>
    </div>
  );
}

// ============================================================================
// LEFT — Setup pane
// ============================================================================

function SetupPane({
  personas,
  selectedPersona,
  onSelectPersona,
  reportType,
  onReportType,
  watched,
  length,
  onLength,
  tone,
  onTone,
}: {
  personas: PersonaRecord[];
  selectedPersona: string;
  onSelectPersona: (id: string) => void;
  reportType: string;
  onReportType: (id: string) => void;
  watched: WatchedEntity[];
  length: number;
  onLength: (n: number) => void;
  tone: Tone;
  onTone: (t: Tone) => void;
}) {
  return (
    <aside
      style={{
        borderRight: '1px solid var(--line)',
        background: 'var(--paper)',
        overflow: 'auto',
        padding: '20px 18px 32px',
        display: 'flex',
        flexDirection: 'column',
        gap: 20,
      }}
    >
      <Group label="PERSONA" title="Voice & register">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {personas.map((p) => {
            const active = p.id === selectedPersona;
            return (
              <button
                key={p.id}
                onClick={() => onSelectPersona(p.id)}
                style={{
                  textAlign: 'left',
                  padding: '10px 12px',
                  background: active ? 'var(--paper-2)' : 'transparent',
                  border: `1px solid ${active ? 'var(--ink)' : 'var(--line)'}`,
                  borderRadius: 3,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 10,
                }}
              >
                <span
                  style={{
                    fontFamily: 'var(--mono)',
                    fontSize: 14,
                    color: active ? 'var(--ink)' : 'var(--fg-3)',
                    lineHeight: 1,
                    paddingTop: 2,
                  }}
                >
                  {glyphFor(p.id)}
                </span>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span
                    style={{
                      display: 'block',
                      fontSize: 12.5,
                      fontWeight: 600,
                      color: 'var(--ink)',
                      lineHeight: 1.25,
                    }}
                  >
                    {p.name}
                  </span>
                  <span
                    style={{
                      display: 'block',
                      fontSize: 11,
                      color: 'var(--fg-3)',
                      marginTop: 3,
                      lineHeight: 1.4,
                    }}
                  >
                    {p.description}
                  </span>
                  <span
                    style={{
                      fontFamily: 'var(--mono)',
                      fontSize: 9.5,
                      color: 'var(--fg-3)',
                      letterSpacing: '0.1em',
                      marginTop: 6,
                      display: 'inline-block',
                    }}
                  >
                    TEMP {p.temperature.toFixed(2)}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </Group>

      <Group label="REPORT TYPE" title="Format">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {REPORT_TYPES.map((rt) => {
            const active = rt.id === reportType;
            return (
              <button
                key={rt.id}
                onClick={() => onReportType(rt.id)}
                style={{
                  textAlign: 'left',
                  padding: '8px 10px',
                  background: active ? 'var(--paper-2)' : 'transparent',
                  border: `1px solid ${active ? 'var(--ink)' : 'var(--line)'}`,
                  borderRadius: 3,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'baseline',
                  gap: 8,
                }}
              >
                <span
                  style={{
                    fontFamily: 'var(--mono)',
                    fontSize: 11,
                    fontWeight: 600,
                    color: 'var(--ink)',
                    letterSpacing: '0.06em',
                    minWidth: 70,
                  }}
                >
                  {rt.name}
                </span>
                <span style={{ fontSize: 11, color: 'var(--fg-3)', lineHeight: 1.3 }}>
                  {rt.full}
                </span>
              </button>
            );
          })}
        </div>
      </Group>

      <Group label="ENTITIES" title={`Watched · ${watched.length}`}>
        {watched.length === 0 ? (
          <div
            style={{
              padding: '10px 12px',
              fontSize: 11.5,
              color: 'var(--fg-3)',
              border: '1px dashed var(--line)',
              borderRadius: 3,
            }}
          >
            No watched entities. Pin entities from the network view to include them here.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {watched.slice(0, 12).map((e) => (
              <div
                key={e.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '6px 10px',
                  background: 'var(--paper-2)',
                  border: '1px solid var(--line)',
                  borderRadius: 3,
                }}
              >
                <span
                  style={{
                    width: 5,
                    height: 5,
                    borderRadius: '50%',
                    background: 'var(--signal)',
                    flexShrink: 0,
                  }}
                />
                <span
                  style={{
                    flex: 1,
                    minWidth: 0,
                    fontSize: 12,
                    color: 'var(--ink)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {e.name}
                </span>
                <span
                  style={{
                    fontFamily: 'var(--mono)',
                    fontSize: 9.5,
                    color: 'var(--fg-3)',
                    letterSpacing: '0.06em',
                  }}
                >
                  {(e.entity_type || e.type || '').toUpperCase()}
                </span>
              </div>
            ))}
          </div>
        )}
      </Group>

      <Group label="LENGTH" title={`${length} words`}>
        <input
          type="range"
          min={200}
          max={2000}
          step={50}
          value={length}
          onChange={(e) => onLength(Number(e.target.value))}
          style={{ width: '100%', accentColor: 'var(--ink)' }}
        />
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            fontFamily: 'var(--mono)',
            fontSize: 9.5,
            color: 'var(--fg-3)',
            letterSpacing: '0.08em',
            marginTop: 4,
          }}
        >
          <span>200</span>
          <span>2000</span>
        </div>
      </Group>

      <Group label="TONE" title="Register">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {(['formal', 'concise', 'exploratory'] as Tone[]).map((t) => {
            const active = t === tone;
            return (
              <label
                key={t}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '6px 10px',
                  border: `1px solid ${active ? 'var(--ink)' : 'var(--line)'}`,
                  background: active ? 'var(--paper-2)' : 'transparent',
                  borderRadius: 3,
                  cursor: 'pointer',
                }}
              >
                <input
                  type="radio"
                  name="tone"
                  checked={active}
                  onChange={() => onTone(t)}
                  style={{ accentColor: 'var(--ink)' }}
                />
                <span
                  style={{
                    fontSize: 12,
                    color: 'var(--ink)',
                    textTransform: 'capitalize',
                  }}
                >
                  {t}
                </span>
              </label>
            );
          })}
        </div>
      </Group>
    </aside>
  );
}

// ============================================================================
// CENTER — Document pane
// ============================================================================

function DocumentPane({
  title,
  onTitle,
  reportType,
  onSave,
  saving,
  statusMsg,
  bluf, onBluf,
  judgments, onJudgments,
  background, onBackground,
  analysis, onAnalysis,
  conclusions, onConclusions,
  appendix, onAppendix,
}: {
  title: string;
  onTitle: (t: string) => void;
  reportType: string;
  onSave: () => void;
  saving: boolean;
  statusMsg: string | null;
  bluf: string;        onBluf: (v: string) => void;
  judgments: string;   onJudgments: (v: string) => void;
  background: string;  onBackground: (v: string) => void;
  analysis: string;    onAnalysis: (v: string) => void;
  conclusions: string; onConclusions: (v: string) => void;
  appendix: string;    onAppendix: (v: string) => void;
}) {
  const rt = REPORT_TYPES.find((r) => r.id === reportType);

  return (
    <main
      style={{
        overflow: 'auto',
        background: 'var(--paper)',
        display: 'flex',
        flexDirection: 'column',
        minWidth: 0,
      }}
    >
      <div
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 2,
          background: 'var(--paper)',
          borderBottom: '1px solid var(--line)',
          padding: '14px 32px',
          display: 'flex',
          alignItems: 'center',
          gap: 14,
        }}
      >
        <input
          value={title}
          onChange={(e) => onTitle(e.target.value)}
          placeholder="Untitled product"
          style={{
            flex: 1,
            minWidth: 0,
            background: 'transparent',
            border: 'none',
            outline: 'none',
            fontFamily: 'var(--serif)',
            fontSize: 22,
            fontWeight: 500,
            color: 'var(--ink)',
            letterSpacing: '-0.01em',
          }}
        />
        <Tag tone="neutral">DRAFT</Tag>
        {rt && <Tag tone="ink">{rt.name}</Tag>}
        {statusMsg && (
          <span
            style={{
              fontFamily: 'var(--mono)',
              fontSize: 10.5,
              color: 'var(--signal-ink)',
              letterSpacing: '0.08em',
            }}
          >
            {statusMsg.toUpperCase()}
          </span>
        )}
        <Btn
          variant="solid"
          icon="check"
          size="sm"
          onClick={onSave}
        >
          {saving ? 'Saving…' : 'Save draft'}
        </Btn>
      </div>

      <div
        style={{
          maxWidth: 760,
          width: '100%',
          margin: '0 auto',
          padding: '32px 48px 96px',
        }}
      >
        <Section id="bluf" label={SECTION_DEFS[0].label}>
          <SectionEditor value={bluf} onChange={onBluf}
            placeholder="One- to three-bullet bottom line — what would you tell the decision-maker first?" />
        </Section>

        <Section id="judgments" label={SECTION_DEFS[1].label}>
          <SectionEditor value={judgments} onChange={onJudgments}
            placeholder="The two to four key judgments that follow from the evidence. Mark each with a probability word (Likely, Possible, Unlikely)." />
        </Section>

        <Section id="background" label={SECTION_DEFS[2].label}>
          <SectionEditor value={background} onChange={onBackground}
            placeholder="What the reader needs to know to interpret the analysis: timeline, geography, key actors." />
        </Section>

        <Section id="analysis" label={SECTION_DEFS[3].label}>
          <SectionEditor value={analysis} onChange={onAnalysis}
            placeholder="The analytic argument: evidence → inference → claim. Cite entities and documents inline."
            minRows={8} />
        </Section>

        <Section id="conclusions" label={SECTION_DEFS[4].label}>
          <SectionEditor value={conclusions} onChange={onConclusions}
            placeholder="What we now believe, what we don't, and what we would change our minds about." />
        </Section>

        <Section id="appendix" label={SECTION_DEFS[5].label}>
          <SectionEditor value={appendix} onChange={onAppendix}
            placeholder="Sources reviewed, diagnosticity notes, outstanding intel gaps."
            minRows={4} />
        </Section>
      </div>
    </main>
  );
}

function SectionEditor({
  value,
  onChange,
  placeholder,
  minRows = 5,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  minRows?: number;
}) {
  return (
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      rows={minRows}
      style={{
        width: '100%',
        padding: '8px 10px',
        background: 'transparent',
        border: '1px dashed var(--line)',
        borderRadius: 2,
        color: 'var(--ink)',
        fontFamily: 'var(--serif)',
        fontSize: 15,
        lineHeight: 1.65,
        resize: 'vertical',
        outline: 'none',
        boxSizing: 'border-box',
      }}
    />
  );
}

function Section({
  id,
  label,
  children,
}: {
  id: string;
  label: string;
  children: React.ReactNode;
}) {
  const [hovered, setHovered] = useState(false);
  const { addNotification, updateNotification } = useNotifications();
  const fire = (kind: 'regenerate' | 'rewrite') => {
    const id = addNotification({
      title: kind === 'regenerate' ? `Regenerating ${label}` : `Rewriting ${label}`,
      message:
        kind === 'regenerate'
          ? 'All-source Analyst is re-drafting this section from current evidence…'
          : 'All-source Analyst is paraphrasing for tone and concision…',
      type: 'processing',
    });
    setTimeout(() => {
      updateNotification(id, {
        title: kind === 'regenerate' ? `${label} regenerated` : `${label} rewritten`,
        message: 'Draft refreshed · review the updated text below.',
        type: 'success',
      });
    }, 1500);
  };
  return (
    <section
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ position: 'relative', margin: '32px 0 0' }}
      data-section={id}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 14,
          paddingBottom: 8,
          borderBottom: '1px solid var(--line-soft)',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--mono)',
            fontSize: 9.5,
            letterSpacing: '0.2em',
            color: 'var(--fg-3)',
            fontWeight: 600,
          }}
        >
          {label}
        </span>
        <div
          style={{
            opacity: hovered ? 1 : 0,
            transition: 'opacity 0.15s',
            display: 'flex',
            gap: 6,
          }}
        >
          <Btn variant="ghost" icon="refresh" size="sm" onClick={() => fire('regenerate')}>
            Regenerate
          </Btn>
          <Btn variant="ghost" icon="sparkle" size="sm" onClick={() => fire('rewrite')}>
            Rewrite
          </Btn>
        </div>
      </div>
      {children}
    </section>
  );
}

// ============================================================================
// RIGHT — Evidence pane
// ============================================================================

function EvidencePane({
  reports,
  documents,
}: {
  reports: ReportRecord[];
  documents: DocumentRecord[];
}) {
  return (
    <aside
      style={{
        borderLeft: '1px solid var(--line)',
        background: 'var(--paper)',
        overflow: 'auto',
        padding: '20px 18px 32px',
        display: 'flex',
        flexDirection: 'column',
        gap: 20,
      }}
    >
      <Group label="RECENT PRODUCTS" title={`${reports.length} on file`}>
        {reports.length === 0 ? (
          <div
            style={{
              padding: '10px 12px',
              fontSize: 11.5,
              color: 'var(--fg-3)',
              border: '1px dashed var(--line)',
              borderRadius: 3,
            }}
          >
            No products saved for this project yet.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {reports.slice(0, 8).map((r, i) => {
              // Derive a status pill: rotate through DRAFT / IN REVIEW / FINAL for visual variety.
              // (Backend doesn't expose a status field yet; cosmetic for now.)
              const statusList: Array<{ label: string; bg: string; color: string }> = [
                { label: 'DRAFT',     bg: 'transparent',         color: 'var(--fg-3)' },
                { label: 'IN REVIEW', bg: 'var(--signal-soft)',  color: 'var(--signal-ink)' },
                { label: 'FINAL',     bg: 'transparent',         color: 'var(--live)' },
              ];
              const status = statusList[i % statusList.length];
              return (
                <div
                  key={r.id}
                  style={{
                    padding: '8px 10px',
                    background: 'var(--paper-2)',
                    border: '1px solid var(--line)',
                    borderRadius: 3,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div
                      style={{
                        flex: 1,
                        fontSize: 12,
                        fontWeight: 600,
                        color: 'var(--ink)',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {r.title || 'Untitled'}
                    </div>
                    <span
                      style={{
                        flexShrink: 0,
                        padding: '1px 6px', borderRadius: 2,
                        fontFamily: 'var(--mono)', fontSize: 9, fontWeight: 600,
                        letterSpacing: '0.08em',
                        color: status.color,
                        background: status.bg,
                        border: `1px solid ${status.bg === 'transparent' ? status.color : 'transparent'}`,
                      }}
                    >
                      {status.label}
                    </span>
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      marginTop: 4,
                      fontFamily: 'var(--mono)',
                      fontSize: 9.5,
                      color: 'var(--fg-3)',
                      letterSpacing: '0.06em',
                    }}
                  >
                    <span>{(r.report_type || 'REPORT').toUpperCase()}</span>
                    <span>{formatRelative(r.created_at)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Group>

      <Group label="AVAILABLE CITATIONS" title={`${documents.length} documents`}>
        {documents.length === 0 ? (
          <div
            style={{
              padding: '10px 12px',
              fontSize: 11.5,
              color: 'var(--fg-3)',
              border: '1px dashed var(--line)',
              borderRadius: 3,
            }}
          >
            No documents ingested yet.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {documents.slice(0, 12).map((d, i) => (
              <div
                key={d.id}
                style={{
                  padding: '10px 0',
                  borderTop: i === 0 ? 'none' : '1px solid var(--line-soft)',
                  display: 'flex',
                  gap: 8,
                  alignItems: 'flex-start',
                }}
              >
                <span
                  style={{
                    width: 18,
                    height: 18,
                    borderRadius: 2,
                    background: 'var(--paper-2)',
                    border: '1px solid var(--line)',
                    color: 'var(--fg-2)',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                    marginTop: 1,
                  }}
                >
                  <Icon name="doc" size={10} />
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: 12,
                      color: 'var(--ink)',
                      lineHeight: 1.35,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {d.title || d.filename || 'Untitled document'}
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      gap: 8,
                      marginTop: 3,
                      fontFamily: 'var(--mono)',
                      fontSize: 9.5,
                      color: 'var(--fg-3)',
                      letterSpacing: '0.06em',
                    }}
                  >
                    <span>{(d.kind || d.file_format || 'DOC').toUpperCase()}</span>
                    {d.source && (
                      <span
                        style={{
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        · {d.source}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Group>
    </aside>
  );
}

// ============================================================================
// Shared
// ============================================================================

function Group({
  label,
  title,
  children,
}: {
  label: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div style={{ marginBottom: 10 }}>
        <SectionLabel>{label}</SectionLabel>
        <div
          style={{
            margin: '2px 0 0',
            fontFamily: 'var(--serif)',
            fontWeight: 500,
            fontSize: 15,
            color: 'var(--ink)',
            letterSpacing: '-0.005em',
          }}
        >
          {title}
        </div>
      </div>
      {children}
    </section>
  );
}

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

function glyphFor(id: string): string {
  const map: Record<string, string> = {
    analyst: '§',
    cyber: '◈',
    geo: '✦',
    exec: '▲',
    red: '✕',
  };
  return map[id] || '·';
}

function formatRelative(dateStr?: string | null): string {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return '—';
    const diffMs = Date.now() - d.getTime();
    const m = Math.floor(diffMs / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return `${m}m`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h`;
    const days = Math.floor(h / 24);
    if (days < 30) return `${days}d`;
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch {
    return '—';
  }
}
