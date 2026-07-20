'use client';
import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Sidebar from '@/components/Sidebar';
import { useProject } from '@/lib/ProjectContext';
import { watchlistApi } from '@/lib/api';
import { TYPE_COLOR_CLASS as TYPE_COLORS } from '@/lib/entityStyles';
import { useNotifications } from '@/components/NotificationProvider';

interface WatchedEntity {
  id: string;
  name: string;
  entity_type: string;
  relationship_count?: number;
}

// TYPE_COLORS imported from '@/lib/entityStyles' (single source of truth)

export default function WatchlistPage() {
  const { activeProject } = useProject();
  const { addNotification } = useNotifications();
  const [entities, setEntities] = useState<WatchedEntity[]>([]);
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const loadWatchlist = useCallback(async () => {
    if (!activeProject) return;
    setLoading(true);
    try {
      const res = await watchlistApi.list(activeProject.id);
      const data = res.data;
      if (Array.isArray(data)) {
        setEntities(data);
      } else if (data && Array.isArray(data.entities)) {
        setEntities(data.entities);
      } else if (data && Array.isArray(data.watchlist)) {
        setEntities(data.watchlist);
      } else {
        setEntities([]);
      }
    } catch {
      console.error('Failed to load watchlist');
      addNotification({
        title: 'Failed to load watchlist',
        message: 'Could not load watched entities for this project. Please try again.',
        type: 'error',
      });
    } finally {
      setLoading(false);
    }
  }, [activeProject, addNotification]);

  useEffect(() => {
    loadWatchlist();
  }, [loadWatchlist]);

  async function removeFromWatchlist(entityId: string) {
    if (!activeProject) return;
    try {
      await watchlistApi.remove(activeProject.id, entityId);
      setEntities(prev => prev.filter(e => e.id !== entityId));
    } catch {
      console.error('Failed to remove from watchlist');
      addNotification({
        title: 'Failed to remove entity',
        message: 'The entity could not be removed from the watchlist. Please try again.',
        type: 'error',
      });
    }
  }

  if (!activeProject) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="md:ml-56 flex-1 p-4 pt-16 pb-24 md:p-8 md:pt-8 md:pb-8">
          <h2 className="text-2xl font-bold mb-4">Watchlist</h2>
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 text-center text-gray-500">
            <p className="text-lg mb-2">No Project Selected</p>
            <p className="text-sm">Go to Projects and select one to view watched entities.</p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="flex">
      <Sidebar />
      <main className="md:ml-56 flex-1 p-4 pt-16 pb-24 md:p-8 md:pt-8 md:pb-8">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold">Watchlist</h2>
          <span className="text-sm text-gray-400">{entities.length} watched entities</span>
        </div>

        {loading ? (
          <div className="text-gray-500 text-center py-8">Loading watchlist...</div>
        ) : entities.length === 0 ? (
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 text-center text-gray-500">
            <p className="text-lg mb-2">No Watched Entities</p>
            <p className="text-sm">Add entities to your watchlist from the Network Analysis page.</p>
          </div>
        ) : (
          <div className="bg-navy-800 border border-navy-600 rounded-lg divide-y divide-navy-700">
            {entities.map((entity) => (
              <div key={entity.id} className="flex items-center justify-between px-5 py-4 hover:bg-navy-700/50 transition-colors">
                <div className="flex items-center gap-3">
                  <span className={`w-3 h-3 rounded-full flex-none ${TYPE_COLORS[entity.entity_type] || 'bg-gray-500'}`} />
                  <span className="font-medium text-gray-200">{entity.name}</span>
                  <span className="text-xs px-2 py-0.5 rounded bg-navy-600 text-gray-400">{entity.entity_type}</span>
                  {entity.relationship_count !== undefined && (
                    <span className="text-xs text-gray-500">{entity.relationship_count} relationships</span>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => router.push(`/network?select=${entity.id}`)}
                    className="text-xs text-accent-blue hover:text-blue-400 transition-colors"
                  >
                    View in Graph
                  </button>
                  <button
                    onClick={() => removeFromWatchlist(entity.id)}
                    className="text-xs text-red-400 hover:text-red-300 transition-colors"
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
