'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useProject } from '@/lib/ProjectContext';
import { projectsApi, watchlistApi, reportsApi, type Project } from '@/lib/api';
import {
  Btn,
  Tag,
  ConfidenceTimeline,
  ENTITY_META,
  Icon,
  PulseDot,
} from '@/components/sentinel';
import {
  CONFIDENCE_TIMELINE_PROJECT,
  ANOMALY_DIGEST,
} from '@/components/sentinel/mockData';

interface ActivityEvent {
  id?: string;
  action?: string;
  entity_name?: string;
  entity_type?: string;
  timestamp?: string;
}
interface Report {
  id: string;
  title?: string;
  content?: string;
  report_type?: string;
  status?: string;
  entity_ids?: string[];
  created_at?: string;
}

// Map a backend activity event to the icon-kind taxonomy the UI already uses.
function activityKind(action?: string): string {
  const a = (action || '').toLowerCase();
  if (a.includes('extract')) return 'extract';
  if (a.includes('acqui') || a.includes('ingest') || a.includes('collect')) return 'acquire';
  if (a.includes('assess') || a.includes('judg')) return 'assess';
  if (a.includes('report') || a.includes('intsum') || a.includes('product') || a.includes('publish')) return 'product';
  return 'graph';
}
function activityClock(ts?: string): string {
  if (!ts) return '';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false });
}

// ============================================================================
// Page wrapper
// ============================================================================

export function HubView() {
  const router = useRouter();
  const { activeProject, setActiveProject } = useProject();
  const [projects, setProjects] = useState<Project[]>([]);
  const [watched, setWatched] = useState<Array<{ id: string; name: string; entity_type?: string; type?: string; confidence?: number; flag?: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [reports, setReports] = useState<Report[]>([]);
  const [activity, setActivity] = useState<ActivityEvent[]>([]);

  useEffect(() => {
    if (typeof window !== 'undefined' && !localStorage.getItem('auth_token')) {
      router.push('/login');
      return;
    }
    projectsApi
      .list()
      .then((res) => {
        const raw = res.data;
        const list = Array.isArray(raw)
          ? raw
          : (raw as { projects?: Project[] })?.projects ?? [];
        setProjects((Array.isArray(list) ? list : []) as Project[]);
      })
      .catch(() => setProjects([]))
      .finally(() => setLoading(false));
  }, [router]);

  useEffect(() => {
    if (!activeProject) {
      setWatched([]);
      setReports([]);
      setActivity([]);
      return;
    }
    watchlistApi
      .list(activeProject.id)
      .then((res) => {
        const raw = res.data as
          | { watched_entities?: unknown[]; items?: unknown[] }
          | unknown[]
          | undefined;
        const items = Array.isArray(raw)
          ? raw
          : raw?.watched_entities ?? raw?.items ?? [];
        setWatched(Array.isArray(items) ? (items as typeof watched) : []);
      })
      .catch(() => setWatched([]));

    reportsApi
      .list(activeProject.id)
      .then((res) => {
        const raw = res.data;
        const list = Array.isArray(raw)
          ? raw
          : (raw as { reports?: Report[] })?.reports ?? [];
        setReports((Array.isArray(list) ? list : []) as Report[]);
      })
      .catch(() => setReports([]));

    projectsApi
      .activity(activeProject.id, 20)
      .then((res) => {
        const raw = res.data as { activity?: ActivityEvent[] } | ActivityEvent[] | undefined;
        const list = Array.isArray(raw) ? raw : raw?.activity ?? [];
        setActivity((Array.isArray(list) ? list : []) as ActivityEvent[]);
      })
      .catch(() => setActivity([]));
  }, [activeProject]);

  const navigate = (view: string) => router.push(view);

  return (
    <div style={{ height: '100%', overflow: 'auto', background: 'var(--paper)' }}>
      <div style={{ maxWidth: 1320, margin: '0 auto', padding: '28px 32px 48px' }}>
        {activeProject ? (
          <>
            <Masthead project={activeProject} />
            <div style={{ marginTop: 22 }}>
              <ConfidenceTimeline
                points={CONFIDENCE_TIMELINE_PROJECT.points}
                start={CONFIDENCE_TIMELINE_PROJECT.start}
                end={CONFIDENCE_TIMELINE_PROJECT.end}
                size="full"
                title="Project confidence · trajectory"
              />
            </div>

            <AnomalyDigest onNavigate={navigate} />

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1.1fr 1.1fr 1.1fr',
                gap: 20,
                marginTop: 28,
              }}
            >
              <PillarCard
                kind="ACQUIRE"
                title="Agentic acquisition"
                line="Sources, plans, and live runs"
                metric={String(activeProject.collection_count ?? 0)}
                metricLabel="active collections"
                tint="var(--cite)"
                onClick={() => navigate('/collections')}
              />
              <PillarCard
                kind="UNDERSTAND"
                title="Graph RAG"
                line={`${(activeProject.entity_count ?? 0).toLocaleString()} entities · ${(activeProject.relationship_count ?? 0).toLocaleString()} relationships`}
                metric={String((activeProject.relationship_count ?? 0).toLocaleString())}
                metricLabel="relationships"
                tint="var(--violet)"
                onClick={() => navigate('/network')}
              />
              <PillarCard
                kind="DELIVER"
                title="Tailored products"
                line="INTSUMs, briefs, assessments"
                metric={String(reports.length)}
                metricLabel="reports"
                tint="var(--signal-ink)"
                onClick={() => navigate('/products')}
              />
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1.4fr 1fr',
                gap: 20,
                marginTop: 28,
              }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                <PIRPanel project={activeProject} onNavigate={navigate} />
                <FindingsPanel reports={reports} onNavigate={navigate} />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                <LiveAgentPanel onNavigate={navigate} />
                <ActivityPanel activity={activity} />
              </div>
            </div>

            <WatchlistStrip watched={watched} onNavigate={navigate} />
          </>
        ) : (
          <NoProjectMasthead />
        )}

        <OtherProjects
          projects={projects}
          loading={loading}
          activeId={activeProject?.id}
          onSelect={(p) => setActiveProject(p)}
          onCreate={() => router.push('/projects/new')}
        />
      </div>
    </div>
  );
}

