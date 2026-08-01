'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  pirsApi,
  type Pir,
  type PirRequirements,
  type PirStatus,
  type RequirementStatus,
} from '@/lib/api';
import { getErrorMessage } from '@/lib/errorMessages';

const colors = {
  primary: '#adc6ff',
  secondary: '#ffb95f',
  tertiary: '#ff5451',
  containerLow: '#161b2a',
  container: '#1a1f2e',
  green: '#4ade80',
};

const STATUSES: PirStatus[] = ['OPEN', 'PARTIAL', 'SATISFIED', 'ARCHIVED'];
const PRIORITIES = ['critical', 'high', 'medium', 'low'];

const STATUS_COLOR: Record<PirStatus, string> = {
  OPEN: colors.primary,
  PARTIAL: colors.secondary,
  SATISFIED: colors.green,
  ARCHIVED: '#6b7280',
};

const PRIORITY_COLOR: Record<string, string> = {
  critical: colors.tertiary,
  high: colors.secondary,
  medium: colors.primary,
  low: '#6b7280',
};

const ELEMENT_COLOR: Record<RequirementStatus, string> = {
  satisfied: colors.green,
  // Tried and given up on. Deliberately a different colour from "open": an
  // analyst deciding whether to collect more needs to tell them apart.
  unmet: colors.tertiary,
  pending: '#6b7280',
};

const ELEMENT_LABEL: Record<RequirementStatus, string> = {
  satisfied: 'answered',
  unmet: 'gave up',
  pending: 'open',
};

/** Per-element collection state, replacing a flat list of criteria.
 *
 * The assessor's reasoning about *why* a requirement is unfinished used to be
 * computed and discarded. Collection now acts on these rows, so the panel shows
 * what was answered, what was tried and abandoned, and what each gap is still
 * missing. Falls back to the plain list when the state cannot be loaded — a
 * requirement's criteria should still be readable if the endpoint is down.
 */
