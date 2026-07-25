'use client';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  attackApi,
  AttackD3fendCountermeasure,
  AttackMapMethod,
  AttackMatrixData,
  AttackReport,
  AttackTechniqueCell,
  AttackTechniqueDetail,
} from '@/lib/api';
import { TYPE_BADGE_CLASS } from '@/lib/entityStyles';
import LoadingSpinner from '@/components/LoadingSpinner';
import Markdown from '@/components/Markdown';

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

// Strip a leading "d3f:" so we can show the bare code, then rebuild the
// canonical D3FEND URL. Robust whether the backend sends "d3f:X" or "X".
function d3fendBareId(id: string): string {
  return id.replace(/^d3f:/i, '');
}
function d3fendExternalUrl(cm: AttackD3fendCountermeasure): string {
  // The canonical D3FEND page uses the d3f: local name (e.g. d3f:DataInventory);
  // the short code (D3-DI) does NOT resolve as a slug. Prefer the backend-supplied
  // `name`, falling back to a PascalCase of the label.
  const slug = (cm.name || '').trim() || cm.label.replace(/[^A-Za-z0-9]/g, '');
  return `https://d3fend.mitre.org/technique/d3f:${slug}/`;
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
  // Lazy D3FEND countermeasures for the open technique. null = not loaded yet,
  // [] = loaded but none found. Reset whenever the drawer target changes.
  const [d3fend, setD3fend] = useState<AttackD3fendCountermeasure[] | null>(null);
  const [d3fendLoading, setD3fendLoading] = useState(false);
  const [d3fendError, setD3fendError] = useState(false);

  // ATT&CK report modal
  const [reportOpen, setReportOpen] = useState(false);
  const [report, setReport] = useState<AttackReport | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState(false);
  const [reportCopied, setReportCopied] = useState(false);

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
    setMapNote(null);
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
      // Was a silent no-op: the button spun, nothing downloaded, nothing said.
      setMapNote({ text: 'Could not build the Navigator layer. Check the backend and try again.', tone: 'warn' });
    } finally {
      setDownloading(false);
    }
  }

  // Generate the project's ATT&CK report and open the modal. Opens immediately
  // (with a spinner) so the analyst gets feedback while the backend aggregates.
  async function handleGenerateReport() {
    setReportOpen(true);
    setReport(null);
    setReportError(false);
    setReportCopied(false);
    setReportLoading(true);
    try {
      const res = await attackApi.report(projectId);
      setReport(res.data);
    } catch {
      setReportError(true);
    } finally {
      setReportLoading(false);
    }
  }

  const closeReport = useCallback(() => {
    setReportOpen(false);
    setReportCopied(false);
  }, []);

  async function handleCopyReport() {
    if (!report) return;
    try {
      await navigator.clipboard.writeText(report.markdown);
      setReportCopied(true);
      setTimeout(() => setReportCopied(false), 2000);
    } catch {
      /* clipboard unavailable — silently ignore */
    }
  }

  function handleDownloadReport() {
    if (!report) return;
    const blob = new Blob([report.markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `attack-report-${projectId.substring(0, 8)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const openTechnique = useCallback(async (id: string) => {
    setSelectedId(id);
    setDetail(null);
    setDetailLoading(true);
    // Reset the lazy D3FEND state for the new technique.
    setD3fend(null);
    setD3fendError(false);
    setD3fendLoading(false);
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
    setD3fend(null);
    setD3fendError(false);
    setD3fendLoading(false);
  }, []);

  // Lazily fetch D3FEND countermeasures for the open technique (a live MITRE
  // lookup, so it can be slow or come back empty on an outage).
  const loadD3fend = useCallback(async () => {
    if (!selectedId) return;
    setD3fendLoading(true);
    setD3fendError(false);
    try {
      const res = await attackApi.d3fend(selectedId);
      setD3fend(res.data.countermeasures || []);
    } catch {
      setD3fendError(true);
    } finally {
      setD3fendLoading(false);
    }
  }, [selectedId]);

  // Close the detail drawer on Escape.
  useEffect(() => {
    if (!selectedId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeDrawer();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selectedId, closeDrawer]);

  // Close the report modal on Escape.
  useEffect(() => {
    if (!reportOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeReport();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [reportOpen, closeReport]);

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

          <button
            onClick={handleGenerateReport}
            disabled={reportLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md font-medium transition-colors disabled:opacity-50"
            style={{ backgroundColor: COVERED_BG, color: ACCENT, border: `1px solid ${COVERED_BORDER}` }}
            title="Generate an ATT&CK coverage report for this project"
            aria-label="Generate ATT&CK report"
          >
            <span className={`material-symbols-outlined text-[16px] ${reportLoading ? 'animate-spin' : ''}`}>
              {reportLoading ? 'progress_activity' : 'description'}
            </span>
            {reportLoading ? 'Generating…' : 'Generate ATT&CK Report'}
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

                  {/* Defenses — ATT&CK Mitigations (M-codes) plus the finer-grained
                      D3FEND countermeasures that complement them. */}
                  <div>
                    <h4 className="text-[10px] uppercase tracking-widest font-bold text-gray-400 mb-2">Defenses</h4>

                    {/* ATT&CK Mitigations (already in the technique detail) */}
                    <div className="mb-3">
                      <h5 className="text-[10px] font-semibold text-gray-500 mb-1.5">ATT&CK Mitigations</h5>
                      {detail.mitigations.length > 0 ? (
                        <div className="space-y-1">
                          {detail.mitigations.map((m) => (
                            <div key={m.id} className="text-xs rounded p-2 flex items-center gap-2" style={{ backgroundColor: '#1a1f2e' }}>
                              <span className="font-mono text-[11px] flex-shrink-0" style={{ color: ACCENT }}>{m.id}</span>
                              <span className="text-gray-300">{m.name}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-gray-500">No ATT&CK mitigations listed for this technique.</p>
                      )}
                    </div>

                    {/* D3FEND countermeasures — lazy live lookup; finer-grained
                        defensive coverage complementing the M-codes above. */}
                    <div>
                      <h5 className="text-[10px] font-semibold text-gray-500 mb-1">D3FEND Countermeasures</h5>
                      <p className="text-[11px] text-gray-500 mb-2 leading-snug">
                        Finer-grained defensive techniques from MITRE D3FEND that complement the ATT&amp;CK mitigations above.
                      </p>
                      {d3fend === null ? (
                        <button
                          onClick={loadD3fend}
                          disabled={d3fendLoading}
                          className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md font-medium transition-colors disabled:opacity-50"
                          style={{ backgroundColor: COVERED_BG, color: ACCENT, border: `1px solid ${COVERED_BORDER}` }}
                          aria-label="Load D3FEND countermeasures for this technique"
                        >
                          <span className={`material-symbols-outlined text-[16px] ${d3fendLoading ? 'animate-spin' : ''}`}>
                            {d3fendLoading ? 'progress_activity' : 'shield'}
                          </span>
                          {d3fendLoading ? 'Loading D3FEND…' : 'Load D3FEND countermeasures'}
                        </button>
                      ) : d3fendError ? (
                        <p className="text-xs text-gray-500">
                          Couldn&apos;t load D3FEND countermeasures.{' '}
                          <button onClick={loadD3fend} className="underline hover:brightness-125" style={{ color: ACCENT }}>
                            Retry
                          </button>
                        </p>
                      ) : d3fend.length === 0 ? (
                        <p className="text-xs text-gray-500">No D3FEND countermeasures found for this technique.</p>
                      ) : (
                        <div className="flex flex-wrap gap-1.5">
                          {d3fend.map((cm) => (
                            <a
                              key={cm.id}
                              href={d3fendExternalUrl(cm)}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded transition-colors hover:brightness-125"
                              style={{ backgroundColor: COVERED_BG, color: ACCENT, border: `1px solid ${COVERED_BORDER}` }}
                              title={`${cm.label} — open on d3fend.mitre.org`}
                            >
                              <span className="font-mono">{d3fendBareId(cm.id)}</span>
                              <span className="text-gray-300 max-w-[180px] truncate">{cm.label}</span>
                              <span className="material-symbols-outlined text-[12px]">open_in_new</span>
                            </a>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

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

                  {/* Enabling CVEs — the project's Vulnerability entities whose
                      weakness chain (CWE→CAPEC) could enable this technique. This is
                      *potential* enablement inferred from the CVE's weaknesses, not
                      an observed TTP; keep that framing in the caption. */}
                  {detail.enabling_cves && detail.enabling_cves.length > 0 && (
                    <div>
                      <h4 className="text-[10px] uppercase tracking-widest font-bold text-gray-400 mb-1.5">Enabling CVEs</h4>
                      <p className="text-[11px] text-gray-500 mb-2 leading-snug">
                        CVEs in this project whose weaknesses (CWE→CAPEC) could enable this technique — potential
                        enablement, distinct from an observed TTP.
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {detail.enabling_cves.map((cve) => (
                          <button
                            key={cve.id}
                            onClick={() => router.push(`/network?select=${cve.id}`)}
                            className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-1 rounded transition-colors hover:brightness-125"
                            style={{ backgroundColor: COVERED_BG, color: ACCENT, border: `1px solid ${COVERED_BORDER}` }}
                            aria-label={`Open ${cve.name} in the network graph`}
                            title={`${cve.name} — could enable this technique via its weakness chain`}
                          >
                            <span className="material-symbols-outlined text-[13px]">bug_report</span>
                            {cve.name}
                            <span className="material-symbols-outlined text-[13px]">arrow_forward</span>
                          </button>
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

      {/* ATT&CK report modal */}
      {reportOpen && (
        <>
          <div
            className="fixed inset-0 z-40"
            style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
            onClick={closeReport}
            aria-hidden="true"
          />
          <div className="fixed inset-0 z-50 flex items-start justify-center p-4 sm:p-8 pointer-events-none">
            <div
              role="dialog"
              aria-modal="true"
              aria-label="ATT&CK report"
              className="w-full max-w-3xl flex flex-col rounded-lg shadow-2xl pointer-events-auto"
              style={{ backgroundColor: '#131826', border: '1px solid #2f3444', maxHeight: 'calc(100vh - 4rem)' }}
            >
              {/* Header + actions */}
              <div
                className="flex items-start justify-between gap-3 px-5 py-4"
                style={{ borderBottom: '1px solid #2f3444' }}
              >
                <div className="min-w-0">
                  <h3 className="text-[10px] uppercase tracking-widest font-bold text-gray-400">MITRE ATT&CK® Report</h3>
                  <p className="text-sm font-semibold text-white mt-0.5">Coverage &amp; candidate attribution</p>
                </div>
                <div className="flex flex-wrap items-center justify-end gap-2 flex-shrink-0">
                  {report && !reportLoading && !reportError && (
                    <>
                      <button
                        onClick={handleCopyReport}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] rounded-md font-medium transition-colors"
                        style={{ backgroundColor: '#1a1f2e', color: ACCENT, border: '1px solid #2f3444' }}
                        aria-label="Copy report markdown to clipboard"
                      >
                        <span className="material-symbols-outlined text-[14px]">{reportCopied ? 'check' : 'content_copy'}</span>
                        {reportCopied ? 'Copied' : 'Copy markdown'}
                      </button>
                      <button
                        onClick={handleDownloadReport}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] rounded-md font-medium transition-colors"
                        style={{ backgroundColor: '#1a1f2e', color: ACCENT, border: '1px solid #2f3444' }}
                        aria-label="Download report as a markdown file"
                      >
                        <span className="material-symbols-outlined text-[14px]">download</span>
                        Download .md
                      </button>
                      <button
                        onClick={handleDownloadLayer}
                        disabled={downloading}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] rounded-md font-medium transition-colors disabled:opacity-50"
                        style={{ backgroundColor: '#1a1f2e', color: ACCENT, border: '1px solid #2f3444' }}
                        aria-label="Download ATT&CK Navigator layer"
                      >
                        <span className="material-symbols-outlined text-[14px]">layers</span>
                        {downloading ? 'Preparing…' : 'Navigator layer'}
                      </button>
                    </>
                  )}
                  <button
                    onClick={closeReport}
                    className="text-gray-400 hover:text-white flex-shrink-0"
                    aria-label="Close report"
                  >
                    <span className="material-symbols-outlined">close</span>
                  </button>
                </div>
              </div>

              {/* Body */}
              <div className="px-5 py-4 overflow-y-auto">
                {reportLoading ? (
                  <div className="py-8">
                    <LoadingSpinner size="md" />
                    <p className="text-center text-xs text-gray-500 mt-3">Aggregating ATT&amp;CK coverage…</p>
                  </div>
                ) : reportError ? (
                  <div className="text-center py-8">
                    <p className="text-sm text-gray-400">Couldn&apos;t generate the ATT&amp;CK report.</p>
                    <button
                      onClick={handleGenerateReport}
                      className="mt-3 px-3 py-1.5 text-xs rounded-md font-medium transition-colors"
                      style={{ backgroundColor: COVERED_BG, color: ACCENT, border: `1px solid ${COVERED_BORDER}` }}
                    >
                      Retry
                    </button>
                  </div>
                ) : !report ? null : !report.narrative && !report.markdown.trim() ? (
                  // Valid response but nothing to report yet (empty project).
                  <div className="text-center py-8">
                    <span className="material-symbols-outlined text-[32px]" style={{ color: '#4b5563' }}>
                      description
                    </span>
                    <p className="text-sm text-gray-400 mt-2">No ATT&amp;CK observations to report yet.</p>
                    <p className="text-xs text-gray-600 mt-1 max-w-sm mx-auto">
                      Map this project&apos;s TTPs to ATT&amp;CK (&ldquo;Map TTPs&rdquo; above), then generate the report again.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {/* Optional LLM narrative */}
                    {report.narrative && (
                      <div
                        className="rounded-md px-3 py-2.5 text-sm text-gray-200"
                        style={{ backgroundColor: 'rgba(173,198,255,0.08)', border: `1px solid ${COVERED_BORDER}` }}
                      >
                        <Markdown content={report.narrative} className="text-sm" />
                      </div>
                    )}

                    {/* Attribution framing — keep it suggestive, not confirmed. */}
                    {report.attribution && report.attribution.length > 0 && (
                      <p className="text-[11px] text-gray-500 flex items-start gap-1.5">
                        <span className="material-symbols-outlined text-[14px] flex-shrink-0" style={{ color: '#9ca3af' }}>info</span>
                        <span>
                          Any attribution below is <span className="text-gray-400">candidate / suggestive</span> technique overlap
                          &mdash; a lead to investigate, not confirmed attribution.
                        </span>
                      </p>
                    )}

                    {/* Rendered report markdown (XSS-safe: no raw HTML) */}
                    <Markdown content={report.markdown} className="text-sm" />
                  </div>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
