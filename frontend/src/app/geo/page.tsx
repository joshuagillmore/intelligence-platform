'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/Sidebar';
import { useProject } from '@/lib/ProjectContext';
import { geoApi, queryApi, entitiesApi } from '@/lib/api';

interface GeoLocation {
  id: string;
  name: string;
  latitude?: number | null;
  longitude?: number | null;
  lat?: number | null;
  lng?: number | null;
  geocoded?: boolean;
  connections?: number;
  entity_type?: string;
  properties?: Record<string, unknown>;
}

interface LocationRelationship {
  source_name?: string;
  target_name?: string;
  source_id: string;
  target_id: string;
  rel_type: string;
}

export default function GeoPage() {
  const { activeProject } = useProject();
  const [locations, setLocations] = useState<GeoLocation[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [expandedRels, setExpandedRels] = useState<LocationRelationship[]>([]);
  const [relsLoading, setRelsLoading] = useState(false);
  const [queryInput, setQueryInput] = useState('');
  const [queryResult, setQueryResult] = useState<string | null>(null);
  const [queryLoading, setQueryLoading] = useState(false);

  const loadLocations = useCallback(async () => {
    if (!activeProject) return;
    setLoading(true);
    try {
      const res = await geoApi.locations(activeProject.id);
      const data = res.data;
      if (Array.isArray(data)) {
        setLocations(data);
      } else if (data.locations) {
        setLocations(data.locations);
      } else {
        setLocations([]);
      }
    } catch {
      // Fallback: try loading Location entities directly
      try {
        const res = await entitiesApi.search(activeProject.id, undefined, 'Location');
        const entities = res.data || [];
        setLocations(entities.map((e: { id: string; name: string; properties?: Record<string, unknown> }) => ({
          id: e.id,
          name: e.name,
          latitude: e.properties?.latitude as number | undefined,
          longitude: e.properties?.longitude as number | undefined,
          geocoded: !!(e.properties?.latitude && e.properties?.longitude),
          connections: 0,
          properties: e.properties,
        })));
      } catch {
        setLocations([]);
      }
    } finally {
      setLoading(false);
    }
  }, [activeProject]);

  useEffect(() => {
    loadLocations();
  }, [loadLocations]);

  async function toggleExpand(loc: GeoLocation) {
    if (expandedId === loc.id) {
      setExpandedId(null);
      setExpandedRels([]);
      return;
    }
    setExpandedId(loc.id);
    setExpandedRels([]);
    setRelsLoading(true);
    try {
      const res = await entitiesApi.get(loc.id);
      setExpandedRels(res.data.relationships || []);
    } catch {
      setExpandedRels([]);
    } finally {
      setRelsLoading(false);
    }
  }

  async function askGeoQuery() {
    if (!queryInput.trim() || !activeProject) return;
    setQueryLoading(true);
    setQueryResult(null);
    try {
      const res = await queryApi.rag(activeProject.id, queryInput);
      setQueryResult(res.data.answer || res.data.response || JSON.stringify(res.data));
    } catch {
      setQueryResult('Failed to process query.');
    } finally {
      setQueryLoading(false);
    }
  }

  const getLat = (loc: GeoLocation) => loc.latitude ?? loc.lat ?? (loc.properties?.latitude as number | undefined);
  const getLng = (loc: GeoLocation) => loc.longitude ?? loc.lng ?? (loc.properties?.longitude as number | undefined);
  const isGeocoded = (loc: GeoLocation) => loc.geocoded ?? !!(getLat(loc) && getLng(loc));
  const totalConnections = locations.reduce((sum, l) => sum + (l.connections || 0), 0);
  const geocodedCount = locations.filter(l => isGeocoded(l)).length;

  if (!activeProject) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="ml-56 flex-1 p-8">
          <h2 className="text-2xl font-bold mb-4">Geo-Intelligence</h2>
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
        <h2 className="text-2xl font-bold mb-6">Geo-Intelligence</h2>

        {/* Summary cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-accent-blue">{locations.length}</div>
            <div className="text-xs text-gray-400">Total Locations</div>
          </div>
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-green-400">{geocodedCount}</div>
            <div className="text-xs text-gray-400">Geocoded</div>
          </div>
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-accent-blue">{totalConnections}</div>
            <div className="text-xs text-gray-400">Total Connections</div>
          </div>
        </div>

        {/* Query interface */}
        <div className="bg-navy-800 border border-navy-600 rounded-lg p-4 mb-6">
          <h3 className="text-sm font-semibold text-gray-400 mb-3">Ask about geographic relationships</h3>
          <div className="flex gap-2">
            <input
              value={queryInput}
              onChange={(e) => setQueryInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && askGeoQuery()}
              placeholder="e.g., What locations are connected to...?"
              className="flex-1 bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-blue"
            />
            <button
              onClick={askGeoQuery}
              disabled={queryLoading || !queryInput.trim()}
              className="bg-accent-blue hover:bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium disabled:opacity-50 transition-colors"
            >
              {queryLoading ? 'Asking...' : 'Ask'}
            </button>
          </div>
          {queryResult && (
            <div className="mt-3 bg-navy-700 rounded p-3 text-sm text-gray-300 whitespace-pre-wrap max-h-48 overflow-y-auto">
              {queryResult}
            </div>
          )}
        </div>

        {/* Locations table */}
        <div className="bg-navy-800 border border-navy-600 rounded-lg">
          <div className="p-4 border-b border-navy-600">
            <h3 className="text-sm font-semibold text-gray-400">Locations</h3>
          </div>
          {loading ? (
            <div className="p-8 text-center text-gray-500 text-sm">Loading locations...</div>
          ) : locations.length === 0 ? (
            <div className="p-8 text-center text-gray-500 text-sm">
              No location entities found. Ingest documents containing geographic references.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-navy-600 text-gray-400 text-xs">
                    <th className="text-left py-3 px-4 font-medium">Name</th>
                    <th className="text-left py-3 px-4 font-medium">Lat</th>
                    <th className="text-left py-3 px-4 font-medium">Lng</th>
                    <th className="text-left py-3 px-4 font-medium">Connections</th>
                    <th className="text-left py-3 px-4 font-medium">Geocoded</th>
                    <th className="text-left py-3 px-4 font-medium"></th>
                  </tr>
                </thead>
                <tbody>
                  {locations.map(loc => (
                    <>
                      <tr
                        key={loc.id}
                        className="border-b border-navy-700 hover:bg-navy-700/50 cursor-pointer"
                        onClick={() => toggleExpand(loc)}
                      >
                        <td className="py-2.5 px-4 text-gray-200 font-medium">{loc.name}</td>
                        <td className="py-2.5 px-4 text-gray-400 font-mono text-xs">
                          {getLat(loc) != null ? Number(getLat(loc)).toFixed(4) : '--'}
                        </td>
                        <td className="py-2.5 px-4 text-gray-400 font-mono text-xs">
                          {getLng(loc) != null ? Number(getLng(loc)).toFixed(4) : '--'}
                        </td>
                        <td className="py-2.5 px-4 text-gray-400">{loc.connections ?? '--'}</td>
                        <td className="py-2.5 px-4">
                          {isGeocoded(loc) ? (
                            <span className="text-xs px-2 py-0.5 rounded bg-green-900/30 text-green-400">Yes</span>
                          ) : (
                            <span className="text-xs px-2 py-0.5 rounded bg-gray-700 text-gray-400">No</span>
                          )}
                        </td>
                        <td className="py-2.5 px-4 text-xs text-gray-500">
                          {expandedId === loc.id ? '▲' : '▼'}
                        </td>
                      </tr>
                      {expandedId === loc.id && (
                        <tr key={`${loc.id}-rels`}>
                          <td colSpan={6} className="px-4 pb-3 pt-1">
                            {relsLoading ? (
                              <p className="text-xs text-gray-500">Loading relationships...</p>
                            ) : expandedRels.length === 0 ? (
                              <p className="text-xs text-gray-500">No relationships found.</p>
                            ) : (
                              <div className="bg-navy-900/50 rounded p-3 space-y-1">
                                {expandedRels.map((rel, i) => (
                                  <div key={i} className="flex items-center gap-2 text-xs">
                                    <span className="text-accent-blue font-medium">{rel.rel_type}</span>
                                    <span className="text-gray-500">&rarr;</span>
                                    <span className="text-gray-300">
                                      {rel.source_name === loc.name
                                        ? (rel.target_name || rel.target_id)
                                        : (rel.source_name || rel.source_id)}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