// ============================================================================
// Sections
// ============================================================================

function Masthead({ project }: { project: Project }) {
  return (
    <div style={{ position: 'relative', paddingBottom: 22, borderBottom: '1px solid var(--line)' }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 32 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.2em', color: 'var(--fg-3)' }}>
              PROJECT BRIEF{project.created_at ? ` · OPENED ${project.created_at.slice(0, 10)}` : ''}
            </span>
            <Tag tone="signal">{project.classification_level}</Tag>
            <Tag tone="live">● {project.status?.toUpperCase() || 'ACTIVE'}</Tag>
            {project.priority && <Tag>PRIORITY · {project.priority.toUpperCase()}</Tag>}
          </div>
          <h1
            style={{
              margin: 0,
              fontFamily: 'var(--serif)',
              fontWeight: 500,
              fontSize: 52,
              letterSpacing: '-0.02em',
              lineHeight: 1,
              color: 'var(--ink)',
            }}
          >
            {project.name}
            <span style={{ color: 'var(--signal)' }}>.</span>
          </h1>
          {project.description && (
            <p
              style={{
                margin: '14px 0 0',
                maxWidth: 720,
                fontFamily: 'var(--serif)',
                fontSize: 17,
                lineHeight: 1.5,
                color: 'var(--fg-2)',
              }}
            >
              {project.description}
            </p>
          )}
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(2, auto)',
            gap: '12px 32px',
            alignItems: 'baseline',
            paddingLeft: 24,
            borderLeft: '1px solid var(--line)',
          }}
        >
          <Stat value={(project.entity_count ?? 0).toLocaleString()} label="entities" />
          <Stat value={(project.relationship_count ?? 0).toLocaleString()} label="relationships" />
          <Stat value={(project.document_count ?? 0).toString()} label="documents" />
          <Stat value={(project.collection_count ?? 0).toString()} label="collections" />
        </div>
      </div>
    </div>
  );
}

