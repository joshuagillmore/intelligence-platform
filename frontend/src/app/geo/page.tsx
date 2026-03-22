'use client';
import { useEffect, useState, useCallback } from 'react';
import dynamic from 'next/dynamic';
import Sidebar from '@/components/Sidebar';
import LoadingSpinner from '@/components/LoadingSpinner';
import { useProject } from '@/lib/ProjectContext';
import { geoApi, queryApi, entitiesApi } from '@/lib/api';

const GeoMap = dynamic(() => import('@/components/GeoMap'), { ssr: false });

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
  const [selectedLocation, setSelectedLocation] = useState<GeoLocation | null>(null);
  const [selectedRels, setSelectedRels] = useState<LocationRelationship[]>([]);
  const [relsLoading, setRelsLoading] = useState(false);
  const [queryInput, setQueryInput] = useState('');
  const [queryResult, setQueryResult] = useState<string | null>(null);
  const [queryLoading, setQueryLoading] = useState(false);
  const [geoEdges, setGeoEdges] = useState<Array<{
    source_coords?: number[]; target_coords?: number[];
    source_name: string; target_name: string;
    weight: number; shared_entities: string[];
  }>>([]);

  const getLat = (loc: GeoLocation) => loc.latitude ?? loc.lat ?? (loc.properties?.latitude as number | undefined);
  const getLng = (loc: GeoLocation) => loc.longitude ?? loc.lng ?? (loc.properties?.longitude as number | undefined);
  const isGeocoded = (loc: GeoLocation) => loc.geocoded ?? !!(getLat(loc) && getLng(loc));

  const loadLocations = useCallback(async () => {
    if (!activeProject) return;
    setLoading(true);
    try {
      const res = await geoApi.locations(activeProject.id);
      const data = res.data;
      if (Array.isArray(data)) {
        setLocations(data);
      } else if (data && data.locations) {
        setLocations(data.locations);
        if (data.edges) setGeoEdges(data.edges);
      } else {
        setLocations([]);
      }
    } catch {
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

  async function handleLocationClick(loc: GeoLocation) {
    if (selectedLocation?.id === loc.id) {
      setSelectedLocation(null);
      setSelectedRels([]);
      return;
    }
    setSelectedLocation(loc);
    setSelectedRels([]);
    setRelsLoading(true);
    try {
      const res = await entitiesApi.get(loc.id);
      setSelectedRels(res.data?.relationships || []);
    } catch {
      setSelectedRels([]);
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
      <main className="ml-56 flex-1 p-6 flex flex-col h-screen">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-bold">Geo-Intelligence</h2>
          <div className="flex gap-4 text-sm">
            <span className="bg-navy-800 px-3 py-1 rounded border border-navy-600">
              {locations.length} Locations
            </span>
            <span className="bg-navy-800 px-3 py-1 rounded border border-navy-600 text-accent-blue">
              {geocodedCount} Geocoded
            </span>
            <span className="bg-navy-800 px-3 py-1 rounded border border-navy-600">
              {totalConnections} Connections
            </span>
            <span className="bg-navy-800 px-3 py-1 rounded border border-navy-600 text-purple-400">
              {geoEdges.length} Location Links
            </span>
          </div>
        </div>

        <div className="flex flex-1 gap-4 min-h-0">
          {/* Map */}
          <div className="flex-1 bg-navy-800 border border-navy-600 rounded-lg overflow-hidden">
            {loading ? (
              <div className="w-full h-full flex items-center justify-center"><LoadingSpinner size="lg" /></div>
            ) : (
              <GeoMap
                locations={locations}
                connectionLines={geoEdges
                  .filter(e => e.source_coords && e.target_coords)
                  .map(e => ({
                    from: [e.source_coords![0], e.source_coords![1]] as [number, number],
                    to: [e.target_coords![0], e.target_coords![1]] as [number, number],
                    names: `${e.source_name} ↔ ${e.target_name}`,
                    weight: e.weight,
                    shared_entities: e.shared_entities,
                  }))}
                onLocationClick={handleLocationClick}
                selectedLocationId={selectedLocation?.id}
              />
            )}
          </div>

          {/* Right panel */}
          <div className="w-80 flex flex-col gap-4">
            {/* Selected location detail */}
            <div className="bg-navy-800 border border-navy-600 rounded-lg p-4 flex-1 overflow-y-auto">
              {selectedLocation ? (
                <>
                  <h3 className="font-semibold text-lg mb-1">{selectedLocation.name}</h3>
                  {getLat(selectedLocation) != null && (
                    <p className="text-xs text-gray-500 mb-3">
                      {Number(getLat(selectedLocation)).toFixed(4)}, {Number(getLng(selectedLocation)).toFixed(4)}
                    </p>
                  )}
                  <h4 className="text-xs font-semibold text-gray-400 mb-2 uppercase">Relationships</h4>
                  <div className="space-y-1">
                    {relsLoading ? (
                      <p className="text-xs text-gray-500">Loading relationships...</p>
                    ) : selectedRels.length === 0 ? (
                      <p className="text-xs text-gray-500">No relationships found.</p>
                    ) : (
                      selectedRels.map((rel, i) => (
                        <div key={i} className="text-xs bg-navy-700 rounded px-2 py-1">
                          <span className="text-accent-blue">{rel.rel_type}</span>
                          <span className="text-gray-400"> &rarr; </span>
                          <span className="text-gray-200">
                            {rel.source_name === selectedLocation.name
                              ? (rel.target_name || rel.target_id)
                              : (rel.source_name || rel.source_id)}
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                </>
              ) : (
                <p className="text-sm text-gray-500">Click a location on the map to see details</p>
              )}
            </div>

            {/* RAG query */}
            <div className="bg-navy-800 border border-navy-600 rounded-lg p-4">
              <h4 className="text-xs font-semibold text-gray-400 mb-2 uppercase">Geographic Query</h4>
              <div className="flex gap-2">
                <input
                  value={queryInput}
                  onChange={e => setQueryInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && askGeoQuery()}
                  placeholder="Ask about locations..."
                  className="flex-1 bg-navy-700 border border-navy-600 rounded px-2 py-1 text-sm focus:outline-none focus:border-accent-blue"
                />
                <button
                  onClick={askGeoQuery}
                  disabled={queryLoading || !queryInput.trim()}
                  className="bg-accent-blue text-white px-3 py-1 rounded text-sm disabled:opacity-50"
                >
                  {queryLoading ? '...' : 'Ask'}
                </button>
              </div>
              {queryResult && (
                <div className="mt-3 text-xs text-gray-300 max-h-48 overflow-y-auto bg-navy-700 rounded p-2">
                  <pre className="whitespace-pre-wrap">{queryResult}</pre>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
