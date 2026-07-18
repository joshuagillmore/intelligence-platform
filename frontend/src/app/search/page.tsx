'use client';
import { Suspense, useEffect, useState, useCallback } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Sidebar from '@/components/Sidebar';
import { useProject } from '@/lib/ProjectContext';
import { searchApi } from '@/lib/api';

interface SearchEntry {
  id: string;
  name: string;
  entity_type: string;
  reliability?: string;
  report_type?: string;
  preview?: string;
}

interface SearchResults {
  entities: SearchEntry[];
  documents: SearchEntry[];
  reports: SearchEntry[];
  total: number;
}

const TYPE_COLORS: Record<string, string> = {
  Person: 'bg-blue-600',
  Organization: 'bg-purple-600',
  Location: 'bg-green-600',
  Event: 'bg-yellow-600',
  Document: 'bg-orange-600',
  Report: 'bg-red-600',
  Weapon: 'bg-rose-700',
  Vehicle: 'bg-teal-600',
};

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="flex"><Sidebar /><main className="ml-56 flex-1 p-8"><p className="text-gray-400">Loading...</p></main></div>}>
      <SearchPageContent />
    </Suspense>
  );
}

function SearchPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { activeProject } = useProject();
  const query = searchParams.get('q') || '';
  const [results, setResults] = useState<SearchResults | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const doSearch = useCallback(async () => {
    if (!query.trim() || !activeProject) return;
    setLoading(true);
    setError(null);
    try {
      const res = await searchApi.search(activeProject.id, query);
      setResults(res.data);
    } catch {
      setError('Search failed. Please try again.');
      setResults(null);
    } finally {
      setLoading(false);
    }
  }, [query, activeProject]);

  useEffect(() => {
    doSearch();
  }, [doSearch]);

  function navigateTo(entry: SearchEntry) {
    if (entry.entity_type === 'Report') {
      router.push(`/products`);
    } else {
      router.push(`/network?select=${entry.id}`);
    }
  }

  function badgeColor(type: string) {
    return TYPE_COLORS[type] || 'bg-gray-600';
  }

  if (!activeProject) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="ml-56 flex-1 p-8">
          <h2 className="text-2xl font-bold mb-4">Search</h2>
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 text-center text-gray-500">
            <p>Select a project first to search.</p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-8">
        <h2 className="text-2xl font-bold mb-2">Search Results</h2>
        <p className="text-sm text-gray-400 mb-6">
          {query ? (
            <>Showing results for <span className="text-accent-blue font-medium">&quot;{query}&quot;</span> in {activeProject.name}</>
          ) : (
            'Enter a search query in the sidebar.'
          )}
        </p>

        {loading && (
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 text-center text-gray-400">
            Searching...
          </div>
        )}

        {error && (
          <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300 text-sm mb-6">
            {error}
          </div>
        )}

        {results && !loading && (
          <div className="space-y-6">
            <p className="text-xs text-gray-500">{results.total} result{results.total !== 1 ? 's' : ''} found</p>

            {/* Entities Section */}
            {results.entities.length > 0 && (
              <div className="bg-navy-800 border border-navy-600 rounded-lg p-6">
                <h3 className="text-sm font-semibold text-gray-400 mb-4">Entities ({results.entities.length})</h3>
                <div className="space-y-2">
                  {results.entities.map((e) => (
                    <button
                      key={e.id}
                      onClick={() => navigateTo(e)}
                      className="w-full text-left flex items-center gap-3 p-3 bg-navy-700 hover:bg-navy-600 rounded transition-colors"
                    >
                      <span className={`text-[10px] px-2 py-0.5 rounded font-medium text-white ${badgeColor(e.entity_type)}`}>
                        {e.entity_type}
                      </span>
                      <span className="text-sm text-gray-200">{e.name}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Documents Section */}
            {results.documents.length > 0 && (
              <div className="bg-navy-800 border border-navy-600 rounded-lg p-6">
                <h3 className="text-sm font-semibold text-gray-400 mb-4">Documents ({results.documents.length})</h3>
                <div className="space-y-2">
                  {results.documents.map((d) => (
                    <button
                      key={d.id}
                      onClick={() => router.push(`/documents/${d.id}`)}
                      className="w-full text-left p-3 bg-navy-700 hover:bg-navy-600 rounded transition-colors"
                    >
                      <div className="flex items-center gap-3 mb-1">
                        <span className={`text-[10px] px-2 py-0.5 rounded font-medium text-white ${badgeColor('Document')}`}>
                          Document
                        </span>
                        <span className="text-sm text-gray-200">{d.name}</span>
                        {d.reliability && (
                          <span className="text-[10px] px-2 py-0.5 rounded bg-navy-600 text-gray-400 ml-auto">
                            {d.reliability}
                          </span>
                        )}
                      </div>
                      {d.preview && (
                        <p className="text-xs text-gray-500 mt-1 line-clamp-2">{d.preview}</p>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Reports Section */}
            {results.reports.length > 0 && (
              <div className="bg-navy-800 border border-navy-600 rounded-lg p-6">
                <h3 className="text-sm font-semibold text-gray-400 mb-4">Reports ({results.reports.length})</h3>
                <div className="space-y-2">
                  {results.reports.map((r) => (
                    <button
                      key={r.id}
                      onClick={() => navigateTo(r)}
                      className="w-full text-left p-3 bg-navy-700 hover:bg-navy-600 rounded transition-colors"
                    >
                      <div className="flex items-center gap-3 mb-1">
                        <span className={`text-[10px] px-2 py-0.5 rounded font-medium text-white ${badgeColor('Report')}`}>
                          Report
                        </span>
                        <span className="text-sm text-gray-200">{r.name}</span>
                        {r.report_type && (
                          <span className="text-[10px] px-2 py-0.5 rounded bg-navy-600 text-gray-400 ml-auto">
                            {r.report_type}
                          </span>
                        )}
                      </div>
                      {r.preview && (
                        <p className="text-xs text-gray-500 mt-1 line-clamp-2">{r.preview}</p>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {results.total === 0 && (
              <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 text-center text-gray-500">
                No results found for &quot;{query}&quot;.
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