function NoProjectMasthead() {
  return (
    <div style={{ paddingBottom: 22, borderBottom: '1px solid var(--line)' }}>
      <span style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.2em', color: 'var(--fg-3)' }}>
        SENTINEL · NO ACTIVE PROJECT
      </span>
      <h1
        style={{
          margin: '8px 0 0',
          fontFamily: 'var(--serif)',
          fontWeight: 500,
          fontSize: 52,
          letterSpacing: '-0.02em',
          lineHeight: 1,
          color: 'var(--ink)',
        }}
      >
        Select a project<span style={{ color: 'var(--signal)' }}>.</span>
      </h1>
      <p
        style={{
          margin: '14px 0 0',
          maxWidth: 720,
          fontFamily: 'var(--serif)',
          fontSize: 17,
          lineHeight: 1.5,
          color: 'var(--fg-2)',
        }}
      >
        Pick a project below to open its workspace, or create a new one to start collecting and analyzing intelligence.
      </p>
    </div>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <div style={{ fontFamily: 'var(--mono)', fontWeight: 500, fontSize: 26, color: 'var(--ink)', letterSpacing: '-0.02em' }}>{value}</div>
      <div style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.18em', color: 'var(--fg-3)', marginTop: 2 }}>
        {label.toUpperCase()}
      </div>
    </div>
  );
}

function PillarCard({
  kind,
  title,
  line,
  metric,
  metricLabel,
  tint,
  onClick,
}: {
  kind: string;
  title: string;
  line: string;
  metric: string;
  metricLabel: string;
  tint: string;
  onClick: () => void;
}) {
  const [h, setH] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      style={{
        position: 'relative',
        textAlign: 'left',
        padding: '20px 22px',
        background: 'var(--paper-2)',
        border: '1px solid var(--line)',
        borderRadius: 4,
        cursor: 'pointer',
        transition: 'all 0.18s',
        overflow: 'hidden',
        transform: h ? 'translateY(-2px)' : 'translateY(0)',
        boxShadow: h ? '0 8px 20px rgba(15,18,22,0.06)' : 'none',
      }}
    >
      <div style={{ position: 'absolute', top: 0, left: 0, width: 3, height: '100%', background: tint }} />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.2em', color: tint, fontWeight: 600 }}>{kind}</span>
        <Icon name="arrow-up-right" size={14} />
      </div>
      <h3 style={{ margin: 0, fontFamily: 'var(--serif)', fontSize: 22, fontWeight: 500, color: 'var(--ink)', letterSpacing: '-0.01em' }}>{title}</h3>
      <p style={{ margin: '4px 0 18px', fontSize: 12.5, color: 'var(--fg-3)' }}>{line}</p>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 32, fontWeight: 500, color: 'var(--ink)', letterSpacing: '-0.02em' }}>{metric}</span>
        <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>{metricLabel}</span>
      </div>
    </button>
  );
}

function PIRPanel({ project, onNavigate }: { project: Project; onNavigate: (v: string) => void }) {
  const pirText = project.description?.trim();
  return (
    <Panel
      label="PRIMARY INTELLIGENCE REQUIREMENT"
      title="What we're trying to answer"
      action={
        <Btn icon="bolt" variant="outline" size="sm" onClick={() => onNavigate('/collections')}>
          {pirText ? 'Run agent' : 'Define PIR'}
        </Btn>
      }
    >
      {pirText ? (
        <p
          style={{
            margin: '6px 0 16px',
            fontFamily: 'var(--serif)',
            fontStyle: 'italic',
            fontSize: 19,
            lineHeight: 1.45,
            color: 'var(--ink)',
          }}
        >
          &ldquo;{pirText}&rdquo;
        </p>
      ) : (
        <p
          style={{
            margin: '6px 0 16px',
            fontFamily: 'var(--serif)',
            fontSize: 15,
            lineHeight: 1.5,
            color: 'var(--fg-3)',
            fontStyle: 'italic',
          }}
        >
          No PIR captured yet — start a collection plan to define one.
        </p>
      )}
    </Panel>
  );
}

