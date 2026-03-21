'use client';
import { useEffect, useState, useCallback, useRef } from 'react';
import Sidebar from '@/components/Sidebar';
import { useProject } from '@/lib/ProjectContext';
import { collectionsApi, ingestApi } from '@/lib/api';

interface Collection {
  id: string;
  pir: string;
  status: string;
  project_id: string;
  created_at?: string;
  results?: unknown;
}

const EXTRACTION_MODES = [
  { value: 'nlp', label: 'NLP' },
  { value: 'llm', label: 'LLM' },
  { value: 'hybrid', label: 'Hybrid' },
];

export default function CollectionsPage() {
  const { activeProject } = useProject();
  const [pir, setPir] = useState('');
  const [collections, setCollections] = useState<Collection[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadContent, setUploadContent] = useState('');
  const [uploadReliability, setUploadReliability] = useState('C3');
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);

  // File upload state
  const [fileUploadOpen, setFileUploadOpen] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [fileReliability, setFileReliability] = useState('C3');
  const [extractionMode, setExtractionMode] = useState('hybrid');
  const [fileUploading, setFileUploading] = useState(false);
  const [fileUploadMsg, setFileUploadMsg] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadCollections = useCallback(async () => {
    try {
      const res = await collectionsApi.list();
      setCollections(res.data);
    } catch (e) {
      console.error('Failed to load collections', e);
    }
  }, []);

  useEffect(() => {
    loadCollections();
  }, [loadCollections]);

  // Poll active tasks
  useEffect(() => {
    const activeTasks = collections.filter(c => c.status === 'pending' || c.status === 'running');
    if (activeTasks.length === 0) return;
    const interval = setInterval(async () => {
      for (const task of activeTasks) {
        try {
          const res = await collectionsApi.status(task.id);
          setCollections(prev => prev.map(c => c.id === task.id ? { ...c, ...res.data } : c));
        } catch { /* ignore polling errors */ }
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [collections]);

  async function createCollection() {
    if (!pir.trim() || !activeProject) return;
    setLoading(true);
    setError(null);
    try {
      await collectionsApi.create({ project_id: activeProject.id, pir: pir.trim() });
      setPir('');
      loadCollections();
    } catch {
      setError('Failed to create collection task.');
    } finally {
      setLoading(false);
    }
  }

  async function uploadDocument() {
    if (!uploadContent.trim() || !activeProject) return;
    setUploading(true);
    setUploadMsg(null);
    try {
      const res = await ingestApi.text(activeProject.id, uploadContent.trim(), uploadReliability);
      const d = res.data;
      const entityCount = d?.entities_created ?? d?.entity_count ?? 0;
      const relCount = d?.relationships_created ?? 0;
      setUploadContent('');
      setUploadMsg(`Document ingested successfully. ${entityCount} entities created, ${relCount} relationships found.`);
    } catch {
      setUploadMsg('Failed to ingest document.');
    } finally {
      setUploading(false);
    }
  }

  function handleFileDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const droppedFiles = Array.from(e.dataTransfer.files).filter(f =>
      f.name.endsWith('.pdf') || f.name.endsWith('.txt') || f.name.endsWith('.md')
    );
    if (droppedFiles.length > 0) {
      setSelectedFiles(prev => [...prev, ...droppedFiles]);
    }
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files) {
      setSelectedFiles(prev => [...prev, ...Array.from(e.target.files!)]);
    }
  }

  function removeFile(index: number) {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
  }

  async function uploadFiles() {
    if (selectedFiles.length === 0 || !activeProject) return;
    setFileUploading(true);
    setFileUploadMsg(null);
    try {
      if (selectedFiles.length === 1) {
        const res = await ingestApi.file(activeProject.id, selectedFiles[0], fileReliability, extractionMode);
        const d = res.data;
        setFileUploadMsg(`"${d?.document_name}" ingested. ${d?.entities_created ?? 0} entities created, ${d?.relationships_created ?? 0} relationships, ${d?.chunks ?? 0} chunks.`);
      } else {
        const res = await ingestApi.batch(activeProject.id, selectedFiles, fileReliability, extractionMode);
        const d = res.data;
        setFileUploadMsg(`${d?.documents_processed ?? selectedFiles.length} files ingested. ${d?.total_entities_created ?? 0} entities, ${d?.total_relationships_created ?? 0} relationships.`);
      }
      setSelectedFiles([]);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch {
      setFileUploadMsg('Failed to upload file(s). Check file format and try again.');
    } finally {
      setFileUploading(false);
    }
  }

  const statusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'bg-green-900/30 text-green-400';
      case 'running': return 'bg-yellow-900/30 text-yellow-400';
      case 'pending': return 'bg-blue-900/30 text-blue-400';
      case 'failed': return 'bg-red-900/30 text-red-400';
      default: return 'bg-gray-900/30 text-gray-400';
    }
  };

  if (!activeProject) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="ml-56 flex-1 p-8">
          <h2 className="text-2xl font-bold mb-4">Collections</h2>
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
        <h2 className="text-2xl font-bold mb-6">Collections</h2>

        <div className="bg-navy-800 border border-navy-600 rounded-lg p-6 mb-6">
          <h3 className="text-sm font-semibold text-gray-400 mb-3">Submit Priority Intelligence Requirement</h3>
          <textarea
            value={pir}
            onChange={(e) => setPir(e.target.value)}
            placeholder="Enter your PIR... e.g., What are the current cyber threats targeting financial institutions in Southeast Asia?"
            className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm h-32 focus:outline-none focus:border-accent-blue resize-none"
          />
          {error && <p className="text-red-400 text-xs mt-2">{error}</p>}
          <button
            onClick={createCollection}
            disabled={loading || !pir.trim()}
            className="mt-3 bg-accent-blue hover:bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium disabled:opacity-50 transition-colors"
          >
            {loading ? 'Creating...' : 'Create Collection'}
          </button>
        </div>

        {/* File Upload Section */}
        <div className="bg-navy-800 border border-navy-600 rounded-lg mb-6">
          <button
            onClick={() => setFileUploadOpen(!fileUploadOpen)}
            className="w-full flex items-center justify-between p-4 text-left"
          >
            <h3 className="text-sm font-semibold text-gray-400">File Upload (PDF, TXT, MD)</h3>
            <span className="text-gray-500 text-xs">{fileUploadOpen ? '▲' : '▼'}</span>
          </button>
          {fileUploadOpen && (
            <div className="px-6 pb-6">
              {/* Drag and drop zone */}
              <div
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleFileDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
                  dragOver
                    ? 'border-accent-blue bg-accent-blue/10'
                    : 'border-navy-600 hover:border-navy-500 hover:bg-navy-700/50'
                }`}
              >
                <div className="text-gray-400 mb-2">
                  <svg className="w-8 h-8 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                </div>
                <p className="text-sm text-gray-400">Drag and drop files here, or click to browse</p>
                <p className="text-xs text-gray-500 mt-1">Accepted: PDF, TXT, MD</p>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".pdf,.txt,.md"
                  onChange={handleFileSelect}
                  className="hidden"
                />
              </div>

              {/* Selected files list */}
              {selectedFiles.length > 0 && (
                <div className="mt-3 space-y-1">
                  {selectedFiles.map((file, i) => (
                    <div key={i} className="flex items-center justify-between bg-navy-700 rounded px-3 py-2 text-xs">
                      <span className="text-gray-300 truncate flex-1">{file.name}</span>
                      <span className="text-gray-500 mx-2">{(file.size / 1024).toFixed(1)} KB</span>
                      <button
                        onClick={() => removeFile(i)}
                        className="text-red-400 hover:text-red-300 ml-2"
                      >
                        x
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Options row */}
              <div className="flex items-center gap-4 mt-3 flex-wrap">
                <div className="flex items-center gap-2">
                  <label className="text-xs text-gray-400">Reliability:</label>
                  <select
                    value={fileReliability}
                    onChange={(e) => setFileReliability(e.target.value)}
                    className="bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs focus:outline-none focus:border-accent-blue"
                  >
                    <option value="A1">A1 - Reliable, Confirmed</option>
                    <option value="A2">A2 - Reliable, Probably True</option>
                    <option value="B2">B2 - Usually Reliable, Probably True</option>
                    <option value="C3">C3 - Fairly Reliable, Possibly True</option>
                    <option value="D4">D4 - Not Usually Reliable, Doubtful</option>
                    <option value="E5">E5 - Unreliable, Improbable</option>
                    <option value="F6">F6 - Cannot Be Judged</option>
                  </select>
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-xs text-gray-400">Extraction Mode:</label>
                  <select
                    value={extractionMode}
                    onChange={(e) => setExtractionMode(e.target.value)}
                    className="bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs focus:outline-none focus:border-accent-blue"
                  >
                    {EXTRACTION_MODES.map(m => (
                      <option key={m.value} value={m.value}>{m.label}</option>
                    ))}
                  </select>
                </div>
                <button
                  onClick={uploadFiles}
                  disabled={fileUploading || selectedFiles.length === 0}
                  className="bg-accent-blue hover:bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium disabled:opacity-50 transition-colors"
                >
                  {fileUploading ? 'Uploading...' : `Upload ${selectedFiles.length > 0 ? `(${selectedFiles.length} file${selectedFiles.length > 1 ? 's' : ''})` : ''}`}
                </button>
              </div>
              {fileUploadMsg && (
                <p className={`text-xs mt-2 ${fileUploadMsg.includes('success') ? 'text-green-400' : 'text-red-400'}`}>
                  {fileUploadMsg}
                </p>
              )}
            </div>
          )}
        </div>

        {/* Manual Document Upload (Text) */}
        <div className="bg-navy-800 border border-navy-600 rounded-lg mb-6">
          <button
            onClick={() => setUploadOpen(!uploadOpen)}
            className="w-full flex items-center justify-between p-4 text-left"
          >
            <h3 className="text-sm font-semibold text-gray-400">Manual Text Upload</h3>
            <span className="text-gray-500 text-xs">{uploadOpen ? '▲' : '▼'}</span>
          </button>
          {uploadOpen && (
            <div className="px-6 pb-6">
              <textarea
                value={uploadContent}
                onChange={(e) => setUploadContent(e.target.value)}
                placeholder="Paste document text here for ingestion and entity extraction..."
                className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm h-40 focus:outline-none focus:border-accent-blue resize-none font-mono"
              />
              <div className="flex items-center gap-4 mt-3">
                <div className="flex items-center gap-2">
                  <label className="text-xs text-gray-400">Reliability:</label>
                  <select
                    value={uploadReliability}
                    onChange={(e) => setUploadReliability(e.target.value)}
                    className="bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs focus:outline-none focus:border-accent-blue"
                  >
                    <option value="A1">A1 - Reliable, Confirmed</option>
                    <option value="A2">A2 - Reliable, Probably True</option>
                    <option value="A3">A3 - Reliable, Possibly True</option>
                    <option value="B1">B1 - Usually Reliable, Confirmed</option>
                    <option value="B2">B2 - Usually Reliable, Probably True</option>
                    <option value="B3">B3 - Usually Reliable, Possibly True</option>
                    <option value="C1">C1 - Fairly Reliable, Confirmed</option>
                    <option value="C2">C2 - Fairly Reliable, Probably True</option>
                    <option value="C3">C3 - Fairly Reliable, Possibly True</option>
                    <option value="D4">D4 - Not Usually Reliable, Doubtful</option>
                    <option value="D5">D5 - Not Usually Reliable, Improbable</option>
                    <option value="E5">E5 - Unreliable, Improbable</option>
                    <option value="E6">E6 - Unreliable, Cannot Be Judged</option>
                    <option value="F6">F6 - Cannot Be Judged</option>
                  </select>
                </div>
                <button
                  onClick={uploadDocument}
                  disabled={uploading || !uploadContent.trim()}
                  className="bg-accent-blue hover:bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium disabled:opacity-50 transition-colors"
                >
                  {uploading ? 'Uploading...' : 'Upload Document'}
                </button>
              </div>
              {uploadMsg && (
                <p className={`text-xs mt-2 ${uploadMsg.includes('success') ? 'text-green-400' : 'text-red-400'}`}>
                  {uploadMsg}
                </p>
              )}
            </div>
          )}
        </div>

        <h3 className="text-lg font-semibold mb-4">Collection Tasks</h3>
        <div className="space-y-3">
          {collections.map((col) => (
            <div key={col.id} className="bg-navy-800 border border-navy-600 rounded-lg p-4">
              <div className="flex items-start justify-between">
                <p className="text-sm text-gray-200 flex-1">{col.pir}</p>
                <span className={`text-xs px-2 py-0.5 rounded ml-3 flex-none ${statusColor(col.status)}`}>
                  {col.status}
                </span>
              </div>
              {col.created_at && (
                <p className="text-xs text-gray-500 mt-2">{new Date(col.created_at).toLocaleString()}</p>
              )}
            </div>
          ))}
          {collections.length === 0 && (
            <p className="text-gray-500 text-sm">No collection tasks yet.</p>
          )}
        </div>
      </main>
    </div>
  );
}
