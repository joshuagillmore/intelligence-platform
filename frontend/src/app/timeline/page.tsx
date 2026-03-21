'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/Sidebar';
import LoadingSpinner from '@/components/LoadingSpinner';
import { useProject } from '@/lib/ProjectContext';
import { timelineApi } from '@/lib/api';

interface TimelineEvent {
  id: string;
  name: string;
  entity_type: string;
  timestamp: string;
  event_type: string;
}

const TYPE_COLORS: Record<string, string> = {
  Person: 'bg-orange-500',
  Organization: 'bg-blue-500',
  Location: 'bg-green-500',
  ThreatActor: 'bg-red-500',
  Document: 'bg-gray-500',
  IPAddress: 'bg-cyan-500',
  Domain: 'bg-purple-500',
  Event: 'bg-yellow-500',
  Hash: 'bg-pink-500',
  Vulnerability: 'bg-rose-500',
  Report: 'bg-indigo-500',
  Topic: 'bg-teal-500',
};

const ENTITY_TYPES = ['Person', 'Organization', 'Location', 'ThreatActor', 'Document', 'IPAddress', 'Domain', 'Event', 'Hash', 'Vulnerability', 'Report', 'Topic'];

function groupByDate(events: TimelineEvent[]): Record<string, TimelineEvent[]> {
  const groups: Record<string, TimelineEvent[]> = {};
  const now = new Date();
  const today = now.toISOString().slice(0, 10);
  const yesterday = new Date(now.getTime() - 86400000).toISOString().slice(0, 10);

  for (const event of events) {
    const dateStr = event.timestamp ? event.timestamp.slice(0, 10) : 'Unknown';
    let label: string;
    if (dateStr === today) label = 'Today';
    else if (dateStr === yesterday) label = 'Yesterday';
    else label = dateStr || 'Unknown';

    if (!groups[label]) groups[label] = [];
    groups[label].push(event);
  }
  return groups;
}

export default function TimelinePage() {
  const { activeProject } = useProject();
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [enabledTypes, setEnabledTypes] = useState<Set<string>>(new Set(ENTITY_TYPES));

  const loadTimeline = useCallback(async () => {
    if (!activeProject) return;
    setLoading(true);
    try {
      const res = await timelineApi.get(activeProject.id);
      setEvents(res.data.events || []);
    } catch (e) {
      console.error('Failed to load timeline', e);
    } finally {
      setLoading(false);
    }
  }, [activeProject]);

  useEffect(() => {
    loadTimeline();
  }, [loadTimeline]);

  function toggleType(t: string) {
    setEnabledTypes(prev => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  }

  const filtered = events.filter(e => enabledTypes.has(e.entity_type));
  const grouped = groupByDate(filtered);

  if (!activeProject) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="ml-56 flex-1 p-8">
          <h2 className="text-2xl font-bold mb-4">Timeline</h2>
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 text-center text-gray-500">
            <p className="text-lg mb-2">No Project Selected</p>
            <p className="text-sm">Go to Projects and select one to begin analysis.</p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="ml-56 flex-1 flex flex-col h-screen overflow-hidden">
        <div className="flex-none px-6 py-4 border-b border-navy-600 bg-navy-800 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold">Timeline</h2>
            <p className="text-xs text-gray-400 mt-1">{filtered.length} events</p>
          </div>
          <button
            onClick={loadTimeline}
            disabled={loading}
            className="bg-accent-blue hover:bg-blue-600 text-white px-4 py-2 rounded text-sm disabled:opacity-50"
          >
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>

        <div className="flex-1 flex overflow-hidden">
          {/* Filter sidebar */}
          <div className="w-56 flex-none bg-navy-800 border-r border-navy-600 p-4 overflow-y-auto">
            <h3 className="text-sm font-semibold text-gray-400 mb-3">Filter by Type</h3>
            <div className="space-y-2">
              {ENTITY_TYPES.map(t => (
                <label key={t} className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={enabledTypes.has(t)}
                    onChange={() => toggleType(t)}
                    className="accent-accent-blue"
                  />
                  <span className={`w-2 h-2 rounded-full ${TYPE_COLORS[t] || 'bg-gray-500'}`} />
                  {t}
                </label>
              ))}
            </div>
            <div className="mt-4 flex gap-2">
              <button
                onClick={() => setEnabledTypes(new Set(ENTITY_TYPES))}
                className="text-xs text-accent-blue hover:underline"
              >
                All
              </button>
              <button
                onClick={() => setEnabledTypes(new Set())}
                className="text-xs text-gray-400 hover:underline"
              >
                None
              </button>
            </div>
          </div>

          {/* Timeline content */}
          <div className="flex-1 overflow-y-auto p-6">
            {loading && events.length === 0 ? (
              <div className="mt-8"><LoadingSpinner size="lg" /></div>
            ) : filtered.length === 0 ? (
              <div className="text-center text-gray-500 mt-8">No events to display.</div>
            ) : (
              <div className="space-y-8">
                {Object.entries(grouped).map(([dateLabel, dateEvents]) => (
                  <div key={dateLabel}>
                    <h3 className="text-sm font-bold text-gray-400 mb-4 sticky top-0 bg-navy-900 py-2 z-10 border-b border-navy-700">
                      {dateLabel}
                      <span className="ml-2 text-xs font-normal text-gray-500">({dateEvents.length})</span>
                    </h3>
                    <div className="relative pl-6 border-l-2 border-navy-600 space-y-4">
                      {dateEvents.map((event) => (
                        <div key={event.id} className="relative">
                          {/* Timeline dot */}
                          <div className={`absolute -left-[25px] top-2 w-3 h-3 rounded-full border-2 border-navy-900 ${TYPE_COLORS[event.entity_type] || 'bg-gray-500'}`} />
                          <div className="bg-navy-800 border border-navy-600 rounded-lg p-4 hover:border-navy-500 transition-colors">
                            <div className="flex items-center justify-between mb-1">
                              <div className="flex items-center gap-2">
                                <span className="font-medium text-gray-200">{event.name}</span>
                                <span className={`text-xs px-2 py-0.5 rounded text-white ${TYPE_COLORS[event.entity_type] || 'bg-gray-500'}`}>
                                  {event.entity_type}
                                </span>
                              </div>
                              <span className="text-xs text-gray-500">
                                {event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : ''}
                              </span>
                            </div>
                            <p className="text-xs text-gray-400">Entity created</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