function FindingsPanel({ reports, onNavigate }: { reports: Report[]; onNavigate: (v: string) => void }) {
  const findings = reports
    .filter((r) => {
      const t = (r.report_type || '').toLowerCase();
      const s = (r.status || '').toLowerCase();
      return t === 'finding' || t === 'assessment' || (t === '' && s === 'draft');
    })
    .slice(0, 4);

  return (
    <Panel
      label="WORKING FINDINGS · AUTO-DRAFTED"
      title="What the graph says so far"
      action={
        <Btn icon="product" variant="outline" size="sm" onClick={() => onNavigate('/products')}>
          Draft INTSUM
        </Btn>
      }
    >
      {findings.length === 0 ? (
        <p style={{ margin: '6px 0 14px', fontFamily: 'var(--serif)', fontSize: 14.5, lineHeight: 1.5, color: 'var(--fg-3)', fontStyle: 'italic' }}>
          Awaiting first auto-drafted findings from the Graph RAG layer.
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
          {findings.map((f, i) => {
            const status = (f.status || 'draft').toLowerCase();
            const evidence = f.entity_ids?.length ?? 0;
            const preview = (f.content || f.title || '').trim();
            const text = preview.length > 220 ? preview.slice(0, 218) + '…' : preview || f.title || 'Untitled finding';
            return (
              <div
                key={f.id}
                style={{
                  display: 'flex',
                  gap: 14,
                  padding: '14px 0',
                  borderTop: i === 0 ? 'none' : '1px solid var(--line-soft)',
                }}
              >
                <div style={{ flexShrink: 0, paddingTop: 6, width: 32, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
                  <span
                    style={{
                      width: 10, height: 10, borderRadius: '50%',
                      background: status === 'final' ? 'var(--live)' : status === 'review' ? 'var(--signal)' : 'var(--fg-4)',
                    }}
                  />
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 8.5, letterSpacing: '0.1em', color: 'var(--fg-3)', textTransform: 'uppercase' }}>{status}</span>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ margin: 0, fontFamily: 'var(--serif)', fontSize: 14.5, lineHeight: 1.5, color: 'var(--ink)' }}>{text}</p>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
                    <Tag>{(f.report_type || 'DRAFT').toUpperCase()}</Tag>
                    <span style={{ flex: 1 }} />
                    <button
                      onClick={() => onNavigate('/products')}
                      style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-3)', display: 'flex', alignItems: 'center', gap: 4, letterSpacing: '0.08em', background: 'none', border: 'none', cursor: 'pointer' }}
                    >
                      <Icon name="link" size={11} /> {evidence} EVIDENCE →
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Panel>
  );
}

function LiveAgentPanel({ onNavigate }: { onNavigate: (v: string) => void }) {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setTick((x) => x + 1), 1200);
    return () => clearInterval(t);
  }, []);

  const steps: { name: string; status: 'done' | 'running' | 'pending'; sub?: string }[] = [
    { name: 'Decompose PIR',           status: 'done' },
    { name: 'Select sources',          status: 'done' },
    { name: 'Query data sources',      status: 'done' },
    { name: 'Resolve entities',        status: 'done' },
    { name: 'Cross-check watchlist',   status: 'done' },
    { name: 'Extract entities & rels', status: 'running', sub: 'in progress' },
    { name: 'Synthesize subgraph',     status: 'pending' },
    { name: 'Flag review queue',       status: 'pending' },
  ];

  return (
    <Panel
      label="LIVE AGENT · ACQUISITION"
      title={
        <span>
          Agent run{' '}
          <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--fg-3)', fontWeight: 400 }}>
            · live
          </span>
        </span>
      }
      action={
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <PulseDot color="var(--signal)" />
          <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--signal-ink)', letterSpacing: '0.12em' }}>
            RUNNING · {String(Math.floor(tick / 2)).padStart(2, '0')}:
            {String((tick * 8) % 60).padStart(2, '0')}
          </span>
        </div>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', position: 'relative' }}>
        <div style={{ position: 'absolute', left: 7, top: 8, bottom: 8, width: 1, background: 'var(--line)' }} />

        {steps.map((s, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '5px 0', position: 'relative' }}>
            <StepDot status={s.status} />
            <div style={{ flex: 1 }}>
              <div
                style={{
                  fontSize: 12.5,
                  color: s.status === 'pending' ? 'var(--fg-4)' : 'var(--ink)',
                  fontWeight: s.status === 'running' ? 600 : 500,
                }}
              >
                {s.name}
              </div>
              {s.sub && (
                <div style={{ fontFamily: 'var(--mono)', fontSize: 10.5, color: 'var(--signal-ink)', marginTop: 2, letterSpacing: '0.04em' }}>
                  <span style={{ animation: 'pulse-dot 1.4s infinite' }}>▸</span> {s.sub}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <button
        onClick={() => onNavigate('/collections')}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 6,
          width: '100%',
          padding: '8px 0',
          marginTop: 12,
          background: 'transparent',
          border: '1px solid var(--line)',
          borderRadius: 3,
          fontSize: 11.5,
          color: 'var(--fg-2)',
          cursor: 'pointer',
        }}
      >
        Open agent trace <Icon name="arrow-right" size={12} />
      </button>
    </Panel>
  );
}

