'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/Sidebar';
import { useProject } from '@/lib/ProjectContext';
import { entitiesApi, ingestApi } from '@/lib/api';

interface DocumentEntity {
  id: string;
  name: string;
  entity_type: string;
  properties?: Record<string, unknown>;
}

export default function DataSourcesPage() {
  const { activeProject } = useProject();
  const [documents, setDocuments] = useState<DocumentEntity[]>([]);
  const [content, setContent] = useState('');
  const [reliability, setReliability] = useState('B');
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);

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

  async function uploadDocument() {
    if (!content.trim() || !activeProject) return;
    setUploading(true);
    setUploadMsg(null);
    try {
      await ingestApi.text(activeProject.id, content.trim(), reliability);
      setContent('');
      setUploadMsg('Document ingested successfully.');
      loadDocuments();
    } catch {
      setUploadMsg('Failed to ingest document.');
    } finally {
      setUploading(false);
    }
  }

  if (!activeProject) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="ml-56 flex-1 p-8">
          <h2 className="text-2xl font-bold mb-4">Data Sources</h2>
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
        <h2 className="text-2xl font-bold mb-6">Data Sources</h2>

        <div className="bg-navy-800 border border-navy-600 rounded-lg p-6 mb-6">
          <h3 className="text-sm font-semibold text-gray-400 mb-3">Upload Document</h3>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Paste text content here for ingestion and entity extraction..."
            className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm h-40 focus:outline-none focus:border-accent-blue resize-none font-mono"
          />
          <div className="flex items-center gap-4 mt-3">
            <div className="flex items-center gap-2">
              <label className="text-xs text-gray-400">Reliability:</label>
              <select
                value={reliability}
                onChange={(e) => setReliability(e.target.value)}
                className="bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs focus:outline-none focus:border-accent-blue"
              >
                <option value="A">A - Completely Reliable</option>
                <option value="B">B - Usually Reliable</option>
                <option value="C">C - Fairly Reliable</option>
                <option value="D">D - Not Usually Reliable</option>
                <option value="E">E - Unreliable</option>
                <option value="F">F - Cannot Be Judged</option>
              </select>
            </div>
            <button
              onClick={uploadDocument}
              disabled={uploading || !content.trim()}
              className="bg-accent-blue hover:bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium disabled:opacity-50 transition-colors"
            >
              {uploading ? 'Ingesting...' : 'Ingest Document'}
            </button>
          </div>
          {uploadMsg && (
            <p className={`text-xs mt-2 ${uploadMsg.includes('success') ? 'text-green-400' : 'text-red-400'}`}>
              {uploadMsg}
            </p>
          )}
        </div>

        <h3 className="text-lg font-semibold mb-4">Documents ({documents.length})</h3>
        <div className="space-y-3">
          {documents.map((doc) => (
            <div key={doc.id} className="bg-navy-800 border border-navy-600 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <h4 className="font-medium text-sm">{doc.name}</h4>
                {doc.properties?.reliability_rating ? (
                  <span className="text-xs px-2 py-0.5 rounded bg-navy-600 text-gray-400">
                    Reliability: {String(doc.properties.reliability_rating)}
                  </span>
                ) : null}
              </div>
              {doc.properties?.content ? (
                <p className="text-xs text-gray-400 line-clamp-3 font-mono">
                  {String(doc.properties.content).substring(0, 300)}
                  {String(doc.properties.content).length > 300 ? '...' : ''}
                </p>
              ) : null}
            </div>
          ))}
          {documents.length === 0 && (
            <p className="text-gray-500 text-sm">No documents found. Upload content to begin.</p>
          )}
        </div>
      </main>
    </div>
  );
}
