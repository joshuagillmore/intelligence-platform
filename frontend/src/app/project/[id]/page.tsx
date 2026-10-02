'use client';
import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Sidebar from '@/components/Sidebar';
import PirPanel from '@/components/PirPanel';
import ProjectMembersPanel from '@/components/ProjectMembersPanel';
import ProjectAccessDenied from '@/components/ProjectAccessDenied';
import { OpenAccessBadge, RoleChip } from '@/components/ProjectAccessBadges';
import { useProject } from '@/lib/ProjectContext';
import {
  projectsApi, graphApi, reportsApi, timelineApi, exportApi, collectionPlansApi, isHttpStatus, type Project,
  type ProjectAccess, type ProjectRole,
} from '@/lib/api';
import { isNoProjectAccess } from '@/lib/projectAccess';
import { useNotifications } from '@/components/NotificationProvider';
import { TYPE_BADGE_CLASS, TYPE_COLOR_HEX } from '@/lib/entityStyles';
import { rankByDegree, type KeyEntity } from '@/lib/centrality';
import { getErrorMessage } from '@/lib/errorMessages';

type HubPanel = 'stats' | 'centrality' | 'timeline' | 'reports' | 'plans';

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
  const { setActiveProject, dropProject } = useProject();
  const { addNotification } = useNotifications();
  const [project, setProject] = useState<Project | null>(null);
  // Why the project itself failed to load, when it was not a plain 404.
  const [projectError, setProjectError] = useState<string | null>(null);
  // A project-scoped read was refused with 403: the analyst is not a member of
  // this restricted project. Its own state, not the generic error above,
  // whose Retry cannot help.
  const [accessDenied, setAccessDenied] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [stats, setStats] = useState<any>(null);
  const [topEntities, setTopEntities] = useState<KeyEntity[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [recentActivity, setRecentActivity] = useState<any[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [reports, setReports] = useState<any[]>([]);
  // Collection plans in the ACTIVE lifecycle state; null until loaded.
  const [activePlans, setActivePlans] = useState<number | null>(null);
  // Panels whose data failed to load. A failed panel says so; it does not
  // render a zero or an empty list as if that were the answer.
  const [panelErrors, setPanelErrors] = useState<Set<HubPanel>>(new Set());
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  const projectId = params.id as string;

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    setLoading(true);
    setProjectError(null);
    setAccessDenied(false);
    Promise.allSettled([
      projectsApi.get(projectId),
      graphApi.statistics(projectId),
      graphApi.centrality(projectId),
      timelineApi.get(projectId),
      reportsApi.list(projectId),
      collectionPlansApi.list(projectId),
    ]).then(([projRes, statsRes, centralRes, timeRes, repRes, plansRes]) => {
      if (cancelled) return;
      // Every call here is a read of this project, so a 403 from any of them
      // means no access to it: show that, and stop offering it as active.
      const refused = [projRes, statsRes, centralRes, timeRes, repRes, plansRes].some(
        (r) => r.status === 'rejected' && isNoProjectAccess(r.reason),
      );
      if (refused) {
        setProject(null);
        setAccessDenied(true);
        dropProject(projectId);
        setLoading(false);
        return;
      }
      if (projRes.status === 'rejected') {
        setProject(null);
        // A 404 is "not found"; anything else is a failure to load, and saying
        // "not found" for it sends the analyst looking for a deleted project.
        setProjectError(isHttpStatus(projRes.reason, 404) ? null : getErrorMessage(projRes.reason));
        setLoading(false);
        return;
      }
      setProject(projRes.value.data);
      setActiveProject(projRes.value.data);

      const failed = new Set<HubPanel>();
      if (statsRes.status === 'fulfilled') setStats(statsRes.value.data);
      else { setStats(null); failed.add('stats'); }
      // /graph/centrality returns `degree`; rank and scale by it.
      if (centralRes.status === 'fulfilled') setTopEntities(rankByDegree(centralRes.value.data, 10));
      else { setTopEntities([]); failed.add('centrality'); }
      if (timeRes.status === 'fulfilled') {
        const events = timeRes.value.data?.events;
        setRecentActivity(Array.isArray(events) ? events.slice(0, 15) : []);
      } else { setRecentActivity([]); failed.add('timeline'); }
      if (repRes.status === 'fulfilled') setReports(Array.isArray(repRes.value.data) ? repRes.value.data : []);
      else { setReports([]); failed.add('reports'); }
      if (plansRes.status === 'fulfilled') {
        const plans = Array.isArray(plansRes.value.data) ? plansRes.value.data : [];
        setActivePlans(plans.filter(p => p.status === 'ACTIVE').length);
      } else { setActivePlans(null); failed.add('plans'); }
      setPanelErrors(failed);
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, [projectId, setActiveProject, dropProject, reloadKey]);

  /** A read made after the load (an export, the members list) was refused. */
  function denyAccess() {
    setAccessDenied(true);
    dropProject(projectId);
  }

  /** The members panel's answer, which follows changes made in it. */
  function followAccess(access: ProjectAccess, myRole: ProjectRole | null) {
    setProject((p) => (p && (p.access !== access || p.my_role !== myRole) ? { ...p, access, my_role: myRole } : p));
  }

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

  if (accessDenied) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="md:ml-56 flex-1 p-4 pt-16 pb-24 md:p-8 md:pt-8 md:pb-8" style={{ backgroundColor: colors.surface, minHeight: '100vh' }}>
          <ProjectAccessDenied projectName={project?.name} />
        </main>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="md:ml-56 flex-1 p-4 pt-16 pb-24 md:p-8 md:pt-8 md:pb-8" style={{ backgroundColor: colors.surface, minHeight: '100vh' }}>
          {projectError ? (
            <div>
              <p style={{ color: colors.tertiary }}>Could not load this project: {projectError}</p>
              <button
                onClick={() => setReloadKey(k => k + 1)}
                className="mt-3 text-xs px-3 py-1.5 rounded bg-navy-700 text-accent-blue hover:bg-navy-600 transition-colors"
              >
                Retry
              </button>
            </div>
          ) : (
            <div style={{ color: colors.tertiary }}>Project not found</div>
          )}
        </main>
      </div>
    );
  }

  const entityCount = stats?.nodes || project.entity_count || 0;
  const relationshipCount = stats?.edges || project.relationship_count || 0;
  const documentCount = project.document_count || 0;
  // Collection plans an analyst has put into the ACTIVE state (not the number
  // of reports, which is what this card used to count).
  const activeCollections = activePlans;
  // Weakly connected components beyond the main one: a fully connected graph
  // has none. The raw component count read 1 for a connected graph.
  const disconnectedClusters = panelErrors.has('stats')
    ? null
    : Math.max((typeof stats?.components === 'number' ? stats.components : 0) - 1, 0);

  const statCards = [
    { label: 'Entities', value: entityCount, color: colors.primary, progress: Math.min(entityCount / 100, 1) },
    { label: 'Relationships', value: relationshipCount, color: colors.secondary, progress: Math.min(relationshipCount / 200, 1) },
    { label: 'Documents', value: documentCount, color: colors.primary, progress: Math.min(documentCount / 50, 1) },
    { label: 'Active Collections', value: activeCollections, color: colors.green, progress: Math.min((activeCollections ?? 0) / 20, 1) },
    { label: 'Disconnected Clusters', value: disconnectedClusters, color: colors.tertiary, progress: Math.min((disconnectedClusters ?? 0) / 10, 1) },
  ];

  // Entity badge classes (activity list) come from the SSOT in
  // '@/lib/entityStyles'; the Key Entities pills derive their inline colors
  // from the SSOT hex map (TYPE_COLOR_HEX) below.

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

  // Heuristic flags derived from graph statistics — simple threshold checks over
  // centrality and counts, not model output. Labeled as such so they are not
  // mistaken for AI-generated confidence scores.
  const insights = [
    ...(topEntities.length > 2 && topEntities[0].degree > 0 ? [{
      tag: 'Centrality',
      description: `Entity "${topEntities[0].name}" has the most connections in the network (${topEntities[0].degree}), suggesting a key node connecting multiple clusters.`,
      action: 'Deep Analysis',
      actionHref: '/network',
    }] : []),
    ...(relationshipCount > 5 ? [{
      tag: 'Density',
      description: `${relationshipCount} relationships across ${entityCount} entities. Density patterns may point to undiscovered connections.`,
      action: 'Verify Connection',
      actionHref: '/network',
    }] : []),
    ...(disconnectedClusters && disconnectedClusters > 0 ? [{
      tag: 'Connectivity',
      description: `${disconnectedClusters} cluster${disconnectedClusters === 1 ? ' is' : 's are'} not connected to the main network. These gaps may indicate missing intelligence links.`,
      action: 'Deep Analysis',
      actionHref: '/network',
    }] : []),
  ];

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
            <div className="flex flex-wrap gap-2 mt-3">
              <span className={`text-xs px-2 py-0.5 rounded ${
                project.priority === 'critical' ? 'bg-red-900/30 text-red-400' :
                project.priority === 'high' ? 'bg-orange-900/30 text-orange-400' :
                'bg-navy-600 text-gray-400'
              }`}>{project.priority}</span>
              <span className="text-xs px-2 py-0.5 rounded bg-green-900/30 text-green-400">{project.status}</span>
              <span className="text-xs px-2 py-0.5 rounded bg-navy-600 text-gray-400">{project.classification_level}</span>
              {/* What this analyst may do here, and whether anyone may. */}
              <RoleChip role={project.my_role} prefix="Your role:" />
              <OpenAccessBadge access={project.access} />
            </div>
          </div>
          <div className="flex gap-3">
            <button
              onClick={async () => {
                try {
                  const res = await exportApi.stix(projectId);
                  const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `stix-export-${projectId.substring(0, 8)}.json`;
                  a.click();
                  URL.revokeObjectURL(url);
                  addNotification({
                    type: 'success',
                    title: 'STIX Export Ready',
                    message: 'The STIX 2.1 bundle has been downloaded.',
                  });
                } catch (e) {
                  if (isNoProjectAccess(e)) {
                    denyAccess();
                    return;
                  }
                  addNotification({
                    type: 'error',
                    title: 'Export Failed',
                    message: 'Could not build the STIX export. Check the backend and try again.',
                  });
                }
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
              <div
                className="text-2xl font-bold text-white"
                title={s.value == null ? 'Could not load this figure' : undefined}
              >
                {s.value ?? '—'}
              </div>
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

        {/* Requirements spine — what this project is trying to answer */}
        <PirPanel projectId={projectId} />

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
                    role={evt.id ? 'button' : undefined}
                    tabIndex={evt.id ? 0 : undefined}
                    title={evt.id ? `View ${evt.name} in the graph` : undefined}
                    onClick={evt.id ? () => router.push(`/network?select=${evt.id}`) : undefined}
                    onKeyDown={evt.id ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); router.push(`/network?select=${evt.id}`); } } : undefined}
                    className={`rounded-md p-3 relative ${evt.id ? 'cursor-pointer hover:brightness-125 transition-[filter]' : ''}`}
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
                      className={`inline-block mt-1.5 text-[10px] px-1.5 py-0.5 rounded ${TYPE_BADGE_CLASS[evt.entity_type] || 'bg-gray-900/30 text-gray-400'}`}
                    >
                      {evt.entity_type}
                    </span>
                  </div>
                );
              })}
              {recentActivity.length === 0 && (panelErrors.has('timeline')
                ? <p className="text-xs text-red-300">Could not load recent activity.</p>
                : <p className="text-xs text-gray-500">No activity yet</p>)}
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
                  {topEntities.map((e, i) => {
                    const badgeHex = TYPE_COLOR_HEX[e.entity_type] || '#9ca3af';
                    // Degree scaled by the best-connected entity (1.000 = most links).
                    const centralityVal = e.score;
                    const centralityPct = centralityVal * 100;
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
                            onClick={() => router.push(e.id ? `/network?select=${e.id}` : '/network')}
                          >
                            {e.name}
                          </button>
                        </td>
                        <td className="py-2.5 pr-4">
                          <span
                            className="text-[10px] px-2 py-1 rounded-full font-medium"
                            style={{ backgroundColor: `${badgeHex}26`, color: badgeHex }}
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
                            <span className="text-[10px] text-gray-500" title={`${e.degree} link${e.degree === 1 ? '' : 's'}`}>
                              {centralityVal.toFixed(3)}
                            </span>
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
              {topEntities.length === 0 && (panelErrors.has('centrality')
                ? <p className="text-xs text-red-300 mt-4">Could not load key entities.</p>
                : <p className="text-xs text-gray-500 mt-4">No entities yet</p>)}
            </div>
          </div>

          {/* Right Column: Heuristic Flags */}
          <div className="space-y-4">
            <div
              className="rounded-lg p-4"
              style={{ backgroundColor: colors.container }}
            >
              <h3 className="text-sm font-semibold text-white mb-1 flex items-center gap-2">
                <span style={{ color: colors.primary }}>|</span> Heuristic Flags
              </h3>
              <p className="text-[10px] text-gray-500 mb-4">Rule-based signals from graph statistics</p>
              <div className="space-y-3">
                {insights.map((insight, i) => (
                  <div
                    key={i}
                    className="rounded-md p-3"
                    style={{ backgroundColor: colors.containerLow }}
                  >
                    <span
                      className="inline-block text-[10px] font-semibold px-2 py-0.5 rounded-full mb-2 uppercase tracking-wider"
                      style={{
                        backgroundColor: 'rgba(173, 198, 255, 0.12)',
                        color: colors.primary,
                      }}
                    >
                      {insight.tag}
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
                  <p className="text-xs text-gray-500">Insufficient data for heuristics. Add more entities and relationships.</p>
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
                  { label: 'Disconnected clusters', value: disconnectedClusters, max: Math.max(entityCount, relationshipCount, documentCount, 1), color: colors.tertiary },
                ].map(bar => (
                  <div key={bar.label}>
                    <div className="flex justify-between text-[10px] mb-1">
                      <span style={{ color: '#6b7280' }}>{bar.label}</span>
                      <span style={{ color: '#6b7280' }}>{bar.value ?? '—'}</span>
                    </div>
                    <div
                      className="h-2 rounded-full overflow-hidden"
                      style={{ backgroundColor: 'rgba(255,255,255,0.06)' }}
                    >
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${Math.max(((bar.value ?? 0) / bar.max) * 100, 2)}%`,
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
                {reports.length === 0 && (panelErrors.has('reports')
                  ? <p className="text-xs text-red-300">Could not load reports.</p>
                  : <p className="text-xs text-gray-500">No reports yet</p>)}
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

        {/* Who can open this project; owners manage it here. */}
        <div className="mt-8">
          <ProjectMembersPanel projectId={projectId} onAccessChange={followAccess} onNoAccess={denyAccess} />
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
          <span>Project ID: {projectId.substring(0, 8)}</span>
          <span>Last Viewed: {new Date().toLocaleString()}</span>
        </div>
      </main>
    </div>
  );
}
