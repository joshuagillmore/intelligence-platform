'use client';
import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import Sidebar from '@/components/Sidebar';
import GraphVisualization from '@/components/GraphVisualization';
import LoadingSpinner from '@/components/LoadingSpinner';
import { useProject } from '@/lib/ProjectContext';
import { entitiesApi, graphApi, assessApi } from '@/lib/api';

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

interface GraphNode {
  id: string;
  name: string;
  entity_type: string;
}

interface GraphEdge {
  source: string;
  target: string;
  source_id: string;
  target_id: string;
  rel_type: string;
  confidence?: number;
}

const IOC_TYPES = ['IPAddress', 'Domain', 'Hash', 'TTP', 'Vulnerability'];

const TYPE_BADGE_STYLES: Record<string, string> = {
  IPAddress: 'bg-cyan-900/30 text-cyan-400',
  Domain: 'bg-purple-900/30 text-purple-400',
  Hash: 'bg-pink-900/30 text-pink-400',
  TTP: 'bg-yellow-900/30 text-yellow-400',
  Vulnerability: 'bg-rose-900/30 text-rose-400',
  ThreatActor: 'bg-red-900/30 text-red-400',
};

const FILTER_TABS = [
  { label: 'All', value: 'all' },
  { label: 'IPs', value: 'IPAddress' },
  { label: 'Domains', value: 'Domain' },
  { label: 'Hashes', value: 'Hash' },
  { label: 'TTPs', value: 'TTP' },
  { label: 'CVEs', value: 'Vulnerability' },
];

const MITRE_TACTICS = [
  { id: 'TA0001', name: 'Initial Access', techniques: [
    { id: 'T1566', name: 'Phishing' },
    { id: 'T1190', name: 'Exploit Public-Facing App' },
    { id: 'T1078', name: 'Valid Accounts' },
    { id: 'T1195', name: 'Supply Chain Compromise' },
  ]},
  { id: 'TA0002', name: 'Execution', techniques: [
    { id: 'T1059', name: 'Command & Scripting' },
    { id: 'T1203', name: 'Exploitation for Client Exec' },
    { id: 'T1204', name: 'User Execution' },
  ]},
  { id: 'TA0003', name: 'Persistence', techniques: [
    { id: 'T1547', name: 'Boot/Logon Autostart' },
    { id: 'T1053', name: 'Scheduled Task/Job' },
    { id: 'T1136', name: 'Create Account' },
  ]},
  { id: 'TA0005', name: 'Defense Evasion', techniques: [
    { id: 'T1036', name: 'Masquerading' },
    { id: 'T1027', name: 'Obfuscated Files' },
    { id: 'T1070', name: 'Indicator Removal' },
  ]},
  { id: 'TA0006', name: 'Credential Access', techniques: [
    { id: 'T1003', name: 'OS Credential Dumping' },
    { id: 'T1110', name: 'Brute Force' },
    { id: 'T1555', name: 'Credentials from Stores' },
  ]},
  { id: 'TA0007', name: 'Discovery', techniques: [
    { id: 'T1082', name: 'System Information' },
    { id: 'T1083', name: 'File and Directory' },
    { id: 'T1046', name: 'Network Service Scan' },
  ]},
  { id: 'TA0011', name: 'Command & Control', techniques: [
    { id: 'T1071', name: 'Application Layer Protocol' },
    { id: 'T1105', name: 'Ingress Tool Transfer' },
    { id: 'T1573', name: 'Encrypted Channel' },
  ]},
  { id: 'TA0010', name: 'Exfiltration', techniques: [
    { id: 'T1567', name: 'Exfil Over Web Service' },
    { id: 'T1048', name: 'Exfil Over Alt Protocol' },
  ]},
  { id: 'TA0040', name: 'Impact', techniques: [
    { id: 'T1486', name: 'Data Encrypted for Impact' },
    { id: 'T1489', name: 'Service Stop' },
    { id: 'T1499', name: 'Endpoint DoS' },
  ]},
];

type PageTab = 'ioc' | 'attack' | 'actors';

