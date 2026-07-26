'use client';
/**
 * Structured Analytic Techniques — the workflow home for the three tradecraft
 * skills (source evaluation, ACH, gap analysis). Every run goes through the
 * grounded /api/analysis/* endpoints, which retrieve real project evidence
 * before prompting; the panel reports how much evidence backed the run and
 * whether an LLM was involved at all.
 */
import { useState, useCallback, useEffect } from 'react';
import Sidebar from '@/components/Sidebar';
import Markdown from '@/components/Markdown';
import { useProject } from '@/lib/ProjectContext';
import { useNotifications } from '@/components/NotificationProvider';
import { getErrorMessage } from '@/lib/errorMessages';
import {
  analysisApi, entitiesApi, documentsApi, reportsApi,
  type Hypothesis, type StructuralGap, type SourceEvaluationItem,
} from '@/lib/api';

type Technique = 'gaps' | 'hypotheses' | 'sources';

const TECHNIQUES: Array<{ id: Technique; label: string; icon: string; description: string }> = [
  {
    id: 'gaps',
    label: 'Gap Analysis',
    icon: 'radar',
    description: 'Where the intelligence picture is thin — isolated entities, unsourced claims, coverage holes.',
  },
  {
    id: 'hypotheses',
    label: 'Competing Hypotheses',
    icon: 'account_tree',
    description: 'ACH: enumerate hypotheses, test them against retrieved evidence, score by inconsistency.',
  },
  {
    id: 'sources',
    label: 'Source Evaluation',
    icon: 'verified_user',
    description: 'Admiralty grading of collected sources from measured provenance and corroboration.',
  },
];

const PRIORITY_STYLE: Record<string, string> = {
  high: 'bg-threat-high/15 text-threat-high border-threat-high/30',
  medium: 'bg-threat-medium/15 text-threat-medium border-threat-medium/30',
  low: 'bg-threat-low/15 text-threat-low border-threat-low/30',
};

interface EntityOption { id: string; name: string; entity_type: string }
interface DocOption { id: string; name: string; reliability_rating: string }

