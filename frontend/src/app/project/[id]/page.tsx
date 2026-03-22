'use client';
import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Sidebar from '@/components/Sidebar';
import { useProject } from '@/lib/ProjectContext';
import { projectsApi, graphApi, reportsApi, timelineApi, type Project } from '@/lib/api';

// Design tokens
const colors = {
  primary: '#adc6ff',
  secondary: '#ffb95f',
  tertiary: '#ff5451',
  surface: '#0e1321',
  containerLow: '#161b2a',
  container: '#1a1f2e',
  green: '#4ade80',
};

export default function ProjectDashboard() {
  const params = useParams();
  const router = useRouter();
  const { setActiveProject } = useProject();
  const [project, setProject] = useState<Project | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [stats, setStats] = useState<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [topEntities, setTopEntities] = useState<any[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [recentActivity, setRecentActivity] = useState<any[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [reports, setReports] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const projectId = params.id as string;

  useEffect(() => {
    if (!projectId) return;
    setLoading(true);
    Promise.all([
      projectsApi.get(projectId).catch(() => null),
      graphApi.statistics(projectId).catch(() => null),
      graphApi.centrality(projectId).catch(() => null),
      timelineApi.get(projectId).catch(() => null),
      reportsApi.list(projectId).catch(() => null),
    ]).then(([projRes, statsRes, centralRes, timeRes, repRes]) => {
      if (projRes?.data) {
        setProject(projRes.data);
        setActiveProject(projRes.data);
      }
      if (statsRes?.data) setStats(statsRes.data);
      if (centralRes?.data) setTopEntities(centralRes.data.slice(0, 10));
      if (timeRes?.data?.events) setRecentActivity(timeRes.data.events.slice(0, 15));
      if (repRes?.data) setReports(Array.isArray(repRes.data) ? repRes.data : []);
      setLoading(false);
    });
  }, [projectId, setActiveProject]);

  if (loading) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="md:ml-56 flex-1 p-4 pt-16 pb-24 md:p-8 md:pt-8 md:pb-8" style={{ backgroundColor: colors.surface, minHeight: '100vh' }}>
          <div className="text-gray-500">Loading project...</div>
        </main>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="md:ml-56 flex-1 p-4 pt-16 pb-24 md:p-8 md:pt-8 md:pb-8" style={{ backgroundColor: colors.surface, minHeight: '100vh' }}>
          <div style={{ color: colors.tertiary }}>Project not found</div>
        </main>
      </div>
    );
  }

  const entityCount = stats?.nodes || project.entity_count || 0;
  const relationshipCount = stats?.edges || project.relationship_count || 0;
  const documentCount = project.document_count || 0;
  const activeCollections = reports.length;
  const unresolvedGaps = stats?.components || 0;

  const statCards = [
    { label: 'Entities', value: entityCount, color: colors.primary, progress: Math.min(entityCount / 100, 1) },
    { label: 'Relationships', value: relationshipCount, color: colors.secondary, progress: Math.min(relationshipCount / 200, 1) },
    { label: 'Documents', value: documentCount, color: colors.primary, progress: Math.min(documentCount / 50, 1) },
    { label: 'Active Collections', value: activeCollections, color: colors.green, progress: Math.min(activeCollections / 20, 1) },
    { label: 'Unresolved Gaps', value: unresolvedGaps, color: colors.tertiary, progress: Math.min(unresolvedGaps / 10, 1) },
  ];

  const typeColor: Record<string, string> = {
    Person: 'bg-orange-900/30 text-orange-400',
    Organization: 'bg-blue-900/30 text-blue-400',
    Location: 'bg-green-900/30 text-green-400',
    IPAddress: 'bg-cyan-900/30 text-cyan-400',
    Domain: 'bg-purple-900/30 text-purple-400',
    Hash: 'bg-pink-900/30 text-pink-400',
    ThreatActor: 'bg-red-900/30 text-red-400',
    TTP: 'bg-yellow-900/30 text-yellow-400',
    Document: 'bg-gray-900/30 text-gray-400',
  };

  const typeBadgeStyle: Record<string, { bg: string; text: string }> = {
    Person: { bg: 'rgba(249, 115, 22, 0.15)', text: '#fb923c' },
    Organization: { bg: 'rgba(59, 130, 246, 0.15)', text: '#60a5fa' },
    Location: { bg: 'rgba(34, 197, 94, 0.15)', text: '#4ade80' },
    IPAddress: { bg: 'rgba(6, 182, 212, 0.15)', text: '#22d3ee' },
    Domain: { bg: 'rgba(168, 85, 247, 0.15)', text: '#a78bfa' },
    Hash: { bg: 'rgba(236, 72, 153, 0.15)', text: '#f472b6' },
    ThreatActor: { bg: 'rgba(239, 68, 68, 0.15)', text: '#f87171' },
    TTP: { bg: 'rgba(234, 179, 8, 0.15)', text: '#facc15' },
    Document: { bg: 'rgba(107, 114, 128, 0.15)', text: '#9ca3af' },
  };

  // Map event entity_type to timeline border color
  const activityBorderColor = (entityType: string): string => {
    const map: Record<string, string> = {
      Collection: colors.green,
      Organization: colors.green,
      Person: colors.tertiary,
      ThreatActor: colors.tertiary,
      Hash: colors.tertiary,
      Document: colors.primary,
      Location: colors.primary,
      Domain: '#a78bfa',
      IPAddress: '#22d3ee',
      TTP: colors.secondary,
    };
    return map[entityType] || '#4b5563';
  };

  // Simulated AI insights based on available data
  const insights = [
    ...(topEntities.length > 2 ? [{
      confidence: 'High' as const,
      description: `Entity "${topEntities[0]?.name}" shows highest centrality in the network, suggesting a key node connecting multiple clusters.`,
      action: 'Deep Analysis',
      actionHref: '/network',
    }] : []),
    ...(relationshipCount > 5 ? [{
      confidence: 'Medium' as const,
      description: `${relationshipCount} relationships detected across ${entityCount} entities. Density patterns suggest potential undiscovered connections.`,
      action: 'Verify Connection',
      actionHref: '/network',
    }] : []),
    ...(unresolvedGaps > 1 ? [{
      confidence: 'Medium' as const,
      description: `${unresolvedGaps} disconnected components identified. These gaps may indicate missing intelligence links.`,
      action: 'Deep Analysis',
      actionHref: '/network',
    }] : []),
  ];

  // Get max centrality for bar scaling
  const maxCentrality = topEntities.reduce((max: number, e: { centrality?: number }) => Math.max(max, e.centrality || 0), 0) || 1;

  return (
    <div className="flex">
      <Sidebar />
      <main className="md:ml-56 flex-1 p-4 pt-16 pb-24 md:p-8 md:pt-8 md:pb-8" style={{ backgroundColor: colors.surface, minHeight: '100vh' }}>
        {/* Header */}
        <div className="flex flex-col md:flex-row justify-between items-start mb-8 gap-4">
          <div>
            <h1 className="text-3xl font-bold text-white tracking-tight">Project Overview</h1>
            <p className="text-sm mt-2" style={{ color: '#8b95a8' }}>
              Target Analysis: {project.description || project.name}
            </p>
            <div className="flex gap-2 mt-3">
              <span className={`text-xs px-2 py-0.5 rounded ${
                project.priority === 'critical' ? 'bg-red-900/30 text-red-400' :
                project.priority === 'high' ? 'bg-orange-900/30 text-orange-400' :
                'bg-navy-600 text-gray-400'
              }`}>{project.priority}</span>
              <span className="text-xs px-2 py-0.5 rounded bg-green-900/30 text-green-400">{project.status}</span>
              <span className="text-xs px-2 py-0.5 rounded bg-navy-600 text-gray-400">{project.classification_level}</span>
            </div>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => {
                window.open(`${process.env.NEXT_PUBLIC_API_URL || ''}/api/export/stix?project_id=${projectId}`, '_blank');
              }}
              className="px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
              style={{
                border: `1px solid ${colors.primary}`,
                color: colors.primary,
                backgroundColor: 'transparent',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = 'rgba(173, 198, 255, 0.1)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = 'transparent';
              }}
            >
              Export Report
            </button>
            <button
              onClick={() => router.push('/products')}
              className="px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
              style={{
                backgroundColor: colors.primary,
                color: colors.surface,
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = '#c5d8ff';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = colors.primary;
              }}
            >
              Generate Intel
            </button>
          </div>
        </div>

        {/* Stat Cards */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
          {statCards.map(s => (
            <div
              key={s.label}
              className="rounded-lg p-4"
              style={{
                backgroundColor: colors.container,
                borderLeft: `3px solid ${s.color}`,
              }}
            >
              <div
                className="text-[10px] font-semibold uppercase mb-2"
                style={{ letterSpacing: '0.15em', color: '#6b7280' }}
              >
                {s.label}
              </div>
              <div className="text-2xl font-bold text-white">{s.value}</div>
              <div
                className="mt-3 h-1 rounded-full overflow-hidden"
                style={{ backgroundColor: 'rgba(255,255,255,0.06)' }}
              >
                <div
                  className="h-full rounded-full transition-all duration-700"
                  style={{
                    backgroundColor: s.color,
                    width: `${Math.max(s.progress * 100, 2)}%`,
                    opacity: 0.7,
                  }}
                />
              </div>
            </div>
          ))}
        </div>

        {/* Three-column bento grid */}
        <div className="grid grid-cols-1 md:grid-cols-[25%_1fr_25%] gap-4">
          {/* Left Column: Recent Activity */}
          <div
            className="rounded-lg p-4"
            style={{ backgroundColor: colors.container }}
          >
            <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
              <span style={{ color: colors.primary }}>|</span> Recent Activity
            </h3>
            <div className="space-y-2 max-h-[520px] overflow-y-auto pr-1" style={{ scrollbarWidth: 'thin' }}>
              {recentActivity.map((evt: { id?: string; name: string; entity_type: string; timestamp?: string }, i: number) => {
                const borderColor = activityBorderColor(evt.entity_type);
                return (
                  <div
                    key={evt.id || i}
                    className="rounded-md p-3 relative"
                    style={{
                      backgroundColor: colors.containerLow,
                      borderLeft: `3px solid ${borderColor}`,
                    }}
                  >
                    {evt.timestamp && (
                      <span
                        className="absolute top-2 right-3 text-[10px]"
                        style={{ color: '#4b5563' }}
                      >
                        {new Date(evt.timestamp).toLocaleDateString()}
                      </span>
                    )}
                    <div className="text-xs text-gray-200 pr-16 leading-relaxed">{evt.name}</div>
                    <span
                      className={`inline-block mt-1.5 text-[10px] px-1.5 py-0.5 rounded ${typeColor[evt.entity_type] || 'bg-gray-900/30 text-gray-400'}`}
                    >
                      {evt.entity_type}
                    </span>
                  </div>
                );
              })}
              {recentActivity.length === 0 && <p className="text-xs text-gray-500">No activity yet</p>}
            </div>
          </div>

          {/* Center Column: Key Entities */}
          <div
            className="rounded-lg p-4"
            style={{ backgroundColor: colors.container }}
          >
            <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
              <span style={{ color: colors.primary }}>|</span> Key Entities
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                    <th className="text-left text-[10px] uppercase font-semibold pb-3 pr-4" style={{ color: '#6b7280', letterSpacing: '0.1em' }}>Entity Name</th>
                    <th className="text-left text-[10px] uppercase font-semibold pb-3 pr-4" style={{ color: '#6b7280', letterSpacing: '0.1em' }}>Type</th>
                    <th className="text-left text-[10px] uppercase font-semibold pb-3 pr-4" style={{ color: '#6b7280', letterSpacing: '0.1em' }}>Centrality</th>
                    <th className="text-left text-[10px] uppercase font-semibold pb-3" style={{ color: '#6b7280', letterSpacing: '0.1em' }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {topEntities.map((e: { id?: string; name: string; entity_type: string; centrality?: number }, i: number) => {
                    const badge = typeBadgeStyle[e.entity_type] || { bg: 'rgba(107,114,128,0.15)', text: '#9ca3af' };
                    const centralityVal = e.centrality || 0;
                    const centralityPct = maxCentrality > 0 ? (centralityVal / maxCentrality) * 100 : 0;
                    return (
                      <tr
                        key={e.id || i}
                        style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}
                        className="group"
                      >
                        <td className="py-2.5 pr-4">
                          <button
                            className="text-sm font-medium text-left hover:underline"
                            style={{ color: colors.primary }}
                            onClick={() => router.push('/network')}
                          >
                            {e.name}
                          </button>
                        </td>
                        <td className="py-2.5 pr-4">
                          <span
                            className="text-[10px] px-2 py-1 rounded-full font-medium"
                            style={{ backgroundColor: badge.bg, color: badge.text }}
                          >
                            {e.entity_type}
                          </span>
                        </td>
                        <td className="py-2.5 pr-4">
                          <div className="flex items-center gap-2">
                            <div
                              className="h-4 rounded-sm"
                              style={{
                                width: `${Math.max(centralityPct, 4)}%`,
                                maxWidth: '100px',
                                minWidth: '4px',
                                backgroundColor: colors.primary,
                                opacity: 0.6,
                              }}
                            />
                            <span className="text-[10px] text-gray-500">{centralityVal.toFixed(3)}</span>
                          </div>
                        </td>
                        <td className="py-2.5">
                          <div className="flex items-center gap-1.5">
                            <div
                              className="w-2 h-2 rounded-full"
                              style={{
                                backgroundColor: centralityVal > 0.5 ? colors.green : centralityVal > 0.1 ? colors.secondary : '#6b7280',
                              }}
                            />
                            <span className="text-[10px] text-gray-500">
                              {centralityVal > 0.5 ? 'Critical' : centralityVal > 0.1 ? 'Active' : 'Low'}
                            </span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {topEntities.length === 0 && <p className="text-xs text-gray-500 mt-4">No entities yet</p>}
            </div>
          </div>

          {/* Right Column: AI Insights */}
          <div className="space-y-4">
            <div
              className="rounded-lg p-4"
              style={{ backgroundColor: colors.container }}
            >
              <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                <span style={{ color: colors.primary }}>|</span> AI Insights
              </h3>
              <div className="space-y-3">
                {insights.map((insight, i) => (
                  <div
                    key={i}
                    className="rounded-md p-3"
                    style={{ backgroundColor: colors.containerLow }}
                  >
                    <span
                      className="inline-block text-[10px] font-semibold px-2 py-0.5 rounded-full mb-2"
                      style={{
                        backgroundColor: insight.confidence === 'High'
                          ? 'rgba(173, 198, 255, 0.15)'
                          : 'rgba(255, 185, 95, 0.15)',
                        color: insight.confidence === 'High'
                          ? colors.primary
                          : colors.secondary,
                      }}
                    >
                      {insight.confidence} Confidence
                    </span>
                    <p className="text-xs text-gray-300 leading-relaxed mb-2">{insight.description}</p>
                    <button
                      className="text-[11px] font-medium hover:underline"
                      style={{ color: colors.primary }}
                      onClick={() => router.push(insight.actionHref)}
                    >
                      {insight.action} &rarr;
                    </button>
                  </div>
                ))}
                {insights.length === 0 && (
                  <p className="text-xs text-gray-500">Insufficient data for insights. Add more entities and relationships.</p>
                )}
              </div>
            </div>

            {/* Pattern Matcher card */}
            <div
              className="rounded-lg p-4"
              style={{ backgroundColor: colors.container }}
            >
              <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                <span style={{ color: colors.secondary }}>|</span> Pattern Matcher
              </h3>
              <div className="space-y-2">
                {[
                  { label: 'Entities', value: entityCount, max: Math.max(entityCount, relationshipCount, documentCount, 1), color: colors.primary },
                  { label: 'Relationships', value: relationshipCount, max: Math.max(entityCount, relationshipCount, documentCount, 1), color: colors.secondary },
                  { label: 'Documents', value: documentCount, max: Math.max(entityCount, relationshipCount, documentCount, 1), color: colors.green },
                  { label: 'Gaps', value: unresolvedGaps, max: Math.max(entityCount, relationshipCount, documentCount, 1), color: colors.tertiary },
                ].map(bar => (
                  <div key={bar.label}>
                    <div className="flex justify-between text-[10px] mb-1">
                      <span style={{ color: '#6b7280' }}>{bar.label}</span>
                      <span style={{ color: '#6b7280' }}>{bar.value}</span>
                    </div>
                    <div
                      className="h-2 rounded-full overflow-hidden"
                      style={{ backgroundColor: 'rgba(255,255,255,0.06)' }}
                    >
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${Math.max((bar.value / bar.max) * 100, 2)}%`,
                          backgroundColor: bar.color,
                          opacity: 0.7,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
              <button
                className="mt-3 text-[11px] font-medium hover:underline"
                style={{ color: colors.primary }}
                onClick={() => router.push('/network')}
              >
                View full analysis &rarr;
              </button>
            </div>

            {/* Reports summary */}
            <div
              className="rounded-lg p-4"
              style={{ backgroundColor: colors.container }}
            >
              <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                <span style={{ color: colors.green }}>|</span> Intelligence Products
              </h3>
              <div className="space-y-2">
                {reports.slice(0, 5).map((r: { id?: string; name?: string; title?: string; report_type?: string }, i: number) => (
                  <div
                    key={r.id || i}
                    className="text-xs rounded-md p-2"
                    style={{ backgroundColor: colors.containerLow }}
                  >
                    <span className="text-gray-200">{r.name || r.title}</span>
                    <div className="text-gray-500 mt-1">{r.report_type || 'Report'}</div>
                  </div>
                ))}
                {reports.length === 0 && <p className="text-xs text-gray-500">No reports yet</p>}
              </div>
              <button
                onClick={() => router.push('/products')}
                className="mt-3 text-[11px] font-medium hover:underline"
                style={{ color: colors.primary }}
              >
                View all products &rarr;
              </button>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="mt-8 flex justify-center gap-4">
          <button
            onClick={() => router.push('/collections')}
            className="px-8 py-3 rounded-lg text-sm font-semibold transition-colors"
            style={{
              backgroundColor: colors.primary,
              color: colors.surface,
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = '#c5d8ff';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = colors.primary;
            }}
          >
            Initiate Collection
          </button>
          <button
            onClick={() => router.push('/collections')}
            className="px-8 py-3 rounded-lg text-sm font-semibold transition-colors"
            style={{
              border: `2px solid ${colors.primary}`,
              color: colors.primary,
              backgroundColor: 'transparent',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = 'rgba(173, 198, 255, 0.1)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'transparent';
            }}
          >
            Add Documents
          </button>
        </div>

        {/* Footer meta */}
        <div
          className="mt-8 rounded-lg px-5 py-3 flex flex-col md:flex-row items-start md:items-center justify-between gap-2 md:gap-0 text-[10px]"
          style={{ backgroundColor: colors.containerLow, color: '#4b5563' }}
        >
          <div className="flex items-center gap-2">
            <span
              className="w-1.5 h-1.5 rounded-full inline-block"
              style={{ backgroundColor: colors.green }}
            />
            <span>Encryption: AES-256 Active</span>
          </div>
          <span>Scan Frequency: Continuous</span>
          <span>Last Sync: {new Date().toLocaleString()}</span>
        </div>
      </main>
    </div>
  );
}
