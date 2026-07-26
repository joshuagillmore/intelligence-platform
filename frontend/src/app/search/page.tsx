'use client';
import { Suspense, useEffect, useState, useCallback, useRef } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Sidebar from '@/components/Sidebar';
import SelectProjectPrompt from '@/components/SelectProjectPrompt';
import HighlightedExcerpt from '@/components/HighlightedExcerpt';
import { useProject } from '@/lib/ProjectContext';
import { searchApi, documentsApi } from '@/lib/api';
import { TYPE_COLOR_CLASS } from '@/lib/entityStyles';

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

/** A passage returned by meaning-based retrieval, with its similarity score. */
interface Passage {
  chunk_text: string;
  document_id: string;
  chunk_index: number;
  similarity: number;
}

type Mode = 'keyword' | 'meaning';

/** Terms too common to be worth highlighting in an excerpt. */
const STOPWORDS = new Set([
  'the', 'and', 'for', 'with', 'from', 'that', 'this', 'was', 'are', 'were',
  'has', 'have', 'had', 'who', 'what', 'when', 'where', 'which', 'their',
  'them', 'they', 'been', 'being', 'into', 'over', 'about', 'against', 'used',
  'using', 'use', 'via', 'any', 'all', 'its', 'his', 'her',
]);

export default function SearchPage() {
  return (
    <Suspense fallback={
      <div className="flex"><Sidebar />
        <main className="md:ml-56 flex-1 p-4 pt-16 pb-24 md:p-8 md:pt-8 md:pb-8">
          <p className="text-gray-400">Loading…</p>
        </main>
      </div>}>
      <SearchPageContent />
    </Suspense>
  );
}

function SearchPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { activeProject } = useProject();
  const urlQuery = searchParams.get('q') || '';

  const [term, setTerm] = useState(urlQuery);
  const [mode, setMode] = useState<Mode>('keyword');
  const [results, setResults] = useState<SearchResults | null>(null);
  const [passages, setPassages] = useState<Passage[] | null>(null);
  const [docNames, setDocNames] = useState<Record<string, string>>({});
  const [ran, setRan] = useState('');           // the term the shown results belong to
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Keep the box in step with a sidebar search, which navigates here with ?q=.
  useEffect(() => { setTerm(urlQuery); }, [urlQuery]);

  // Document titles for passage attribution — meaning-mode returns ids only.
  useEffect(() => {
    if (!activeProject) return;
    let cancelled = false;
    documentsApi.list(activeProject.id)
      .then(res => {
        if (cancelled) return;
        const rows = res.data?.documents || res.data || [];
        const map: Record<string, string> = {};
        for (const d of rows) map[d.id] = d.name;
        setDocNames(map);
      })
      .catch(() => { /* names are a nicety; passages still render without them */ });
    return () => { cancelled = true; };
  }, [activeProject]);

  const run = useCallback(async (q: string, m: Mode) => {
    if (!q.trim() || !activeProject) return;
    setLoading(true);
    setError(null);
    setResults(null);
    setPassages(null);
    try {
      if (m === 'meaning') {
        const res = await searchApi.semantic(activeProject.id, q.trim());
        setPassages(res.data?.results || []);
      } else {
        const res = await searchApi.search(activeProject.id, q.trim());
        setResults(res.data);
      }
      setRan(q.trim());
    } catch {
      setError(
        m === 'meaning'
          ? 'Meaning search failed. It needs document embeddings — ingest a document, then try again.'
          : 'Search failed. Check the backend is reachable, then try again.',
      );
    } finally {
      setLoading(false);
    }
  }, [activeProject]);

  // Run on arrival with ?q=, and whenever the mode changes with a live term.
  useEffect(() => { if (urlQuery.trim()) run(urlQuery, mode); }, [urlQuery, mode, run]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!term.trim()) return;
    // Reflect the term in the URL so a search is shareable and back works.
    router.replace(`/search?q=${encodeURIComponent(term.trim())}`);
    run(term, mode);
  }

  // Highlight only terms that carry meaning. Without the stopword filter,
  // "and" lights up inside "Netherlands" and "Sandworm" and the excerpt reads
  // as noise rather than as evidence.
  const keywords = ran
    .split(/\s+/)
    .map(w => w.replace(/[^\w.-]/g, ''))
    .filter(w => w.length > 3 && !STOPWORDS.has(w.toLowerCase()));
  const badge = (t: string) => TYPE_COLOR_CLASS[t] || 'bg-gray-500';

  if (!activeProject) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="md:ml-56 flex-1 p-4 pt-16 pb-24 md:p-8 md:pt-8 md:pb-8">
          <h2 className="text-2xl font-bold mb-4">Search</h2>
          <SelectProjectPrompt action="search" />
        </main>
      </div>
    );
  }

  const nothingYet = !loading && !error && !results && !passages;
  const emptyKeyword = results && results.total === 0;
  const emptyMeaning = passages && passages.length === 0;

  return (
    <div className="flex">
      <Sidebar />
      <main className="md:ml-56 flex-1 min-w-0 p-4 pt-16 pb-24 md:p-8 md:pt-8 md:pb-8">
        <h2 className="text-2xl font-bold mb-1">Search</h2>
        <p className="text-sm text-gray-400 mb-5">
          Across entities, documents and products in{' '}
          <span className="text-accent-periwinkle font-medium">{activeProject.name}</span>
        </p>

        {/* The page owns its input — it used to tell you to go and use the sidebar. */}
        <form onSubmit={submit} className="mb-3">
          <div className="flex gap-2">
            <input
              ref={inputRef}
              value={term}
              onChange={e => setTerm(e.target.value)}
              placeholder="Search this project…"
              aria-label="Search query"
              autoFocus
              className="flex-1 min-w-0 bg-navy-800 border border-navy-600 rounded-lg px-4 py-2.5 text-sm
                         text-gray-100 placeholder-gray-500 focus:outline-none focus:border-accent-blue"
            />
            <button
              type="submit"
              disabled={!term.trim() || loading}
              className="bg-accent-blue hover:bg-blue-600 disabled:opacity-40 text-white px-5 py-2.5
                         rounded-lg text-sm font-medium transition-colors whitespace-nowrap"
            >
              {loading ? 'Searching…' : 'Search'}
            </button>
          </div>
        </form>

        {/* Two genuinely different retrieval strategies, named for what they do. */}
        <div className="flex flex-wrap items-center gap-2 mb-6">
          {(['keyword', 'meaning'] as Mode[]).map(m => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`text-xs px-3 py-1.5 rounded-md border transition-colors ${
                mode === m
                  ? 'bg-accent-periwinkle/15 border-accent-periwinkle/40 text-accent-periwinkle font-medium'
                  : 'bg-navy-800 border-navy-600 text-gray-400 hover:text-gray-200'
              }`}
            >
              {m === 'keyword' ? 'Keyword' : 'Meaning'}
            </button>
          ))}
          <span className="text-[11px] text-gray-500">
            {mode === 'keyword'
              ? 'Matches names and text exactly.'
              : 'Finds passages that mean the same thing, even with different words.'}
          </span>
        </div>

        {error && (
          <div className="rounded-lg border border-red-600/40 bg-red-950/30 p-4 text-sm text-red-300 mb-6" role="alert">
            {error}
          </div>
        )}

        {loading && (
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 text-center text-gray-400">
            Searching…
          </div>
        )}

        {/* Idle: say what can be searched and how the modes differ, rather than nothing. */}
        {nothingYet && (
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-8">
            <h3 className="text-base font-semibold text-gray-300 mb-1">Search the project</h3>
            <p className="text-sm text-gray-500 mb-5 max-w-xl">
              Keyword search matches entity names and document text. Meaning search retrieves
              passages by what they say — useful when you don&apos;t know the exact wording.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-2xl">
              {[
                { m: 'keyword' as Mode, q: '45.83.12.7', hint: 'an indicator' },
                { m: 'keyword' as Mode, q: 'CVE-2024-3400', hint: 'a vulnerability' },
                { m: 'meaning' as Mode, q: 'command and control infrastructure', hint: 'a concept' },
                { m: 'meaning' as Mode, q: 'who is behind the campaign', hint: 'a question' },
              ].map(ex => (
                <button
                  key={ex.q}
                  onClick={() => { setTerm(ex.q); setMode(ex.m); run(ex.q, ex.m); }}
                  className="text-left bg-navy-700 hover:bg-navy-600 border border-navy-600 rounded-md
                             px-3 py-2.5 transition-colors"
                >
                  <div className="text-sm text-gray-200 font-mono">{ex.q}</div>
                  <div className="text-[11px] text-gray-500 mt-0.5">
                    {ex.hint} · {ex.m === 'keyword' ? 'Keyword' : 'Meaning'}
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Meaning results: passages with their similarity and source ── */}
        {passages && passages.length > 0 && (
          <div className="space-y-3">
            <p className="text-xs text-gray-500">
              {passages.length} passage{passages.length !== 1 ? 's' : ''} ranked by similarity
            </p>
            {passages.map((p, i) => (
              <button
                key={`${p.document_id}-${p.chunk_index}-${i}`}
                onClick={() => router.push(`/documents/${p.document_id}`)}
                className="w-full text-left bg-navy-800 border border-navy-600 hover:border-accent-blue
                           rounded-lg p-4 transition-colors"
              >
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[10px] px-2 py-0.5 rounded font-medium text-white bg-gray-500">
                    Document
                  </span>
                  <span className="text-sm text-gray-200 truncate">
                    {docNames[p.document_id] || 'Source document'}
                  </span>
                  <span className="ml-auto text-[11px] font-mono text-accent-periwinkle whitespace-nowrap">
                    {Math.round(p.similarity * 100)}% match
                  </span>
                </div>
                <HighlightedExcerpt
                  text={p.chunk_text}
                  keywords={keywords}
                  className="text-xs text-gray-400 leading-relaxed"
                  maxLength={340}
                />
              </button>
            ))}
          </div>
        )}

        {/* ── Keyword results ── */}
        {results && results.total > 0 && (
          <div className="space-y-6">
            <p className="text-xs text-gray-500">
              {results.total} result{results.total !== 1 ? 's' : ''} for
              <span className="text-gray-300"> &quot;{ran}&quot;</span>
            </p>

            {results.entities.length > 0 && (
              <section className="bg-navy-800 border border-navy-600 rounded-lg p-5">
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                  Entities ({results.entities.length})
                </h3>
                <div className="space-y-2">
                  {results.entities.map(e => (
                    <button
                      key={e.id}
                      onClick={() => router.push(`/network?select=${e.id}`)}
                      className="w-full text-left flex items-center gap-3 p-3 bg-navy-700 hover:bg-navy-600
                                 rounded transition-colors"
                    >
                      <span className={`text-[10px] px-2 py-0.5 rounded font-medium text-white ${badge(e.entity_type)}`}>
                        {e.entity_type}
                      </span>
                      <span className="text-sm text-gray-200 truncate">{e.name}</span>
                      <span className="ml-auto text-[11px] text-gray-500 whitespace-nowrap">View in graph →</span>
                    </button>
                  ))}
                </div>
              </section>
            )}

            {results.documents.length > 0 && (
              <section className="bg-navy-800 border border-navy-600 rounded-lg p-5">
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                  Documents ({results.documents.length})
                </h3>
                <div className="space-y-2">
                  {results.documents.map(d => (
                    <button
                      key={d.id}
                      onClick={() => router.push(`/documents/${d.id}`)}
                      className="w-full text-left p-3 bg-navy-700 hover:bg-navy-600 rounded transition-colors"
                    >
                      <div className="flex items-center gap-3 mb-1">
                        <span className={`text-[10px] px-2 py-0.5 rounded font-medium text-white ${badge('Document')}`}>
                          Document
                        </span>
                        <span className="text-sm text-gray-200 truncate">{d.name}</span>
                        {d.reliability && (
                          <span className="text-[10px] px-2 py-0.5 rounded bg-navy-600 text-gray-400 ml-auto whitespace-nowrap">
                            {d.reliability}
                          </span>
                        )}
                      </div>
                      {d.preview && (
                        <HighlightedExcerpt
                          text={d.preview}
                          keywords={keywords}
                          className="text-xs text-gray-500 leading-relaxed"
                          maxLength={260}
                        />
                      )}
                    </button>
                  ))}
                </div>
              </section>
            )}

            {results.reports.length > 0 && (
              <section className="bg-navy-800 border border-navy-600 rounded-lg p-5">
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                  Products ({results.reports.length})
                </h3>
                <div className="space-y-2">
                  {results.reports.map(r => (
                    <button
                      key={r.id}
                      // Carry the id so Products can open this one rather than
                      // dropping the analyst on an undifferentiated list.
                      onClick={() => router.push(`/products?report=${r.id}`)}
                      className="w-full text-left p-3 bg-navy-700 hover:bg-navy-600 rounded transition-colors"
                    >
                      <div className="flex items-center gap-3 mb-1">
                        <span className={`text-[10px] px-2 py-0.5 rounded font-medium text-white ${badge('Report')}`}>
                          Product
                        </span>
                        <span className="text-sm text-gray-200 truncate">{r.name}</span>
                        {r.report_type && (
                          <span className="text-[10px] px-2 py-0.5 rounded bg-navy-600 text-gray-400 ml-auto whitespace-nowrap">
                            {r.report_type}
                          </span>
                        )}
                      </div>
                      {r.preview && (
                        <HighlightedExcerpt
                          text={r.preview}
                          keywords={keywords}
                          className="text-xs text-gray-500 leading-relaxed"
                          maxLength={260}
                        />
                      )}
                    </button>
                  ))}
                </div>
              </section>
            )}
          </div>
        )}

        {/* Empty results say which mode was used and offer the other one. */}
        {(emptyKeyword || emptyMeaning) && !loading && (
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 text-center">
            <p className="text-sm text-gray-300 mb-1">
              No {mode === 'meaning' ? 'passages' : 'results'} for &quot;{ran}&quot;
            </p>
            <p className="text-xs text-gray-500 mb-4">
              {mode === 'meaning'
                ? 'Meaning search only covers ingested document text.'
                : 'Keyword search matches names and text exactly.'}
            </p>
            <button
              onClick={() => { const next: Mode = mode === 'keyword' ? 'meaning' : 'keyword'; setMode(next); run(ran, next); }}
              className="text-xs bg-navy-700 hover:bg-navy-600 border border-navy-600 text-gray-200
                         px-4 py-2 rounded-md transition-colors"
            >
              Try {mode === 'keyword' ? 'Meaning' : 'Keyword'} search instead
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
