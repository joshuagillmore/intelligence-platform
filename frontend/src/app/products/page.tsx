'use client';
import { useState, useCallback, useEffect, useMemo } from 'react';
import Sidebar from '@/components/Sidebar';
import SelectProjectPrompt from '@/components/SelectProjectPrompt';
import { useProject } from '@/lib/ProjectContext';
import { entitiesApi, reportsApi, exportApi } from '@/lib/api';
import { useNotifications } from '@/components/NotificationProvider';
import Markdown from '@/components/Markdown';
import PrintableProduct from '@/components/PrintableProduct';
import {
  buildProductFilename,
  buildProductMarkdown,
  normalizeClassification,
  type ProductDocument,
} from '@/lib/reportExport';

const REPORT_TYPES = [
  { value: 'threat_assessment', label: 'Threat Assessment', skill: 'threat_assessment', icon: 'warning', description: 'Evaluate threat actors, capabilities, and intent against targets' },
  { value: 'intsum', label: 'INTSUM', skill: 'report_writing', icon: 'description', description: 'Intelligence summary for a defined period or operation' },
  { value: 'network_brief', label: 'Network Analysis Brief', skill: 'report_writing', icon: 'hub', description: 'Map relationships and communication patterns across entities' },
  { value: 'indicator_report', label: 'Indicator Report', skill: 'report_writing', icon: 'fingerprint', description: 'Technical indicators of compromise with context and provenance' },
  { value: 'custom', label: 'Custom', skill: 'report_writing', icon: 'edit_note', description: 'Free-form intelligence product with custom structure' },
];

const ENTITY_COLORS: Record<string, string> = {
  'threat-actor': 'bg-red-500/20 text-red-300 border-red-500/30',
  'malware': 'bg-orange-500/20 text-orange-300 border-orange-500/30',
  'infrastructure': 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30',
  'campaign': 'bg-purple-500/20 text-purple-300 border-purple-500/30',
  'identity': 'bg-green-500/20 text-green-300 border-green-500/30',
  'vulnerability': 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
  'indicator': 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  'default': 'bg-[#adc6ff]/15 text-[#adc6ff] border-[#adc6ff]/30',
};

function getEntityColor(entityType: string) {
  const key = entityType.toLowerCase().replace(/[_ ]/g, '-');
  return ENTITY_COLORS[key] || ENTITY_COLORS['default'];
}

interface SearchedEntity {
  id: string;
  name: string;
  entity_type: string;
}

interface ReportHistoryItem {
  id: string;
  reportType: string;
  entities: string[];
  content: string;
  timestamp: Date;
}

interface SavedReport {
  id: string;
  title: string;
  content: string;
  report_type: string;
  created_at?: string;
  entity_ids?: string[];
  status?: string;
}

/**
 * Dissemination metadata for whichever report is currently on screen — a fresh
 * draft, a session-history item, or a saved report being viewed. Exports read
 * this so they describe the *selected* product, not the last generation.
 */
interface ProductContext {
  /** Identifies the report this context belongs to, so async updates can't land on a different one. */
  sourceId: string;
  title: string;
  reportTypeLabel: string;
  entities: string[];
  generatedAt: Date;
}

/** Cap on the per-ID name lookups a saved report triggers when opened. */
const ENTITY_RESOLVE_LIMIT = 25;

