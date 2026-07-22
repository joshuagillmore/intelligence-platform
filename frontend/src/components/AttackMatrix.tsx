'use client';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  attackApi,
  AttackMapMethod,
  AttackMatrixData,
  AttackTechniqueCell,
  AttackTechniqueDetail,
} from '@/lib/api';
import { TYPE_BADGE_CLASS } from '@/lib/entityStyles';
import LoadingSpinner from '@/components/LoadingSpinner';

// Surface colors reused from the cyber page's navy/dark palette.
const COVERED_BG = 'rgba(173,198,255,0.15)';
const COVERED_BORDER = 'rgba(173,198,255,0.3)';
const ACCENT = '#adc6ff';

/**
 * Build the canonical attack.mitre.org URL for a technique id.
 * "T1566" -> /techniques/T1566/ ; "T1566.001" -> /techniques/T1566/001/
 */
function techniqueExternalUrl(id: string): string {
  if (id.includes('.')) {
    const [base, sub] = id.split('.');
    return `https://attack.mitre.org/techniques/${base}/${sub}/`;
  }
  return `https://attack.mitre.org/techniques/${id}/`;
}

// A technique counts as covered if it, or any of its sub-techniques, was observed.
function isTechniqueCovered(t: AttackTechniqueCell): boolean {
  return t.observed_count > 0 || t.subtechniques.some((s) => s.observed_count > 0);
}

function badgeClass(entityType: string): string {
  return TYPE_BADGE_CLASS[entityType] || 'bg-gray-900/30 text-gray-400';
}

// A small badge distinguishing an AI (RAG+LLM) mapping from explicit T-code
// resolution. AI mappings always show, with their confidence; T-code is the
// implicit baseline and only labelled when `showTcode` is set (detail drawer).
function MethodBadge({
  method,
  confidence,
  showTcode = false,
}: {
  method?: AttackMapMethod;
  confidence?: number | null;
  showTcode?: boolean;
}) {
  if (method === 'llm') {
    const pct = typeof confidence === 'number' ? Math.round(confidence * 100) : null;
    return (
      <span
        className="inline-flex items-center gap-0.5 text-[9px] font-bold rounded px-1 py-0.5 flex-shrink-0 leading-none"
        style={{
          backgroundColor: 'rgba(96,165,250,0.18)',
          color: '#93c5fd',
          border: '1px solid rgba(96,165,250,0.35)',
        }}
        title={`AI-mapped (RAG + LLM)${pct !== null ? ` — ${pct}% confidence` : ''}`}
      >
        <span className="material-symbols-outlined text-[11px] leading-none">auto_awesome</span>
        AI{pct !== null ? ` ${pct}%` : ''}
      </span>
    );
  }
  if (method === 'tcode' && showTcode) {
    return (
      <span
        className="text-[9px] font-medium rounded px-1 py-0.5 flex-shrink-0 leading-none"
        style={{ backgroundColor: '#2f3444', color: '#9ca3af' }}
        title="Resolved from an explicit ATT&CK T-code"
      >
        T-code
      </span>
    );
  }
  return null;
}

// A technique cell counts as AI-mapped when its rolled-up methods include "llm".
// The backend already unions a technique's own + its sub-techniques' methods into
// the top-level cell's `methods`, so no manual sub rollup is needed here.
function cellIsAiMapped(t: AttackTechniqueCell): boolean {
  return (t.methods || []).includes('llm');
}

