'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/Sidebar';
import { useProject } from '@/lib/ProjectContext';
import { entitiesApi } from '@/lib/api';

interface DocumentEntity {
  id: string;
  name: string;
  entity_type: string;
  properties?: Record<string, unknown>;
}

export default function DataSourcesPage() {
  const { activeProject } = useProject();
  const [documents, setDocuments] = useState<DocumentEntity[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [docEntities, setDocEntities] = useState<Record<string, string[]>>({});

  const loadDocuments = useCallback(async () => {
    if (!activeProject) return;
    try {
      const res = await entitiesApi.search(activeProject.id, undefined, 'Document');
      setDocuments(res.data);
    } catch (e) {
      console.error('Failed to load documents', e);
    }
  }, [activeProject]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  async function toggleExpand(doc: DocumentEntity) {
    if (expandedId === doc.id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(doc.id);
    // Load entities related to this document if not already loaded
    if (!docEntities[doc.id]) {
      try {
        const res = await entitiesApi.get(doc.id);
        const rels = res.data.relationships || [];
        const entityNames = rels.map((r: { source_name?: string; target_name?: string }) =>
          r.source_name || r.target_name || ''
        ).filter(Boolean);
        setDocEntities(prev => ({ ...prev, [doc.id]: entityNames }));
      } catch {
        setDocEntities(prev => ({ ...prev, [doc.id]: [] }));
      }
    }
  }

  function highlightEntities(text: string, entityNames: string[]) {
    if (!entityNames || entityNames.length === 0) return text;
    // Sort by length descending to match longer names first
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
      case 'A': return 'bg-green-900/40 text-green-400';
      case 'B': return 'bg-blue-900/40 text-blue-400';
      case 'C': return 'bg-yellow-900/40 text-yellow-400';
      case 'D': return 'bg-orange-900/40 text-orange-400';
      case 'E': return 'bg-red-900/40 text-red-400';
      case 'F': return 'bg-gray-700 text-gray-400';
      default: return 'bg-gray-700 text-gray-400';
    }
  };

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

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-8">
        <h2 className="text-2xl font-bold mb-6">Source Review</h2>

        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">Documents ({documents.length})</h3>
        </div>

        <div className="space-y-3">
          {documents.map((doc) => {
            const content = doc.properties?.content ? String(doc.properties.content) : '';
            const reliability = doc.properties?.reliability_rating ? String(doc.properties.reliability_rating) : '';
            const ingestionDate = (doc.properties?.ingestion_date || doc.properties?.created_at) as string | undefined;
            const isExpanded = expandedId === doc.id;
            const entityNames = docEntities[doc.id] || [];

            return (
              <div
                key={doc.id}
                className="bg-navy-800 border border-navy-600 rounded-lg cursor-pointer transition-colors hover:border-navy-500"
                onClick={() => toggleExpand(doc)}
              >
                <div className="p-4">
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-medium text-sm">{doc.name}</h4>
                    <div className="flex items-center gap-2">
                      {reliability && (
                        <span className={`text-xs px-2 py-0.5 rounded font-medium ${reliabilityColor(reliability)}`}>
                          {reliability}
                        </span>
                      )}
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
                      dangerouslySetInnerHTML={{ __html: highlightEntities(content, entityNames) }}
                    />
                  </div>
                )}
              </div>
            );
          })}
          {documents.length === 0 && (
            <p className="text-gray-500 text-sm">No documents found. Upload content via Collections to begin.</p>
          )}
        </div>
      </main>
    </div>
  );
}
