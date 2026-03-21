'use client';
import { useState } from 'react';
import Sidebar from '@/components/Sidebar';
import { useProject } from '@/lib/ProjectContext';
import { llmApi } from '@/lib/api';

const REPORT_TYPES = [
  { value: 'intelligence_brief', label: 'Intelligence Brief' },
  { value: 'threat_assessment', label: 'Threat Assessment' },
  { value: 'situation_report', label: 'Situation Report' },
  { value: 'target_profile', label: 'Target Profile' },
  { value: 'risk_assessment', label: 'Risk Assessment' },
];

export default function ProductsPage() {
  const { activeProject } = useProject();
  const [reportType, setReportType] = useState('intelligence_brief');
  const [entities, setEntities] = useState('');
  const [generatedReport, setGeneratedReport] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function generateReport() {
    if (!entities.trim()) return;
    setLoading(true);
    setGeneratedReport(null);
    try {
      const prompt = `Generate a ${REPORT_TYPES.find(r => r.value === reportType)?.label || reportType} covering the following entities/topics: ${entities.trim()}. ${activeProject ? `Project context: ${activeProject.name}` : ''}`;
      const res = await llmApi.query(
        [{ role: 'user', content: prompt }],
        'report_writing'
      );
      setGeneratedReport(res.data.response || res.data.content || JSON.stringify(res.data));
    } catch {
      setGeneratedReport('Failed to generate report. Check that the LLM service is configured.');
    } finally {
      setLoading(false);
    }
  }

  if (!activeProject) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="ml-56 flex-1 p-8">
          <h2 className="text-2xl font-bold mb-4">Products &amp; Artefacts</h2>
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 text-center text-gray-500">
            <p>Select a project first.</p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-8">
        <h2 className="text-2xl font-bold mb-6">Products &amp; Artefacts</h2>

        <div className="bg-navy-800 border border-navy-600 rounded-lg p-6 mb-6">
          <h3 className="text-sm font-semibold text-gray-400 mb-3">Generate Report</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="text-xs text-gray-400 block mb-1">Report Type</label>
              <select
                value={reportType}
                onChange={(e) => setReportType(e.target.value)}
                className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-blue"
              >
                {REPORT_TYPES.map(rt => (
                  <option key={rt.value} value={rt.value}>{rt.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400 block mb-1">Entities / Topics</label>
              <input
                value={entities}
                onChange={(e) => setEntities(e.target.value)}
                placeholder="e.g., APT29, SolarWinds, Microsoft Exchange"
                className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-blue"
              />
            </div>
          </div>
          <button
            onClick={generateReport}
            disabled={loading || !entities.trim()}
            className="bg-accent-blue hover:bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium disabled:opacity-50 transition-colors"
          >
            {loading ? 'Generating...' : 'Generate Report'}
          </button>
        </div>

        {generatedReport && (
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-gray-400">Generated Report</h3>
              <button
                onClick={() => navigator.clipboard.writeText(generatedReport)}
                className="text-xs text-accent-blue hover:text-blue-400"
              >
                Copy to Clipboard
              </button>
            </div>
            <div className="prose prose-invert prose-sm max-w-none">
              <pre className="whitespace-pre-wrap text-sm text-gray-300 font-sans leading-relaxed">
                {generatedReport}
              </pre>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