export default function AttackMatrix({
  projectId,
  focusTechniqueId,
  onFocusConsumed,
}: {
  projectId: string;
  focusTechniqueId?: string | null;
  onFocusConsumed?: () => void;
}) {
  const router = useRouter();
  const [matrix, setMatrix] = useState<AttackMatrixData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [mapping, setMapping] = useState(false);
  const [embedding, setEmbedding] = useState(false);
  // Post-action feedback for the AI map / embed flow, and a flag that steers the
  // analyst to embed techniques first when a map yields nothing.
  const [mapNote, setMapNote] = useState<{ text: string; tone: 'ok' | 'warn' } | null>(null);
  const [needsEmbed, setNeedsEmbed] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [showOnlyCovered, setShowOnlyCovered] = useState(false);
  const [expandedTechniques, setExpandedTechniques] = useState<Record<string, boolean>>({});

  // Technique detail drawer
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AttackTechniqueDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadMatrix = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(false);
    try {
      const res = await attackApi.matrix(projectId);
      setMatrix(res.data);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadMatrix();
  }, [loadMatrix]);

  async function handleIngest() {
    setIngesting(true);
    try {
      await attackApi.ingest();
      await loadMatrix();
    } catch {
      setError(true);
    } finally {
      setIngesting(false);
    }
  }

  // Re-map the project's TTPs onto techniques, then reload so newly-extracted
  // TTPs show up as covered.
  async function handleResolve() {
    setResolving(true);
    try {
      await attackApi.resolve(projectId);
      await loadMatrix();
    } catch {
      /* ignore — matrix still shows last-known coverage */
    } finally {
      setResolving(false);
    }
  }

  // AI mapping: RAG+LLM map the project's TTPs that lack an explicit T-code, then
  // reload so newly-mapped techniques light up. Slow — the button shows a spinner.
  // A 0-mapped result with entities skipped is the signal techniques aren't
  // embedded yet, so we surface the Embed affordance.
  async function handleMap() {
    setMapping(true);
    setMapNote(null);
    try {
      const res = await attackApi.map(projectId);
      const { mapped, skipped } = res.data;
      if (mapped > 0) {
        setNeedsEmbed(false);
        setMapNote({
          text: `AI mapped ${mapped} TTP${mapped === 1 ? '' : 's'} to ATT&CK${skipped ? ` · ${skipped} skipped` : ''}.`,
          tone: 'ok',
        });
        await loadMatrix();
      } else if (skipped > 0) {
        // Nothing mapped but TTPs were considered — most likely techniques
        // aren't embedded yet. Point the analyst at the one-time Embed step.
        setNeedsEmbed(true);
        setMapNote({
          text: `No TTPs were mapped. If you haven't embedded techniques yet, run "Embed techniques" first, then map again.`,
          tone: 'warn',
        });
      } else {
        setMapNote({ text: 'No unmapped TTPs to map — everything with a match is already resolved.', tone: 'ok' });
      }
    } catch {
      setMapNote({ text: 'AI mapping failed. Check the backend LLM/embedding provider and try again.', tone: 'warn' });
    } finally {
      setMapping(false);
    }
  }

  // Admin one-time step: embed the 697 ATT&CK techniques into pgvector so RAG
  // mapping has candidates to retrieve. Idempotent and slow (~30-90s).
  async function handleEmbed() {
    setEmbedding(true);
    setMapNote(null);
    try {
      const res = await attackApi.embed();
      setNeedsEmbed(false);
      setMapNote({
        text: `Embedded ${res.data.embedded} techniques. You can now map TTPs with AI.`,
        tone: 'ok',
      });
    } catch {
      setMapNote({ text: 'Embedding failed. Check the backend embedding provider and try again.', tone: 'warn' });
    } finally {
      setEmbedding(false);
    }
  }

  async function handleDownloadLayer() {
    setDownloading(true);
    try {
      const res = await attackApi.navigatorLayer(projectId);
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `attack-navigator-layer-${projectId.substring(0, 8)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      /* ignore */
    } finally {
      setDownloading(false);
    }
  }

  const openTechnique = useCallback(async (id: string) => {
    setSelectedId(id);
    setDetail(null);
    setDetailLoading(true);
    try {
      const res = await attackApi.technique(id, projectId);
      setDetail(res.data);
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }, [projectId]);

  const closeDrawer = useCallback(() => {
    setSelectedId(null);
    setDetail(null);
  }, []);

  // Close the detail drawer on Escape.
  useEffect(() => {
    if (!selectedId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeDrawer();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selectedId, closeDrawer]);

  // Open a technique's drawer when a parent view requests focus (e.g. clicking a
  // shared technique in the attribution panel switches to this tab and deep-links
  // the drawer). Consume the request so it fires only once.
  useEffect(() => {
    if (!focusTechniqueId) return;
    openTechnique(focusTechniqueId);
    onFocusConsumed?.();
  }, [focusTechniqueId, openTechnique, onFocusConsumed]);

  // Coverage headline — dedupe technique ids so techniques that appear under
  // multiple tactics aren't double-counted.
  const coverage = useMemo(() => {
    const all = new Set<string>();
    const observed = new Set<string>();
    (matrix?.tactics || []).forEach((tactic) => {
      tactic.techniques.forEach((tech) => {
        all.add(tech.id);
        if (tech.observed_count > 0) observed.add(tech.id);
        tech.subtechniques.forEach((sub) => {
          all.add(sub.id);
          if (sub.observed_count > 0) observed.add(sub.id);
        });
      });
    });
    return { observed: observed.size, total: all.size };
  }, [matrix]);

  // Tactics with per-tactic technique lists, filtered by the "show only
  // covered" toggle. Tactics left with no visible techniques are dropped.
  const visibleTactics = useMemo(() => {
    const tactics = matrix?.tactics || [];
    if (!showOnlyCovered) return tactics;
    return tactics
      .map((tactic) => ({
        ...tactic,
        techniques: tactic.techniques.filter(isTechniqueCovered),
      }))
      .filter((tactic) => tactic.techniques.length > 0);
  }, [matrix, showOnlyCovered]);

  if (loading) {
    return (
      <div className="rounded-lg p-8" style={{ backgroundColor: '#1a1f2e', border: '1px solid #2f3444' }}>
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg p-8 text-center" style={{ backgroundColor: '#1a1f2e', border: '1px solid #2f3444' }}>
        <p className="text-gray-300">Couldn&apos;t load the MITRE ATT&CK® matrix.</p>
        <button
          onClick={loadMatrix}
          className="mt-4 px-4 py-2 text-sm rounded-md font-medium transition-colors"
          style={{ backgroundColor: COVERED_BG, color: ACCENT, border: `1px solid ${COVERED_BORDER}` }}
        >
          Retry
        </button>
      </div>
    );
  }

  // ATT&CK data not loaded yet — offer the one-time ingest.
  if (matrix && !matrix.ingested) {
    return (
      <div
        className="rounded-lg p-10 text-center flex flex-col items-center"
        style={{ backgroundColor: '#1a1f2e', border: '1px solid #2f3444' }}
      >
        <span className="material-symbols-outlined text-[40px]" style={{ color: ACCENT }}>
          grid_view
        </span>
        <h3 className="text-lg font-semibold text-white mt-3">MITRE ATT&CK® data not loaded</h3>
        <p className="text-sm text-gray-400 mt-2 max-w-md">
          Load the ATT&CK Enterprise knowledge base to map this project&apos;s observed TTPs onto
          the full tactics-and-techniques matrix. This downloads the dataset server-side and may
          take up to a minute.
        </p>
        <button
          onClick={handleIngest}
          disabled={ingesting}
          className="mt-5 flex items-center gap-2 px-4 py-2.5 text-sm rounded-md font-medium transition-colors disabled:opacity-60"
          style={{ backgroundColor: ACCENT, color: '#0e1321' }}
          aria-label="Ingest MITRE ATT&CK data"
        >
          {ingesting && <span className="material-symbols-outlined text-[18px] animate-spin">progress_activity</span>}
          {ingesting ? 'Ingesting ATT&CK data…' : 'Ingest ATT&CK data'}
        </button>
      </div>
    );
  }

  return (
    <div>
      {/* Header: coverage headline + actions */}
      <div className="flex flex-col md:flex-row md:items-start justify-between mb-4 gap-3">
        <div>
          <h3 className="text-[10px] uppercase tracking-widest font-bold text-gray-400">
            MITRE ATT&CK® Coverage
          </h3>
          <p className="text-sm text-gray-300 mt-1">
            <span className="font-semibold" style={{ color: ACCENT }}>{coverage.observed}</span>
            {' '}of {coverage.total} techniques observed
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md font-medium cursor-pointer select-none"
            style={{ backgroundColor: '#1a1f2e', color: '#9ca3af', border: '1px solid #2f3444' }}
          >
            <input
              type="checkbox"
              checked={showOnlyCovered}
              onChange={(e) => setShowOnlyCovered(e.target.checked)}
              className="accent-[#adc6ff]"
            />
            Show only covered
          </label>

          <button
            onClick={handleResolve}
            disabled={resolving}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md font-medium transition-colors disabled:opacity-50"
            style={{ backgroundColor: '#1a1f2e', color: ACCENT, border: '1px solid #2f3444' }}
            title="Re-map this project's TTPs onto ATT&CK techniques"
            aria-label="Refresh ATT&CK coverage from project TTPs"
          >
            <span className={`material-symbols-outlined text-[16px] ${resolving ? 'animate-spin' : ''}`}>refresh</span>
            {resolving ? 'Refreshing…' : 'Refresh'}
          </button>

          <button
            onClick={handleMap}
            disabled={mapping}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md font-medium transition-colors disabled:opacity-50"
            style={{ backgroundColor: 'rgba(96,165,250,0.15)', color: '#93c5fd', border: '1px solid rgba(96,165,250,0.35)' }}
            title="Use RAG + LLM to map prose TTPs (no explicit T-code) onto ATT&CK techniques — can be slow"
            aria-label="Map TTPs to ATT&CK techniques with AI"
          >
            <span className={`material-symbols-outlined text-[16px] ${mapping ? 'animate-spin' : ''}`}>
              {mapping ? 'progress_activity' : 'auto_awesome'}
            </span>
            {mapping ? 'Mapping…' : 'Map TTPs → ATT&CK (AI)'}
          </button>

          <button
            onClick={handleDownloadLayer}
            disabled={downloading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md font-medium transition-colors disabled:opacity-50"
            style={{ backgroundColor: '#1a1f2e', color: ACCENT, border: '1px solid #2f3444' }}
            title="Download an ATT&CK Navigator layer for this project"
            aria-label="Download ATT&CK Navigator layer"
          >
            <span className="material-symbols-outlined text-[16px]">download</span>
            {downloading ? 'Preparing…' : 'Navigator layer'}
          </button>

          {/* One-time admin: embed techniques into pgvector so AI mapping has
              candidates. Highlighted when a map came back empty (likely un-embedded). */}
          <button
            onClick={handleEmbed}
            disabled={embedding}
            className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] rounded-md transition-colors disabled:opacity-50"
            style={
              needsEmbed
                ? { backgroundColor: 'rgba(96,165,250,0.15)', color: '#93c5fd', border: '1px solid rgba(96,165,250,0.45)' }
                : { backgroundColor: 'transparent', color: '#6b7280', border: '1px solid #2f3444' }
            }
            title="One-time admin step: embed all ATT&CK techniques so AI mapping can retrieve candidates (~30-90s)"
            aria-label="Embed ATT&CK techniques for AI mapping"
          >
            <span className={`material-symbols-outlined text-[14px] ${embedding ? 'animate-spin' : ''}`}>
              {embedding ? 'progress_activity' : 'database'}
            </span>
            {embedding ? 'Embedding…' : 'Embed techniques'}
          </button>

          {/* Subtle re-sync affordance + current dataset version. */}
          <button
            onClick={handleIngest}
            disabled={ingesting}
            className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] rounded-md transition-colors disabled:opacity-50"
            style={{ backgroundColor: 'transparent', color: '#6b7280', border: '1px solid #2f3444' }}
            title="Re-download the latest ATT&CK dataset"
            aria-label="Re-sync ATT&CK dataset"
          >
            <span className={`material-symbols-outlined text-[14px] ${ingesting ? 'animate-spin' : ''}`}>sync</span>
            {ingesting ? 'Syncing…' : `Re-sync${matrix?.version ? ` • v${matrix.version}` : ''}`}
          </button>
        </div>
      </div>

      {/* AI map / embed feedback */}
      {mapNote && (
        <div
          role="status"
          className="flex items-start gap-2 rounded-md px-3 py-2 mb-3 text-xs"
          style={
            mapNote.tone === 'warn'
              ? { backgroundColor: 'rgba(234,179,8,0.1)', color: '#fcd34d', border: '1px solid rgba(234,179,8,0.3)' }
              : { backgroundColor: 'rgba(96,165,250,0.1)', color: '#93c5fd', border: '1px solid rgba(96,165,250,0.3)' }
          }
        >
          <span className="material-symbols-outlined text-[16px] flex-shrink-0">
            {mapNote.tone === 'warn' ? 'info' : 'check_circle'}
          </span>
          <span className="flex-1">{mapNote.text}</span>
          <button
            onClick={() => setMapNote(null)}
            aria-label="Dismiss message"
            className="flex-shrink-0 hover:brightness-125"
          >
            <span className="material-symbols-outlined text-[16px]">close</span>
          </button>
        </div>
      )}

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs text-gray-400 mb-3">
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded inline-block" style={{ backgroundColor: ACCENT }} /> Observed
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded inline-block" style={{ backgroundColor: '#1a1f2e', border: '1px solid #2f3444' }} /> Not observed
        </span>
      </div>

      {/* Matrix — one column per tactic, horizontally scrollable */}
      {visibleTactics.length === 0 ? (
        <div className="rounded-lg p-8 text-center text-gray-500" style={{ backgroundColor: '#1a1f2e', border: '1px solid #2f3444' }}>
          <p>No observed techniques yet.</p>
          <p className="text-xs mt-1 text-gray-600">Toggle off &ldquo;Show only covered&rdquo; to see the full matrix, or Refresh after extracting TTPs.</p>
        </div>
      ) : (
        <div className="overflow-x-auto pb-4" style={{ height: 'calc(100vh - 320px)' }}>
          <div className="flex gap-2 min-w-max">
            {visibleTactics.map((tactic) => (
              <div key={tactic.id} className="flex flex-col w-44 flex-shrink-0">
                {/* Tactic header */}
                <div className="rounded-t-lg px-3 py-2 text-center sticky top-0 z-10" style={{ backgroundColor: '#2f3444' }}>
                  <div className="text-[10px] uppercase tracking-widest font-bold text-white leading-tight">{tactic.name}</div>
                  <div className="text-[10px] text-gray-500 mt-0.5">{tactic.techniques.length} techniques</div>
                </div>
                {/* Technique cells */}
                <div className="flex flex-col gap-1 mt-1">
                  {tactic.techniques.map((tech) => {
                    const covered = isTechniqueCovered(tech);
                    const isSelected = selectedId === tech.id;
                    const subCount = tech.subtechniques.length;
                    const isExpanded = expandedTechniques[tech.id];
                    return (
                      <div key={`${tactic.id}-${tech.id}`}>
                        <div
                          className={`rounded px-2 py-2 transition-all ${isSelected ? 'ring-1 ring-[#adc6ff]' : ''}`}
                          style={{
                            backgroundColor: covered ? COVERED_BG : '#1a1f2e',
                            border: covered ? `1px solid ${COVERED_BORDER}` : '1px solid #2f3444',
                          }}
                        >
                          <button
                            onClick={() => openTechnique(tech.id)}
                            className="w-full text-left"
                            aria-label={`Open detail for ${tech.name} (${tech.id})`}
                          >
                            <div className="flex items-start justify-between gap-1">
                              <div className="text-[11px] font-medium leading-tight" style={{ color: covered ? ACCENT : '#9ca3af' }}>
                                {tech.name}
                              </div>
                              {tech.observed_count > 0 && (
                                <span
                                  className="text-[9px] font-bold rounded-full px-1.5 py-0.5 flex-shrink-0"
                                  style={{ backgroundColor: ACCENT, color: '#0e1321' }}
                                  title={`${tech.observed_count} observed in this project`}
                                >
                                  {tech.observed_count}
                                </span>
                              )}
                            </div>
                            <div className="text-[10px] text-gray-500 mt-0.5">{tech.id}</div>
                            {cellIsAiMapped(tech) && (
                              <div className="mt-1">
                                <MethodBadge method="llm" />
                              </div>
                            )}
                          </button>
                          {subCount > 0 && (
                            <button
                              onClick={() => setExpandedTechniques((prev) => ({ ...prev, [tech.id]: !prev[tech.id] }))}
                              className="mt-1 flex items-center gap-0.5 text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
                              aria-label={`${isExpanded ? 'Hide' : 'Show'} ${subCount} sub-techniques of ${tech.id}`}
                              aria-expanded={isExpanded}
                            >
                              <span className="material-symbols-outlined text-[14px]">{isExpanded ? 'expand_less' : 'expand_more'}</span>
                              {subCount} sub{subCount === 1 ? '' : 's'}
                            </button>
                          )}
                        </div>
                        {/* Sub-technique list */}
                        {isExpanded && subCount > 0 && (
                          <div className="flex flex-col gap-1 mt-1 ml-2 pl-1" style={{ borderLeft: '1px solid #2f3444' }}>
                            {tech.subtechniques.map((sub) => {
                              const subCovered = sub.observed_count > 0;
                              const subSelected = selectedId === sub.id;
                              return (
                                <button
                                  key={`${tactic.id}-${sub.id}`}
                                  onClick={() => openTechnique(sub.id)}
                                  className={`rounded px-2 py-1.5 text-left transition-all ${subSelected ? 'ring-1 ring-[#adc6ff]' : ''}`}
                                  style={{
                                    backgroundColor: subCovered ? COVERED_BG : '#161b28',
                                    border: subCovered ? `1px solid ${COVERED_BORDER}` : '1px solid #2f3444',
                                  }}
                                  aria-label={`Open detail for ${sub.name} (${sub.id})`}
                                >
                                  <div className="flex items-start justify-between gap-1">
                                    <div className="text-[10px] leading-tight" style={{ color: subCovered ? ACCENT : '#9ca3af' }}>
                                      {sub.name}
                                    </div>
                                    {sub.observed_count > 0 && (
                                      <span
                                        className="text-[9px] font-bold rounded-full px-1.5 py-0.5 flex-shrink-0"
                                        style={{ backgroundColor: ACCENT, color: '#0e1321' }}
                                        title={`${sub.observed_count} observed in this project`}
                                      >
                                        {sub.observed_count}
                                      </span>
                                    )}
                                  </div>
                                  <div className="text-[9px] text-gray-500 mt-0.5">{sub.id}</div>
                                  {(sub.methods || []).includes('llm') && (
                                    <div className="mt-1">
                                      <MethodBadge method="llm" />
                                    </div>
                                  )}
                                </button>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Technique detail drawer */}
      {selectedId && (
        <>
          <div
            className="fixed inset-0 z-40"
            style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
            onClick={closeDrawer}
            aria-hidden="true"
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Technique detail"
            className="fixed top-0 right-0 z-50 h-full w-full max-w-md overflow-y-auto shadow-2xl"
            style={{ backgroundColor: '#131826', borderLeft: '1px solid #2f3444' }}
          >
            <div
              className="sticky top-0 flex items-start justify-between gap-3 px-5 py-4 z-10"
              style={{ backgroundColor: '#131826', borderBottom: '1px solid #2f3444' }}
            >
              <div>
                <div className="font-mono text-xs" style={{ color: ACCENT }}>{selectedId}</div>
                <h3 className="text-lg font-semibold text-white leading-tight mt-0.5">
                  {detail?.name || (detailLoading ? 'Loading…' : selectedId)}
                </h3>
              </div>
              <button
                onClick={closeDrawer}
                className="text-gray-400 hover:text-white flex-shrink-0"
                aria-label="Close technique detail"
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>

            <div className="px-5 py-4">
              {detailLoading ? (
                <LoadingSpinner size="md" />
              ) : !detail ? (
                <p className="text-sm text-gray-500">Couldn&apos;t load technique detail.</p>
              ) : (
                <div className="space-y-5">
                  {/* Tactic chips */}
                  {detail.tactics.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {detail.tactics.map((t) => (
                        <span
                          key={t.id}
                          className="text-[10px] px-2 py-0.5 rounded-full"
                          style={{ backgroundColor: COVERED_BG, color: ACCENT, border: `1px solid ${COVERED_BORDER}` }}
                        >
                          {t.name}
                        </span>
                      ))}
                    </div>
                  )}

                  {detail.description && (
                    <div>
                      <h4 className="text-[10px] uppercase tracking-widest font-bold text-gray-400 mb-1.5">Description</h4>
                      <p className="text-sm text-gray-300 whitespace-pre-line">{detail.description}</p>
                    </div>
                  )}

                  {detail.platforms.length > 0 && (
                    <div>
                      <h4 className="text-[10px] uppercase tracking-widest font-bold text-gray-400 mb-1.5">Platforms</h4>
                      <div className="flex flex-wrap gap-1.5">
                        {detail.platforms.map((p) => (
                          <span key={p} className="text-[10px] px-2 py-0.5 rounded" style={{ backgroundColor: '#2f3444', color: '#d1d5db' }}>
                            {p}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {detail.detection && (
                    <div>
                      <h4 className="text-[10px] uppercase tracking-widest font-bold text-gray-400 mb-1.5">Detection</h4>
                      <p className="text-sm text-gray-300 whitespace-pre-line">{detail.detection}</p>
                    </div>
                  )}

                  {detail.mitigations.length > 0 && (
                    <div>
                      <h4 className="text-[10px] uppercase tracking-widest font-bold text-gray-400 mb-1.5">Mitigations</h4>
                      <div className="space-y-1">
                        {detail.mitigations.map((m) => (
                          <div key={m.id} className="text-xs rounded p-2 flex items-center gap-2" style={{ backgroundColor: '#1a1f2e' }}>
                            <span className="font-mono text-[11px] flex-shrink-0" style={{ color: ACCENT }}>{m.id}</span>
                            <span className="text-gray-300">{m.name}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {detail.groups.length > 0 && (
                    <div>
                      <h4 className="text-[10px] uppercase tracking-widest font-bold text-gray-400 mb-1.5">Groups using this technique</h4>
                      <div className="space-y-1">
                        {detail.groups.map((g) => (
                          <div key={g.id} className="text-xs rounded p-2 flex items-center gap-2" style={{ backgroundColor: '#1a1f2e' }}>
                            <span className="font-mono text-[11px] flex-shrink-0" style={{ color: ACCENT }}>{g.id}</span>
                            <span className="text-gray-300">{g.name}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Related project entities — click through to the graph */}
                  <div>
                    <h4 className="text-[10px] uppercase tracking-widest font-bold text-gray-400 mb-1.5">Related entities in this project</h4>
                    {detail.related_entities.length > 0 ? (
                      <div className="space-y-1">
                        {detail.related_entities.map((ent) => (
                          <button
                            key={ent.id}
                            onClick={() => router.push(`/network?select=${ent.id}`)}
                            className="w-full text-left rounded p-2 flex items-center justify-between gap-2 transition-colors hover:brightness-125"
                            style={{ backgroundColor: '#2f3444' }}
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="text-sm font-mono text-white truncate">{ent.name}</span>
                              <span className={`text-[10px] px-2 py-0.5 rounded flex-shrink-0 ${badgeClass(ent.entity_type)}`}>
                                {ent.entity_type}
                              </span>
                              <MethodBadge method={ent.method} confidence={ent.confidence} showTcode />
                            </div>
                            <span className="material-symbols-outlined text-[16px] flex-shrink-0" style={{ color: ACCENT }}>arrow_forward</span>
                          </button>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-gray-500">No entities in this project map to this technique.</p>
                    )}
                  </div>

                  <a
                    href={techniqueExternalUrl(detail.id)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-xs font-medium transition-colors hover:underline"
                    style={{ color: ACCENT }}
                  >
                    View on attack.mitre.org
                    <span className="material-symbols-outlined text-[14px]">open_in_new</span>
                  </a>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
