'use client';
import { useState, useCallback, useEffect } from 'react';
import Sidebar from '@/components/Sidebar';
import { useProject } from '@/lib/ProjectContext';
import { llmApi, entitiesApi } from '@/lib/api';

const REPORT_TYPES = [
  { value: 'threat_assessment', label: 'Threat Assessment', skill: 'threat_assessment' },
  { value: 'intsum', label: 'INTSUM', skill: 'report_writing' },
  { value: 'network_brief', label: 'Network Analysis Brief', skill: 'report_writing' },
  { value: 'indicator_report', label: 'Indicator Report', skill: 'report_writing' },
];

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

export default function ProductsPage() {
  const { activeProject } = useProject();
  const [reportType, setReportType] = useState('threat_assessment');
  const [entitySearch, setEntitySearch] = useState('');
  const [searchResults, setSearchResults] = useState<SearchedEntity[]>([]);
  const [selectedEntities, setSelectedEntities] = useState<SearchedEntity[]>([]);
  const [generatedReport, setGeneratedReport] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [reportHistory, setReportHistory] = useState<ReportHistoryItem[]>([]);
  const [viewingHistoryId, setViewingHistoryId] = useState<string | null>(null);

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

  useEffect(() => {
    const timer = setTimeout(() => {
      searchEntities(entitySearch);
    }, 300);
    return () => clearTimeout(timer);
  }, [entitySearch, searchEntities]);

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
    if (selectedEntities.length === 0) return;
    setLoading(true);
    setGeneratedReport(null);
    setViewingHistoryId(null);
    try {
      const rt = REPORT_TYPES.find(r => r.value === reportType);
      const entityContext = selectedEntities.map(e => `${e.name} (${e.entity_type})`).join(', ');
      const prompt = `Generate a ${rt?.label || reportType} report covering the following entities: ${entityContext}.${activeProject ? ` Project context: ${activeProject.name}.` : ''} Provide a comprehensive, structured intelligence product.`;

      const res = await llmApi.query(
        [{ role: 'user', content: prompt }],
        rt?.skill || 'report_writing'
      );
      const content = res.data.content || res.data.response || JSON.stringify(res.data);
      setGeneratedReport(content);

      // Add to history
      setReportHistory(prev => [{
        id: Date.now().toString(),
        reportType: rt?.label || reportType,
        entities: selectedEntities.map(e => e.name),
        content,
        timestamp: new Date(),
      }, ...prev]);
    } catch {
      setGeneratedReport('Failed to generate report. Check that the LLM service is configured.');
    } finally {
      setLoading(false);
    }
  }

  function exportAsText() {
    if (!generatedReport) return;
    const blob = new Blob([generatedReport], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `report_${reportType}_${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function viewHistoryItem(item: ReportHistoryItem) {
    setGeneratedReport(item.content);
    setViewingHistoryId(item.id);
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

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: Report Configuration */}
          <div className="lg:col-span-2 space-y-6">
            <div className="bg-navy-800 border border-navy-600 rounded-lg p-6">
              <h3 className="text-sm font-semibold text-gray-400 mb-4">Generate Report</h3>

              {/* Report type selector */}
              <div className="mb-4">
                <label className="text-xs text-gray-400 block mb-1">Report Type</label>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  {REPORT_TYPES.map(rt => (
                    <button
                      key={rt.value}
                      onClick={() => setReportType(rt.value)}
                      className={`px-3 py-2 rounded text-xs font-medium transition-colors border ${
                        reportType === rt.value
                          ? 'bg-accent-blue border-accent-blue text-white'
                          : 'bg-navy-700 border-navy-600 text-gray-300 hover:border-navy-500'
                      }`}
                    >
                      {rt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Entity search */}
              <div className="mb-4">
                <label className="text-xs text-gray-400 block mb-1">Search Entities</label>
                <div className="relative">
                  <input
                    value={entitySearch}
                    onChange={(e) => setEntitySearch(e.target.value)}
                    placeholder="Search for entities to include in the report..."
                    className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-blue"
                  />
                  {searching && (
                    <span className="absolute right-3 top-2.5 text-xs text-gray-500">Searching...</span>
                  )}
                  {searchResults.length > 0 && (
                    <div className="absolute z-10 w-full mt-1 bg-navy-700 border border-navy-600 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                      {searchResults.map(entity => (
                        <button
                          key={entity.id}
                          onClick={() => addEntity(entity)}
                          className="w-full text-left px-3 py-2 text-sm hover:bg-navy-600 transition-colors flex items-center gap-2"
                        >
                          <span className="text-gray-200">{entity.name}</span>
                          <span className="text-xs text-gray-500">{entity.entity_type}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Selected entities as chips */}
              {selectedEntities.length > 0 && (
                <div className="mb-4">
                  <label className="text-xs text-gray-400 block mb-1">Selected Entities</label>
                  <div className="flex flex-wrap gap-2">
                    {selectedEntities.map(entity => (
                      <span
                        key={entity.id}
                        className="inline-flex items-center gap-1 bg-accent-blue/20 text-accent-blue border border-accent-blue/30 rounded-full px-3 py-1 text-xs"
                      >
                        {entity.name}
                        <span className="text-gray-400 text-[10px]">({entity.entity_type})</span>
                        <button
                          onClick={() => removeEntity(entity.id)}
                          className="ml-1 text-gray-400 hover:text-red-400"
                        >
                          x
                        </button>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <button
                onClick={generateReport}
                disabled={loading || selectedEntities.length === 0}
                className="bg-accent-blue hover:bg-blue-600 text-white px-6 py-2 rounded text-sm font-medium disabled:opacity-50 transition-colors"
              >
                {loading ? 'Generating Report...' : 'Generate Report'}
              </button>
            </div>

            {/* Generated report */}
            {generatedReport && (
              <div className="bg-navy-800 border border-navy-600 rounded-lg p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-gray-400">
                    {viewingHistoryId ? 'Report (from history)' : 'Generated Report'}
                  </h3>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => navigator.clipboard.writeText(generatedReport)}
                      className="text-xs bg-navy-700 hover:bg-navy-600 text-gray-300 px-3 py-1 rounded transition-colors"
                    >
                      Copy
                    </button>
                    <button
                      onClick={exportAsText}
                      className="text-xs bg-navy-700 hover:bg-navy-600 text-gray-300 px-3 py-1 rounded transition-colors"
                    >
                      Export .txt
                    </button>
                  </div>
                </div>
                <div className="prose prose-invert prose-sm max-w-none">
                  <pre className="whitespace-pre-wrap text-sm text-gray-300 font-sans leading-relaxed bg-navy-900/50 rounded p-4 max-h-[600px] overflow-y-auto">
                    {generatedReport}
                  </pre>
                </div>
              </div>
            )}
          </div>

          {/* Right: Report History */}
          <div className="space-y-6">
            <div className="bg-navy-800 border border-navy-600 rounded-lg p-4">
              <h3 className="text-sm font-semibold text-gray-400 mb-3">Report History</h3>
              {reportHistory.length === 0 ? (
                <p className="text-xs text-gray-500">No reports generated yet this session.</p>
              ) : (
                <div className="space-y-2 max-h-[600px] overflow-y-auto">
                  {reportHistory.map(item => (
                    <button
                      key={item.id}
                      onClick={() => viewHistoryItem(item)}
                      className={`w-full text-left p-3 rounded text-xs transition-colors border ${
                        viewingHistoryId === item.id
                          ? 'bg-accent-blue/10 border-accent-blue/30'
                          : 'bg-navy-700 border-navy-700 hover:border-navy-500'
                      }`}
                    >
                      <div className="font-medium text-gray-200">{item.reportType}</div>
                      <div className="text-gray-400 mt-1 truncate">{item.entities.join(', ')}</div>
                      <div className="text-gray-500 mt-1">{item.timestamp.toLocaleTimeString()}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
