'use client';
import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
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

interface Relationship {
  rel_type: string;
  source_id: string;
  target_id: string;
  confidence?: number;
  source_name?: string;
  target_name?: string;
}

const IOC_TYPES = ['IPAddress', 'Domain', 'Hash', 'TTP', 'Vulnerability'];

const TYPE_BADGE_STYLES: Record<string, string> = {
  IPAddress: 'bg-cyan-900/30 text-cyan-400',
  Domain: 'bg-purple-900/30 text-purple-400',
  Hash: 'bg-pink-900/30 text-pink-400',
  TTP: 'bg-yellow-900/30 text-yellow-400',
  Vulnerability: 'bg-rose-900/30 text-rose-400',
};

const FILTER_TABS = [
  { label: 'All', value: 'all' },
  { label: 'IPs', value: 'IPAddress' },
  { label: 'Domains', value: 'Domain' },
  { label: 'Hashes', value: 'Hash' },
  { label: 'TTPs', value: 'TTP' },
  { label: 'CVEs', value: 'Vulnerability' },
];

function StatCard({ label, count, color }: { label: string; count: number; color: string }) {
  return (
    <div className="bg-navy-800 border border-navy-600 rounded-lg p-4 flex flex-col items-center min-w-[100px]">
      <span className={`text-2xl font-bold ${color}`}>{count}</span>
      <span className="text-xs text-gray-400 mt-1">{label}</span>
    </div>
  );
}

