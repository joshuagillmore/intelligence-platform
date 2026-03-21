'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/Sidebar';
import { useProject } from '@/lib/ProjectContext';
import { entitiesApi } from '@/lib/api';

interface IOCEntity {
  id: string;
  name: string;
  entity_type: string;
  properties?: Record<string, unknown>;
  relationship_count?: number;
}

const IOC_TYPES = ['IPAddress', 'Domain', 'Hash'];

export default function CyberPage() {
  const { activeProject } = useProject();
  const [iocs, setIocs] = useState<IOCEntity[]>([]);
  const [selectedIoc, setSelectedIoc] = useState<IOCEntity | null>(null);
  const [relationships, setRelationships] = useState<Array<{ rel_type: string; source_id: string; target_id: string; confidence?: number; source_name?: string; target_name?: string }>>([]);

  const loadIOCs = useCallback(async () => {
    if (!activeProject) return;
    const allIocs: IOCEntity[] = [];
    for (const type of IOC_TYPES) {
      try {
        const res = await entitiesApi.search(activeProject.id, undefined, type);
        allIocs.push(...res.data);
      } catch {}
    }
    setIocs(allIocs);
  }, [activeProject]);

  useEffect(() => {
    loadIOCs();
  }, [loadIOCs]);

  async function selectIoc(ioc: IOCEntity) {
    setSelectedIoc(ioc);
    try {
      const res = await entitiesApi.get(ioc.id);
      setRelationships(res.data.relationships || []);
      if (res.data.entity) setSelectedIoc(res.data.entity);
    } catch {}
  }

  if (!activeProject) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="ml-56 flex-1 p-8">
          <h2 className="text-2xl font-bold mb-4">Cyber Intelligence</h2>
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
        <h2 className="text-2xl font-bold mb-6">Cyber Intelligence</h2>

        <div className="flex gap-6">
          <div className="flex-1">
            <div className="bg-navy-800 border border-navy-600 rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-navy-600 text-left">
                    <th className="px-4 py-3 text-xs font-semibold text-gray-400">Name</th>
                    <th className="px-4 py-3 text-xs font-semibold text-gray-400">Type</th>
                    <th className="px-4 py-3 text-xs font-semibold text-gray-400">First Seen</th>
                    <th className="px-4 py-3 text-xs font-semibold text-gray-400">Relationships</th>
                  </tr>
                </thead>
                <tbody>
                  {iocs.map((ioc) => (
                    <tr
                      key={ioc.id}
                      onClick={() => selectIoc(ioc)}
                      className={`border-b border-navy-700 cursor-pointer transition-colors ${
                        selectedIoc?.id === ioc.id ? 'bg-navy-700' : 'hover:bg-navy-700'
                      }`}
                    >
                      <td className="px-4 py-2 font-mono text-xs">{ioc.name}</td>
                      <td className="px-4 py-2">
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          ioc.entity_type === 'IPAddress' ? 'bg-cyan-900/30 text-cyan-400' :
                          ioc.entity_type === 'Domain' ? 'bg-purple-900/30 text-purple-400' :
                          'bg-pink-900/30 text-pink-400'
                        }`}>{ioc.entity_type}</span>
                      </td>
                      <td className="px-4 py-2 text-xs text-gray-400">
                        {ioc.properties?.first_seen ? String(ioc.properties.first_seen) : '--'}
                      </td>
                      <td className="px-4 py-2 text-xs text-gray-400">{ioc.relationship_count ?? '--'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {iocs.length === 0 && (
                <p className="text-gray-500 text-sm p-4 text-center">No IOCs found in project.</p>
              )}
            </div>
          </div>

          {selectedIoc && (
            <div className="w-80 bg-navy-800 border border-navy-600 rounded-lg p-4">
              <h3 className="font-bold text-lg mb-1">{selectedIoc.name}</h3>
              <span className={`inline-block text-xs px-2 py-0.5 rounded mb-3 ${
                selectedIoc.entity_type === 'IPAddress' ? 'bg-cyan-900/30 text-cyan-400' :
                selectedIoc.entity_type === 'Domain' ? 'bg-purple-900/30 text-purple-400' :
                'bg-pink-900/30 text-pink-400'
              }`}>{selectedIoc.entity_type}</span>

              {selectedIoc.properties && Object.keys(selectedIoc.properties).length > 0 && (
                <div className="mb-4">
                  <h4 className="text-xs font-semibold text-gray-400 mb-2">Properties</h4>
                  {Object.entries(selectedIoc.properties).map(([k, v]) => (
                    <div key={k} className="text-xs mb-1">
                      <span className="text-gray-500">{k}:</span> <span className="text-gray-300">{String(v)}</span>
                    </div>
                  ))}
                </div>
              )}

              {relationships.length > 0 && (
                <div>
                  <h4 className="text-xs font-semibold text-gray-400 mb-2">Relationships</h4>
                  {relationships.map((r, i) => (
                    <div key={i} className="text-xs bg-navy-700 rounded p-2 mb-1">
                      <span className="text-accent-blue">{r.rel_type}</span>
                      {r.confidence !== undefined && <span className="text-gray-500 ml-1">({(r.confidence * 100).toFixed(0)}%)</span>}
                      <div className="text-gray-400">{r.source_name || r.source_id} &rarr; {r.target_name || r.target_id}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
