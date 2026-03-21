'use client';
import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Sidebar from '@/components/Sidebar';
import { useProject } from '@/lib/ProjectContext';
import { projectsApi, graphApi, reportsApi, timelineApi, type Project } from '@/lib/api';

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
        <main className="ml-56 flex-1 p-8">
          <div className="text-gray-500">Loading project...</div>
        </main>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="ml-56 flex-1 p-8">
          <div className="text-red-400">Project not found</div>
        </main>
      </div>
    );
  }

  const statCards = [
    { label: 'Entities', value: stats?.nodes || project.entity_count || 0, color: 'text-accent-blue' },
    { label: 'Relationships', value: stats?.edges || project.relationship_count || 0, color: 'text-green-400' },
    { label: 'Documents', value: project.document_count || 0, color: 'text-yellow-400' },
    { label: 'Components', value: stats?.components || 0, color: 'text-purple-400' },
    { label: 'Density', value: stats?.density ? stats.density.toFixed(4) : '0', color: 'text-cyan-400' },
    { label: 'Reports', value: reports.length, color: 'text-orange-400' },
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

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        {/* Header */}
        <div className="flex justify-between items-start mb-6">
          <div>
            <h2 className="text-2xl font-bold">{project.name}</h2>
            <p className="text-sm text-gray-400 mt-1">{project.description || 'No description'}</p>
            <div className="flex gap-2 mt-2">
              <span className={`text-xs px-2 py-0.5 rounded ${
                project.priority === 'critical' ? 'bg-red-900/30 text-red-400' :
                project.priority === 'high' ? 'bg-orange-900/30 text-orange-400' :
                'bg-navy-600 text-gray-400'
              }`}>{project.priority}</span>
              <span className="text-xs px-2 py-0.5 rounded bg-green-900/30 text-green-400">{project.status}</span>
              <span className="text-xs px-2 py-0.5 rounded bg-navy-600 text-gray-400">{project.classification_level}</span>
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={() => router.push('/collections')} className="bg-accent-blue hover:bg-blue-600 text-white px-4 py-2 rounded text-sm">Start Collection</button>
            <button onClick={() => router.push('/network')} className="bg-navy-700 hover:bg-navy-600 text-gray-200 px-4 py-2 rounded text-sm border border-navy-600">View Graph</button>
          </div>
        </div>

        {/* Stat Cards */}
        <div className="grid grid-cols-6 gap-3 mb-6">
          {statCards.map(s => (
            <div key={s.label} className="bg-navy-800 border border-navy-600 rounded-lg p-4 text-center">
              <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
              <div className="text-xs text-gray-500 mt-1">{s.label}</div>
            </div>
          ))}
        </div>

        {/* Quick Actions */}
        <div className="grid grid-cols-5 gap-3 mb-6">
          {[
            { label: 'Ingest Document', icon: '📄', href: '/collections' },
            { label: 'Analyze Network', icon: '🔗', href: '/network' },
            { label: 'View Data Sources', icon: '🗄️', href: '/data-sources' },
            { label: 'Generate Report', icon: '📊', href: '/products' },
            { label: 'Export STIX', icon: '🛡️', action: 'stix' },
          ].map((action) => (
            <button
              key={action.label}
              onClick={() => {
                if (action.action === 'stix') {
                  window.open(`http://localhost:8000/api/projects/${projectId}/export/stix`, '_blank');
                } else if (action.href) {
                  router.push(action.href);
                }
              }}
              className="bg-navy-800 border border-navy-600 rounded-lg p-3 flex items-center gap-3 hover:bg-navy-700 hover:border-accent-blue transition-colors text-left"
            >
              <span className="text-lg">{action.icon}</span>
              <span className="text-sm text-gray-300">{action.label}</span>
            </button>
          ))}
        </div>

        <div className="grid grid-cols-3 gap-4">
          {/* Top Entities */}
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-gray-400 mb-3">Top Entities (by centrality)</h3>
            <div className="space-y-2">
              {topEntities.map((e: { id?: string; name: string; entity_type: string }, i: number) => (
                <div key={e.id || i} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <span className="text-gray-500 text-xs w-4">{i + 1}</span>
                    <span className="text-gray-200 truncate max-w-[150px]">{e.name}</span>
                  </div>
                  <span className={`text-xs px-1.5 py-0.5 rounded ${typeColor[e.entity_type] || 'bg-gray-900/30 text-gray-400'}`}>
                    {e.entity_type}
                  </span>
                </div>
              ))}
              {topEntities.length === 0 && <p className="text-xs text-gray-500">No entities yet</p>}
            </div>
          </div>

          {/* Recent Activity */}
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-gray-400 mb-3">Recent Activity</h3>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {recentActivity.map((evt: { id?: string; name: string; entity_type: string; timestamp?: string }, i: number) => (
                <div key={evt.id || i} className="text-xs border-l-2 border-navy-600 pl-3 py-1">
                  <span className="text-gray-200">{evt.name}</span>
                  <div className="flex gap-2 mt-0.5">
                    <span className={`px-1 py-0 rounded ${typeColor[evt.entity_type] || 'bg-gray-900/30 text-gray-400'}`}>
                      {evt.entity_type}
                    </span>
                    <span className="text-gray-600">{evt.timestamp ? new Date(evt.timestamp).toLocaleDateString() : ''}</span>
                  </div>
                </div>
              ))}
              {recentActivity.length === 0 && <p className="text-xs text-gray-500">No activity yet</p>}
            </div>
          </div>

          {/* Reports */}
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-gray-400 mb-3">Intelligence Products</h3>
            <div className="space-y-2">
              {reports.map((r: { id?: string; name?: string; title?: string; report_type?: string }, i: number) => (
                <div key={r.id || i} className="text-xs bg-navy-700 rounded p-2">
                  <span className="text-gray-200">{r.name || r.title}</span>
                  <div className="text-gray-500 mt-1">{r.report_type || 'Report'}</div>
                </div>
              ))}
              {reports.length === 0 && <p className="text-xs text-gray-500">No reports yet</p>}
            </div>
            <button onClick={() => router.push('/products')} className="mt-3 text-xs text-accent-blue hover:text-blue-400">
              View all products &rarr;
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