function StepDot({ status }: { status: 'done' | 'running' | 'pending' }) {
  if (status === 'done')
    return (
      <span
        style={{
          position: 'relative',
          zIndex: 1,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 15,
          height: 15,
          borderRadius: '50%',
          background: 'var(--ink)',
          color: 'var(--paper)',
          flexShrink: 0,
        }}
      >
        <Icon name="check" size={9} stroke={2.5} />
      </span>
    );
  if (status === 'running')
    return (
      <span
        style={{
          position: 'relative',
          zIndex: 1,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 15,
          height: 15,
          borderRadius: '50%',
          background: 'var(--paper)',
          border: '1.5px solid var(--signal)',
          flexShrink: 0,
        }}
      >
        <span
          style={{
            width: 5,
            height: 5,
            borderRadius: '50%',
            background: 'var(--signal)',
            animation: 'pulse-dot 1s infinite',
          }}
        />
      </span>
    );
  return (
    <span
      style={{
        position: 'relative',
        zIndex: 1,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 15,
        height: 15,
        borderRadius: '50%',
        background: 'var(--paper)',
        border: '1.5px solid var(--line)',
        flexShrink: 0,
      }}
    />
  );
}

function ActivityPanel({ activity }: { activity: ActivityEvent[] }) {
  if (activity.length === 0) {
    return (
      <Panel label="ACTIVITY" title="Last 24 hours">
        <p style={{ margin: '6px 0 14px', fontFamily: 'var(--serif)', fontSize: 14, color: 'var(--fg-3)', fontStyle: 'italic' }}>
          Nothing in the last 24h.
        </p>
      </Panel>
    );
  }
  return (
    <Panel label="ACTIVITY" title="Last 24 hours">
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {activity.slice(0, 8).map((a, i) => {
          const kind = activityKind(a.action);
          const label = a.entity_name
            ? `${a.action || 'Event'} · ${a.entity_name}`
            : a.action || 'Event';
          return (
            <div
              key={a.id || i}
              style={{
                display: 'flex',
                gap: 12,
                padding: '10px 0',
                borderTop: i === 0 ? 'none' : '1px solid var(--line-soft)',
                alignItems: 'flex-start',
              }}
            >
              <span
                style={{
                  fontFamily: 'var(--mono)',
                  fontSize: 10,
                  color: 'var(--fg-3)',
                  letterSpacing: '0.04em',
                  minWidth: 56,
                  paddingTop: 1,
                }}
              >
                {activityClock(a.timestamp)}
              </span>
              <ActivityIcon kind={kind} />
              <span style={{ flex: 1, fontSize: 12.5, color: 'var(--ink)' }}>{label}</span>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

function ActivityIcon({ kind }: { kind: string }) {
  const map: Record<string, { icon: string; tint: string }> = {
    acquire: { icon: 'acquire', tint: 'var(--cite)' },
    extract: { icon: 'bolt',    tint: 'var(--signal-ink)' },
    assess:  { icon: 'sparkle', tint: 'var(--violet)' },
    graph:   { icon: 'graph',   tint: 'var(--ink)' },
    product: { icon: 'product', tint: 'var(--live)' },
  };
  const m = map[kind] || map.graph;
  return (
    <span
      style={{
        width: 18,
        height: 18,
        borderRadius: 2,
        background: 'var(--paper-2)',
        border: '1px solid var(--line)',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: m.tint,
        flexShrink: 0,
      }}
    >
      <Icon name={m.icon} size={11} />
    </span>
  );
}

interface WatchedEntity {
  id: string;
  name: string;
  entity_type?: string;
  type?: string;
  confidence?: number;
  flag?: string;
}

function WatchlistStrip({
  watched,
  onNavigate,
}: {
  watched: WatchedEntity[];
  onNavigate: (v: string) => void;
}) {
  if (!watched.length) return null;
  return (
    <div style={{ marginTop: 28 }}>
      <SectionTitle
        label="WATCHLIST"
        title="Pinned entities"
        action={
          <button
            onClick={() => onNavigate('/watchlist')}
            style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-2)', letterSpacing: '0.1em', background: 'transparent', border: 'none', cursor: 'pointer' }}
          >
            OPEN WATCHLIST →
          </button>
        }
      />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
        {watched.slice(0, 9).map((e) => (
          <WatchTile key={e.id} entity={e} onClick={() => onNavigate(`/network?entity=${e.id}`)} />
        ))}
      </div>
    </div>
  );
}

function WatchTile({ entity, onClick }: { entity: WatchedEntity; onClick: () => void }) {
  const type = (entity.entity_type || entity.type || 'PERSON').toUpperCase();
  const meta = ENTITY_META[type] || { icon: 'entity', tint: 'var(--fg-3)' };
  const flag = entity.flag || '—';

  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '14px 16px',
        background: 'var(--paper-2)',
        border: '1px solid var(--line)',
        borderRadius: 3,
        cursor: 'pointer',
        textAlign: 'left',
      }}
    >
      <span
        style={{
          width: 32,
          height: 32,
          borderRadius: 3,
          background: meta.tint,
          color: '#fff',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        <Icon name={meta.icon} size={16} />
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: 'var(--ink)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {entity.name}
        </div>
        <div
          style={{
            fontFamily: 'var(--mono)',
            fontSize: 10,
            color: 'var(--fg-3)',
            letterSpacing: '0.06em',
            marginTop: 2,
          }}
        >
          {type} · {flag.toUpperCase()}
        </div>
      </div>
    </button>
  );
}

function OtherProjects({
  projects,
  loading,
  activeId,
  onSelect,
  onCreate,
}: {
  projects: Project[];
  loading: boolean;
  activeId?: string;
  onSelect: (p: Project) => void;
  onCreate: () => void;
}) {
  const others = projects.filter((p) => p.id !== activeId);

  return (
    <div style={{ marginTop: 28 }}>
      <SectionTitle
        label={activeId ? 'OTHER PROJECTS' : 'PROJECTS'}
        title="Across the desk"
        action={
          <Btn icon="plus" variant="outline" size="sm" onClick={onCreate}>
            New project
          </Btn>
        }
      />

      {loading ? (
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
      ) : others.length === 0 ? (
        <div
          style={{
            padding: '32px 20px',
            textAlign: 'center',
            background: 'var(--paper-2)',
            border: '1px solid var(--line)',
            borderRadius: 3,
            color: 'var(--fg-3)',
            fontSize: 12.5,
          }}
        >
          {activeId ? 'No other projects on this desk yet.' : 'No projects yet — create one to get started.'}
        </div>
      ) : (
        <div
          style={{
            background: 'var(--paper-2)',
            border: '1px solid var(--line)',
            borderRadius: 3,
            overflow: 'hidden',
          }}
        >
          {others.map((p, i) => (
            <button
              key={p.id}
              onClick={() => onSelect(p)}
              style={{
                width: '100%',
                display: 'grid',
                gridTemplateColumns: '1.4fr 0.8fr 0.6fr 0.6fr 0.6fr 60px',
                gap: 16,
                padding: '12px 18px',
                alignItems: 'center',
                borderTop: i === 0 ? 'none' : '1px solid var(--line-soft)',
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                textAlign: 'left',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: '50%',
                    background:
                      p.priority === 'critical'
                        ? 'var(--warn)'
                        : p.priority === 'high'
                        ? 'var(--signal)'
                        : 'var(--fg-4)',
                  }}
                />
                <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--ink)' }}>{p.name}</span>
                <Tag>{p.classification_level}</Tag>
              </div>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-3)' }}>
                {(p.status || 'active').toUpperCase()}
              </span>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-2)' }}>
                {(p.entity_count ?? 0).toLocaleString()} ent
              </span>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-2)' }}>
                {p.document_count ?? 0} docs
              </span>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-3)' }}>
                {formatDate(p.updated_at)}
              </span>
              <span style={{ justifySelf: 'end', color: 'var(--fg-3)' }}>
                <Icon name="arrow-right" size={14} />
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function formatDate(dateStr?: string | null): string {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return '—';
    const now = new Date();
    const diffHours = (now.getTime() - d.getTime()) / (1000 * 60 * 60);
    if (diffHours < 1) {
      const mins = Math.floor((now.getTime() - d.getTime()) / 60000);
      return mins <= 0 ? 'just now' : `${mins}m ago`;
    }
    if (diffHours < 24) return `${Math.floor(diffHours)}h ago`;
    if (diffHours < 48) return 'yesterday';
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch {
    return '—';
  }
}

// ============================================================================
// Shared
// ============================================================================

function Panel({
  label,
  title,
  action,
  children,
  style,
}: {
  label: string;
  title: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <section
      style={{
        background: 'var(--paper-2)',
        border: '1px solid var(--line)',
        borderRadius: 3,
        padding: '18px 20px',
        ...style,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          gap: 12,
          marginBottom: 12,
          paddingBottom: 10,
          borderBottom: '1px solid var(--line-soft)',
        }}
      >
        <div>
          <div style={{ fontFamily: 'var(--mono)', fontSize: 9.5, letterSpacing: '0.2em', color: 'var(--fg-3)', fontWeight: 600 }}>
            {label}
          </div>
          <h2 style={{ margin: '2px 0 0', fontFamily: 'var(--serif)', fontSize: 19, fontWeight: 500, color: 'var(--ink)', letterSpacing: '-0.01em' }}>
            {title}
          </h2>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

function AnomalyDigest({ onNavigate }: { onNavigate: (v: string) => void }) {
  return (
    <div style={{ marginTop: 22 }}>
      <SectionTitle
        label="WHILE YOU WERE OUT · AGENT NOTICED"
        title="Patterns you didn't ask for"
        action={
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--fg-3)' }}>
            <PulseDot color="var(--signal)" size={5} />
            <span style={{ fontFamily: 'var(--mono)', fontSize: 10.5, letterSpacing: '0.1em' }}>{ANOMALY_DIGEST.length} NEW · LAST 24H</span>
          </span>
        }
      />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
        {ANOMALY_DIGEST.map((a, i) => (
          <button
            key={i}
            onClick={() => onNavigate('/network')}
            style={{
              position: 'relative',
              textAlign: 'left',
              padding: '14px 16px',
              background: 'var(--paper-2)',
              border: '1px solid var(--line)',
              borderRadius: 3,
              cursor: 'pointer',
              overflow: 'hidden',
            }}
          >
            <div style={{ position: 'absolute', top: 0, left: 0, width: 2, height: '100%', background: a.tint }} />
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <Icon
                name={a.kind === 'community' ? 'hub' : a.kind === 'degree' ? 'graph' : 'sparkle'}
                size={14}
              />
              <span style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.15em', color: a.tint, fontWeight: 600 }}>
                {a.kind.toUpperCase()}
              </span>
              <span style={{ flex: 1 }} />
              <span style={{ fontFamily: 'var(--mono)', fontSize: 13, color: 'var(--ink)', fontWeight: 600 }}>{a.delta}</span>
            </div>
            <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--ink)', lineHeight: 1.35 }}>{a.title}</div>
            <div style={{ fontSize: 11.5, color: 'var(--fg-3)', marginTop: 4 }}>{a.detail}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

function SectionTitle({
  label,
  title,
  action,
}: {
  label: string;
  title: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'baseline',
        justifyContent: 'space-between',
        marginBottom: 12,
        paddingBottom: 8,
        borderBottom: '1px solid var(--line-soft)',
      }}
    >
      <div>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 9.5, letterSpacing: '0.2em', color: 'var(--fg-3)', fontWeight: 600 }}>
          {label}
        </div>
        <h2 style={{ margin: '2px 0 0', fontFamily: 'var(--serif)', fontSize: 18, fontWeight: 500, color: 'var(--ink)' }}>
          {title}
        </h2>
      </div>
      {action}
    </div>
  );
}
