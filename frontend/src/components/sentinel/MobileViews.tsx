'use client';

/**
 * Sentinel Mobile views — Hub, Acquire trace, Ask (Graph RAG), Products, Review.
 * Ported from sentinel-2/src/mobile-screens.jsx. These are paper-aesthetic
 * mobile-native layouts intended to render inside MobileShell at narrow widths;
 * the existing desktop views render at >= 768px.
 */

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Icon, Tag, PulseDot, ENTITY_META } from '@/components/sentinel';
import { useNotifications } from '@/components/NotificationProvider';
import { useProject } from '@/lib/ProjectContext';
import {
  collectionPlansApi,
  reportsApi,
  personasApi,
  queryApi,
  projectsApi,
} from '@/lib/api';

// ----------------------------------------------------------------------------
// Shared types for project-scoped data
// ----------------------------------------------------------------------------

interface MobileReport {
  id: string;
  title?: string;
  content?: string;
  report_type?: string;
  status?: string;
  entity_ids?: string[];
  created_at?: string;
}
interface MobilePersona {
  id?: string;
  name?: string;
  description?: string;
}
interface MobileActivityEvent {
  id?: string;
  action?: string;
  entity_name?: string;
  entity_type?: string;
  timestamp?: string;
}

function fmtClock(ts?: string): string {
  if (!ts) return '';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return '';
  const mins = Math.max(0, Math.floor((Date.now() - d.getTime()) / 60000));
  if (mins < 1) return 'now';
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  return `${Math.floor(hrs / 24)}d`;
}

// ----------------------------------------------------------------------------
// Atoms
// ----------------------------------------------------------------------------

function MCard({ children, style, onClick }: { children: React.ReactNode; style?: React.CSSProperties; onClick?: () => void }) {
  return (
    <div
      onClick={onClick}
      style={{
        background: 'var(--paper-2)', border: '1px solid var(--line)',
        borderRadius: 10, padding: 14, cursor: onClick ? 'pointer' : undefined,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

function MLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontFamily: 'var(--mono)', fontSize: 9.5, letterSpacing: '0.18em', color: 'var(--fg-3)', fontWeight: 600 }}>
      {children}
    </div>
  );
}

function MBtn({
  children, icon, variant = 'solid', onClick, style,
}: {
  children?: React.ReactNode;
  icon?: string;
  variant?: 'solid' | 'signal' | 'outline' | 'ghost';
  onClick?: () => void;
  style?: React.CSSProperties;
}) {
  const v = {
    solid:   { bg: 'var(--ink)',    color: 'var(--paper)', border: 'var(--ink)' },
    signal:  { bg: 'var(--signal)', color: 'var(--ink)',   border: 'var(--signal)' },
    outline: { bg: 'transparent',   color: 'var(--fg)',    border: 'var(--line)' },
    ghost:   { bg: 'transparent',   color: 'var(--fg-2)',  border: 'transparent' },
  }[variant];
  return (
    <button
      onClick={onClick}
      style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 7,
        padding: '11px 16px', borderRadius: 8,
        background: v.bg, color: v.color, border: `1px solid ${v.border}`,
        fontSize: 14, fontWeight: 600, fontFamily: 'var(--sans)',
        cursor: 'pointer',
        ...style,
      }}
    >
      {icon && <Icon name={icon} size={16} />}
      {children}
    </button>
  );
}

// ============================================================================
// MHub — mobile hub / project masthead
// ============================================================================

interface ActivePlan {
  id: string;
  name?: string;
  status?: string;
  pir?: string;
  refined_pir?: string;
}