export default function AnalysisPage() {
  const { activeProject } = useProject();
  const { addNotification } = useNotifications();

  const [technique, setTechnique] = useState<Technique>('gaps');
  const [loading, setLoading] = useState(false);

  // Shared output
  const [output, setOutput] = useState<string | null>(null);
  const [outputTitle, setOutputTitle] = useState('');
  const [meta, setMeta] = useState<{ model: string; tokens: number; note: string } | null>(null);
  const [gaps, setGaps] = useState<StructuralGap[]>([]);
  const [hypotheses, setHypotheses] = useState<Hypothesis[]>([]);
  const [ratings, setRatings] = useState<SourceEvaluationItem[]>([]);

  // Inputs
  const [entitySearch, setEntitySearch] = useState('');
  const [entityResults, setEntityResults] = useState<EntityOption[]>([]);
  const [selectedEntities, setSelectedEntities] = useState<EntityOption[]>([]);
  const [question, setQuestion] = useState('');
  const [focus, setFocus] = useState('');
  const [saveAssessment, setSaveAssessment] = useState(false);
  const [documents, setDocuments] = useState<DocOption[]>([]);
  const [selectedDocs, setSelectedDocs] = useState<string[]>([]);
  const [applyRatings, setApplyRatings] = useState(false);

  // Save-to-products
  const [saveTitle, setSaveTitle] = useState('');
  const [saving, setSaving] = useState(false);

  const searchEntities = useCallback(async (query: string) => {
    if (!query.trim() || !activeProject) {
      setEntityResults([]);
      return;
    }
    try {
      const res = await entitiesApi.search(activeProject.id, query);
      setEntityResults((res.data || []).slice(0, 8));
    } catch {
      setEntityResults([]);
    }
  }, [activeProject]);

  useEffect(() => {
    const timer = setTimeout(() => searchEntities(entitySearch), 300);
    return () => clearTimeout(timer);
  }, [entitySearch, searchEntities]);

  useEffect(() => {
    if (technique !== 'sources' || !activeProject) return;
    documentsApi.list(activeProject.id)
      .then(res => setDocuments(res.data?.documents || []))
      .catch(() => setDocuments([]));
  }, [technique, activeProject]);

  // Switching technique clears a result that no longer matches the controls.
  useEffect(() => {
    setOutput(null);
    setMeta(null);
    setGaps([]);
    setHypotheses([]);
    setRatings([]);
  }, [technique]);

  function resetResult() {
    setOutput(null);
    setMeta(null);
    setGaps([]);
    setHypotheses([]);
    setRatings([]);
  }

  function fail(title: string, error: unknown) {
    // Failures surface as a toast; the output panel keeps whatever was last
    // valid so an error string can never be saved as if it were analysis.
    addNotification({ type: 'error', title, message: getErrorMessage(error) });
  }

  async function runGapAnalysis() {
    if (!activeProject) return;
    setLoading(true);
    resetResult();
    try {
      const res = await analysisApi.gaps({
        project_id: activeProject.id,
        entity_ids: selectedEntities.map(e => e.id),
        focus: focus.trim(),
      });
      const d = res.data;
      setOutput(d.analysis);
      setOutputTitle('Gap Analysis');
      setGaps(d.structural_gaps || []);
      setMeta({
        model: d.model,
        tokens: d.tokens_used,
        note: `${d.coverage.entities} entities · ${d.coverage.relationships} relationships · ${d.coverage.documents} documents measured`,
      });
    } catch (e) {
      fail('Gap Analysis Failed', e);
    } finally {
      setLoading(false);
    }
  }

  async function runHypotheses() {
    if (!activeProject || !question.trim()) return;
    setLoading(true);
    resetResult();
    try {
      const res = await analysisApi.hypotheses({
        project_id: activeProject.id,
        question: question.trim(),
        entity_ids: selectedEntities.map(e => e.id),
        save_assessment: saveAssessment && selectedEntities.length > 0,
      });
      const d = res.data;
      setOutput(d.analysis);
      setOutputTitle('Analysis of Competing Hypotheses');
      setHypotheses(d.hypotheses || []);
      setMeta({
        model: d.model,
        tokens: d.tokens_used,
        note: `${d.retrieval_mode} · ${d.context_nodes} entities, ${d.context_edges} relationships${d.vector_hits ? `, ${d.vector_hits} similar passages` : ''}`,
      });
      if (d.assessment_id) {
        addNotification({
          type: 'success',
          title: 'Assessment Saved',
          message: `Leading hypothesis recorded against ${d.focus_entities[0] || 'the focus entity'}.`,
        });
      }
    } catch (e) {
      fail('Hypothesis Generation Failed', e);
    } finally {
      setLoading(false);
    }
  }

  async function runSourceEvaluation() {
    if (!activeProject) return;
    setLoading(true);
    resetResult();
    try {
      const res = await analysisApi.sourceEvaluation({
        project_id: activeProject.id,
        document_ids: selectedDocs,
        apply_ratings: applyRatings,
      });
      const d = res.data;
      setOutput(d.analysis);
      setOutputTitle('Source Evaluation');
      setRatings(d.evaluations || []);
      setMeta({
        model: d.model,
        tokens: d.tokens_used,
        note: `${d.documents_evaluated} document(s) graded${d.ratings_applied ? ` · ${d.ratings_applied} rating(s) written back` : ''}`,
      });
      if (d.ratings_applied) {
        documentsApi.list(activeProject.id)
          .then(r => setDocuments(r.data?.documents || []))
          .catch(() => { /* the list is a convenience; the grading already succeeded */ });
      }
    } catch (e) {
      fail('Source Evaluation Failed', e);
    } finally {
      setLoading(false);
    }
  }

  async function saveToProducts() {
    if (!output || !activeProject || !saveTitle.trim()) return;
    setSaving(true);
    try {
      await reportsApi.save({
        project_id: activeProject.id,
        title: saveTitle.trim(),
        content: output,
        report_type: technique === 'gaps' ? 'gap_analysis' : technique === 'hypotheses' ? 'hypothesis_generation' : 'source_evaluation',
        entity_ids: selectedEntities.map(e => e.id),
      });
      setSaveTitle('');
      addNotification({ type: 'success', title: 'Saved', message: 'Analysis saved to Products & Artefacts.' });
    } catch (e) {
      fail('Save Failed', e);
    } finally {
      setSaving(false);
    }
  }

  const canRun = technique !== 'hypotheses' || question.trim().length > 0;

  if (!activeProject) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="md:ml-56 flex-1 p-4 pt-16 pb-24 md:p-8 md:pt-8 md:pb-8" style={{ backgroundColor: '#0e1321' }}>
          <h2 className="text-2xl font-bold mb-4">Analytic Techniques</h2>
          <div className="rounded-lg p-8 text-center text-gray-500 border border-navy-600" style={{ backgroundColor: '#1a1f2e' }}>
            <p>Select a project first.</p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="flex">
      <Sidebar />
      <main className="md:ml-56 flex-1 p-4 pt-16 pb-24 md:p-8 md:pt-8 md:pb-8 min-h-screen" style={{ backgroundColor: '#0e1321' }}>
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-semibold uppercase tracking-widest text-gray-500">Workbench</span>
            <span className="text-gray-600 text-[10px]">/</span>
            <span className="text-[10px] font-semibold uppercase tracking-widest text-accent-periwinkle">Tradecraft</span>
          </div>
          <h2 className="text-xl font-semibold text-gray-100">Structured Analytic Techniques</h2>
          <p className="text-xs text-gray-500 mt-1">
            Each technique retrieves this project&apos;s own graph and source evidence before it reasons.
          </p>
        </div>

        {/* Technique selector */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-6">
          {TECHNIQUES.map(t => (
            <button
              key={t.id}
              onClick={() => setTechnique(t.id)}
              className={`text-left p-4 rounded-lg transition-all border ${
                technique === t.id
                  ? 'border-l-2 border-accent-periwinkle ring-1 ring-accent-periwinkle/30'
                  : 'border-navy-600 hover:border-navy-500'
              }`}
              style={{ backgroundColor: '#1a1f2e' }}
            >
              <span className={`material-symbols-outlined text-xl mb-2 block ${technique === t.id ? 'text-accent-periwinkle' : 'text-gray-500'}`}>
                {t.icon}
              </span>
              <div className={`text-sm font-medium mb-1 ${technique === t.id ? 'text-gray-100' : 'text-gray-300'}`}>{t.label}</div>
              <div className="text-[11px] text-gray-500 leading-snug">{t.description}</div>
            </button>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Controls */}
          <div className="space-y-4">
            <div className="rounded-lg p-5 border border-navy-600 space-y-4" style={{ backgroundColor: '#1a1f2e' }}>
              {technique === 'hypotheses' && (
                <div>
                  <label className="text-[10px] font-semibold uppercase tracking-widest text-gray-500 block mb-2">
                    Analytic question
                  </label>
                  <textarea
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    placeholder="Who is responsible for the depot shipments?"
                    className="w-full rounded-md px-3 py-2 text-sm h-20 border border-navy-600 bg-navy-700 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-accent-periwinkle/50"
                  />
                </div>
              )}

              {technique === 'gaps' && (
                <div>
                  <label className="text-[10px] font-semibold uppercase tracking-widest text-gray-500 block mb-2">
                    Focus / PIR <span className="text-gray-600 normal-case tracking-normal">(optional)</span>
                  </label>
                  <textarea
                    value={focus}
                    onChange={(e) => setFocus(e.target.value)}
                    placeholder="What we still need to know about the logistics network..."
                    className="w-full rounded-md px-3 py-2 text-sm h-20 border border-navy-600 bg-navy-700 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-accent-periwinkle/50"
                  />
                </div>
              )}

              {technique === 'sources' && (
                <div>
                  <label className="text-[10px] font-semibold uppercase tracking-widest text-gray-500 block mb-2">
                    Documents <span className="text-gray-600 normal-case tracking-normal">(none selected = all)</span>
                  </label>
                  <div className="max-h-56 overflow-y-auto space-y-1 border border-navy-600 rounded-md p-2 bg-navy-700">
                    {documents.length === 0 && (
                      <p className="text-[11px] text-gray-500 px-1 py-2">No documents held for this project.</p>
                    )}
                    {documents.map(doc => (
                      <label key={doc.id} className="flex items-start gap-2 text-[11px] text-gray-300 cursor-pointer px-1 py-1 rounded hover:bg-navy-600">
                        <input
                          type="checkbox"
                          checked={selectedDocs.includes(doc.id)}
                          onChange={() => setSelectedDocs(prev =>
                            prev.includes(doc.id) ? prev.filter(x => x !== doc.id) : [...prev, doc.id]
                          )}
                          className="mt-0.5 accent-accent-periwinkle"
                        />
                        <span className="flex-1 truncate">{doc.name}</span>
                        <span className="text-[10px] text-gray-500 flex-none">{doc.reliability_rating || 'unrated'}</span>
                      </label>
                    ))}
                  </div>
                  <label className="flex items-center gap-2 mt-3 text-xs text-gray-400 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={applyRatings}
                      onChange={(e) => setApplyRatings(e.target.checked)}
                      className="accent-accent-periwinkle"
                    />
                    Write ratings back to the documents
                  </label>
                </div>
              )}

              {technique !== 'sources' && (
                <div>
                  <label className="text-[10px] font-semibold uppercase tracking-widest text-gray-500 block mb-2">
                    Focus entities <span className="text-gray-600 normal-case tracking-normal">(optional)</span>
                  </label>
                  {selectedEntities.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mb-2">
                      {selectedEntities.map(entity => (
                        <span key={entity.id} className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] bg-navy-700 border border-navy-600 text-gray-300">
                          {entity.name}
                          <button
                            onClick={() => setSelectedEntities(prev => prev.filter(x => x.id !== entity.id))}
                            className="opacity-60 hover:opacity-100"
                            aria-label={`Remove ${entity.name}`}
                          >
                            <span className="material-symbols-outlined text-[13px]">close</span>
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                  <input
                    value={entitySearch}
                    onChange={(e) => setEntitySearch(e.target.value)}
                    placeholder="Search entities..."
                    className="w-full rounded-md px-3 py-2 text-sm border border-navy-600 bg-navy-700 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-accent-periwinkle/50"
                  />
                  {entityResults.length > 0 && (
                    <div className="mt-1 border border-navy-600 rounded-md max-h-40 overflow-y-auto" style={{ backgroundColor: '#252b3d' }}>
                      {entityResults.map(entity => (
                        <button
                          key={entity.id}
                          onClick={() => {
                            setSelectedEntities(prev => prev.some(x => x.id === entity.id) ? prev : [...prev, entity]);
                            setEntitySearch('');
                            setEntityResults([]);
                          }}
                          className="w-full text-left px-3 py-2 text-xs hover:bg-navy-600 flex items-center gap-2"
                        >
                          <span className="text-gray-200 truncate">{entity.name}</span>
                          <span className="text-[10px] text-gray-500 ml-auto flex-none">{entity.entity_type}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {technique === 'hypotheses' && (
                <label className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={saveAssessment}
                    onChange={(e) => setSaveAssessment(e.target.checked)}
                    disabled={selectedEntities.length === 0}
                    className="accent-accent-periwinkle"
                  />
                  Record leading hypothesis as an assessment
                  {selectedEntities.length === 0 && <span className="text-gray-600">(needs a focus entity)</span>}
                </label>
              )}

              <button
                onClick={technique === 'gaps' ? runGapAnalysis : technique === 'hypotheses' ? runHypotheses : runSourceEvaluation}
                disabled={loading || !canRun}
                className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold text-white disabled:opacity-40 transition-all"
                style={{
                  background: loading || !canRun ? '#313849' : 'linear-gradient(135deg, #3b82f6, #6366f1, #8b5cf6)',
                }}
              >
                <span className="material-symbols-outlined text-lg">auto_awesome</span>
                {loading ? 'Running...' : `Run ${TECHNIQUES.find(t => t.id === technique)?.label}`}
              </button>
            </div>

            {/* Structured side-car results */}
            {gaps.length > 0 && (
              <div className="rounded-lg p-5 border border-navy-600" style={{ backgroundColor: '#1a1f2e' }}>
                <h3 className="text-[10px] font-semibold uppercase tracking-widest text-gray-500 mb-3">Measured gaps</h3>
                <div className="space-y-2">
                  {gaps.map((gap, i) => (
                    <div key={`${gap.kind}-${i}`} className="border border-navy-600 rounded-md p-2.5 bg-navy-700">
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span className="text-xs font-medium text-gray-200">{gap.title}</span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${PRIORITY_STYLE[gap.priority] || PRIORITY_STYLE.low}`}>
                          {gap.priority}
                        </span>
                      </div>
                      <p className="text-[11px] text-gray-400 leading-snug">{gap.detail}</p>
                      {gap.examples.length > 0 && (
                        <p className="text-[10px] text-gray-500 mt-1 truncate">e.g. {gap.examples.join(', ')}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {hypotheses.length > 0 && (
              <div className="rounded-lg p-5 border border-navy-600" style={{ backgroundColor: '#1a1f2e' }}>
                <h3 className="text-[10px] font-semibold uppercase tracking-widest text-gray-500 mb-3">Hypotheses</h3>
                <div className="space-y-2">
                  {hypotheses.map(h => (
                    <div key={h.id} className="border border-navy-600 rounded-md p-2.5 bg-navy-700">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-accent-periwinkle">{h.id}</span>
                        <span className="text-[10px] text-gray-400">{h.probability_label} ({(h.probability * 100).toFixed(0)}%)</span>
                      </div>
                      <p className="text-[11px] text-gray-300 mt-1 leading-snug">{h.statement}</p>
                      <div className="mt-1.5 h-1 rounded-full bg-navy-800 overflow-hidden">
                        <div className="h-full bg-accent-periwinkle" style={{ width: `${Math.round(h.probability * 100)}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {ratings.length > 0 && (
              <div className="rounded-lg p-5 border border-navy-600" style={{ backgroundColor: '#1a1f2e' }}>
                <h3 className="text-[10px] font-semibold uppercase tracking-widest text-gray-500 mb-3">Admiralty ratings</h3>
                <div className="space-y-1.5">
                  {ratings.map(r => (
                    <div key={r.document_id} className="flex items-center gap-2 text-[11px]">
                      <span className="text-gray-300 truncate flex-1">{r.name}</span>
                      <span className="text-[10px] text-gray-500 flex-none">{r.corroborating_documents} corrob.</span>
                      <span className="font-mono text-accent-periwinkle flex-none w-8 text-right">{r.admiralty_rating || '—'}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Output */}
          <div className="lg:col-span-2">
            <div className="rounded-lg p-6 border border-navy-600 min-h-[16rem]" style={{ backgroundColor: '#1a1f2e' }}>
              {!output && !loading && (
                <p className="text-sm text-gray-500">
                  Pick a technique and run it — the result appears here.
                </p>
              )}
              {loading && (
                <p className="text-sm text-gray-400">Retrieving evidence and reasoning over it...</p>
              )}
              {output && (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                    <h3 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
                      <span className="material-symbols-outlined text-accent-periwinkle text-lg">article</span>
                      {outputTitle}
                    </h3>
                    <div className="flex items-center gap-2">
                      <input
                        value={saveTitle}
                        onChange={(e) => setSaveTitle(e.target.value)}
                        placeholder="Title to save as..."
                        className="rounded-md px-2 py-1.5 text-xs border border-navy-600 bg-navy-700 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-accent-periwinkle/50"
                      />
                      <button
                        onClick={saveToProducts}
                        disabled={saving || !saveTitle.trim()}
                        className="inline-flex items-center gap-1 text-xs bg-green-600/20 hover:bg-green-600/30 text-green-400 border border-green-600/30 px-3 py-1.5 rounded-md disabled:opacity-40 transition-colors"
                      >
                        <span className="material-symbols-outlined text-sm">save</span>
                        {saving ? 'Saving...' : 'Save to Products'}
                      </button>
                      <button
                        onClick={() => navigator.clipboard.writeText(output)}
                        className="inline-flex items-center gap-1 text-xs bg-navy-700 hover:bg-navy-600 text-gray-300 border border-navy-600 px-3 py-1.5 rounded-md transition-colors"
                      >
                        <span className="material-symbols-outlined text-sm">content_copy</span>
                        Copy
                      </button>
                    </div>
                  </div>

                  {meta && (
                    <div className="mb-4 flex flex-wrap items-center gap-2">
                      <span className="inline-flex items-center gap-1.5 text-[11px] text-green-400 bg-green-500/10 border border-green-500/20 rounded-md px-2.5 py-1">
                        <span className="material-symbols-outlined text-[13px]">verified</span>
                        {meta.note}
                      </span>
                      {meta.model === 'none' ? (
                        <span className="inline-flex items-center gap-1.5 text-[11px] text-yellow-400 bg-yellow-500/10 border border-yellow-500/20 rounded-md px-2.5 py-1">
                          <span className="material-symbols-outlined text-[13px]">warning</span>
                          No LLM provider configured — measured findings only
                        </span>
                      ) : (
                        <span className="text-[11px] text-gray-500">{meta.model} · {meta.tokens} tokens</span>
                      )}
                    </div>
                  )}

                  <Markdown content={output} className="text-sm" />
                </>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
