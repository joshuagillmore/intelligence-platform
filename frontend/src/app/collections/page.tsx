'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/Sidebar';
import { useProject } from '@/lib/ProjectContext';
import { collectionsApi } from '@/lib/api';

interface Collection {
  id: string;
  pir: string;
  status: string;
  project_id: string;
  created_at?: string;
  results?: unknown;
}

export default function CollectionsPage() {
  const { activeProject } = useProject();
  const [pir, setPir] = useState('');
  const [collections, setCollections] = useState<Collection[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
        } catch {}
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