function StatCard({ label, count, color }: { label: string; count: number; color: string }) {
  return (
    <div className="bg-navy-800 border border-navy-600 rounded-lg p-3 flex flex-col items-center min-w-[80px]">
      <span className={`text-xl font-bold ${color}`}>{count}</span>
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
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphEdges, setGraphEdges] = useState<GraphEdge[]>([]);
  const [selectedGraphNode, setSelectedGraphNode] = useState<string | null>(null);
  const [iocsLoading, setIocsLoading] = useState(false);
  const [pageTab, setPageTab] = useState<PageTab>('ioc');
  const [threatActors, setThreatActors] = useState<IOCEntity[]>([]);
  const [actorRelationships, setActorRelationships] = useState<Record<string, Relationship[]>>({});
  const [expandedActorId, setExpandedActorId] = useState<string | null>(null);
  const [generatingProfile, setGeneratingProfile] = useState<string | null>(null);
  const [selectedTechniqueId, setSelectedTechniqueId] = useState<string | null>(null);

  const loadIOCs = useCallback(async () => {
    if (!activeProject) return;
    setIocsLoading(true);
    const allIocs: IOCEntity[] = [];
    for (const type of IOC_TYPES) {
      try {
        const res = await entitiesApi.search(activeProject.id, undefined, type);
        allIocs.push(...res.data);
      } catch { /* type may not exist */ }
    }
    setIocs(allIocs);
    setIocsLoading(false);
  }, [activeProject]);

  const loadGraph = useCallback(async () => {
    if (!activeProject) return;
    try {
      const res = await graphApi.full(activeProject.id);
      const data = res.data;
      const nodes: GraphNode[] = (data.nodes || []).filter((n: GraphNode) =>
        IOC_TYPES.includes(n.entity_type)
      );
      const nodeIds = new Set(nodes.map(n => n.id));
      const edges: GraphEdge[] = (data.edges || data.relationships || []).filter((e: GraphEdge) => {
        const srcId = typeof e.source === 'string' ? e.source : e.source_id;
        const tgtId = typeof e.target === 'string' ? e.target : e.target_id;
        return nodeIds.has(srcId) && nodeIds.has(tgtId);
      }).map((e: GraphEdge) => ({
        ...e,
        source: typeof e.source === 'string' ? e.source : e.source_id,
        target: typeof e.target === 'string' ? e.target : e.target_id,
      }));
      setGraphNodes(nodes);
      setGraphEdges(edges);
    } catch (e) {
      console.error('Failed to load graph', e);
    }
  }, [activeProject]);

  const loadThreatActors = useCallback(async () => {
    if (!activeProject) return;
    try {
      const res = await entitiesApi.search(activeProject.id, undefined, 'ThreatActor');
      setThreatActors(res.data);
    } catch { /* ignore */ }
  }, [activeProject]);

  useEffect(() => {
    loadIOCs();
    loadGraph();
    loadThreatActors();
  }, [loadIOCs, loadGraph, loadThreatActors]);

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

  // Build a set of TTP IDs present in the project for ATT&CK matrix highlighting
  const ttpNames = useMemo(() => {
    const names = new Set<string>();
    iocs.filter(i => i.entity_type === 'TTP').forEach(i => {
      names.add(i.name.toUpperCase());
    });
    return names;
  }, [iocs]);

  const isTechniquePresent = useCallback((techId: string) => {
    return ttpNames.has(techId.toUpperCase()) ||
      Array.from(ttpNames).some(n => n.includes(techId.toUpperCase()));
  }, [ttpNames]);

  const coveredCount = useMemo(() => {
    let count = 0;
    MITRE_TACTICS.forEach(tactic => {
      tactic.techniques.forEach(tech => {
        if (isTechniquePresent(tech.id)) count++;
      });
    });
    return count;
  }, [isTechniquePresent]);

  const totalTechniques = useMemo(() => {
    return MITRE_TACTICS.reduce((sum, t) => sum + t.techniques.length, 0);
  }, []);

  // Get entities related to a technique
  const getRelatedEntities = useCallback((techId: string) => {
    return iocs.filter(i =>
      i.entity_type === 'TTP' &&
      (i.name.toUpperCase().includes(techId.toUpperCase()))
    );
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

  async function toggleActorRow(actor: IOCEntity) {
    if (expandedActorId === actor.id) {
      setExpandedActorId(null);
      return;
    }
    setExpandedActorId(actor.id);
    if (!actorRelationships[actor.id]) {
      try {
        const res = await entitiesApi.get(actor.id);
        setActorRelationships(prev => ({ ...prev, [actor.id]: res.data.relationships || [] }));
      } catch { /* ignore */ }
    }
  }

  async function generateProfile(actor: IOCEntity) {
    if (!activeProject) return;
    setGeneratingProfile(actor.id);
    try {
      await assessApi.generate(actor.id, {
        entity_id: actor.id,
        project_id: activeProject.id,
      });
      // Refresh actor data
      const res = await entitiesApi.get(actor.id);
      if (res.data.entity) {
        setThreatActors(prev => prev.map(a => a.id === actor.id ? { ...a, ...res.data.entity } : a));
      }
    } catch (e) {
      console.error('Failed to generate profile', e);
    }
    setGeneratingProfile(null);
  }

  function getBadgeStyle(entityType: string): string {
    return TYPE_BADGE_STYLES[entityType] || 'bg-gray-900/30 text-gray-400';
  }

  function handleGraphNodeClick(node: GraphNode) {
    setSelectedGraphNode(node.id);
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
        <h2 className="text-2xl font-bold mb-4">Cyber Intelligence</h2>

        {/* Page-level tabs */}
        <div className="flex gap-1 mb-6 border-b border-navy-600 pb-0">
          {([
            { label: 'IOC Dashboard', value: 'ioc' as PageTab },
            { label: 'ATT&CK Matrix', value: 'attack' as PageTab },
            { label: 'Threat Actors', value: 'actors' as PageTab },
          ]).map(tab => (
            <button
              key={tab.value}
              onClick={() => setPageTab(tab.value)}
              className={`px-5 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-[1px] ${
                pageTab === tab.value
                  ? 'border-accent-blue text-white'
                  : 'border-transparent text-gray-400 hover:text-white hover:border-gray-600'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* IOC Dashboard Tab */}
        {pageTab === 'ioc' && (
          <>
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

            {/* Split layout: IOC table + Graph */}
            <div className="flex gap-6" style={{ height: 'calc(100vh - 380px)' }}>

              {/* Left: IOC table (55%) */}
              <div className="w-[55%] overflow-hidden flex flex-col">
                <div className="bg-navy-800 border border-navy-600 rounded-lg overflow-hidden flex-1 overflow-y-auto">
                  {iocsLoading ? (
                    <LoadingSpinner size="lg" />
                  ) : (
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-navy-800 z-10">
                      <tr className="border-b border-navy-600 text-left">
                        <th className="px-4 py-3 text-xs font-semibold text-gray-400">Indicator</th>
                        <th className="px-4 py-3 text-xs font-semibold text-gray-400">Type</th>
                        <th className="px-4 py-3 text-xs font-semibold text-gray-400">Rels</th>
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
                  )}
                  {!iocsLoading && filteredIocs.length === 0 && (
                    <p className="text-gray-500 text-sm p-4 text-center">No IOCs found{activeFilter !== 'all' ? ` for type "${activeFilter}"` : ' in project'}.</p>
                  )}
                </div>
              </div>

              {/* Right: Cyber Relationship Graph (45%) */}
              <div className="w-[45%] flex flex-col overflow-hidden">
                <div className="bg-navy-800 border border-navy-600 rounded-lg flex-1 overflow-hidden flex flex-col">
                  <div className="px-4 py-3 border-b border-navy-600 flex items-center justify-between">
                    <h3 className="text-sm font-semibold">Cyber Relationship Graph</h3>
                    <span className="text-xs text-gray-400">{graphNodes.length} nodes, {graphEdges.length} edges</span>
                  </div>
                  <div className="flex-1 relative">
                    {graphNodes.length > 0 ? (
                      <GraphVisualization
                        nodes={graphNodes}
                        edges={graphEdges}
                        onNodeClick={handleGraphNodeClick}
                        selectedNodeId={selectedGraphNode}
                      />
                    ) : (
                      <div className="flex items-center justify-center h-full text-gray-500 text-sm">
                        <div className="text-center">
                          <p>No cyber entities to visualize.</p>
                          <p className="text-xs mt-1 text-gray-600">Ingest threat intelligence data to populate the graph.</p>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </>
        )}

        {/* ATT&CK Matrix Tab */}
        {pageTab === 'attack' && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-lg font-semibold">MITRE ATT&CK Coverage</h3>
                <p className="text-sm text-gray-400 mt-1">
                  {coveredCount} of {totalTechniques} techniques detected in project TTPs
                </p>
              </div>
              <div className="flex items-center gap-4 text-xs text-gray-400">
                <span className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded bg-accent-blue inline-block" /> Detected
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded bg-navy-700 inline-block" /> Not Detected
                </span>
              </div>
            </div>

            <div className="overflow-x-auto pb-4" style={{ height: 'calc(100vh - 280px)' }}>
              <div className="flex gap-2 min-w-max">
                {MITRE_TACTICS.map(tactic => (
                  <div key={tactic.id} className="flex flex-col w-40 flex-shrink-0">
                    {/* Tactic header */}
                    <div className="bg-navy-700 border border-navy-600 rounded-t-lg px-3 py-2 text-center">
                      <div className="text-xs font-bold text-white leading-tight">{tactic.name}</div>
                      <div className="text-[10px] text-gray-500 mt-0.5">{tactic.id}</div>
                    </div>
                    {/* Technique cells */}
                    <div className="flex flex-col gap-1 mt-1">
                      {tactic.techniques.map(tech => {
                        const present = isTechniquePresent(tech.id);
                        const isSelected = selectedTechniqueId === tech.id;
                        return (
                          <button
                            key={tech.id}
                            onClick={() => setSelectedTechniqueId(isSelected ? null : tech.id)}
                            className={`rounded px-2 py-2 text-left border transition-all ${
                              present
                                ? 'bg-accent-blue/20 border-accent-blue/40 hover:bg-accent-blue/30'
                                : 'bg-navy-800 border-navy-700 hover:border-navy-500'
                            } ${isSelected ? 'ring-1 ring-accent-blue' : ''}`}
                          >
                            <div className={`text-[11px] font-medium leading-tight ${present ? 'text-accent-blue' : 'text-gray-400'}`}>
                              {tech.name}
                            </div>
                            <div className="text-[10px] text-gray-500 mt-0.5">{tech.id}</div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Selected technique detail panel */}
            {selectedTechniqueId && (
              <div className="mt-4 bg-navy-800 border border-navy-600 rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-sm font-semibold">
                    {selectedTechniqueId} - Related Entities
                  </h4>
                  <button
                    onClick={() => setSelectedTechniqueId(null)}
                    className="text-gray-400 hover:text-white text-xs"
                  >
                    Close
                  </button>
                </div>
                {getRelatedEntities(selectedTechniqueId).length > 0 ? (
                  <div className="space-y-2">
                    {getRelatedEntities(selectedTechniqueId).map(entity => (
                      <div key={entity.id} className="bg-navy-700 rounded p-3 flex items-center justify-between">
                        <div>
                          <span className="text-sm font-mono text-white">{entity.name}</span>
                          <span className={`text-xs px-2 py-0.5 rounded ml-2 ${getBadgeStyle(entity.entity_type)}`}>
                            {entity.entity_type}
                          </span>
                        </div>
                        <button
                          onClick={() => router.push('/network')}
                          className="text-xs text-accent-blue hover:underline"
                        >
                          View in Graph
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-gray-500">No matching TTP entities found for this technique.</p>
                )}
              </div>
            )}
          </div>
        )}

        {/* Threat Actors Tab */}
        {pageTab === 'actors' && (
          <div style={{ height: 'calc(100vh - 240px)' }}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">Threat Actors ({threatActors.length})</h3>
            </div>

            {threatActors.length === 0 ? (
              <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 text-center text-gray-500">
                <p>No threat actors found in this project.</p>
                <p className="text-xs mt-1 text-gray-600">Ingest threat intelligence reports to extract threat actor entities.</p>
              </div>
            ) : (
              <div className="space-y-2 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 300px)' }}>
                {threatActors.map(actor => {
                  const isExpanded = expandedActorId === actor.id;
                  const rels = actorRelationships[actor.id] || [];
                  return (
                    <div key={actor.id} className="bg-navy-800 border border-navy-600 rounded-lg overflow-hidden">
                      <div
                        onClick={() => toggleActorRow(actor)}
                        className={`px-4 py-3 cursor-pointer transition-colors flex items-center justify-between ${
                          isExpanded ? 'bg-navy-700' : 'hover:bg-navy-700/50'
                        }`}
                      >
                        <div className="flex items-center gap-3">
                          <span className="w-2 h-2 rounded-full bg-red-500" />
                          <span className="font-medium">{actor.name}</span>
                          <span className={`text-xs px-2 py-0.5 rounded ${getBadgeStyle('ThreatActor')}`}>
                            ThreatActor
                          </span>
                          {actor.relationship_count !== undefined && (
                            <span className="text-xs text-gray-400">{actor.relationship_count} connections</span>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              generateProfile(actor);
                            }}
                            disabled={generatingProfile === actor.id}
                            className="px-3 py-1.5 text-xs bg-accent-blue/20 text-accent-blue border border-accent-blue/30 rounded hover:bg-accent-blue/30 transition-colors disabled:opacity-50"
                          >
                            {generatingProfile === actor.id ? 'Generating...' : 'Generate Profile'}
                          </button>
                          <span className="text-gray-400 text-sm">{isExpanded ? '\u25B2' : '\u25BC'}</span>
                        </div>
                      </div>

                      {isExpanded && (
                        <div className="px-4 py-4 border-t border-navy-700">
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                              <h4 className="text-xs font-semibold text-gray-400 mb-2">Connected Entities</h4>
                              {rels.length > 0 ? (
                                <div className="space-y-1 max-h-48 overflow-y-auto">
                                  {rels.map((r, i) => (
                                    <div key={i} className="text-xs bg-navy-700 rounded p-2 flex items-center gap-2">
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
                            <div>
                              {actor.properties && Object.keys(actor.properties).length > 0 && (
                                <div>
                                  <h4 className="text-xs font-semibold text-gray-400 mb-2">Properties / Assessment</h4>
                                  {Object.entries(actor.properties).map(([k, v]) => (
                                    <div key={k} className="text-xs mb-1">
                                      <span className="text-gray-500">{k}:</span>{' '}
                                      <span className="text-gray-300">{String(v)}</span>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