export function MHub() {
  const router = useRouter();
  const { activeProject } = useProject();
  const go = (route: string) => router.push(route);

  const [reports, setReports] = useState<MobileReport[]>([]);
  const [activity, setActivity] = useState<MobileActivityEvent[]>([]);
  const [plans, setPlans] = useState<ActivePlan[]>([]);

  useEffect(() => {
    if (!activeProject) {
      setReports([]); setActivity([]); setPlans([]);
      return;
    }
    reportsApi
      .list(activeProject.id)
      .then((r) => {
        const raw = r.data;
        const list = Array.isArray(raw) ? raw : (raw as { reports?: MobileReport[] })?.reports ?? [];
        setReports((Array.isArray(list) ? list : []) as MobileReport[]);
      })
      .catch(() => setReports([]));
    projectsApi
      .activity(activeProject.id, 6)
      .then((r) => {
        const raw = r.data as { activity?: MobileActivityEvent[] } | MobileActivityEvent[] | undefined;
        const list = Array.isArray(raw) ? raw : raw?.activity ?? [];
        setActivity((Array.isArray(list) ? list : []) as MobileActivityEvent[]);
      })
      .catch(() => setActivity([]));
    collectionPlansApi
      .list(activeProject.id)
      .then((r) => {
        const raw = r.data;
        const list = Array.isArray(raw) ? raw : (raw as { plans?: ActivePlan[] })?.plans ?? [];
        setPlans((Array.isArray(list) ? list : []) as ActivePlan[]);
      })
      .catch(() => setPlans([]));
  }, [activeProject]);

  if (!activeProject) {
    return (
      <div style={{ padding: '36px 16px', textAlign: 'center' }}>
        <Icon name="hub" size={28} />
        <h2 style={{ margin: '12px 0 4px', fontFamily: 'var(--serif)', fontSize: 22, fontWeight: 500, color: 'var(--ink)' }}>
          No active project
        </h2>
        <p style={{ margin: 0, fontSize: 13, color: 'var(--fg-3)' }}>
          Tap the menu to switch projects, or create a new one.
        </p>
      </div>
    );
  }

  const entityCount = activeProject.entity_count ?? 0;
  const relCount = activeProject.relationship_count ?? 0;
  const docCount = activeProject.document_count ?? 0;
  const colCount = activeProject.collection_count ?? 0;
  const activePlan = plans.find((p) => {
    const s = (p.status || '').toUpperCase();
    return s === 'ACTIVE' || s === 'RUNNING' || s === 'PROGRESS' || s === 'STARTED' || s === 'PENDING';
  });

  return (
    <div style={{ padding: '8px 16px 24px' }}>
      {/* Masthead */}
      <div style={{ marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
          <Tag tone="signal">{activeProject.classification_level || 'UNCLASSIFIED'}</Tag>
          <Tag tone="live">● {(activeProject.status || 'ACTIVE').toUpperCase()}</Tag>
          {activeProject.priority && <Tag>{activeProject.priority.toUpperCase()}</Tag>}
        </div>
        <h1
          style={{
            margin: 0, fontFamily: 'var(--serif)', fontSize: 32, fontWeight: 500,
            letterSpacing: '-0.02em', color: 'var(--ink)', lineHeight: 1.05,
          }}
        >
          {activeProject.name}
          <span style={{ color: 'var(--signal)' }}>.</span>
        </h1>
        {activeProject.description ? (
          <p style={{ margin: '10px 0 0', fontFamily: 'var(--serif)', fontSize: 14, lineHeight: 1.5, color: 'var(--fg-2)' }}>
            {activeProject.description}
          </p>
        ) : (
          <p style={{ margin: '10px 0 0', fontFamily: 'var(--serif)', fontSize: 13, lineHeight: 1.5, color: 'var(--fg-3)', fontStyle: 'italic' }}>
            No PIR captured yet — start a collection plan to define one.
          </p>
        )}
      </div>

      {/* Stats strip */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, margin: '16px 0' }}>
        {[
          [formatStat(entityCount), 'entities'],
          [formatStat(relCount),    'rels'],
          [formatStat(docCount),    'docs'],
          [formatStat(colCount),    'plans'],
        ].map(([v, l]) => (
          <div key={l} style={{ textAlign: 'center' }}>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 18, fontWeight: 600, color: 'var(--ink)' }}>{v}</div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 8.5, letterSpacing: '0.1em', color: 'var(--fg-3)' }}>
              {l.toUpperCase()}
            </div>
          </div>
        ))}
      </div>

      {/* Pillars */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {[
          { k: 'ACQUIRE',    t: 'Agentic acquisition', l: `${colCount} plan${colCount === 1 ? '' : 's'} · ${docCount} document${docCount === 1 ? '' : 's'}`,                    tint: 'var(--cite)',       route: '/collections' },
          { k: 'UNDERSTAND', t: 'Graph RAG',           l: `${formatStat(entityCount)} entities · ask anything`, tint: 'var(--violet)',     route: '/network' },
          { k: 'DELIVER',    t: 'Tailored products',   l: `${reports.length} report${reports.length === 1 ? '' : 's'} on file`, tint: 'var(--signal-ink)', route: '/products' },
        ].map((p) => (
          <MCard
            key={p.k}
            onClick={() => go(p.route)}
            style={{ position: 'relative', overflow: 'hidden', paddingLeft: 18 }}
          >
            <div style={{ position: 'absolute', top: 0, left: 0, width: 3, height: '100%', background: p.tint }} />
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 9, letterSpacing: '0.15em', color: p.tint, fontWeight: 600 }}>
                  {p.k}
                </span>
                <div style={{ fontFamily: 'var(--serif)', fontSize: 18, fontWeight: 500, color: 'var(--ink)', marginTop: 2 }}>
                  {p.t}
                </div>
                <div style={{ fontSize: 12, color: 'var(--fg-3)', marginTop: 2 }}>{p.l}</div>
              </div>
              <Icon name="arrow-up-right" size={16} />
            </div>
          </MCard>
        ))}
      </div>

      {/* Recent activity (real, replaces ARCTIC SHIFT anomaly digest) */}
      <div style={{ marginTop: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <MLabel>RECENT ACTIVITY</MLabel>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 9.5, color: 'var(--fg-3)' }}>
            {activity.length === 0 ? 'NONE' : `LAST ${activity.length}`}
          </span>
        </div>
        {activity.length === 0 ? (
          <MCard>
            <p style={{ margin: 0, fontFamily: 'var(--serif)', fontSize: 13, color: 'var(--fg-3)', fontStyle: 'italic' }}>
              Nothing in the recent feed — run a collection or ingest a document.
            </p>
          </MCard>
        ) : (
          activity.slice(0, 4).map((a, i) => {
            const action = a.action || 'Event';
            return (
              <MCard
                key={a.id || i}
                onClick={() => go('/network')}
                style={{ marginBottom: 8, position: 'relative', overflow: 'hidden', paddingLeft: 18 }}
              >
                <div style={{ position: 'absolute', top: 0, left: 0, width: 2, height: '100%', background: 'var(--signal)' }} />
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 9, letterSpacing: '0.12em', color: 'var(--signal-ink)', fontWeight: 600 }}>
                    {(a.entity_type || '—').toUpperCase()}
                  </span>
                  <span style={{ flex: 1 }} />
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-2)' }}>{fmtClock(a.timestamp)}</span>
                </div>
                <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--ink)', lineHeight: 1.35 }}>
                  {action}{a.entity_name ? ` · ${a.entity_name}` : ''}
                </div>
              </MCard>
            );
          })
        )}
      </div>

      {/* Live agent — only shown when a real plan is active */}
      {activePlan && (
        <div style={{ marginTop: 10 }}>
          <MLabel>LIVE AGENT · {(activePlan.id || '').slice(0, 8).toUpperCase()}</MLabel>
          <MCard style={{ marginTop: 8 }} onClick={() => go('/collections')}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <PulseDot color="var(--signal)" />
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--signal-ink)', letterSpacing: '0.1em' }}>
                {(activePlan.status || 'RUNNING').toUpperCase()}
              </span>
              <span style={{ flex: 1 }} />
              <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-2)' }}>OPEN →</span>
            </div>
            <div style={{ fontSize: 12.5, color: 'var(--ink)', lineHeight: 1.4 }}>
              {activePlan.name || activePlan.refined_pir || activePlan.pir || 'Active collection plan'}
            </div>
          </MCard>
        </div>
      )}
    </div>
  );
}