export default function CyberPage() {
  const { activeProject } = useProject();
  const router = useRouter();
  const [iocs, setIocs] = useState<IOCEntity[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [relationships, setRelationships] = useState<Record<string, Relationship[]>>({});
  const [expandedEntity, setExpandedEntity] = useState<Record<string, IOCEntity>>({});
  const [activeFilter, setActiveFilter] = useState('all');

  const loadIOCs = useCallback(async () => {
    if (!activeProject) return;
    const allIocs: IOCEntity[] = [];
    for (const type of IOC_TYPES) {
      try {
        const res = await entitiesApi.search(activeProject.id, undefined, type);
        allIocs.push(...res.data);
      } catch { /* type may not exist */ }
    }
    setIocs(allIocs);
  }, [activeProject]);

  useEffect(() => {
    loadIOCs();
  }, [loadIOCs]);

  const filteredIocs = useMemo(() => {
    if (activeFilter === 'all') return iocs;
    return iocs.filter(i => i.entity_type === activeFilter);
  }, [iocs, activeFilter]);

  const stats = useMemo(() => {
    const counts: Record<string, number> = { total: iocs.length };
    IOC_TYPES.forEach(t => { counts[t] = 0; });
    iocs.forEach(i => { counts[i.entity_type] = (counts[i.entity_type] || 0) + 1; });
    return counts;
  }, [iocs]);

  async function toggleRow(ioc: IOCEntity) {
    if (expandedId === ioc.id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(ioc.id);
    if (!relationships[ioc.id]) {
      try {
        const res = await entitiesApi.get(ioc.id);
        setRelationships(prev => ({ ...prev, [ioc.id]: res.data.relationships || [] }));
        if (res.data.entity) {
          setExpandedEntity(prev => ({ ...prev, [ioc.id]: res.data.entity }));
        }
      } catch { /* ignore */ }
    }
  }

  function getBadgeStyle(entityType: string): string {
    return TYPE_BADGE_STYLES[entityType] || 'bg-gray-900/30 text-gray-400';
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

        {/* Summary stat cards */}
        <div className="flex gap-3 mb-6 flex-wrap">
          <StatCard label="Total IOCs" count={stats.total} color="text-white" />
          <StatCard label="IPs" count={stats.IPAddress || 0} color="text-cyan-400" />
          <StatCard label="Domains" count={stats.Domain || 0} color="text-purple-400" />
          <StatCard label="Hashes" count={stats.Hash || 0} color="text-pink-400" />
          <StatCard label="TTPs" count={stats.TTP || 0} color="text-yellow-400" />
          <StatCard label="CVEs" count={stats.Vulnerability || 0} color="text-rose-400" />
        </div>

        {/* Filter tabs */}
        <div className="flex gap-1 mb-4">
          {FILTER_TABS.map(tab => (
            <button
              key={tab.value}
              onClick={() => setActiveFilter(tab.value)}
              className={`px-4 py-1.5 text-xs rounded-md font-medium transition-colors ${
                activeFilter === tab.value
                  ? 'bg-accent-blue text-white'
                  : 'bg-navy-800 text-gray-400 hover:text-white hover:bg-navy-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* IOC table */}
        <div className="bg-navy-800 border border-navy-600 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-navy-600 text-left">
                <th className="px-4 py-3 text-xs font-semibold text-gray-400">Indicator</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-400">Type</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-400">Relationships</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-400">First Seen</th>
              </tr>
            </thead>
            <tbody>
              {filteredIocs.map((ioc) => {
                const isExpanded = expandedId === ioc.id;
                const rels = relationships[ioc.id] || [];
                const entity = expandedEntity[ioc.id] || ioc;
                return (
                  <React.Fragment key={ioc.id}>
                    <tr
                      onClick={() => toggleRow(ioc)}
                      className={`border-b border-navy-700 cursor-pointer transition-colors ${
                        isExpanded ? 'bg-navy-700' : 'hover:bg-navy-700/50'
                      }`}
                    >
                      <td className="px-4 py-2 font-mono text-xs">{ioc.name}</td>
                      <td className="px-4 py-2">
                        <span className={`text-xs px-2 py-0.5 rounded ${getBadgeStyle(ioc.entity_type)}`}>
                          {ioc.entity_type}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-xs text-gray-400">{ioc.relationship_count ?? '--'}</td>
                      <td className="px-4 py-2 text-xs text-gray-400">
                        {ioc.properties?.first_seen ? String(ioc.properties.first_seen) : '--'}
                      </td>
                    </tr>

                    {/* Expanded detail row */}
                    {isExpanded && (
                      <tr className="bg-navy-750 border-b border-navy-700">
                        <td colSpan={4} className="px-6 py-4">
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {/* Connected entities */}
                            <div>
                              <h4 className="text-xs font-semibold text-gray-400 mb-2">Connected Entities</h4>
                              {rels.length > 0 ? (
                                <div className="space-y-1 max-h-40 overflow-y-auto">
                                  {rels.map((r, i) => (
                                    <div key={i} className="text-xs bg-navy-800 rounded p-2 flex items-center gap-2">
                                      <span className="text-accent-blue font-medium">{r.rel_type}</span>
                                      {r.confidence !== undefined && (
                                        <span className="text-gray-500">({(r.confidence * 100).toFixed(0)}%)</span>
                                      )}
                                      <span className="text-gray-400 ml-auto truncate">
                                        {r.source_name || r.source_id} &rarr; {r.target_name || r.target_id}
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <p className="text-xs text-gray-500">No relationships found.</p>
                              )}
                            </div>

                            {/* Properties & actions */}
                            <div>
                              {entity.properties && Object.keys(entity.properties).length > 0 && (
                                <div className="mb-3">
                                  <h4 className="text-xs font-semibold text-gray-400 mb-2">Properties</h4>
                                  {Object.entries(entity.properties).map(([k, v]) => (
                                    <div key={k} className="text-xs mb-1">
                                      <span className="text-gray-500">{k}:</span>{' '}
                                      <span className="text-gray-300">{String(v)}</span>
                                    </div>
                                  ))}
                                </div>
                              )}

                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  router.push('/network');
                                }}
                                className="mt-2 px-3 py-1.5 text-xs bg-accent-blue/20 text-accent-blue border border-accent-blue/30 rounded hover:bg-accent-blue/30 transition-colors"
                              >
                                View in Graph &rarr;
                              </button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
          {filteredIocs.length === 0 && (
            <p className="text-gray-500 text-sm p-4 text-center">No IOCs found{activeFilter !== 'all' ? ` for type "${activeFilter}"` : ' in project'}.</p>
          )}
        </div>
      </main>
    </div>
  );
}
