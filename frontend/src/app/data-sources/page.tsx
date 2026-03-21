'use client';
import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Sidebar from '@/components/Sidebar';
import { useProject } from '@/lib/ProjectContext';
import { entitiesApi } from '@/lib/api';

interface DocumentEntity {
  id: string;
  name: string;
  entity_type: string;
  properties?: Record<string, unknown>;
}

interface DocWithCount extends DocumentEntity {
  entityCount: number;
  entityNames: string[];
}

export default function DataSourcesPage() {
  const { activeProject } = useProject();
  const router = useRouter();
  const [documents, setDocuments] = useState<DocWithCount[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [searchFilter, setSearchFilter] = useState('');
  const [groupByRating, setGroupByRating] = useState(false);
  const [loading, setLoading] = useState(false);

  const loadDocuments = useCallback(async () => {
    if (!activeProject) return;
    setLoading(true);
    try {
      const res = await entitiesApi.search(activeProject.id, undefined, 'Document');
      const docs: DocumentEntity[] = res.data || [];

      // Load entity counts for each document
      const docsWithCounts: DocWithCount[] = await Promise.all(
        docs.map(async (doc) => {
          try {
            const detailRes = await entitiesApi.get(doc.id);
            const rels = detailRes.data.relationships || [];
            const entityNames = rels.map((r: { source_name?: string; target_name?: string }) =>
              r.source_name || r.target_name || ''
            ).filter(Boolean);
            return { ...doc, entityCount: rels.length, entityNames };
          } catch {
            return { ...doc, entityCount: 0, entityNames: [] };
          }
        })
      );
      setDocuments(docsWithCounts);
    } catch (e) {
      console.error('Failed to load documents', e);
    } finally {
      setLoading(false);
    }
  }, [activeProject]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  function highlightEntities(text: string, entityNames: string[]) {
    if (!entityNames || entityNames.length === 0) return text;
    const sorted = [...entityNames].sort((a, b) => b.length - a.length);
    const escaped = sorted.map(n => n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    const pattern = new RegExp(`(${escaped.join('|')})`, 'gi');
    const parts = text.split(pattern);
    return parts.map((part) => {
      const isEntity = sorted.some(n => n.toLowerCase() === part.toLowerCase());
      if (isEntity) {
        return `<strong class="text-accent-blue">${part}</strong>`;
      }
      return part;
    }).join('');
  }

  const reliabilityColor = (rating: string) => {
    if (!rating) return 'bg-gray-700 text-gray-400';
    const letter = rating.charAt(0).toUpperCase();
    switch (letter) {
      case 'A': return 'bg-green-900/40 text-green-400 border-green-800';
      case 'B': return 'bg-blue-900/40 text-blue-400 border-blue-800';
      case 'C': return 'bg-yellow-900/40 text-yellow-400 border-yellow-800';
      case 'D': return 'bg-orange-900/40 text-orange-400 border-orange-800';
      case 'E': return 'bg-red-900/40 text-red-400 border-red-800';
      case 'F': return 'bg-red-900/40 text-red-400 border-red-800';
      default: return 'bg-gray-700 text-gray-400 border-gray-600';
    }
  };

  const reliabilityLabel = (letter: string) => {
    switch (letter) {
      case 'A': return 'A - Reliable';
      case 'B': return 'B - Usually Reliable';
      case 'C': return 'C - Fairly Reliable';
      case 'D': return 'D - Not Usually Reliable';
      case 'E': return 'E - Unreliable';
      case 'F': return 'F - Cannot Be Judged';
      default: return 'Unrated';
    }
  };

  function navigateToGraph(docId: string) {
    router.push(`/network?highlight=${docId}`);
  }

  // Filter documents
  const filteredDocs = documents.filter(doc => {
    if (!searchFilter) return true;
    const lf = searchFilter.toLowerCase();
    return doc.name.toLowerCase().includes(lf) ||
      (doc.properties?.content && String(doc.properties.content).toLowerCase().includes(lf));
  });

  // Group documents by reliability rating
  function getGroupedDocs(): Record<string, DocWithCount[]> {
    const groups: Record<string, DocWithCount[]> = {};
    for (const doc of filteredDocs) {
      const rating = doc.properties?.reliability_rating ? String(doc.properties.reliability_rating).charAt(0).toUpperCase() : 'Unrated';
      if (!groups[rating]) groups[rating] = [];
      groups[rating].push(doc);
    }
    // Sort groups: A, B, C, D, E, F, Unrated
    const order = ['A', 'B', 'C', 'D', 'E', 'F', 'Unrated'];
    const sorted: Record<string, DocWithCount[]> = {};
    for (const key of order) {
      if (groups[key]) sorted[key] = groups[key];
    }
    return sorted;
  }

  function renderDocCard(doc: DocWithCount) {
    const content = doc.properties?.content ? String(doc.properties.content) : '';
    const reliability = doc.properties?.reliability_rating ? String(doc.properties.reliability_rating) : '';
    const ingestionDate = (doc.properties?.ingestion_date || doc.properties?.created_at) as string | undefined;
    const isExpanded = expandedId === doc.id;

    return (
      <div
        key={doc.id}
        className="bg-navy-800 border border-navy-600 rounded-lg transition-colors hover:border-navy-500"
      >
        <div
          className="p-4 cursor-pointer"
          onClick={() => setExpandedId(isExpanded ? null : doc.id)}
        >
          <div className="flex items-center justify-between mb-2">
            <h4 className="font-medium text-sm flex-1 truncate">{doc.name}</h4>
            <div className="flex items-center gap-2 flex-none">
              <span className="text-xs bg-navy-700 text-gray-300 px-2 py-0.5 rounded">
                {doc.entityCount} entities
              </span>
              {reliability && (
                <span className={`text-xs px-2 py-0.5 rounded font-medium border ${reliabilityColor(reliability)}`}>
                  {reliability}
                </span>
              )}
              <button
                onClick={(e) => { e.stopPropagation(); navigateToGraph(doc.id); }}
                className="text-xs text-accent-blue hover:text-blue-400 px-2 py-0.5 rounded border border-accent-blue/30 hover:border-accent-blue/60 transition-colors"
                title="View in Network Graph"
              >
                View in Graph
              </button>
              <span className="text-xs text-gray-500">{isExpanded ? '▲' : '▼'}</span>
            </div>
          </div>
          {ingestionDate && (
            <p className="text-xs text-gray-500 mb-2">
              Ingested: {new Date(String(ingestionDate)).toLocaleString()}
            </p>
          )}
          {!isExpanded && content && (
            <p className="text-xs text-gray-400 line-clamp-3 font-mono">
              {content.substring(0, 200)}{content.length > 200 ? '...' : ''}
            </p>
          )}
        </div>
        {isExpanded && content && (
          <div className="border-t border-navy-600 p-4">
            <div
              className="text-sm text-gray-300 whitespace-pre-wrap font-mono leading-relaxed"
              dangerouslySetInnerHTML={{ __html: highlightEntities(content, doc.entityNames) }}
            />
          </div>
        )}
      </div>
    );
  }

  if (!activeProject) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="ml-56 flex-1 p-8">
          <h2 className="text-2xl font-bold mb-4">Source Review</h2>
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 text-center text-gray-500">
            <p>Select a project first.</p>
          </div>
        </main>
      </div>
    );
  }

  const groupedDocs = getGroupedDocs();

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-8">
        <h2 className="text-2xl font-bold mb-6">Source Review</h2>

        {/* Search and filter bar */}
        <div className="bg-navy-800 border border-navy-600 rounded-lg p-4 mb-6 flex items-center gap-4 flex-wrap">
          <div className="flex-1 min-w-[200px]">
            <input
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              placeholder="Search documents by name or content..."
              className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-blue"
            />
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs text-gray-400">Group by Rating</label>
            <button
              onClick={() => setGroupByRating(!groupByRating)}
              className={`w-10 h-5 rounded-full transition-colors relative ${
                groupByRating ? 'bg-accent-blue' : 'bg-navy-600'
              }`}
            >
              <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                groupByRating ? 'left-5' : 'left-0.5'
              }`} />
            </button>
          </div>
          <span className="text-sm text-gray-400">{filteredDocs.length} documents</span>
        </div>

        {loading ? (
          <div className="text-center text-gray-500 py-8">Loading documents...</div>
        ) : groupByRating ? (
          /* Grouped view */
          <div className="space-y-6">
            {Object.entries(groupedDocs).map(([rating, docs]) => (
              <div key={rating}>
                <div className="flex items-center gap-3 mb-3">
                  <span className={`text-xs px-2 py-0.5 rounded font-medium border ${reliabilityColor(rating)}`}>
                    {rating}
                  </span>
                  <h3 className="text-sm font-semibold text-gray-400">{reliabilityLabel(rating)}</h3>
                  <span className="text-xs text-gray-500">({docs.length})</span>
                </div>
                <div className="space-y-3">
                  {docs.map(doc => renderDocCard(doc))}
                </div>
              </div>
            ))}
            {Object.keys(groupedDocs).length === 0 && (
              <p className="text-gray-500 text-sm">No documents match the filter.</p>
            )}
          </div>
        ) : (
          /* Flat view */
          <div className="space-y-3">
            {filteredDocs.map(doc => renderDocCard(doc))}
            {filteredDocs.length === 0 && (
              <p className="text-gray-500 text-sm">No documents found. Upload content via Collections to begin.</p>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