export default function ProductsPage() {
  const { activeProject } = useProject();
  const { addNotification, updateNotification } = useNotifications();
  const [reportType, setReportType] = useState('threat_assessment');
  const [entitySearch, setEntitySearch] = useState('');
  const [searchResults, setSearchResults] = useState<SearchedEntity[]>([]);
  const [selectedEntities, setSelectedEntities] = useState<SearchedEntity[]>([]);
  const [generatedReport, setGeneratedReport] = useState<string | null>(null);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [productContext, setProductContext] = useState<ProductContext | null>(null);
  const [reportMeta, setReportMeta] = useState<{ retrievalMode: string; contextNodes: number; contextEdges: number } | null>(null);
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [reportHistory, setReportHistory] = useState<ReportHistoryItem[]>([]);
  const [viewingHistoryId, setViewingHistoryId] = useState<string | null>(null);
  const [savedReports, setSavedReports] = useState<SavedReport[]>([]);
  const [savedReportsLoading, setSavedReportsLoading] = useState(false);
  const [saveLoading, setSaveLoading] = useState(false);
  const [saveTitle, setSaveTitle] = useState('');
  const [showSaveForm, setShowSaveForm] = useState(false);
  const [viewingSavedReport, setViewingSavedReport] = useState<SavedReport | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [includeEvidence, setIncludeEvidence] = useState(true);
  const [probabilityAssessments, setProbabilityAssessments] = useState(false);
  const [hoveredReportId, setHoveredReportId] = useState<string | null>(null);

  const searchEntities = useCallback(async (query: string) => {
    if (!query.trim() || !activeProject) {
      setSearchResults([]);
      return;
    }
    setSearching(true);
    try {
      const res = await entitiesApi.search(activeProject.id, query);
      setSearchResults((res.data || []).slice(0, 10));
    } catch {
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  }, [activeProject]);

  const loadSavedReports = useCallback(async () => {
    if (!activeProject) return;
    setSavedReportsLoading(true);
    try {
      const res = await reportsApi.list(activeProject.id);
      const rows = Array.isArray(res.data) ? res.data : res.data.reports || [];
      // Reports are Neo4j entities, so the API returns the title as `name`.
      // Normalise once here — everything downstream (panel header, export
      // filename and front matter, error messages) reads `.title`.
      setSavedReports(
        rows.map((r: SavedReport & { name?: string }) => ({
          ...r,
          title: r.title || r.name || r.report_type || 'Untitled report',
        })),
      );
    } catch {
      setSavedReports([]);
    } finally {
      setSavedReportsLoading(false);
    }
  }, [activeProject]);

  useEffect(() => {
    const timer = setTimeout(() => {
      searchEntities(entitySearch);
    }, 300);
    return () => clearTimeout(timer);
  }, [entitySearch, searchEntities]);

  useEffect(() => {
    loadSavedReports();
  }, [loadSavedReports]);

  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(null), 3000);
      return () => clearTimeout(t);
    }
  }, [toast]);

  /** The project's marking, verbatim from `classification_level` (null if unset). */
  const classificationMarking = useMemo(
    () => normalizeClassification(activeProject?.classification_level),
    [activeProject],
  );

  /**
   * The finished product currently on screen — a fresh draft, a history item or
   * a saved report — assembled with its dissemination metadata. Every export
   * path reads this, so they always act on what the analyst is looking at.
   * Null whenever there is no real report body (a generation failure never
   * produces one).
   */
  const currentProduct = useMemo<ProductDocument | null>(() => {
    if (!generatedReport || !activeProject || !productContext) return null;
    return {
      title: productContext.title,
      reportType: productContext.reportTypeLabel,
      classification: classificationMarking,
      projectName: activeProject.name,
      generatedAt: productContext.generatedAt,
      entities: productContext.entities,
      content: generatedReport,
    };
  }, [generatedReport, activeProject, productContext, classificationMarking]);

  function addEntity(entity: SearchedEntity) {
    if (!selectedEntities.find(e => e.id === entity.id)) {
      setSelectedEntities(prev => [...prev, entity]);
    }
    setEntitySearch('');
    setSearchResults([]);
  }

  function removeEntity(id: string) {
    setSelectedEntities(prev => prev.filter(e => e.id !== id));
  }

  async function generateReport() {
    if (selectedEntities.length === 0 || !activeProject) return;
    setLoading(true);
    setGeneratedReport(null);
    setGenerateError(null);
    setProductContext(null);
    setReportMeta(null);
    setViewingHistoryId(null);
    setViewingSavedReport(null);
    const rt = REPORT_TYPES.find(r => r.value === reportType);
    const notifId = addNotification({
      type: 'processing',
      title: 'Generating Report',
      message: `Creating ${rt?.label || reportType} report...`,
    });
    try {
      // Grounded generation: the backend retrieves real graph + document evidence
      // for these entities via the Graph-RAG pipeline before drafting — it doesn't
      // just hand the LLM a bare list of names.
      const res = await reportsApi.generate({
        project_id: activeProject.id,
        report_type: rt?.label || reportType,
        skill_name: rt?.skill || 'report_writing',
        entity_ids: selectedEntities.map(e => e.id),
        include_evidence: includeEvidence,
        probability_assessments: probabilityAssessments,
      });
      const content = res.data.content || JSON.stringify(res.data);
      setGeneratedReport(content);
      setReportMeta({
        retrievalMode: res.data.retrieval_mode || 'ungrounded',
        contextNodes: res.data.context_nodes || 0,
        contextEdges: res.data.context_edges || 0,
      });

      // Add to history
      const historyId = Date.now().toString();
      const draftedAt = new Date();
      setReportHistory(prev => [{
        id: historyId,
        reportType: rt?.label || reportType,
        entities: selectedEntities.map(e => e.name),
        content,
        timestamp: draftedAt,
      }, ...prev]);

      // Dissemination metadata for the export/print paths. An untitled draft is
      // named after its type and project until the analyst saves it under a title.
      setProductContext({
        sourceId: `draft:${historyId}`,
        title: `${rt?.label || reportType} — ${activeProject.name}`,
        reportTypeLabel: rt?.label || reportType,
        entities: selectedEntities.map(e => e.name),
        generatedAt: draftedAt,
      });

      const grounded = res.data.retrieval_mode === 'grounded';
      updateNotification(notifId, {
        type: 'success',
        title: 'Report Ready',
        message: grounded
          ? `${rt?.label || reportType} report generated from graph evidence.`
          : `${rt?.label || reportType} report generated — no supporting evidence was found for these entities.`,
        link: '/products',
      });
    } catch {
      // Surfaced as an alert + toast only. Writing it into `generatedReport`
      // would make an error string savable/exportable as if it were a product.
      setGenerateError('Report generation failed. Check that the LLM provider is configured and reachable, then try again.');
      updateNotification(notifId, {
        type: 'error',
        title: 'Report Failed',
        message: 'Report generation failed. Check LLM configuration.',
      });
    } finally {
      setLoading(false);
    }
  }

  async function saveReport() {
    if (!generatedReport || !activeProject || !saveTitle.trim()) return;
    setSaveLoading(true);
    try {
      await reportsApi.save({
        project_id: activeProject.id,
        title: saveTitle,
        content: generatedReport,
        report_type: reportType,
        entity_ids: selectedEntities.map(e => e.id),
      });
      // The draft now has an analyst-given title — carry it into the export header.
      const savedTitle = saveTitle;
      setProductContext(prev => (prev ? { ...prev, title: savedTitle } : prev));
      setShowSaveForm(false);
      setSaveTitle('');
      setToast('Report saved successfully.');
      loadSavedReports();
    } catch {
      setToast('Failed to save report.');
    } finally {
      setSaveLoading(false);
    }
  }

  async function deleteSavedReport(id: string) {
    if (!confirm('Are you sure you want to delete this saved report?')) return;
    try {
      await reportsApi.delete(id);
      setSavedReports(prev => prev.filter(r => r.id !== id));
      if (viewingSavedReport?.id === id) {
        setViewingSavedReport(null);
        setGeneratedReport(null);
        setProductContext(null);
      }
      setToast('Report deleted.');
    } catch {
      setToast('Failed to delete report.');
    }
  }

  /**
   * A saved report stores entity *ids*, not names. Resolve them so the exported
   * product can state what it covers. All-or-nothing on purpose: a partial list
   * would understate coverage, which is worse than stating none.
   */
  async function resolveEntityNames(ids: string[]): Promise<string[]> {
    if (ids.length === 0 || ids.length > ENTITY_RESOLVE_LIMIT) return [];
    const results = await Promise.allSettled(ids.map(id => entitiesApi.get(id)));
    const names = results
      .map(r => (r.status === 'fulfilled' ? (r.value.data?.entity?.name as string | undefined) : undefined))
      .filter((n): n is string => Boolean(n));
    return names.length === ids.length ? names : [];
  }

  async function viewSavedReport(report: SavedReport) {
    setViewingSavedReport(report);
    setViewingHistoryId(null);
    setReportMeta(null);
    setGenerateError(null);
    const sourceId = `saved:${report.id}`;
    setProductContext({
      sourceId,
      title: report.title,
      reportTypeLabel: getReportTypeLabel(report.report_type),
      entities: [],
      generatedAt: report.created_at ? new Date(report.created_at) : new Date(),
    });
    // If content is available directly, use it
    if (report.content) {
      setGeneratedReport(report.content);
    } else {
      // Fetch full content
      try {
        const res = await reportsApi.get(report.id);
        const full = res.data;
        setGeneratedReport(full.content || JSON.stringify(full));
      } catch {
        // Never let failure text become report content — it would be savable,
        // copyable and exportable as if it were the product. Also drop the
        // "viewing saved report" state, or the panel keeps its title header
        // with no body underneath.
        setGeneratedReport(null);
        setProductContext(null);
        setViewingSavedReport(null);
        setGenerateError('Could not load this saved report. It may have been deleted, or the backend is unreachable.');
        addNotification({
          type: 'error',
          title: 'Report Unavailable',
          message: `Failed to load "${report.title}".`,
        });
        return;
      }
    }
    const names = await resolveEntityNames(report.entity_ids || []);
    if (names.length > 0) {
      setProductContext(prev => (prev && prev.sourceId === sourceId ? { ...prev, entities: names } : prev));
    }
  }

  /**
   * Export the selected product as Markdown — the format it was drafted in, so
   * headings, tables and probability language survive intact — with a front
   * matter/header block carrying title, type, classification, date and coverage.
   */
  function exportAsMarkdown() {
    if (!currentProduct) return;
    try {
      const markdown = buildProductMarkdown(currentProduct);
      const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = buildProductFilename(currentProduct, 'md');
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      addNotification({
        type: 'error',
        title: 'Export Failed',
        message: 'Could not build the Markdown file for this product.',
      });
    }
  }

  /**
   * Hand the product to the browser's own print-to-PDF. `PrintableProduct`
   * renders the paginated, chrome-free layout under `@media print`, so no PDF
   * library is involved and the output works offline.
   */
  function exportAsPdf() {
    if (!currentProduct) return;
    try {
      window.print();
    } catch {
      addNotification({
        type: 'error',
        title: 'Print Unavailable',
        message: 'The browser blocked the print dialog. Use the browser menu (Print) to save this product as PDF.',
      });
    }
  }

  function viewHistoryItem(item: ReportHistoryItem) {
    setGeneratedReport(item.content);
    setViewingHistoryId(item.id);
    setViewingSavedReport(null);
    setReportMeta(null);
    setGenerateError(null);
    setProductContext({
      sourceId: `history:${item.id}`,
      title: `${item.reportType} — ${activeProject?.name ?? ''}`.trim().replace(/\s+—\s*$/, ''),
      reportTypeLabel: item.reportType,
      entities: item.entities,
      generatedAt: item.timestamp,
    });
  }

  function getStatusBadge(report: SavedReport) {
    const status = report.status || 'Draft';
    switch (status.toLowerCase()) {
      case 'final':
        return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-green-500/15 text-green-400 border border-green-500/20">Final</span>;
      case 'in review':
      case 'review':
        return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-yellow-500/15 text-yellow-400 border border-yellow-500/20">In Review</span>;
      default:
        return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-orange-500/15 text-orange-400 border border-orange-500/20">Draft</span>;
    }
  }

  function getReportTypeLabel(type: string) {
    const rt = REPORT_TYPES.find(r => r.value === type);
    return rt?.label || type;
  }

  if (!activeProject) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="md:ml-56 flex-1 p-4 pt-16 pb-24 md:p-8 md:pt-8 md:pb-8" style={{ backgroundColor: '#0e1321' }}>
          <h2 className="text-2xl font-bold mb-4">Products &amp; Artefacts</h2>
          <SelectProjectPrompt action="draft products for" />
        </main>
      </div>
    );
  }

  return (
    <div className="flex">
      <Sidebar />
      <main className="md:ml-56 flex-1 p-4 pt-16 pb-24 md:p-8 md:pt-8 md:pb-8 min-h-screen" style={{ backgroundColor: '#0e1321' }}>
        {/* Breadcrumb + Title */}
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-semibold uppercase tracking-widest text-gray-500">Workbench</span>
            <span className="text-gray-600 text-[10px]">/</span>
            <span className="text-[10px] font-semibold uppercase tracking-widest text-[#adc6ff]">Production</span>
          </div>
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <h2 className="text-xl font-semibold text-gray-100">Generate New Intelligence Product</h2>
            <div className="flex flex-wrap items-center gap-3 md:gap-5">
              {/* Toggle: Include Evidence Chains */}
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <span className="text-xs text-gray-400">Include Evidence Chains</span>
                <button
                  onClick={() => setIncludeEvidence(!includeEvidence)}
                  className={`relative w-9 h-5 rounded-full transition-colors ${includeEvidence ? 'bg-[#adc6ff]' : 'bg-navy-600'}`}
                >
                  <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${includeEvidence ? 'translate-x-4' : 'translate-x-0'}`} />
                </button>
              </label>
              {/* Toggle: Probability Assessments */}
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <span className="text-xs text-gray-400">Probability Assessments</span>
                <button
                  onClick={() => setProbabilityAssessments(!probabilityAssessments)}
                  className={`relative w-9 h-5 rounded-full transition-colors ${probabilityAssessments ? 'bg-[#adc6ff]' : 'bg-navy-600'}`}
                >
                  <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${probabilityAssessments ? 'translate-x-4' : 'translate-x-0'}`} />
                </button>
              </label>
            </div>
          </div>
        </div>

        {/* Report Type Cards - 5 column grid */}
        <div className="mb-6">
          <label className="text-[10px] font-semibold uppercase tracking-widest text-gray-500 block mb-3">Report Type</label>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
            {REPORT_TYPES.map(rt => (
              <button
                key={rt.value}
                onClick={() => setReportType(rt.value)}
                className={`relative text-left p-4 rounded-lg transition-all border ${
                  reportType === rt.value
                    ? 'border-l-2 border-[#adc6ff] ring-1 ring-[#adc6ff]/30'
                    : 'border-navy-600 hover:border-navy-500'
                }`}
                style={{ backgroundColor: reportType === rt.value ? '#1a1f2e' : '#1a1f2e' }}
              >
                <span
                  className={`material-symbols-outlined text-xl mb-2 block ${
                    reportType === rt.value ? 'text-[#adc6ff]' : 'text-gray-500'
                  }`}
                >
                  {rt.icon}
                </span>
                <div className={`text-sm font-medium mb-1 ${reportType === rt.value ? 'text-gray-100' : 'text-gray-300'}`}>
                  {rt.label}
                </div>
                <div className="text-[11px] text-gray-500 leading-snug">
                  {rt.description}
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: Entity Selector + Generate */}
          <div className="lg:col-span-2 space-y-6">
            <div className="rounded-lg p-6 border border-navy-600" style={{ backgroundColor: '#1a1f2e' }}>
              <div className="flex items-center justify-between mb-4">
                <label className="text-[10px] font-semibold uppercase tracking-widest text-gray-500">Entity Selection</label>
                {selectedEntities.length > 0 && (
                  <span className="text-[11px] text-gray-500">{selectedEntities.length} selected</span>
                )}
              </div>

              {/* Selected entities as colored chips */}
              {selectedEntities.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-4">
                  {selectedEntities.map(entity => (
                    <span
                      key={entity.id}
                      className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium border ${getEntityColor(entity.entity_type)}`}
                    >
                      <span>{entity.name}</span>
                      <span className="text-[10px] opacity-60">({entity.entity_type})</span>
                      <button
                        onClick={() => removeEntity(entity.id)}
                        className="ml-1 opacity-60 hover:opacity-100 transition-opacity"
                      >
                        <span className="material-symbols-outlined text-[14px]">close</span>
                      </button>
                    </span>
                  ))}
                </div>
              )}

              {/* Entity search */}
              <div className="relative mb-4">
                <span className="material-symbols-outlined absolute left-3 top-2.5 text-gray-500 text-lg">search</span>
                <input
                  value={entitySearch}
                  onChange={(e) => setEntitySearch(e.target.value)}
                  placeholder="Search entities to include..."
                  className="w-full rounded-md pl-10 pr-3 py-2.5 text-sm focus:outline-none focus:ring-1 focus:ring-[#adc6ff]/50 border border-navy-600 bg-navy-700 placeholder-gray-500"
                />
                {searching && (
                  <span className="absolute right-3 top-3 text-xs text-gray-500">Searching...</span>
                )}
                {searchResults.length > 0 && (
                  <div className="absolute z-10 w-full mt-1 border border-navy-600 rounded-lg shadow-xl max-h-48 overflow-y-auto" style={{ backgroundColor: '#252b3d' }}>
                    {searchResults.map(entity => (
                      <button
                        key={entity.id}
                        onClick={() => addEntity(entity)}
                        className="w-full text-left px-3 py-2.5 text-sm hover:bg-navy-600 transition-colors flex items-center gap-2 border-b border-navy-600/50 last:border-b-0"
                      >
                        <span className="material-symbols-outlined text-base text-gray-500">add_circle</span>
                        <span className="text-gray-200">{entity.name}</span>
                        <span className="text-[11px] text-gray-500 ml-auto">{entity.entity_type}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Generate button - bottom right */}
              <div className="flex justify-end">
                <button
                  onClick={generateReport}
                  disabled={loading || selectedEntities.length === 0}
                  className="inline-flex items-center gap-2 px-6 py-2.5 rounded-lg text-sm font-semibold text-white disabled:opacity-40 transition-all"
                  style={{
                    background: loading || selectedEntities.length === 0
                      ? '#313849'
                      : 'linear-gradient(135deg, #3b82f6, #6366f1, #8b5cf6)',
                  }}
                >
                  <span className="material-symbols-outlined text-lg">auto_awesome</span>
                  {loading ? 'Generating...' : 'Generate Draft'}
                </button>
              </div>
            </div>

            {/* Generation / load error — an alert, never savable or exportable content */}
            {generateError && (
              <div className="rounded-lg p-4 border border-red-600/40 bg-red-950/30 text-sm text-red-300 flex items-start gap-2" role="alert">
                <span className="material-symbols-outlined text-red-400 text-lg">error</span>
                <span>{generateError}</span>
              </div>
            )}

            {/* Generated report */}
            {generatedReport && (
              <div className="rounded-lg p-6 border border-navy-600" style={{ backgroundColor: '#1a1f2e' }}>
                <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
                  <h3 className="text-sm font-semibold text-gray-300 flex flex-wrap items-center gap-2">
                    <span className="material-symbols-outlined text-[#adc6ff] text-lg">article</span>
                    {viewingSavedReport ? `Saved: ${viewingSavedReport.title}` : viewingHistoryId ? 'Report (from history)' : 'Generated Report'}
                    {/* The project's marking, carried onto every exported/printed copy. */}
                    {classificationMarking && (
                      <span
                        className="text-[10px] font-semibold uppercase tracking-widest text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded px-2 py-0.5"
                        title="Classification marking inherited from this project"
                      >
                        {classificationMarking}
                      </span>
                    )}
                  </h3>
                  <div className="flex flex-wrap items-center gap-2">
                    {!viewingSavedReport && (
                      <button
                        onClick={() => setShowSaveForm(!showSaveForm)}
                        className="inline-flex items-center gap-1 text-xs bg-green-600/20 hover:bg-green-600/30 text-green-400 border border-green-600/30 px-3 py-1.5 rounded-md transition-colors"
                      >
                        <span className="material-symbols-outlined text-sm">save</span>
                        Save Report
                      </button>
                    )}
                    <button
                      onClick={() => navigator.clipboard.writeText(generatedReport)}
                      className="inline-flex items-center gap-1 text-xs bg-navy-700 hover:bg-navy-600 text-gray-300 border border-navy-600 px-3 py-1.5 rounded-md transition-colors"
                    >
                      <span className="material-symbols-outlined text-sm">content_copy</span>
                      Copy
                    </button>
                    <button
                      onClick={exportAsMarkdown}
                      disabled={!currentProduct}
                      title="Download the finished product as Markdown (headings, tables and sourcing preserved)"
                      className="inline-flex items-center gap-1 text-xs bg-navy-700 hover:bg-navy-600 text-gray-300 border border-navy-600 px-3 py-1.5 rounded-md transition-colors disabled:opacity-40"
                    >
                      <span className="material-symbols-outlined text-sm">download</span>
                      Export .md
                    </button>
                    <button
                      onClick={exportAsPdf}
                      disabled={!currentProduct}
                      title="Open the print dialog with a clean, classification-marked layout — save as PDF from there"
                      className="inline-flex items-center gap-1 text-xs bg-[#adc6ff]/15 hover:bg-[#adc6ff]/25 text-[#adc6ff] border border-[#adc6ff]/30 px-3 py-1.5 rounded-md transition-colors disabled:opacity-40"
                    >
                      <span className="material-symbols-outlined text-sm">picture_as_pdf</span>
                      Export PDF
                    </button>
                  </div>
                </div>

                {reportMeta && (
                  <div className="mb-4">
                    {reportMeta.retrievalMode === 'grounded' ? (
                      <span className="inline-flex items-center gap-1.5 text-[11px] text-green-400 bg-green-500/10 border border-green-500/20 rounded-md px-2.5 py-1">
                        <span className="material-symbols-outlined text-[13px]">verified</span>
                        Grounded in {reportMeta.contextNodes} graph entities, {reportMeta.contextEdges} relationships
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 text-[11px] text-yellow-400 bg-yellow-500/10 border border-yellow-500/20 rounded-md px-2.5 py-1">
                        <span className="material-symbols-outlined text-[13px]">warning</span>
                        No graph or document evidence found for these entities — ungrounded draft
                      </span>
                    )}
                  </div>
                )}

                {/* Save form */}
                {showSaveForm && (
                  <div className="mb-4 bg-navy-700 rounded-lg p-3 flex gap-2 items-center border border-navy-600">
                    <input
                      value={saveTitle}
                      onChange={(e) => setSaveTitle(e.target.value)}
                      placeholder="Report title..."
                      className="flex-1 bg-navy-600 border border-navy-500 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-[#adc6ff]/50"
                    />
                    <button
                      onClick={saveReport}
                      disabled={saveLoading || !saveTitle.trim()}
                      className="bg-green-600 hover:bg-green-700 text-white px-3 py-1.5 rounded-md text-xs font-medium disabled:opacity-50 transition-colors"
                    >
                      {saveLoading ? 'Saving...' : 'Save'}
                    </button>
                    <button
                      onClick={() => { setShowSaveForm(false); setSaveTitle(''); }}
                      className="text-gray-400 hover:text-gray-200 px-2 py-1.5 text-xs"
                    >
                      Cancel
                    </button>
                  </div>
                )}

                <div className="prose prose-invert prose-sm max-w-none">
                  <div className="text-sm rounded-lg p-4 max-h-[600px] overflow-y-auto border border-navy-600" style={{ backgroundColor: '#0e1321' }}>
                    <Markdown content={generatedReport} />
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Right: Report History + Saved Reports */}
          <div className="space-y-6">
            {/* Saved Reports - table-like layout */}
            <div className="rounded-lg p-4 border border-navy-600" style={{ backgroundColor: '#1a1f2e' }}>
              <h3 className="text-[10px] font-semibold uppercase tracking-widest text-gray-500 mb-3 flex items-center gap-2">
                <span className="material-symbols-outlined text-sm">folder</span>
                Saved Reports
              </h3>
              {savedReportsLoading ? (
                <p className="text-xs text-gray-500">Loading...</p>
              ) : savedReports.length === 0 ? (
                <p className="text-xs text-gray-500">No saved reports yet.</p>
              ) : (
                <div className="space-y-1 max-h-[400px] overflow-y-auto">
                  {savedReports.map(report => (
                    <div
                      key={report.id}
                      onMouseEnter={() => setHoveredReportId(report.id)}
                      onMouseLeave={() => setHoveredReportId(null)}
                      className={`group p-3 rounded-md text-xs transition-colors cursor-pointer border ${
                        viewingSavedReport?.id === report.id
                          ? 'border-[#adc6ff]/30 bg-[#adc6ff]/5'
                          : 'border-transparent hover:bg-navy-700/50'
                      }`}
                      onClick={() => viewSavedReport(report)}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-start gap-2 min-w-0 flex-1">
                          <span className={`material-symbols-outlined text-sm mt-0.5 ${
                            viewingSavedReport?.id === report.id ? 'text-[#adc6ff]' : 'text-gray-500'
                          }`}>description</span>
                          <div className="min-w-0 flex-1">
                            <div className="font-medium text-gray-200 truncate">{report.title}</div>
                            <div className="text-gray-500 mt-0.5 flex items-center gap-2">
                              <span>{getReportTypeLabel(report.report_type)}</span>
                              {report.entity_ids && report.entity_ids.length > 0 && (
                                <span className="inline-flex items-center gap-0.5 text-gray-500">
                                  <span className="material-symbols-outlined text-[11px]">group</span>
                                  {report.entity_ids.length}
                                </span>
                              )}
                            </div>
                            {report.created_at && (
                              <div className="text-gray-600 mt-0.5 text-[10px]">{new Date(report.created_at).toLocaleString()}</div>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5 shrink-0">
                          {getStatusBadge(report)}
                          {hoveredReportId === report.id && (
                            <div className="flex items-center gap-0.5 ml-1">
                              <button
                                onClick={(e) => { e.stopPropagation(); viewSavedReport(report); }}
                                className="p-1 rounded hover:bg-navy-600 text-gray-400 hover:text-[#adc6ff] transition-colors"
                                title="View"
                              >
                                <span className="material-symbols-outlined text-sm">visibility</span>
                              </button>
                              <button
                                onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(report.content || ''); setToast('Report content copied.'); }}
                                className="p-1 rounded hover:bg-navy-600 text-gray-400 hover:text-gray-200 transition-colors"
                                title="Copy"
                              >
                                <span className="material-symbols-outlined text-sm">content_copy</span>
                              </button>
                              <button
                                onClick={(e) => { e.stopPropagation(); deleteSavedReport(report.id); }}
                                className="p-1 rounded hover:bg-navy-600 text-gray-400 hover:text-red-400 transition-colors"
                                title="Delete"
                              >
                                <span className="material-symbols-outlined text-sm">delete</span>
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Session Report History */}
            <div className="rounded-lg p-4 border border-navy-600" style={{ backgroundColor: '#1a1f2e' }}>
              <h3 className="text-[10px] font-semibold uppercase tracking-widest text-gray-500 mb-3 flex items-center gap-2">
                <span className="material-symbols-outlined text-sm">history</span>
                Session History
              </h3>
              {reportHistory.length === 0 ? (
                <p className="text-xs text-gray-500">No reports generated yet this session.</p>
              ) : (
                <div className="space-y-1 max-h-[300px] overflow-y-auto">
                  {reportHistory.map(item => (
                    <button
                      key={item.id}
                      onClick={() => viewHistoryItem(item)}
                      className={`w-full text-left p-3 rounded-md text-xs transition-colors border ${
                        viewingHistoryId === item.id
                          ? 'border-[#adc6ff]/30 bg-[#adc6ff]/5'
                          : 'border-transparent hover:bg-navy-700/50'
                      }`}
                    >
                      <div className="flex items-start gap-2">
                        <span className={`material-symbols-outlined text-sm mt-0.5 ${
                          viewingHistoryId === item.id ? 'text-[#adc6ff]' : 'text-gray-500'
                        }`}>schedule</span>
                        <div className="min-w-0 flex-1">
                          <div className="font-medium text-gray-200">{item.reportType}</div>
                          <div className="text-gray-500 mt-0.5 truncate">{item.entities.join(', ')}</div>
                          <div className="text-gray-600 mt-0.5 text-[10px]">{item.timestamp.toLocaleTimeString()}</div>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Export Section */}
        <div className="mt-6 rounded-lg p-6 border border-navy-600" style={{ backgroundColor: '#1a1f2e' }}>
          <h3 className="text-[10px] font-semibold uppercase tracking-widest text-gray-500 mb-1 flex items-center gap-2">
            <span className="material-symbols-outlined text-sm">download</span>
            Export Project Data
          </h3>
          {/* Distinct from the product exports above: these dump the whole
              project's graph, not the drafted report. */}
          <p className="text-[11px] text-gray-500 mb-4">
            Machine-readable dumps of the whole project graph — not the drafted product. Use Export .md or Export PDF above for a finished report.
          </p>
          <div className="flex flex-col sm:flex-row gap-3">
            <button
              onClick={async () => {
                try {
                  const res = await exportApi.graph(activeProject.id);
                  const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `graph-export-${activeProject.id.substring(0, 8)}.json`;
                  a.click();
                  URL.revokeObjectURL(url);
                  setToast('Graph exported as JSON.');
                } catch {
                  setToast('Failed to export graph.');
                }
              }}
              className="inline-flex items-center gap-2 bg-navy-700 hover:bg-navy-600 text-gray-300 border border-navy-600 px-4 py-2 rounded-md text-sm transition-colors"
            >
              <span className="material-symbols-outlined text-base">data_object</span>
              Export Graph (JSON)
            </button>
            <button
              onClick={async () => {
                try {
                  const res = await exportApi.entities(activeProject.id);
                  const csvContent = res.data.csv || '';
                  const blob = new Blob([csvContent], { type: 'text/csv' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `entities-export-${activeProject.id.substring(0, 8)}.csv`;
                  a.click();
                  URL.revokeObjectURL(url);
                  setToast(`Entities exported (${res.data.count || 0} records).`);
                } catch {
                  setToast('Failed to export entities.');
                }
              }}
              className="inline-flex items-center gap-2 bg-navy-700 hover:bg-navy-600 text-gray-300 border border-navy-600 px-4 py-2 rounded-md text-sm transition-colors"
            >
              <span className="material-symbols-outlined text-base">table_view</span>
              Export Entities (CSV)
            </button>
            <button
              onClick={async () => {
                try {
                  const res = await exportApi.stix(activeProject.id);
                  const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `stix-export-${activeProject.id.substring(0, 8)}.json`;
                  a.click();
                  URL.revokeObjectURL(url);
                  setToast(`STIX 2.1 bundle exported (${res.data.objects?.length || 0} objects).`);
                } catch {
                  setToast('Failed to export STIX bundle.');
                }
              }}
              className="inline-flex items-center gap-2 bg-navy-700 hover:bg-navy-600 text-gray-300 border border-navy-600 px-4 py-2 rounded-md text-sm transition-colors"
            >
              <span className="material-symbols-outlined text-base">security</span>
              Export STIX 2.1
            </button>
          </div>
        </div>

        {toast && (
          <div className="fixed bottom-6 right-6 bg-[#adc6ff] text-[#0e1321] px-4 py-2.5 rounded-lg shadow-lg text-sm font-medium animate-pulse">
            {toast}
          </div>
        )}

        {/* Print-only rendering of the selected product; invisible on screen. */}
        <PrintableProduct doc={currentProduct} />
      </main>
    </div>
  );
}
