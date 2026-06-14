'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useProject } from '@/lib/ProjectContext';
import {
  collectionPlansApi,
  documentsApi,
  ingestApi,
  type CollectionSourceEntry,
} from '@/lib/api';
import { useNotifications } from '@/components/NotificationProvider';
import {
  Btn,
  Tag,
  PulseDot,
  Icon,
  Meter,
} from '@/components/sentinel';

type Phase = 'draft' | 'planning' | 'running' | 'paused' | 'completed' | 'archived';
type Tab = 'trace' | 'sources' | 'catalog' | 'upload';

interface Collection {
  id: string;
  pir?: string;
  refined_pir?: string;
  status?: string;
  plan?: unknown[];
  refinement?: string;
  created_at?: string;
  updated_at?: string;
}

interface DocItem {
  id: string;
  name?: string;
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

const PHASES: { id: Phase; label: string }[] = [
  { id: 'draft',     label: 'DRAFT' },
  { id: 'planning',  label: 'PLANNING' },
  { id: 'running',   label: 'RUNNING' },
  { id: 'completed', label: 'COMPLETED' },
];

export function AcquireView() {
  const router = useRouter();
  const { activeProject } = useProject();
  const { addNotification, updateNotification } = useNotifications();

  const [collections, setCollections] = useState<Collection[]>([]);
  const [documents, setDocuments] = useState<DocItem[]>([]);
  const [activeCollectionId, setActiveCollectionId] = useState<string | null>(null);
  const [pir, setPir] = useState('');
  const [phase, setPhase] = useState<Phase>('draft');
  const [tab, setTab] = useState<Tab>('trace');
  const [refining, setRefining] = useState(false);
  const [refined, setRefined] = useState<{ title?: string; description?: string; refinedPir?: string; planText?: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [draftPlanId, setDraftPlanId] = useState<string | null>(null);
  const [proposedSources, setProposedSources] = useState<CollectionSourceEntry[]>([]);
  const [approvedSourceIds, setApprovedSourceIds] = useState<Set<string>>(new Set());
  const [extractionMode, setExtractionMode] = useState<'nlp' | 'llm' | 'hybrid'>('hybrid');

  const activeCollection = collections.find((c) => c.id === activeCollectionId) || null;

  // Load collection plans (agentic pipeline) + documents
  useEffect(() => {
    if (!activeProject) return;
    collectionPlansApi
      .list(activeProject.id)
      .then((res) => {
        const list = (res.data || []) as Collection[];
        setCollections(list);
        if (list.length && !activeCollectionId) {
          // Prefer an ACTIVE plan, else most recent.
          const target = list.find((c) => c.status?.toUpperCase() === 'ACTIVE') || list[0];
          setActiveCollectionId(target.id);
          setPir(target.refined_pir || target.pir || '');
          setPhase(mapStatusToPhase(target.status));
        }
      })
      .catch(() => setCollections([]));

    documentsApi
      .list(activeProject.id)
      .then((res) => {
        const raw = res.data;
        const list = Array.isArray(raw)
          ? raw
          : (raw as { documents?: unknown[] })?.documents ?? [];
        setDocuments((Array.isArray(list) ? list : []) as DocItem[]);
      })
      .catch(() => setDocuments([]));
  }, [activeProject, activeCollectionId]);

  // Poll execution status of running agentic plan
  useEffect(() => {
    if (!activeCollectionId) return;
    if (phase !== 'running') return;
    const interval = setInterval(async () => {
      try {
        const res = await collectionPlansApi.executionStatus(activeCollectionId);
        const status = (res.data as { status?: string })?.status;
        // execution-status values: running | completed | failed | idle
        if (status === 'completed' || status === 'failed' || status === 'idle') {
          setPhase('completed');
        }
      } catch {
        /* ignore */
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [activeCollectionId, phase]);

  const submitPir = async () => {
    if (!activeProject || !pir.trim()) return;
    setSubmitting(true);
    const notifId = addNotification({
      type: 'processing',
      title: 'Starting agent run',
      message: 'Resolving sources and starting acquisition…',
    });
    try {
      // Agentic flow: if a draft plan was already created by refinePir, reuse it
      // (and disable sources the analyst un-approved) so we don't double-create.
      let planId = draftPlanId;
      if (!planId) {
        const planRes = await collectionPlansApi.fromPir({ project_id: activeProject.id, pir, extraction_mode: extractionMode });
        const created = planRes.data as Collection;
        setCollections((prev) => [created, ...prev]);
        planId = created.id;
      } else {
        // Sync source enable/disable based on approval set.
        await Promise.all(
          proposedSources.map(async (s) => {
            const shouldEnable = approvedSourceIds.has(s.id);
            if (Boolean(s.enabled) !== shouldEnable) {
              try { await collectionPlansApi.updateSource(planId!, s.id, { enabled: shouldEnable }); } catch { /* ignore */ }
            }
          })
        );
      }
      setActiveCollectionId(planId);
      await collectionPlansApi.execute(planId);
      setPhase('running');
      updateNotification(notifId, {
        type: 'success',
        title: 'Agent run started',
        message: 'Watch the Trace tab for live activity.',
      });
    } catch (e) {
      updateNotification(notifId, {
        type: 'error',
        title: 'Failed to start collection',
        message: (e as Error).message,
      });
    } finally {
      setSubmitting(false);
    }
  };

  const refinePir = async () => {
    if (!activeProject || !pir.trim()) return;
    setRefining(true);
    try {
      const res = await collectionPlansApi.fromPir({ project_id: activeProject.id, pir, extraction_mode: extractionMode });
      const data = res.data as {
        id?: string;
        llm_plan_text?: string;
        refined_pir?: string;
        name?: string;
        description?: string;
        sources?: CollectionSourceEntry[];
      };
      if (data.refined_pir) setPir(data.refined_pir);
      setRefined({
        title: data.name,
        description: data.description,
        refinedPir: data.refined_pir,
        planText: data.llm_plan_text,
      });

      // Capture the draft plan id + its proposed sources so the planning panel
      // can render real backend-proposed sources instead of demo placeholders.
      const planId = data.id || null;
      setDraftPlanId(planId);
      let srcs: CollectionSourceEntry[] = Array.isArray(data.sources) ? data.sources : [];
      if (planId && srcs.length === 0) {
        try {
          const sRes = await collectionPlansApi.listSources(planId);
          const raw = sRes.data as CollectionSourceEntry[] | { sources?: CollectionSourceEntry[] };
          srcs = Array.isArray(raw) ? raw : (raw?.sources ?? []);
        } catch { /* keep srcs empty */ }
      }
      setProposedSources(srcs);
      setApprovedSourceIds(new Set(srcs.filter((s) => s.enabled !== false).map((s) => s.id)));
      setPhase('planning');
    } catch {
      // refinement is optional; just proceed to planning with empty source list
      setProposedSources([]);
      setApprovedSourceIds(new Set());
      setPhase('planning');
    } finally {
      setRefining(false);
    }
  };

  const cancelRun = async () => {
    if (!activeCollectionId) return;
    try {
      await collectionPlansApi.pause(activeCollectionId);
      setPhase('paused');
    } catch {
      /* ignore */
    }
  };

  const newRun = () => {
    setActiveCollectionId(null);
    setPir('');
    setPhase('draft');
  };

  if (!activeProject) {
    return <NoProject onPick={() => router.push('/')} />;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <PhaseRibbon phase={phase} onPhaseClick={(p) => p === 'draft' && newRun()} />

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '380px 1fr',
          flex: 1,
          overflow: 'hidden',
        }}
      >
        {/* LEFT */}
        <aside
          style={{
            background: 'var(--paper-2)',
            borderRight: '1px solid var(--line)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          {phase === 'draft' && (
            <DraftPanel
              pir={pir}
              setPir={setPir}
              onRefine={refinePir}
              onSkip={() => setPhase('planning')}
              refining={refining}
              refined={refined}
            />
          )}
          {phase === 'planning' && (
            <PlanningPanel
              pir={pir}
              proposedSources={proposedSources}
              approvedSourceIds={approvedSourceIds}
              setApprovedSourceIds={setApprovedSourceIds}
              extractionMode={extractionMode}
              setExtractionMode={setExtractionMode}
              draftPlanId={draftPlanId}
              onApprove={submitPir}
              onBack={() => setPhase('draft')}
              submitting={submitting}
            />
          )}
          {(phase === 'running' || phase === 'paused' || phase === 'completed' || phase === 'archived') && (
            <RunPanel
              pir={pir}
              setPir={setPir}
              phase={phase}
              collection={activeCollection}
              onCancel={cancelRun}
              onNew={newRun}
            />
          )}

          {collections.length > 0 && (
            <CollectionList
              collections={collections}
              activeId={activeCollectionId}
              onSelect={(c) => {
                setActiveCollectionId(c.id);
                setPir(c.refined_pir || c.pir || '');
                setPhase(mapStatusToPhase(c.status));
              }}
            />
          )}
        </aside>

        {/* RIGHT */}
        <main
          style={{
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            background: 'var(--paper)',
          }}
        >
          <Tabs active={tab} setActive={setTab} sourceCount={0} docCount={documents.length} />
          <div style={{ flex: 1, overflow: 'auto' }}>
            {tab === 'trace' && (
              <TraceTab collection={activeCollection} phase={phase} />
            )}
            {tab === 'sources' && (
              <SourcesTab
                projectId={activeProject.id}
                onNewPlan={() => {
                  setTab('trace');
                  newRun();
                }}
              />
            )}
            {tab === 'catalog' && <CatalogTab documents={documents} />}
            {tab === 'upload' && (
              <UploadTab
                projectId={activeProject.id}
                onUploaded={(doc) => setDocuments((prev) => [doc, ...prev])}
              />
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

function mapStatusToPhase(status?: string): Phase {
  const s = status?.toUpperCase();
  if (s === 'PENDING') return 'planning';
  if (s === 'ACTIVE' || s === 'STARTED' || s === 'PROGRESS' || s === 'RUNNING') return 'running';
  if (s === 'COMPLETED' || s === 'SUCCESS') return 'completed';
  if (s === 'CANCELLED' || s === 'PAUSED') return 'paused';
  if (s === 'ARCHIVED') return 'archived';
  return 'draft';
}

// ============================================================================
// PhaseRibbon
// ============================================================================

function PhaseRibbon({ phase, onPhaseClick }: { phase: Phase; onPhaseClick: (p: Phase) => void }) {
  const idx = PHASES.findIndex((p) => p.id === phase);
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 0,
        padding: '12px 24px',
        background: 'var(--paper)',
        borderBottom: '1px solid var(--line)',
      }}
    >
      {PHASES.map((p, i) => {
        const active = i === idx;
        const done = i < idx;
        return (
          <React.Fragment key={p.id}>
            <button
              onClick={() => onPhaseClick(p.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '6px 12px',
                background: active ? 'var(--ink)' : done ? 'transparent' : 'transparent',
                color: active ? 'var(--paper)' : done ? 'var(--ink)' : 'var(--fg-3)',
                border: active ? 'none' : '1px solid var(--line)',
                borderRadius: 3,
                fontFamily: 'var(--mono)',
                fontSize: 10,
                fontWeight: 600,
                letterSpacing: '0.14em',
                cursor: 'pointer',
              }}
            >
              <span
                style={{
                  width: 16,
                  height: 16,
                  borderRadius: '50%',
                  background: active ? 'var(--signal)' : done ? 'var(--ink)' : 'transparent',
                  color: active ? 'var(--ink)' : done ? 'var(--paper)' : 'var(--fg-3)',
                  border: done || active ? 'none' : '1px solid var(--line)',
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 9,
                  fontWeight: 700,
                }}
              >
                {done ? '✓' : i + 1}
              </span>
              {p.label}
            </button>
            {i < PHASES.length - 1 && (
              <span
                style={{
                  width: 24,
                  height: 1,
                  background: i < idx ? 'var(--ink)' : 'var(--line)',
                  margin: '0 4px',
                }}
              />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// ============================================================================
// Left-pane variants
// ============================================================================

function DraftPanel({
  pir,
  setPir,
  onRefine,
  onSkip,
  refining,
  refined,
}: {
  pir: string;
  setPir: (v: string) => void;
  onRefine: () => void;
  onSkip: () => void;
  refining: boolean;
  refined?: { title?: string; description?: string; refinedPir?: string; planText?: string } | null;
}) {
  return (
    <div style={{ padding: '24px 22px', display: 'flex', flexDirection: 'column', gap: 14, overflowY: 'auto' }}>
      <SectionLabel>PRIMARY INTELLIGENCE REQUIREMENT</SectionLabel>
      <textarea
        value={pir}
        onChange={(e) => setPir(e.target.value)}
        rows={8}
        placeholder="What do you need to know? e.g. Identify vessels and shell companies enabling sanctioned cargo transits…"
        style={{
          width: '100%',
          resize: 'none',
          background: 'var(--paper)',
          border: '1px solid var(--line)',
          borderRadius: 3,
          padding: '12px',
          fontFamily: 'var(--serif)',
          fontSize: 14,
          lineHeight: 1.5,
          color: 'var(--ink)',
          outline: 'none',
        }}
      />
      <div style={{ display: 'flex', gap: 8 }}>
        <Btn
          variant="signal"
          icon="sparkle"
          onClick={onRefine}
          size="sm"
          style={{ flex: 1, justifyContent: 'center' }}
        >
          {refining ? 'Refining…' : refined ? 'Re-refine' : 'Refine with AI'}
        </Btn>
        <Btn variant="outline" icon="arrow-right" onClick={onSkip} size="sm">
          Skip
        </Btn>
      </div>
      {!refining && !refined && (
        <p style={{ margin: 0, fontSize: 11.5, color: 'var(--fg-3)', lineHeight: 1.45 }}>
          The agent will decompose your PIR into sub-questions, propose sources, and (after your
          approval) execute the plan.
        </p>
      )}

      {/* Refinement skeleton while LLM is working */}
      {refining && (
        <div
          style={{
            padding: '14px 16px',
            background: 'var(--paper)',
            border: '1px solid var(--line)',
            borderRadius: 3,
            position: 'relative',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              position: 'absolute', inset: 0,
              background: 'linear-gradient(90deg, transparent, var(--signal-soft) 50%, transparent)',
              backgroundSize: '200% 100%', animation: 'shimmer 1.4s linear infinite',
              pointerEvents: 'none',
            }}
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <Icon name="sparkle" size={14} />
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink)' }}>
              Agent is critiquing and decomposing the PIR…
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {[80, 95, 60, 70].map((w, i) => (
              <div key={i} style={{ height: 8, width: `${w}%`, background: 'var(--line)', borderRadius: 4 }} />
            ))}
          </div>
        </div>
      )}

      {/* Refinement card — what the LLM returned */}
      {!refining && refined && (
        <>
          {refined.refinedPir && (
            <div
              style={{
                padding: '12px 14px',
                background: 'var(--paper)',
                border: '1px solid var(--live)',
                borderLeft: '3px solid var(--live)',
                borderRadius: 3,
              }}
            >
              <div style={{ fontFamily: 'var(--mono)', fontSize: 9.5, letterSpacing: '0.18em', color: 'var(--live)', fontWeight: 600, marginBottom: 6 }}>
                REFINED PIR
              </div>
              <p style={{ margin: 0, fontFamily: 'var(--serif)', fontSize: 14, lineHeight: 1.55, color: 'var(--ink)' }}>
                {refined.refinedPir}
              </p>
            </div>
          )}
          {refined.title && (
            <div
              style={{
                padding: '12px 14px',
                background: 'var(--paper)',
                border: '1px solid var(--line)',
                borderRadius: 3,
              }}
            >
              <div style={{ fontFamily: 'var(--mono)', fontSize: 9.5, letterSpacing: '0.18em', color: 'var(--fg-3)', fontWeight: 600, marginBottom: 6 }}>
                PROPOSED PLAN
              </div>
              <div style={{ fontFamily: 'var(--serif)', fontSize: 15, fontWeight: 500, color: 'var(--ink)' }}>
                {refined.title}
              </div>
              {refined.description && (
                <p style={{ margin: '6px 0 0', fontSize: 12.5, lineHeight: 1.5, color: 'var(--fg-2)' }}>
                  {refined.description}
                </p>
              )}
            </div>
          )}
          {refined.planText && (
            <details
              style={{
                background: 'var(--paper-2)',
                border: '1px solid var(--line-soft)',
                borderRadius: 3,
              }}
            >
              <summary
                style={{
                  padding: '8px 12px',
                  cursor: 'pointer',
                  fontFamily: 'var(--mono)',
                  fontSize: 10,
                  letterSpacing: '0.15em',
                  color: 'var(--fg-3)',
                  fontWeight: 600,
                }}
              >
                AGENT&apos;S RAW PLAN OUTPUT
              </summary>
              <pre
                style={{
                  margin: 0,
                  padding: '0 12px 12px',
                  fontFamily: 'var(--mono)',
                  fontSize: 11,
                  color: 'var(--fg-2)',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  maxHeight: 240,
                  overflowY: 'auto',
                }}
              >
                {refined.planText}
              </pre>
            </details>
          )}
        </>
      )}
    </div>
  );
}

function PlanningPanel({
  pir,
  proposedSources,
  approvedSourceIds,
  setApprovedSourceIds,
  extractionMode,
  setExtractionMode,
  draftPlanId,
  onApprove,
  onBack,
  submitting,
}: {
  pir: string;
  proposedSources: CollectionSourceEntry[];
  approvedSourceIds: Set<string>;
  setApprovedSourceIds: React.Dispatch<React.SetStateAction<Set<string>>>;
  extractionMode: 'nlp' | 'llm' | 'hybrid';
  setExtractionMode: (m: 'nlp' | 'llm' | 'hybrid') => void;
  draftPlanId: string | null;
  onApprove: () => void;
  onBack: () => void;
  submitting: boolean;
}) {
  const typeMap: Record<string, { icon: string; label: string }> = {
    feed:    { icon: 'bolt',     label: 'FEED' },
    scraper: { icon: 'download', label: 'SCRAPER' },
    api:     { icon: 'link',     label: 'API' },
    monitor: { icon: 'eye',      label: 'MONITOR' },
  };
  const toggle = (id: string) =>
    setApprovedSourceIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const approvedCount = proposedSources.filter((s) => approvedSourceIds.has(s.id)).length;

  return (
    <div style={{ padding: '22px 22px 24px', display: 'flex', flexDirection: 'column', gap: 14, overflowY: 'auto' }}>
      <div>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 9.5, letterSpacing: '0.2em', color: 'var(--cite)', fontWeight: 600, marginBottom: 6 }}>
          COLLECTION PLAN · APPROVAL GATE
        </div>
        <p style={{ margin: 0, padding: 12, background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 3, fontFamily: 'var(--serif)', fontSize: 14, lineHeight: 1.5, color: 'var(--ink)', fontStyle: 'italic' }}>
          &ldquo;{pir}&rdquo;
        </p>
      </div>

      {/* Plan stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 1, background: 'var(--line)', borderRadius: 2, overflow: 'hidden' }}>
        <PlanStat label="SOURCES" value={`${approvedCount} / ${proposedSources.length}`} hint="approved" />
        <PlanStat label="EXTRACTION" value={extractionMode.toUpperCase()} hint="pipeline" />
      </div>

      {/* Sources list */}
      <div>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 9.5, letterSpacing: '0.2em', color: 'var(--fg-3)', fontWeight: 600, marginBottom: 8 }}>
          PROPOSED SOURCES · TOGGLE TO INCLUDE
        </div>
        {proposedSources.length === 0 ? (
          <div style={{
            padding: '12px 14px', background: 'var(--paper)',
            border: '1px dashed var(--line)', borderRadius: 3,
            fontSize: 12, color: 'var(--fg-3)', fontStyle: 'italic',
          }}>
            Backend did not propose any sources for this PIR{draftPlanId ? ` (plan ${draftPlanId.slice(0, 8)}…)` : ''}. Approving will execute with the plan&rsquo;s defaults.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {proposedSources.map((s) => {
              const tp = typeMap[s.source_type] || { icon: 'link', label: (s.source_type || 'SOURCE').toUpperCase() };
              const approved = approvedSourceIds.has(s.id);
              return (
                <button
                  key={s.id}
                  onClick={() => toggle(s.id)}
                  style={{
                    display: 'grid', gridTemplateColumns: '20px 28px 1fr auto', gap: 10, alignItems: 'flex-start',
                    padding: '10px 12px', background: 'var(--paper)',
                    border: '1px solid ' + (approved ? 'var(--line)' : 'var(--line-soft)'),
                    borderRadius: 2, opacity: approved ? 1 : 0.55, textAlign: 'left', cursor: 'pointer',
                  }}
                >
                  <span style={{
                    width: 16, height: 16, borderRadius: 2,
                    background: approved ? 'var(--ink)' : 'var(--paper-2)',
                    color: approved ? 'var(--signal)' : 'var(--fg-4)',
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    border: '1px solid ' + (approved ? 'var(--ink)' : 'var(--line)'),
                    marginTop: 2,
                  }}>
                    {approved && <Icon name="check" size={10} stroke={3} />}
                  </span>
                  <span style={{
                    width: 24, height: 24, borderRadius: 2, background: 'var(--paper-2)',
                    color: 'var(--fg-2)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Icon name={tp.icon} size={12} />
                  </span>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                      <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink)' }}>{s.name}</span>
                      <Tag>{tp.label}</Tag>
                    </div>
                    {s.schedule_cron && (
                      <div style={{ fontSize: 11.5, color: 'var(--fg-2)', marginTop: 3, lineHeight: 1.45 }}>
                        schedule · {s.schedule_cron}
                      </div>
                    )}
                  </div>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 9.5, color: 'var(--fg-3)', whiteSpace: 'nowrap' }}>
                    {s.total_records_acquired ? `${s.total_records_acquired} rec` : '—'}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Extraction mode */}
      <div style={{
        padding: '10px 12px', background: 'var(--paper)',
        border: '1px solid var(--line-soft)', borderRadius: 2,
        display: 'flex', alignItems: 'center', gap: 12,
      }}>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 9.5, color: 'var(--fg-3)', letterSpacing: '0.15em' }}>
          EXTRACTION MODE
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {(['nlp', 'llm', 'hybrid'] as const).map((m) => (
            <button
              key={m}
              onClick={() => setExtractionMode(m)}
              style={{
                padding: '3px 10px', borderRadius: 2,
                background: m === extractionMode ? 'var(--ink)' : 'transparent',
                color: m === extractionMode ? 'var(--paper)' : 'var(--fg-2)',
                border: '1px solid ' + (m === extractionMode ? 'var(--ink)' : 'var(--line)'),
                fontFamily: 'var(--mono)', fontSize: 11, fontWeight: 500, textTransform: 'uppercase', cursor: 'pointer',
              }}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: 6 }}>
        <Btn variant="outline" icon="chevron-right" onClick={onBack} size="sm" style={{ transform: 'scaleX(-1)' }}>
          {' '}
        </Btn>
        <Btn variant="signal" icon="play" onClick={onApprove} size="sm" style={{ flex: 1, justifyContent: 'center' }}>
          {submitting ? 'Submitting…' : `Approve & execute${proposedSources.length > 0 ? ` · ${approvedCount} source${approvedCount === 1 ? '' : 's'}` : ''}`}
        </Btn>
      </div>
      <p style={{ margin: 0, fontFamily: 'var(--mono)', fontSize: 9.5, color: 'var(--fg-3)', letterSpacing: '0.06em', textAlign: 'center' }}>
        The agent will pause for analyst approval at the synthesis step.
      </p>
    </div>
  );
}

function PlanStat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div style={{ padding: '10px 14px', background: 'var(--paper-2)' }}>
      <div style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--fg-3)', letterSpacing: '0.12em' }}>{label}</div>
      <div style={{ fontFamily: 'var(--mono)', fontSize: 14, fontWeight: 500, color: 'var(--ink)', marginTop: 2 }}>{value}</div>
      <div style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--fg-3)', marginTop: 1 }}>{hint}</div>
    </div>
  );
}

function RunPanel({
  pir,
  setPir,
  phase,
  collection,
  onCancel,
  onNew,
}: {
  pir: string;
  setPir: (v: string) => void;
  phase: Phase;
  collection: Collection | null;
  onCancel: () => void;
  onNew: () => void;
}) {
  return (
    <div style={{ padding: '24px 22px', borderBottom: '1px solid var(--line)' }}>
      <SectionLabel>PRIMARY INTELLIGENCE REQUIREMENT</SectionLabel>
      <textarea
        value={pir}
        onChange={(e) => setPir(e.target.value)}
        rows={4}
        readOnly={phase !== 'paused'}
        style={{
          width: '100%',
          resize: 'none',
          background: 'var(--paper)',
          border: '1px solid var(--line)',
          borderRadius: 3,
          padding: '10px 12px',
          fontFamily: 'var(--serif)',
          fontSize: 13.5,
          lineHeight: 1.5,
          color: 'var(--ink)',
          outline: 'none',
          marginTop: 6,
        }}
      />
      <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
        {phase === 'running' && (
          <Btn
            variant="outline"
            icon="pause"
            onClick={onCancel}
            size="sm"
            style={{ flex: 1, justifyContent: 'center' }}
          >
            Cancel run
          </Btn>
        )}
        {(phase === 'completed' || phase === 'paused' || phase === 'archived') && (
          <Btn
            variant="outline"
            icon="plus"
            onClick={onNew}
            size="sm"
            style={{ flex: 1, justifyContent: 'center' }}
          >
            New run
          </Btn>
        )}
      </div>

      {/* Run metadata */}
      <div
        style={{
          marginTop: 14,
          padding: '10px 12px',
          background: 'var(--paper)',
          border: '1px solid var(--line)',
          borderRadius: 3,
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-3)', letterSpacing: '0.12em' }}>
            RUN {(collection?.id || '').slice(0, 8).toUpperCase() || 'NEW'}
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <PulseDot
              color={
                phase === 'running'
                  ? 'var(--signal)'
                  : phase === 'completed'
                  ? 'var(--live)'
                  : 'var(--fg-4)'
              }
            />
            <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-2)', letterSpacing: '0.1em' }}>
              {phase.toUpperCase()}
            </span>
          </span>
        </div>
        {collection?.created_at && (
          <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>
            Started {new Date(collection.created_at).toLocaleString()}
          </div>
        )}
      </div>
    </div>
  );
}

function CollectionList({
  collections,
  activeId,
  onSelect,
}: {
  collections: Collection[];
  activeId: string | null;
  onSelect: (c: Collection) => void;
}) {
  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '14px 0', borderTop: '1px solid var(--line)' }}>
      <div
        style={{
          padding: '0 22px 8px',
          fontFamily: 'var(--mono)',
          fontSize: 9.5,
          letterSpacing: '0.2em',
          color: 'var(--fg-3)',
          fontWeight: 600,
        }}
      >
        RECENT RUNS · {collections.length}
      </div>
      {collections.slice(0, 30).map((c) => {
        const active = c.id === activeId;
        const phaseLabel = mapStatusToPhase(c.status).toUpperCase();
        return (
          <button
            key={c.id}
            onClick={() => onSelect(c)}
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 4,
              width: '100%',
              padding: '10px 22px',
              background: active ? 'var(--paper)' : 'transparent',
              borderLeft: active ? '2px solid var(--signal)' : '2px solid transparent',
              border: 'none',
              cursor: 'pointer',
              textAlign: 'left',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-3)', letterSpacing: '0.1em' }}>
                {c.id.slice(0, 8)}
              </span>
              <Tag tone={c.status?.toUpperCase() === 'COMPLETED' ? 'live' : 'neutral'}>{phaseLabel}</Tag>
            </div>
            <span
              style={{
                fontSize: 12,
                color: 'var(--ink)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                display: '-webkit-box',
                WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical',
              }}
            >
              {c.refined_pir || c.pir || '—'}
            </span>
          </button>
        );
      })}
    </div>
  );
}

// ============================================================================
// Right-pane tabs
// ============================================================================

function Tabs({
  active,
  setActive,
  sourceCount,
  docCount,
}: {
  active: Tab;
  setActive: (t: Tab) => void;
  sourceCount: number;
  docCount: number;
}) {
  const tabs: { id: Tab; label: string; icon: string; count?: number }[] = [
    { id: 'trace',   label: 'Agent trace',   icon: 'sparkle' },
    { id: 'sources', label: 'Sources',       icon: 'acquire', count: sourceCount },
    { id: 'catalog', label: 'Data catalog',  icon: 'layers',  count: docCount },
    { id: 'upload',  label: 'Manual upload', icon: 'upload' },
  ];
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        padding: '0 24px',
        borderBottom: '1px solid var(--line)',
        background: 'var(--paper)',
      }}
    >
      {tabs.map((t) => {
        const isActive = active === t.id;
        return (
          <button
            key={t.id}
            onClick={() => setActive(t.id)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '14px 14px 12px',
              borderBottom: `2px solid ${isActive ? 'var(--ink)' : 'transparent'}`,
              background: 'transparent',
              border: 'none',
              borderBottomStyle: 'solid',
              borderBottomWidth: 2,
              borderBottomColor: isActive ? 'var(--ink)' : 'transparent',
              color: isActive ? 'var(--ink)' : 'var(--fg-3)',
              fontSize: 13,
              fontWeight: isActive ? 600 : 500,
              cursor: 'pointer',
            }}
          >
            <Icon name={t.icon} size={14} />
            {t.label}
            {t.count != null && (
              <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-3)', fontWeight: 400 }}>
                {t.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

function TraceTab({
  collection,
  phase,
}: {
  collection: Collection | null;
  phase: Phase;
}) {
  if (!collection) {
    return (
      <EmptyState
        icon="sparkle"
        title="No active run"
        body="Submit a PIR on the left to start an agent run, or pick a recent run to see its trace."
      />
    );
  }
  return (
    <div style={{ padding: '24px 32px 48px', maxWidth: 1100, margin: '0 auto' }}>
      <div
        style={{
          padding: '16px 20px',
          background: 'var(--paper-2)',
          border: '1px solid var(--line)',
          borderRadius: 3,
          marginBottom: 24,
          display: 'flex',
          gap: 14,
          alignItems: 'flex-start',
        }}
      >
        <span
          style={{
            width: 26,
            height: 26,
            borderRadius: 3,
            background: 'var(--ink)',
            color: 'var(--paper)',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <Icon name="sparkle" size={14} />
        </span>
        <div style={{ flex: 1 }}>
          <div
            style={{
              fontFamily: 'var(--mono)',
              fontSize: 10,
              color: 'var(--fg-3)',
              letterSpacing: '0.12em',
              marginBottom: 4,
            }}
          >
            AGENT REASONING · STATUS {phase.toUpperCase()}
          </div>
          <p style={{ margin: 0, fontFamily: 'var(--serif)', fontSize: 15, lineHeight: 1.5, color: 'var(--ink)' }}>
            {collection.refinement || collection.refined_pir || collection.pir || 'No reasoning available yet.'}
            {phase === 'running' && (
              <span style={{ marginLeft: 4, color: 'var(--signal)', animation: 'caret-blink 1s infinite' }}>▋</span>
            )}
          </p>
        </div>
      </div>

      <SectionLabel style={{ marginBottom: 10 }}>LIVE ACTIVITY</SectionLabel>
      <ActivityFeed planId={collection.id} phase={phase} />
    </div>
  );
}

function ActivityFeed({ planId, phase }: { planId: string; phase: Phase }) {
  const [entries, setEntries] = useState<Array<{
    id: string;
    event: string;
    message: string;
    created_at: string;
  }>>([]);

  // Poll activity (every 3s while running, every 10s otherwise — initial fetch always).
  useEffect(() => {
    let cancelled = false;
    const fetchOnce = async () => {
      try {
        const res = await collectionPlansApi.activity(planId);
        if (!cancelled) setEntries((res.data || []) as typeof entries);
      } catch {
        /* ignore */
      }
    };
    fetchOnce();
    const intervalMs = phase === 'running' ? 3000 : 10000;
    const interval = setInterval(fetchOnce, intervalMs);
    return () => { cancelled = true; clearInterval(interval); };
  }, [planId, phase]);

  if (entries.length === 0) {
    return (
      <EmptyState
        icon="bolt"
        title="No activity yet"
        body={phase === 'running'
          ? 'Waiting for the agent to emit its first step…'
          : 'No activity recorded for this run.'}
      />
    );
  }

  // Map event types to tone (matches the paper/ink palette).
  const toneFor = (ev: string): string => {
    if (ev.endsWith('_failed') || ev === 'plan_failed') return 'var(--warn)';
    if (ev.endsWith('_fetched') || ev.endsWith('_succeeded') || ev === 'plan_completed') return 'var(--signal)';
    if (ev.endsWith('_fetching') || ev.endsWith('_collecting') || ev.endsWith('_resolving')) return 'var(--cite)';
    return 'var(--fg-3)';
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {entries.slice().reverse().map((e) => (
        <div
          key={e.id}
          style={{
            display: 'flex',
            gap: 12,
            alignItems: 'flex-start',
            padding: '8px 12px',
            background: 'var(--paper-2)',
            border: '1px solid var(--line)',
            borderRadius: 3,
          }}
        >
          <span
            style={{
              fontFamily: 'var(--mono)',
              fontSize: 10,
              letterSpacing: '0.08em',
              color: toneFor(e.event),
              minWidth: 110,
              paddingTop: 2,
            }}
          >
            {e.event.toUpperCase()}
          </span>
          <span style={{ flex: 1, fontSize: 12, color: 'var(--ink)', wordBreak: 'break-word' }}>
            {e.message}
          </span>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-4)', whiteSpace: 'nowrap' }}>
            {new Date(e.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </span>
        </div>
      ))}
    </div>
  );
}

function SourcesTab({ projectId, onNewPlan }: { projectId: string; onNewPlan: () => void }) {
  const [plans, setPlans] = useState<Array<{ id: string; name?: string; status?: string; source_count?: number }>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    collectionPlansApi
      .list(projectId)
      .then((res) => setPlans((res.data || []) as typeof plans))
      .catch(() => setPlans([]))
      .finally(() => setLoading(false));
  }, [projectId]);

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1300 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: 0, fontFamily: 'var(--serif)', fontSize: 22, fontWeight: 500, color: 'var(--ink)' }}>
            Collection plans
          </h2>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--fg-3)' }}>
            Managed acquisition pipelines and their sources.
          </p>
        </div>
        <Btn variant="outline" icon="plus" size="sm" onClick={onNewPlan}>
          New plan
        </Btn>
      </div>

      {loading ? (
        <EmptyState icon="acquire" title="Loading…" />
      ) : plans.length === 0 ? (
        <EmptyState
          icon="acquire"
          title="No collection plans yet"
          body="Create a plan from a PIR or add ad-hoc sources to start collecting."
        />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
          {plans.map((p) => (
            <div
              key={p.id}
              style={{
                padding: 16,
                background: 'var(--paper-2)',
                border: '1px solid var(--line)',
                borderRadius: 3,
                display: 'flex',
                flexDirection: 'column',
                gap: 10,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span
                  style={{
                    width: 32,
                    height: 32,
                    background: 'var(--paper)',
                    border: '1px solid var(--line)',
                    borderRadius: 3,
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'var(--fg-2)',
                  }}
                >
                  <Icon name="bolt" size={15} />
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {p.name || p.id}
                  </div>
                  <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-3)', letterSpacing: '0.08em', marginTop: 2 }}>
                    {(p.status || 'DRAFT').toUpperCase()} · {p.source_count ?? 0} SOURCES
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CatalogTab({ documents }: { documents: DocItem[] }) {
  return (
    <div style={{ padding: '24px 32px', maxWidth: 1300 }}>
      <h2 style={{ margin: '0 0 4px', fontFamily: 'var(--serif)', fontSize: 22, fontWeight: 500, color: 'var(--ink)' }}>
        Data catalog
      </h2>
      <p style={{ margin: '0 0 16px', fontSize: 13, color: 'var(--fg-3)' }}>
        Every document the agent has ingested · {documents.length} total.
      </p>

      {documents.length === 0 ? (
        <EmptyState icon="doc" title="No documents yet" body="Upload one in the Manual upload tab, or run a collection." />
      ) : (
        <div style={{ background: 'var(--paper-2)', border: '1px solid var(--line)', borderRadius: 3, overflow: 'hidden' }}>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '2.4fr 0.8fr 1.4fr 0.6fr 0.9fr',
              gap: 16,
              padding: '10px 18px',
              background: 'var(--paper)',
              borderBottom: '1px solid var(--line)',
            }}
          >
            {['Title', 'Kind', 'Source', 'Rel.', 'Ingested'].map((h) => (
              <span
                key={h}
                style={{
                  fontFamily: 'var(--mono)',
                  fontSize: 9.5,
                  letterSpacing: '0.18em',
                  color: 'var(--fg-3)',
                  fontWeight: 600,
                }}
              >
                {h.toUpperCase()}
              </span>
            ))}
          </div>
          {documents.slice(0, 200).map((d, i) => (
            <div
              key={d.id}
              style={{
                display: 'grid',
                gridTemplateColumns: '2.4fr 0.8fr 1.4fr 0.6fr 0.9fr',
                gap: 16,
                padding: '12px 18px',
                alignItems: 'center',
                borderTop: i === 0 ? 'none' : '1px solid var(--line-soft)',
                fontSize: 12,
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                <Icon name="doc" size={14} />
                <span
                  style={{
                    color: 'var(--ink)',
                    fontWeight: 500,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {d.title || d.name || d.filename || d.id}
                </span>
              </span>
              <Tag>{(d.kind || d.file_format || '—').toUpperCase()}</Tag>
              <span style={{ color: 'var(--fg-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {d.source || '—'}
              </span>
              <ReliabilityBadge grade={d.reliability_rating || d.reliability} />
              <span style={{ fontFamily: 'var(--mono)', color: 'var(--fg-3)', fontSize: 11 }}>
                {formatTime(d.created_at || d.uploaded_at)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function UploadTab({
  projectId,
  onUploaded,
}: {
  projectId: string;
  onUploaded: (d: DocItem) => void;
}) {
  const [reliability, setReliability] = useState<'A' | 'B' | 'C' | 'D' | 'E' | 'F'>('B');
  const [credibility, setCredibility] = useState<1 | 2 | 3 | 4 | 5 | 6>(2);
  const [extraction, setExtraction] = useState<'fast' | 'accurate'>('fast');
  const [dragOver, setDragOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const { addNotification, updateNotification } = useNotifications();

  const upload = async (files: File[]) => {
    if (!files.length) return;
    setBusy(true);
    setProgress({ done: 0, total: files.length });
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const notifId = addNotification({
        type: 'processing',
        title: `Uploading ${file.name}`,
        message: `${(file.size / 1024).toFixed(1)} KB · ${reliability}${credibility} · ${extraction}`,
      });
      try {
        const res = await ingestApi.file(projectId, file, reliability, extraction);
        const data = res.data as DocItem;
        if (data) onUploaded({ ...data, title: data.title || file.name });
        updateNotification(notifId, {
          type: 'success',
          title: 'Uploaded',
          message: file.name,
        });
      } catch (e) {
        updateNotification(notifId, {
          type: 'error',
          title: `Failed: ${file.name}`,
          message: (e as Error).message,
        });
      }
      setProgress({ done: i + 1, total: files.length });
    }
    setBusy(false);
    setProgress(null);
  };

  return (
    <div style={{ padding: '24px 32px', maxWidth: 900 }}>
      <h2 style={{ margin: '0 0 4px', fontFamily: 'var(--serif)', fontSize: 22, fontWeight: 500, color: 'var(--ink)' }}>
        Manual upload
      </h2>
      <p style={{ margin: '0 0 18px', fontSize: 13, color: 'var(--fg-3)' }}>
        Drop documents to ingest. Entity & relationship extraction runs automatically.
      </p>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          upload(Array.from(e.dataTransfer.files));
        }}
        onClick={() => inputRef.current?.click()}
        style={{
          padding: '40px 20px',
          background: dragOver ? 'var(--signal-soft)' : 'var(--paper-2)',
          border: `2px dashed ${dragOver ? 'var(--signal)' : 'var(--line)'}`,
          borderRadius: 4,
          textAlign: 'center',
          cursor: busy ? 'wait' : 'pointer',
          transition: 'background 0.15s',
        }}
      >
        <Icon name="upload" size={28} />
        <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--ink)', marginTop: 10 }}>
          Drop files here or click to browse
        </div>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-3)', letterSpacing: '0.1em', marginTop: 6 }}>
          PDF · DOCX · TXT · CSV · JSON · HTML
        </div>
        <input
          ref={inputRef}
          type="file"
          multiple
          style={{ display: 'none' }}
          onChange={(e) => upload(Array.from(e.target.files || []))}
        />
      </div>

      {progress && (
        <div style={{ marginTop: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11.5, color: 'var(--fg-2)', marginBottom: 4 }}>
            <span>Uploading…</span>
            <span style={{ fontFamily: 'var(--mono)' }}>
              {progress.done} / {progress.total}
            </span>
          </div>
          <Meter value={progress.done / progress.total} tone="var(--signal)" width={undefined as unknown as number} />
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18, marginTop: 24 }}>
        <div>
          <SectionLabel style={{ marginBottom: 8 }}>RELIABILITY · NATO ADMIRALTY · {reliability}{credibility}</SectionLabel>
          <div style={{ fontFamily: 'var(--mono)', fontSize: 9.5, letterSpacing: '0.12em', color: 'var(--fg-3)', marginBottom: 6 }}>
            SOURCE
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 4, marginBottom: 10 }}>
            {(['A', 'B', 'C', 'D', 'E', 'F'] as const).map((r) => {
              const labels: Record<typeof r, string> = {
                A: 'completely',
                B: 'usually',
                C: 'fairly',
                D: 'not usually',
                E: 'unreliable',
                F: 'unjudgeable',
              };
              return (
                <button
                  key={r}
                  onClick={() => setReliability(r)}
                  title={labels[r]}
                  style={{
                    padding: '8px 0',
                    background: reliability === r ? 'var(--ink)' : 'var(--paper-2)',
                    color: reliability === r ? 'var(--paper)' : 'var(--fg-2)',
                    border: '1px solid var(--line)',
                    borderRadius: 3,
                    fontFamily: 'var(--mono)',
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  {r}
                </button>
              );
            })}
          </div>
          <div style={{ fontFamily: 'var(--mono)', fontSize: 9.5, letterSpacing: '0.12em', color: 'var(--fg-3)', marginBottom: 6 }}>
            CREDIBILITY
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 4 }}>
            {([1, 2, 3, 4, 5, 6] as const).map((c) => {
              const labels: Record<typeof c, string> = {
                1: 'confirmed',
                2: 'probably true',
                3: 'possibly true',
                4: 'doubtful',
                5: 'improbable',
                6: 'unjudgeable',
              };
              return (
                <button
                  key={c}
                  onClick={() => setCredibility(c)}
                  title={labels[c]}
                  style={{
                    padding: '8px 0',
                    background: credibility === c ? 'var(--ink)' : 'var(--paper-2)',
                    color: credibility === c ? 'var(--paper)' : 'var(--fg-2)',
                    border: '1px solid var(--line)',
                    borderRadius: 3,
                    fontFamily: 'var(--mono)',
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  {c}
                </button>
              );
            })}
          </div>
        </div>
        <div>
          <SectionLabel style={{ marginBottom: 8 }}>EXTRACTION MODE</SectionLabel>
          <div style={{ display: 'flex', gap: 6 }}>
            {(['fast', 'accurate'] as const).map((m) => (
              <button
                key={m}
                onClick={() => setExtraction(m)}
                style={{
                  flex: 1,
                  padding: '10px 0',
                  background: extraction === m ? 'var(--ink)' : 'var(--paper-2)',
                  color: extraction === m ? 'var(--paper)' : 'var(--fg-2)',
                  border: '1px solid var(--line)',
                  borderRadius: 3,
                  fontFamily: 'var(--mono)',
                  fontSize: 12,
                  fontWeight: 600,
                  letterSpacing: '0.08em',
                  cursor: 'pointer',
                }}
              >
                {m.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Helpers
// ============================================================================

function SectionLabel({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div
      style={{
        fontFamily: 'var(--mono)',
        fontSize: 9.5,
        letterSpacing: '0.2em',
        color: 'var(--fg-3)',
        fontWeight: 600,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

function ReliabilityBadge({ grade }: { grade?: string }) {
  const map: Record<string, { color: string; label: string }> = {
    A: { color: 'var(--live)', label: 'A' },
    B: { color: 'var(--signal-ink)', label: 'B' },
    C: { color: 'var(--warn)', label: 'C' },
  };
  const m = map[grade?.toUpperCase() || 'B'] || map.B;
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 18,
        height: 18,
        borderRadius: 2,
        border: `1px solid ${m.color}`,
        color: m.color,
        fontFamily: 'var(--mono)',
        fontSize: 10,
        fontWeight: 600,
      }}
    >
      {m.label}
    </span>
  );
}

function EmptyState({ icon, title, body }: { icon: string; title: string; body?: string }) {
  return (
    <div
      style={{
        padding: '48px 24px',
        textAlign: 'center',
        background: 'var(--paper-2)',
        border: '1px dashed var(--line)',
        borderRadius: 4,
        color: 'var(--fg-3)',
      }}
    >
      <Icon name={icon} size={32} />
      <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--ink)', marginTop: 12 }}>{title}</div>
      {body && <div style={{ fontSize: 12.5, color: 'var(--fg-3)', marginTop: 4, maxWidth: 480, margin: '4px auto 0' }}>{body}</div>}
    </div>
  );
}

function NoProject({ onPick }: { onPick: () => void }) {
  return (
    <div
      style={{
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--paper)',
      }}
    >
      <div style={{ textAlign: 'center', maxWidth: 400 }}>
        <Icon name="acquire" size={36} />
        <h2 style={{ margin: '12px 0 6px', fontFamily: 'var(--serif)', fontSize: 22, fontWeight: 500, color: 'var(--ink)' }}>
          No active project
        </h2>
        <p style={{ margin: '0 0 18px', fontSize: 13, color: 'var(--fg-3)' }}>
          Acquisition runs are scoped to a project. Pick one to continue.
        </p>
        <Btn variant="signal" icon="hub" onClick={onPick}>
          Open Hub
        </Btn>
      </div>
    </div>
  );
}

function formatTime(s?: string): string {
  if (!s) return '—';
  try {
    const d = new Date(s);
    if (isNaN(d.getTime())) return '—';
    const diffH = (Date.now() - d.getTime()) / 3600000;
    if (diffH < 1) return `${Math.max(0, Math.floor(diffH * 60))}m ago`;
    if (diffH < 24) return `${Math.floor(diffH)}h ago`;
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch {
    return '—';
  }
}
