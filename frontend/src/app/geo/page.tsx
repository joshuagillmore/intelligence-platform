'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/Sidebar';
import { useProject } from '@/lib/ProjectContext';
import { entitiesApi } from '@/lib/api';

interface LocationEntity {
  id: string;
  name: string;
  entity_type: string;
  properties?: Record<string, unknown>;
}

interface LocationRelationship {
  source_name?: string;
  target_name?: string;
  source_id: string;
  target_id: string;
  rel_type: string;
}

interface LocationWithRels {
  entity: LocationEntity;
  relationships: LocationRelationship[];
}

export default function GeoPage() {
  const { activeProject } = useProject();
  const [locations, setLocations] = useState<LocationWithRels[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const loadLocations = useCallback(async () => {
    if (!activeProject) return;
    setLoading(true);
    try {
      const res = await entitiesApi.search(activeProject.id, undefined, 'Location');
      const locationEntities: LocationEntity[] = res.data || [];

      // Load relationships for each location
      const locationsWithRels: LocationWithRels[] = await Promise.all(
        locationEntities.map(async (loc) => {
          try {
            const detailRes = await entitiesApi.get(loc.id);
            return {
              entity: loc,
              relationships: detailRes.data.relationships || [],
            };
          } catch {
            return { entity: loc, relationships: [] };
          }
        })
      );
      setLocations(locationsWithRels);
    } catch (e) {
      console.error('Failed to load locations', e);
    } finally {
      setLoading(false);
    }
  }, [activeProject]);

  useEffect(() => {
    loadLocations();
  }, [loadLocations]);

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

        {/* Map Placeholder */}
        <div className="bg-navy-900 border border-navy-600 rounded-lg mb-6 flex items-center justify-center" style={{ height: '400px' }}>
          <div className="text-center">
            <svg className="w-16 h-16 mx-auto mb-4 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
            </svg>
            <p className="text-gray-400 text-lg font-medium mb-1">Map Visualization</p>
            <p className="text-gray-500 text-sm">Map visualization requires Deck.gl integration</p>
            <p className="text-gray-600 text-xs mt-2">{locations.length} location entities available</p>
          </div>
        </div>

        {/* Location Summary */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-accent-blue">{locations.length}</div>
            <div className="text-xs text-gray-400">Location Entities</div>
          </div>
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-accent-blue">
              {locations.reduce((sum, l) => sum + l.relationships.length, 0)}
            </div>
            <div className="text-xs text-gray-400">Total Connections</div>
          </div>
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-accent-blue">
              {new Set(locations.flatMap(l => l.relationships.map(r => r.rel_type))).size}
            </div>
            <div className="text-xs text-gray-400">Relationship Types</div>
          </div>
        </div>

        {/* Location Entities Table */}
        <div className="bg-navy-800 border border-navy-600 rounded-lg">
          <div className="p-4 border-b border-navy-600">
            <h3 className="text-sm font-semibold text-gray-400">Location Entities &amp; Relationships</h3>
          </div>
          {loading ? (
            <div className="p-8 text-center text-gray-500 text-sm">Loading locations...</div>
          ) : locations.length === 0 ? (
            <div className="p-8 text-center text-gray-500 text-sm">
              No location entities found. Ingest documents containing geographic references to populate this view.
            </div>
          ) : (
            <div className="divide-y divide-navy-700">
              {locations.map(({ entity, relationships }) => (
                <div key={entity.id}>
                  <button
                    onClick={() => setExpandedId(expandedId === entity.id ? null : entity.id)}
                    className="w-full text-left px-4 py-3 hover:bg-navy-700/50 transition-colors flex items-center justify-between"
                  >
                    <div className="flex items-center gap-3">
                      <span className="w-2 h-2 rounded-full bg-green-500 flex-none" />
                      <span className="text-sm text-gray-200 font-medium">{entity.name}</span>
                      <span className="text-xs text-gray-500">{relationships.length} connections</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {entity.properties?.country ? (
                        <span className="text-xs bg-navy-700 text-gray-400 px-2 py-0.5 rounded">
                          {String(entity.properties.country)}
                        </span>
                      ) : null}
                      <span className="text-xs text-gray-500">
                        {expandedId === entity.id ? '▲' : '▼'}
                      </span>
                    </div>
                  </button>
                  {expandedId === entity.id && relationships.length > 0 && (
                    <div className="px-4 pb-3">
                      <div className="bg-navy-900/50 rounded p-3 space-y-1">
                        {relationships.map((rel, i) => (
                          <div key={i} className="flex items-center gap-2 text-xs">
                            <span className="text-accent-blue font-medium">{rel.rel_type}</span>
                            <span className="text-gray-500">&rarr;</span>
                            <span className="text-gray-300">
                              {rel.source_name === entity.name
                                ? (rel.target_name || rel.target_id)
                                : (rel.source_name || rel.source_id)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