function RequirementMatrix({ pirId, eeis }: { pirId: string; eeis: string[] }) {
  const [data, setData] = useState<PirRequirements | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    pirsApi
      .requirements(pirId)
      .then(res => { if (!cancelled) setData(res.data); })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, [pirId]);

  if (failed || !data || data.elements.length === 0) {
    return (
      <ul className="mt-2 space-y-0.5">
        {eeis.map((eei, i) => (
          <li key={i} className="text-[11px] text-gray-400">• {eei}</li>
        ))}
      </ul>
    );
  }

  const { satisfied = 0, unmet = 0, pending = 0 } = data.counts;

  return (
    <div className="mt-2 space-y-1">
      <div className="text-[10px] uppercase tracking-wider text-gray-500">
        {satisfied}/{data.total} answered
        {unmet > 0 && <span style={{ color: colors.tertiary }}> · {unmet} gave up</span>}
        {pending > 0 && <span className="text-gray-500"> · {pending} open</span>}
      </div>
      <ul className="space-y-1">
        {data.elements.map(element => (
          <li key={element.ordinal} className="text-[11px] text-gray-400">
            <span className="flex items-start gap-1.5">
              <span
                className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ backgroundColor: ELEMENT_COLOR[element.status] }}
                aria-hidden="true"
              />
              <span className="flex-1">
                {element.text}
                <span
                  className="ml-1.5 text-[10px] uppercase tracking-wider"
                  style={{ color: ELEMENT_COLOR[element.status] }}
                >
                  {ELEMENT_LABEL[element.status]}
                  {element.attempts > 0 && element.status !== 'satisfied' &&
                    ` after ${element.attempts}`}
                </span>
                {element.missing && element.status !== 'satisfied' && (
                  <span className="block text-[10px] text-gray-500">
                    missing: {element.missing}
                  </span>
                )}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Pill({ label, color }: { label: string; color: string }) {
  return (
    <span
      className="text-[10px] px-2 py-0.5 rounded-full font-medium uppercase tracking-wider"
      style={{ backgroundColor: `${color}26`, color }}
    >
      {label}
    </span>
  );
}

interface Draft {
  title: string;
  text: string;
  priority: string;
  status: PirStatus;
}

const EMPTY_DRAFT: Draft = { title: '', text: '', priority: 'medium', status: 'OPEN' };

/**
 * Priority Intelligence Requirements for a project — the requirements spine.
 *
 * Shows what the project is trying to answer, whether each requirement is still
 * open, and which collection plans it drove. Sits on the project hub because
 * that is where an analyst starts; "Collect" hands the PIR to /collections so
 * the question never has to be retyped.
 */
export default function PirPanel({ projectId }: { projectId: string }) {
  const router = useRouter();
  const [pirs, setPirs] = useState<Pir[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const res = await pirsApi.list(projectId);
      setPirs(res.data);
      setError(null);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  async function saveDraft() {
    if (!draft.text.trim()) return;
    setSaving(true);
    setError(null);
    try {
      if (editingId) {
        await pirsApi.update(editingId, {
          title: draft.title.trim(),
          text: draft.text.trim(),
          priority: draft.priority,
          status: draft.status,
        });
      } else {
        await pirsApi.create({
          project_id: projectId,
          title: draft.title.trim(),
          text: draft.text.trim(),
          priority: draft.priority,
          status: draft.status,
        });
      }
      setDraft(EMPTY_DRAFT);
      setEditingId(null);
      setShowCreate(false);
      await load();
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  async function setStatus(pir: Pir, status: PirStatus) {
    setError(null);
    try {
      await pirsApi.update(pir.id, { status });
      setPirs(prev => prev.map(p => (p.id === pir.id ? { ...p, status } : p)));
    } catch (e) {
      setError(getErrorMessage(e));
    }
  }

  async function remove(pir: Pir) {
    setError(null);
    try {
      await pirsApi.delete(pir.id);
      setPirs(prev => prev.filter(p => p.id !== pir.id));
    } catch (e) {
      setError(getErrorMessage(e));
    }
  }

  function startEdit(pir: Pir) {
    setEditingId(pir.id);
    setDraft({ title: pir.title, text: pir.text, priority: pir.priority, status: pir.status });
    setShowCreate(true);
  }

  function startCreate() {
    setEditingId(null);
    setDraft(EMPTY_DRAFT);
    setShowCreate(true);
  }

  const openCount = pirs.filter(p => p.status === 'OPEN' || p.status === 'PARTIAL').length;

  return (
    <div className="rounded-lg p-4 mb-8" style={{ backgroundColor: colors.container }}>
      <div className="flex items-start justify-between mb-1 gap-4">
        <div>
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <span style={{ color: colors.primary }}>|</span> Priority Intelligence Requirements
          </h3>
          <p className="text-[10px] text-gray-500 mt-1">
            What this project is trying to answer — {openCount} outstanding of {pirs.length}
          </p>
        </div>
        <button
          onClick={showCreate ? () => { setShowCreate(false); setEditingId(null); } : startCreate}
          className="px-3 py-1.5 rounded-md text-xs font-medium shrink-0 transition-colors"
          style={{ border: `1px solid ${colors.primary}`, color: colors.primary }}
        >
          {showCreate ? 'Cancel' : 'New PIR'}
        </button>
      </div>

      {error && <p className="text-xs mt-2" style={{ color: colors.tertiary }}>{error}</p>}

      {showCreate && (
        <div className="mt-3 rounded-md p-3 space-y-2" style={{ backgroundColor: colors.containerLow }}>
          <input
            value={draft.title}
            onChange={e => setDraft({ ...draft, title: e.target.value })}
            placeholder="Short label (optional) — e.g. PIR-1 Actor infrastructure"
            className="w-full rounded-md px-3 py-2 text-xs text-gray-200 outline-none"
            style={{ backgroundColor: colors.container, border: '1px solid rgba(255,255,255,0.08)' }}
          />
          <textarea
            value={draft.text}
            onChange={e => setDraft({ ...draft, text: e.target.value })}
            rows={3}
            placeholder="The intelligence question — e.g. What infrastructure does the actor use for command and control, and how is it acquired?"
            className="w-full rounded-md px-3 py-2 text-xs text-gray-200 outline-none resize-y"
            style={{ backgroundColor: colors.container, border: '1px solid rgba(255,255,255,0.08)' }}
          />
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={draft.priority}
              onChange={e => setDraft({ ...draft, priority: e.target.value })}
              className="rounded-md px-2 py-1.5 text-xs text-gray-300 outline-none"
              style={{ backgroundColor: colors.container, border: '1px solid rgba(255,255,255,0.08)' }}
            >
              {PRIORITIES.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
            <select
              value={draft.status}
              onChange={e => setDraft({ ...draft, status: e.target.value as PirStatus })}
              className="rounded-md px-2 py-1.5 text-xs text-gray-300 outline-none"
              style={{ backgroundColor: colors.container, border: '1px solid rgba(255,255,255,0.08)' }}
            >
              {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <button
              onClick={saveDraft}
              disabled={saving || !draft.text.trim()}
              className="px-3 py-1.5 rounded-md text-xs font-semibold disabled:opacity-40"
              style={{ backgroundColor: colors.primary, color: colors.container }}
            >
              {saving ? 'Saving...' : editingId ? 'Save changes' : 'Add requirement'}
            </button>
          </div>
        </div>
      )}

      <div className="mt-3 space-y-2">
        {loading && <p className="text-xs text-gray-500">Loading requirements...</p>}

        {!loading && pirs.length === 0 && !showCreate && (
          <p className="text-xs text-gray-500">
            No requirements yet. A PIR anchors the cycle — collection, graph and products all
            answer back to it. Add one to get started.
          </p>
        )}

        {pirs.map(pir => (
          <div key={pir.id} className="rounded-md p-3" style={{ backgroundColor: colors.containerLow }}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <Pill label={pir.status} color={STATUS_COLOR[pir.status] || '#6b7280'} />
                  <Pill label={pir.priority} color={PRIORITY_COLOR[pir.priority] || '#6b7280'} />
                  <span className="text-xs font-semibold text-gray-200 truncate">{pir.title}</span>
                </div>
                {/* An untitled PIR gets its title derived from its own text, so
                    rendering both would just print the requirement twice. */}
                {pir.text !== pir.title && (
                  <p className="text-xs text-gray-300 mt-2 leading-relaxed">{pir.text}</p>
                )}
                {pir.refined_text && pir.refined_text !== pir.text && (
                  <p className="text-[11px] mt-1.5" style={{ color: colors.primary }}>
                    Refined: {pir.refined_text}
                  </p>
                )}
                {pir.eeis.length > 0 && (
                  <RequirementMatrix pirId={pir.id} eeis={pir.eeis} />
                )}
              </div>
              <div className="flex flex-col items-end gap-1.5 shrink-0">
                <select
                  value={pir.status}
                  onChange={e => setStatus(pir, e.target.value as PirStatus)}
                  aria-label="PIR status"
                  className="rounded-md px-2 py-1 text-[10px] text-gray-300 outline-none"
                  style={{ backgroundColor: colors.container, border: '1px solid rgba(255,255,255,0.08)' }}
                >
                  {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
                <div className="flex gap-2">
                  <button
                    onClick={() => router.push(`/collections?pir=${encodeURIComponent(pir.id)}`)}
                    className="text-[11px] font-medium hover:underline"
                    style={{ color: colors.primary }}
                  >
                    Collect &rarr;
                  </button>
                  <button onClick={() => startEdit(pir)} className="text-[11px] text-gray-400 hover:underline">
                    Edit
                  </button>
                  <button
                    onClick={() => remove(pir)}
                    className="text-[11px] hover:underline"
                    style={{ color: colors.tertiary }}
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>

            {/* The chain: the collection plans this requirement drove */}
            {pir.plans.length > 0 && (
              <div className="mt-3 pt-2 flex flex-wrap gap-2" style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                <span className="text-[10px] uppercase tracking-widest text-gray-500 self-center">Collection</span>
                {pir.plans.map(plan => (
                  <button
                    key={plan.id}
                    onClick={() => router.push('/collections')}
                    className="text-[10px] px-2 py-1 rounded-md text-gray-300 hover:text-white"
                    style={{ backgroundColor: colors.container }}
                    title={`${plan.status} · ${plan.source_count} source(s) · ${plan.records_acquired} record(s)`}
                  >
                    {plan.name.length > 48 ? `${plan.name.slice(0, 48)}...` : plan.name}
                    <span className="ml-1.5 text-gray-500">{plan.status}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