function formatStat(n: number): string {
  if (n >= 1000) {
    const k = n / 1000;
    return (k >= 10 ? Math.round(k) : Math.round(k * 10) / 10) + 'k';
  }
  return n.toLocaleString();
}

// ============================================================================
// MAcquire — agent trace
// ============================================================================

export function MAcquire() {
  const { activeProject } = useProject();
  const { addNotification, updateNotification } = useNotifications();

  const [phase, setPhase] = useState<'draft' | 'running'>('draft');
  const [pir, setPir] = useState('');
  const [running, setRunning] = useState(true);
  const [replanning, setReplanning] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const onStart = async () => {
    const q = pir.trim();
    if (!q) return;
    setSubmitting(true);
    const toastId = addNotification({
      type: 'processing',
      title: 'Starting agent run',
      message: 'Resolving sources and queuing acquisition…',
    });
    try {
      if (activeProject) {
        const planRes = await collectionPlansApi.fromPir({ project_id: activeProject.id, pir: q });
        const created = (planRes.data || {}) as { id?: string };
        if (created.id) await collectionPlansApi.execute(created.id);
      }
      setPhase('running');
      updateNotification(toastId, {
        type: 'success',
        title: 'Agent run started',
        message: 'Watch the trace below for live activity.',
      });
    } catch (e) {
      // Real API may be unavailable on mobile demo — fall through to the trace anyway.
      setPhase('running');
      updateNotification(toastId, {
        type: 'info',
        title: 'Demo trace started',
        message: (e as Error).message || 'Backend offline — showing simulated trace.',
      });
    } finally {
      setSubmitting(false);
    }
  };

  const onNewPlan = () => {
    setPhase('draft');
    setPir('');
    setRunning(true);
  };

  const onReplan = () => {
    setReplanning(true);
    const id = addNotification({
      title: 'Replanning agent',
      message: 'Re-decomposing the PIR and re-selecting sources…',
      type: 'processing',
    });
    setTimeout(() => {
      setReplanning(false);
      updateNotification(id, {
        title: 'Plan updated',
        message: '8-step trace refreshed · 2 new sources added',
        type: 'success',
      });
    }, 1400);
  };

  if (phase === 'draft') {
    return <MAcquireDraft
      pir={pir}
      setPir={setPir}
      submitting={submitting}
      onStart={onStart}
      hasProject={Boolean(activeProject)}
    />;
  }

  const steps: { n: string; s: 'done' | 'running' | 'pending'; r?: string; sub?: string }[] = [
    { n: 'Decompose PIR',           s: 'done' },
    { n: 'Select sources',          s: 'done' },
    { n: 'Query MarineCadastre',    s: 'done',    r: '14 anomalous vessels' },
    { n: 'Resolve vessel owners',   s: 'done',    r: '11/14 · 3 shell cos' },
    { n: 'Cross-check OFAC SDN',    s: 'done',    r: '2 direct matches' },
    { n: 'Extract entities & rels', s: 'running', sub: '4 / 7 documents' },
    { n: 'Synthesize subgraph',     s: 'pending' },
    { n: 'Flag review queue',       s: 'pending' },
  ];

  return (
    <div style={{ padding: '8px 16px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <MLabel>PRIMARY INTELLIGENCE REQUIREMENT</MLabel>
        <button
          onClick={onNewPlan}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            background: 'none', border: 'none', cursor: 'pointer',
            fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.08em',
            color: 'var(--fg-2)',
          }}
        >
          <Icon name="plus" size={11} /> NEW PLAN
        </button>
      </div>
      <MCard style={{ marginTop: 4 }}>
        <p style={{ margin: 0, fontFamily: 'var(--serif)', fontStyle: 'italic', fontSize: 14, lineHeight: 1.5, color: 'var(--ink)' }}>
          &ldquo;{pir || 'No PIR captured.'}&rdquo;
        </p>
      </MCard>

      <div style={{ display: 'flex', gap: 8, margin: '12px 0' }}>
        <MBtn
          variant={running ? 'outline' : 'signal'}
          icon={running ? 'pause' : 'play'}
          style={{ flex: 1 }}
          onClick={() => setRunning(!running)}
        >
          {running ? 'Pause agent' : 'Resume'}
        </MBtn>
        <MBtn variant="outline" icon="bolt" style={{ flex: 1 }} onClick={onReplan}>
          {replanning ? 'Replanning…' : 'Replan'}
        </MBtn>
      </div>

      <div
        style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '10px 14px', background: 'var(--paper-2)',
          border: '1px solid var(--line)', borderRadius: 10, marginBottom: 14,
        }}
      >
        <PulseDot color="var(--signal)" />
        <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--signal-ink)', letterSpacing: '0.08em' }}>
          {running ? 'RUNNING' : 'PAUSED'}
        </span>
        <span style={{ flex: 1 }} />
      </div>

      <MLabel>AGENT TRACE</MLabel>
      <div style={{ marginTop: 10, position: 'relative', paddingLeft: 4 }}>
        <div style={{ position: 'absolute', left: 9, top: 8, bottom: 8, width: 1, background: 'var(--line)' }} />
        {steps.map((st, i) => (
          <div key={i} style={{ display: 'flex', gap: 12, padding: '7px 0', position: 'relative' }}>
            <MStepDot status={st.s} />
            <div style={{ flex: 1 }}>
              <div
                style={{
                  fontSize: 13.5,
                  fontWeight: st.s === 'running' ? 600 : 500,
                  color: st.s === 'pending' ? 'var(--fg-4)' : 'var(--ink)',
                }}
              >
                {st.n}
              </div>
              {st.r && <div style={{ fontSize: 11.5, color: 'var(--fg-3)', marginTop: 1 }}>→ {st.r}</div>}
              {st.sub && (
                <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--signal-ink)', marginTop: 2 }}>
                  ▸ {st.sub}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function MAcquireDraft({
  pir, setPir, submitting, onStart, hasProject,
}: {
  pir: string;
  setPir: (s: string) => void;
  submitting: boolean;
  onStart: () => void;
  hasProject: boolean;
}) {
  return (
    <div style={{ padding: '8px 16px 24px' }}>
      <MLabel>NEW COLLECTION PLAN</MLabel>
      <h1
        style={{
          margin: '6px 0 4px', fontFamily: 'var(--serif)',
          fontSize: 26, fontWeight: 500, color: 'var(--ink)', lineHeight: 1.1,
          letterSpacing: '-0.01em',
        }}
      >
        What do you need to know<span style={{ color: 'var(--signal)' }}>?</span>
      </h1>
      <p style={{ margin: '0 0 14px', fontFamily: 'var(--serif)', fontSize: 13.5, color: 'var(--fg-2)', lineHeight: 1.45 }}>
        State the primary intelligence requirement (PIR). The agent will decompose it, select sources, and start collecting.
      </p>

      <div style={{ marginBottom: 10 }}>
        <MLabel>PRIMARY INTELLIGENCE REQUIREMENT</MLabel>
      </div>
      <textarea
        value={pir}
        onChange={(e) => setPir(e.target.value)}
        placeholder="What entities, events, or relationships do you need to surface? Be specific about scope and timeframe."
        rows={6}
        style={{
          width: '100%', padding: '14px 14px',
          background: 'var(--paper-2)', border: '1px solid var(--line)',
          borderRadius: 10, color: 'var(--ink)',
          fontFamily: 'var(--serif)', fontSize: 15, lineHeight: 1.5,
          resize: 'vertical', minHeight: 140,
          outline: 'none', boxSizing: 'border-box',
        }}
      />

      <div style={{ display: 'flex', gap: 8, marginTop: 10, marginBottom: 14 }}>
        <span style={{ flex: 1 }} />
        <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-3)', alignSelf: 'center' }}>
          {pir.trim().length} chars
        </span>
      </div>

      <MBtn
        variant="signal"
        icon="bolt"
        style={{ width: '100%', justifyContent: 'center', padding: '14px 16px', fontSize: 15 }}
        onClick={onStart}
      >
        {submitting ? 'Starting agent…' : 'Plan & start agent'}
      </MBtn>

      {!hasProject && (
        <p style={{ margin: '12px 0 0', fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-3)', textAlign: 'center', letterSpacing: '0.06em' }}>
          NO ACTIVE PROJECT · WILL RUN AS SIMULATED TRACE
        </p>
      )}
    </div>
  );
}

function MStepDot({ status }: { status: 'done' | 'running' | 'pending' }) {
  if (status === 'done') {
    return (
      <span
        style={{
          zIndex: 1, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 18, height: 18, borderRadius: '50%',
          background: 'var(--ink)', color: 'var(--paper)', flexShrink: 0,
        }}
      >
        <Icon name="check" size={11} stroke={3} />
      </span>
    );
  }
  if (status === 'running') {
    return (
      <span
        style={{
          zIndex: 1, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 18, height: 18, borderRadius: '50%',
          background: 'var(--paper)', border: '2px solid var(--signal)', flexShrink: 0,
        }}
      >
        <span
          style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--signal)', animation: 'pulse-dot 1s infinite' }}
        />
      </span>
    );
  }
  return (
    <span
      style={{
        zIndex: 1, display: 'inline-block', width: 18, height: 18, borderRadius: '50%',
        background: 'var(--paper)', border: '2px solid var(--line)', flexShrink: 0,
      }}
    />
  );
}

// ============================================================================
// MAsk — graph-RAG answer with citations
// ============================================================================

interface RagSource { id?: string; title?: string; name?: string; excerpt?: string; reliability?: string }
interface RagEntity { id?: string; name?: string; entity_type?: string }
interface RagResult {
  answer?: string;
  response?: string;
  sources?: RagSource[];
  documents?: RagSource[];
  entities?: RagEntity[];
}

export function MAsk() {
  const router = useRouter();
  const { activeProject } = useProject();
  const { addNotification, updateNotification } = useNotifications();
  const [saved, setSaved] = useState(false);
  const [asking, setAsking] = useState(false);
  const [query, setQuery] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [result, setResult] = useState<RagResult | null>(null);
  const [errMsg, setErrMsg] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState<number | null>(null);

  const onAsk = async () => {
    const q = query.trim();
    if (!q || !activeProject) return;
    setAsking(true);
    setErrMsg(null);
    setResult(null);
    setSubmittedQuery(q);
    const start = Date.now();
    const id = addNotification({
      title: 'Asking knowledge graph',
      message: 'Walking the subgraph and gathering evidence…',
      type: 'processing',
    });
    try {
      const res = await queryApi.rag(activeProject.id, q);
      const data = (res.data || {}) as RagResult;
      setResult(data);
      setElapsed((Date.now() - start) / 1000);
      updateNotification(id, {
        title: 'Answer ready',
        message: `Grounded in ${data.sources?.length ?? data.documents?.length ?? 0} source${(data.sources?.length ?? data.documents?.length ?? 0) === 1 ? '' : 's'}.`,
        type: 'success',
      });
    } catch (e) {
      const msg = (e as Error).message || 'Query failed';
      setErrMsg(msg);
      updateNotification(id, { title: 'Ask failed', message: msg, type: 'error' });
    } finally {
      setAsking(false);
    }
  };

  const onAdd = () => {
    addNotification({
      title: 'Added to product draft',
      message: 'Open the Products tab to keep editing.',
      type: 'success',
      link: '/products',
    });
    router.push('/products');
  };
  const onSave = () => {
    setSaved((v) => !v);
    addNotification({
      title: saved ? 'Removed from saved' : 'Saved to Pinboard',
      message: saved ? 'Answer unpinned.' : 'You can find this under Pinboard.',
      type: 'success',
    });
  };

  const answerText = result?.answer || result?.response || '';
  const cites: RagSource[] = result?.sources ?? result?.documents ?? [];
  const entities: RagEntity[] = result?.entities ?? [];

  return (
    <div style={{ padding: '8px 16px 24px' }}>
      {/* Ask box */}
      <div style={{ background: 'var(--paper-2)', border: '1px solid var(--line)', borderRadius: 10, padding: 12, marginBottom: 14 }}>
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onAsk(); } }}
          placeholder={activeProject ? `Ask anything about ${activeProject.name}…` : 'No active project'}
          rows={3}
          style={{
            width: '100%', padding: 0, border: 'none', resize: 'vertical',
            background: 'transparent', outline: 'none',
            fontFamily: 'var(--serif)', fontSize: 15, lineHeight: 1.4, color: 'var(--ink)',
            boxSizing: 'border-box',
          }}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 10 }}>
          <Tag tone="cite">GRAPH-RAG</Tag>
          {activeProject && (
            <Tag>{formatStat(activeProject.entity_count ?? 0).toUpperCase()} ENTITIES</Tag>
          )}
          <span style={{ flex: 1 }} />
          <button
            onClick={onAsk}
            disabled={asking || !query.trim() || !activeProject}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              padding: '5px 10px', borderRadius: 6,
              background: 'var(--ink)', color: 'var(--paper)',
              fontSize: 12, fontWeight: 600, border: 'none', cursor: 'pointer',
              opacity: (asking || !query.trim() || !activeProject) ? 0.6 : 1,
            }}
          >
            {asking ? 'Asking…' : 'Ask'} <Icon name="arrow-right" size={12} />
          </button>
        </div>
      </div>

      {!result && !errMsg && !asking && (
        <p style={{ margin: '24px 0 0', fontFamily: 'var(--serif)', fontSize: 14, color: 'var(--fg-3)', fontStyle: 'italic', textAlign: 'center' }}>
          Ask a question to get a grounded answer with citations.
        </p>
      )}

      {errMsg && (
        <div style={{ padding: '10px 12px', background: 'var(--paper-2)', border: '1px solid var(--warn)', borderRadius: 8, color: 'var(--warn)', fontSize: 12 }}>
          {errMsg}
        </div>
      )}

      {result && (
        <>
          {/* Answer */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <Tag tone="signal">ANSWER</Tag>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-3)' }}>
              {elapsed ? `${elapsed.toFixed(1)}s · ` : ''}{submittedQuery && `“${submittedQuery.slice(0, 40)}${submittedQuery.length > 40 ? '…' : ''}”`}
            </span>
          </div>
          <p style={{ margin: '0 0 16px', fontFamily: 'var(--serif)', fontSize: 15, lineHeight: 1.65, color: 'var(--ink)', whiteSpace: 'pre-wrap' }}>
            {answerText || <em style={{ color: 'var(--fg-3)' }}>No answer text returned.</em>}
          </p>

          {entities.length > 0 && (
            <>
              <MLabel>ENTITIES · {entities.length}</MLabel>
              <div style={{ marginTop: 8, marginBottom: 14, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {entities.slice(0, 12).map((e, i) => {
                  const meta = e.entity_type ? ENTITY_META[e.entity_type.toUpperCase()] : null;
                  return (
                    <button
                      key={e.id || i}
                      onClick={() => router.push('/network')}
                      style={{
                        padding: '4px 8px', borderRadius: 3, border: 'none', cursor: 'pointer',
                        background: 'var(--signal-soft)', color: 'var(--ink)',
                        borderBottom: `2px solid ${meta ? meta.tint : 'var(--signal)'}`,
                        fontSize: 12, fontWeight: 600,
                      }}
                    >
                      {e.name || e.id}
                    </button>
                  );
                })}
              </div>
            </>
          )}

          {cites.length > 0 && (
            <>
              <MLabel>EVIDENCE · {cites.length} EXCERPT{cites.length === 1 ? '' : 'S'}</MLabel>
              <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
                {cites.slice(0, 6).map((c, i) => {
                  const title = c.title || c.name || `Source ${i + 1}`;
                  const rel = (c.reliability || '').charAt(0).toUpperCase();
                  const isA = rel === 'A';
                  return (
                    <div
                      key={c.id || i}
                      style={{
                        padding: '10px 12px', background: 'var(--paper-2)',
                        border: '1px solid var(--line)', borderRadius: 8,
                        borderLeft: '2px solid var(--cite)',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                        <span style={{ fontFamily: 'var(--mono)', fontSize: 9.5, color: 'var(--cite)', fontWeight: 600 }}>[{i + 1}]</span>
                        <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--ink)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{title}</span>
                        {rel && (
                          <span
                            style={{
                              width: 16, height: 16, borderRadius: 2,
                              border: `1px solid ${isA ? 'var(--live)' : 'var(--signal-ink)'}`,
                              color: isA ? 'var(--live)' : 'var(--signal-ink)',
                              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                              fontFamily: 'var(--mono)', fontSize: 9, fontWeight: 600,
                            }}
                          >
                            {rel}
                          </span>
                        )}
                      </div>
                      {c.excerpt && (
                        <p style={{ margin: 0, fontFamily: 'var(--serif)', fontStyle: 'italic', fontSize: 12, color: 'var(--fg-2)', lineHeight: 1.5 }}>
                          {c.excerpt.length > 220 ? c.excerpt.slice(0, 218) + '…' : c.excerpt}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}

          <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
            <MBtn variant="outline" icon="product" style={{ flex: 1 }} onClick={onAdd}>Add to product</MBtn>
            <MBtn
              variant={saved ? 'signal' : 'outline'}
              icon="star"
              onClick={onSave}
            >
              {saved ? 'Saved' : 'Save'}
            </MBtn>
          </div>
        </>
      )}
    </div>
  );
}

// ============================================================================
// MProducts — INTSUM draft with chip citations
// ============================================================================

export function MProducts() {
  const router = useRouter();
  const { activeProject } = useProject();
  const { addNotification, updateNotification } = useNotifications();
  const [status, setStatus] = useState<'draft' | 'regenerating' | 'published'>('draft');
  const [reports, setReports] = useState<MobileReport[]>([]);
  const [persona, setPersona] = useState<MobilePersona | null>(null);

  useEffect(() => {
    if (!activeProject) { setReports([]); return; }
    reportsApi
      .list(activeProject.id)
      .then((r) => {
        const raw = r.data;
        const list = Array.isArray(raw) ? raw : (raw as { reports?: MobileReport[] })?.reports ?? [];
        setReports((Array.isArray(list) ? list : []) as MobileReport[]);
      })
      .catch(() => setReports([]));
  }, [activeProject]);

  useEffect(() => {
    personasApi
      .active()
      .then((r) => setPersona(r.data as MobilePersona))
      .catch(() => setPersona(null));
  }, []);
  const onRegenerate = () => {
    setStatus('regenerating');
    const id = addNotification({
      title: 'Regenerating INTSUM',
      message: 'All-source Analyst is redrafting BLUF and Key Judgments…',
      type: 'processing',
    });
    setTimeout(() => {
      setStatus('draft');
      updateNotification(id, {
        title: 'Draft v4 ready',
        message: 'BLUF tightened · 1 new judgment from BoreaBank subgraph',
        type: 'success',
      });
    }, 1600);
  };
  const onPublish = () => {
    setStatus('published');
    addNotification({
      title: 'INTSUM published',
      message: 'ARCTIC-2026-0412-01 released to All-source Analyst feed',
      type: 'success',
      link: '/products',
    });
  };
  return (
    <div style={{ padding: '8px 16px 24px' }}>
      <button
        onClick={() =>
          addNotification({
            type: 'info',
            title: 'Persona picker',
            message: 'Manage analyst personas under Admin → Personas.',
          })
        }
        style={{
          display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12, width: '100%',
          background: 'transparent', border: 'none', padding: 0, cursor: 'pointer',
        }}
      >
        <Icon name="sparkle" size={14} />
        <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-3)', letterSpacing: '0.08em' }}>
          DRAFTING WITH
        </span>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)' }}>{persona?.name || 'No persona'}</span>
        <span style={{ flex: 1 }} />
        <Icon name="chevron-down" size={14} />
      </button>

      {/* Document */}
      {(() => {
        const latest = reports[0];
        if (!latest) {
          return (
            <div style={{ background: 'var(--paper)', border: '1px dashed var(--line)', borderRadius: 10, padding: '32px 18px', textAlign: 'center' }}>
              <Icon name="product" size={22} />
              <h3 style={{ margin: '12px 0 4px', fontFamily: 'var(--serif)', fontSize: 18, fontWeight: 500, color: 'var(--ink)' }}>
                No drafts yet
              </h3>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--fg-3)' }}>
                {activeProject ? 'Generate a report from the desktop Products view, then it will appear here.' : 'Switch to an active project to draft a product.'}
              </p>
            </div>
          );
        }
        const cls = activeProject?.classification_level || 'U';
        const body = (latest.content || '').trim();
        const ts = latest.created_at ? new Date(latest.created_at) : null;
        const idLabel = `${(latest.report_type || 'REPORT').toUpperCase()}-${(latest.id || '').slice(0, 8)}`;
        return (
          <div style={{ background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 10, padding: '16px 16px 18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ fontFamily: 'var(--mono)', fontSize: 9, letterSpacing: '0.18em', color: 'var(--signal-ink)', fontWeight: 600 }}>
                {`${cls} // FOR OFFICIAL USE ONLY`}
              </div>
              <span style={{ flex: 1 }} />
              {status === 'published' && <Tag tone="live">PUBLISHED</Tag>}
              {status === 'regenerating' && <Tag tone="signal">REGENERATING</Tag>}
              {status === 'draft' && latest.status && <Tag>{latest.status.toUpperCase()}</Tag>}
            </div>
            <h1
              style={{
                margin: '8px 0 0', fontFamily: 'var(--serif)',
                fontSize: 22, fontWeight: 600, letterSpacing: '-0.01em',
                color: 'var(--ink)', lineHeight: 1.15,
              }}
            >
              {(latest.report_type || 'Report').toUpperCase()}: <span style={{ fontWeight: 400, fontStyle: 'italic' }}>{latest.title || 'Untitled'}</span>
            </h1>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 9.5, color: 'var(--fg-2)', marginTop: 8 }}>
              {idLabel}{ts ? ` · ${ts.toLocaleDateString()}` : ''}{persona?.name ? ` · ${persona.name}` : ''}
            </div>

            <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--line-soft)' }}>
              <p style={{ margin: 0, fontFamily: 'var(--serif)', fontSize: 14.5, lineHeight: 1.55, color: 'var(--ink)', whiteSpace: 'pre-wrap' }}>
                {body || <em style={{ color: 'var(--fg-3)' }}>No body content.</em>}
              </p>
            </div>

            {reports.length > 1 && (
              <button
                onClick={() => router.push('/products')}
                style={{
                  marginTop: 12, width: '100%', padding: '8px 10px',
                  background: 'transparent', border: '1px solid var(--line)',
                  borderRadius: 6, fontFamily: 'var(--mono)', fontSize: 10,
                  letterSpacing: '0.08em', color: 'var(--fg-2)', cursor: 'pointer',
                }}
              >
                +{reports.length - 1} MORE REPORT{reports.length - 1 === 1 ? '' : 'S'} ON DESKTOP →
              </button>
            )}
          </div>
        );
      })()}

      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <MBtn
          variant="outline"
          icon="bolt"
          style={{ flex: 1, opacity: status === 'regenerating' ? 0.6 : 1 }}
          onClick={onRegenerate}
        >
          {status === 'regenerating' ? 'Regenerating…' : 'Regenerate'}
        </MBtn>
        <MBtn
          variant={status === 'published' ? 'signal' : 'solid'}
          icon={status === 'published' ? 'check' : 'check'}
          style={{ flex: 1 }}
          onClick={onPublish}
        >
          {status === 'published' ? 'Published' : 'Publish'}
        </MBtn>
      </div>
    </div>
  );
}

// ============================================================================
// MReview — pending until backend review endpoint exists
// ============================================================================

export function MReview() {
  const { activeProject } = useProject();
  return (
    <div style={{ padding: '8px 16px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <Tag tone="signal">PENDING BACKEND</Tag>
      </div>
      <MLabel>ANALYST REVIEW</MLabel>
      <h1
        style={{
          margin: '4px 0 14px', fontFamily: 'var(--serif)',
          fontSize: 26, fontWeight: 500, color: 'var(--ink)', lineHeight: 1.1,
        }}
      >
        Second pair of eyes<span style={{ color: 'var(--signal)' }}>.</span>
      </h1>
      <MCard style={{ borderStyle: 'dashed' }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
          <span
            style={{
              width: 36, height: 36, borderRadius: 4,
              background: 'var(--paper)', border: '1px solid var(--line)',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              color: 'var(--fg-2)', flexShrink: 0,
            }}
          >
            <Icon name="check" size={18} />
          </span>
          <div>
            <h3 style={{ margin: '0 0 6px', fontFamily: 'var(--serif)', fontSize: 16, fontWeight: 500, color: 'var(--ink)' }}>
              Review queue endpoint pending
            </h3>
            <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.5, color: 'var(--fg-2)' }}>
              {activeProject
                ? `Once the backend exposes a review API, flagged claims from "${activeProject.name}" (single-source, inferred, auto-tagged) will appear here for Approve / Reject.`
                : 'Open a project to load its review queue here once the backend review endpoint is wired.'}
            </p>
          </div>
        </div>
      </MCard>
    </div>
  );
}

// ============================================================================
// MobileSwap — render desktop view by default, mobile view at narrow widths
// ============================================================================

export function MobileSwap({ desktop, mobile }: { desktop: React.ReactNode; mobile: React.ReactNode }) {
  return (
    <>
      <div className="sentinel-desktop-only" style={{ height: '100%' }}>{desktop}</div>
      <div className="sentinel-mobile-only" style={{ minHeight: '100%' }}>{mobile}</div>
    </>
  );
}
