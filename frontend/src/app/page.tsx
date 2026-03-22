'use client';
import { useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import Sidebar from '@/components/Sidebar';
import { projectsApi, watchlistApi, type Project } from '@/lib/api';
import { useProject } from '@/lib/ProjectContext';

function formatDate(dateStr?: string): string {
  if (!dateStr) return '--';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return '--';
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffHours = diffMs / (1000 * 60 * 60);
    if (diffHours < 1) {
      const mins = Math.floor(diffMs / 60000);
      return mins <= 0 ? 'just now' : `${mins}m ago`;
    }
    if (diffHours < 24) return `${Math.floor(diffHours)}h ago`;
    if (diffHours < 48) return 'yesterday';
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return '--';
  }
}

type SortKey = 'name' | 'created' | 'modified' | 'priority';
type SortDir = 'asc' | 'desc';
type ViewMode = 'grid' | 'list';

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [toast, setToast] = useState<string | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [watchedEntities, setWatchedEntities] = useState<any[]>([]);
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [batchDeleting, setBatchDeleting] = useState(false);
  const { activeProject, setActiveProject } = useProject();
  const router = useRouter();

  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [sortBy, setSortBy] = useState<SortKey>('modified');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  useEffect(() => {
    loadProjects();
  }, []);

  useEffect(() => {
    if (activeProject) {
      loadWatchedEntities(activeProject.id);
    } else {
      setWatchedEntities([]);
    }
  }, [activeProject]);

  async function loadWatchedEntities(projectId: string) {
    try {
      const res = await watchlistApi.list(projectId);
      setWatchedEntities(res.data || []);
    } catch {
      setWatchedEntities([]);
    }
  }

  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(null), 3000);
      return () => clearTimeout(t);
    }
  }, [toast]);

  async function loadProjects() {
    try {
      const res = await projectsApi.list();
      setProjects(res.data);
    } catch (e) {
      console.error('Failed to load projects', e);
    }
  }

  async function createProject() {
    if (!newName) return;
    try {
      await projectsApi.create({ name: newName, description: newDesc });
      setNewName('');
      setNewDesc('');
      setShowCreate(false);
      loadProjects();
    } catch (e) {
      console.error('Failed to create project', e);
    }
  }

  async function deleteProject(project: Project) {
    if (!confirm(`Are you sure you want to delete this project? "${project.name}"`)) return;
    try {
      await projectsApi.delete(project.id);
      if (activeProject?.id === project.id) {
        setActiveProject(null);
      }
      loadProjects();
      setToast(`Deleted: ${project.name}`);
    } catch (e) {
      console.error('Failed to delete project', e);
    }
  }

  function toggleChecked(projectId: string) {
    setCheckedIds(prev => {
      const next = new Set(prev);
      if (next.has(projectId)) next.delete(projectId);
      else next.add(projectId);
      return next;
    });
  }

  async function batchDeleteProjects() {
    if (checkedIds.size === 0) return;
    if (!confirm(`Are you sure you want to delete ${checkedIds.size} selected project(s)? This action cannot be undone.`)) return;
    setBatchDeleting(true);
    try {
      await projectsApi.batchDelete(Array.from(checkedIds));
      if (activeProject && checkedIds.has(activeProject.id)) {
        setActiveProject(null);
      }
      setCheckedIds(new Set());
      loadProjects();
      setToast(`Deleted ${checkedIds.size} project(s).`);
    } catch {
      // Fallback: delete one by one
      try {
        const ids = Array.from(checkedIds);
        for (let i = 0; i < ids.length; i++) {
          await projectsApi.delete(ids[i]);
        }
        if (activeProject && checkedIds.has(activeProject.id)) {
          setActiveProject(null);
        }
        setCheckedIds(new Set());
        loadProjects();
        setToast(`Deleted ${checkedIds.size} project(s).`);
      } catch {
        setToast('Failed to delete some projects.');
      }
    } finally {
      setBatchDeleting(false);
    }
  }

  function selectProject(project: Project) {
    setActiveProject(project);
    setToast(`Selected: ${project.name}`);
    router.push(`/project/${project.id}`);
  }

  const sortedProjects = useMemo(() => {
    const sorted = [...projects].sort((a, b) => {
      switch (sortBy) {
        case 'name':
          return a.name.localeCompare(b.name);
        case 'priority': {
          const order: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
          return (order[a.priority] ?? 99) - (order[b.priority] ?? 99);
        }
        case 'created':
          return (a.created_at || '').localeCompare(b.created_at || '');
        case 'modified':
          return (a.updated_at || a.created_at || '').localeCompare(b.updated_at || b.created_at || '');
        default:
          return 0;
      }
    });
    return sortDir === 'desc' ? sorted.reverse() : sorted;
  }, [projects, sortBy, sortDir]);

  function handleColumnSort(key: SortKey) {
    if (sortBy === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(key);
      setSortDir('asc');
    }
  }

  function sortArrow(key: SortKey) {
    if (sortBy !== key) return '';
    return sortDir === 'asc' ? ' \u25B2' : ' \u25BC';
  }

  return (
    <div className="flex">
      <Sidebar />
      <main className="md:ml-56 flex-1 p-4 pt-16 pb-24 md:p-8 md:pt-8 md:pb-8">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold">Projects</h2>
          <div className="flex items-center gap-3">
            {checkedIds.size > 0 && (
              <button
                onClick={batchDeleteProjects}
                disabled={batchDeleting}
                className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
              >
                {batchDeleting ? 'Deleting...' : `Delete Selected (${checkedIds.size})`}
              </button>
            )}
            <button
              onClick={() => setShowCreate(!showCreate)}
              className="bg-accent-blue hover:bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              + New Project
            </button>
          </div>
        </div>

        {showCreate && (
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-6 mb-6">
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Project name"
              className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm mb-3 focus:outline-none focus:border-accent-blue"
            />
            <textarea
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder="Description"
              className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm mb-3 h-20 focus:outline-none focus:border-accent-blue"
            />
            <button onClick={createProject} className="bg-accent-blue text-white px-4 py-2 rounded text-sm">
              Create
            </button>
          </div>
        )}

        {/* Sort & View Controls */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            {/* Sort dropdown */}
            <label className="text-xs text-gray-500">Sort by:</label>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortKey)}
              className="bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs text-gray-300 focus:outline-none focus:border-accent-blue"
            >
              <option value="name">Alphabetical</option>
              <option value="modified">Last Modified</option>
              <option value="created">Date Added</option>
              <option value="priority">Priority</option>
            </select>
            {/* Sort direction toggle */}
            <button
              onClick={() => setSortDir(d => d === 'asc' ? 'desc' : 'asc')}
              className="bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs text-gray-400 hover:text-gray-200 transition-colors"
              title={sortDir === 'asc' ? 'Ascending' : 'Descending'}
            >
              {sortDir === 'asc' ? '\u2191 Asc' : '\u2193 Desc'}
            </button>
          </div>
          {/* View toggle */}
          <div className="flex items-center bg-navy-700 border border-navy-600 rounded overflow-hidden">
            <button
              onClick={() => setViewMode('grid')}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                viewMode === 'grid' ? 'bg-accent-blue text-white' : 'text-gray-400 hover:text-gray-200'
              }`}
              title="Grid view"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
              </svg>
            </button>
            <button
              onClick={() => setViewMode('list')}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                viewMode === 'list' ? 'bg-accent-blue text-white' : 'text-gray-400 hover:text-gray-200'
              }`}
              title="List view"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
              </svg>
            </button>
          </div>
        </div>

        {/* Grid View */}
        {viewMode === 'grid' && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {sortedProjects.map((project) => (
              <div key={project.id} className={`bg-navy-800 border rounded-lg p-5 transition-colors ${
                activeProject?.id === project.id ? 'border-accent-blue' : 'border-navy-600 hover:border-accent-blue'
              }`}>
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    checked={checkedIds.has(project.id)}
                    onChange={(e) => { e.stopPropagation(); toggleChecked(project.id); }}
                    className="w-4 h-4 mt-1.5 rounded border-2 border-gray-500 bg-navy-700 accent-blue-500 cursor-pointer flex-shrink-0"
                  />
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-lg mb-1">{project.name}</h3>
                    <p className="text-gray-400 text-sm mb-3">{project.description || 'No description'}</p>
                    <div className="flex gap-4 text-xs text-gray-500 mb-1">
                      <span>{project.entity_count} entities</span>
                      <span>{project.relationship_count} relationships</span>
                      <span>{project.document_count} documents</span>
                      {(project.collection_count ?? 0) > 0 && <span>{project.collection_count} collections</span>}
                    </div>
                    <div className="flex gap-4 text-[10px] text-gray-600 mb-3">
                      <span>Created: {formatDate(project.created_at)}</span>
                      <span>Modified: {formatDate(project.updated_at)}</span>
                    </div>
                    <div className="flex gap-2 items-center">
                      <span className={`text-xs px-2 py-0.5 rounded ${
                        project.priority === 'critical' ? 'bg-threat-critical/20 text-threat-critical' :
                        project.priority === 'high' ? 'bg-threat-high/20 text-threat-high' :
                        'bg-navy-600 text-gray-400'
                      }`}>
                        {project.priority}
                      </span>
                      <span className="text-xs px-2 py-0.5 rounded bg-green-900/30 text-green-400">
                        {project.status}
                      </span>
                      <button
                        onClick={() => selectProject(project)}
                        className="ml-auto bg-accent-blue hover:bg-blue-600 text-white px-3 py-1 rounded text-xs font-medium transition-colors"
                      >
                        Select
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); deleteProject(project); }}
                        className="text-gray-500 hover:text-red-400 px-2 py-1 rounded text-xs transition-colors"
                        title="Delete project"
                      >
                        &times;
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
            {projects.length === 0 && (
              <p className="text-gray-500 col-span-3">No projects yet. Create one to get started.</p>
            )}
          </div>
        )}

        {/* List View */}
        {viewMode === 'list' && (
          <div className="bg-navy-800 border border-navy-600 rounded-lg overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-navy-700/50 border-b border-navy-600">
                    <th className="px-3 py-2 text-left w-8">
                      <input
                        type="checkbox"
                        checked={checkedIds.size === sortedProjects.length && sortedProjects.length > 0}
                        onChange={() => {
                          if (checkedIds.size === sortedProjects.length) {
                            setCheckedIds(new Set());
                          } else {
                            setCheckedIds(new Set(sortedProjects.map(p => p.id)));
                          }
                        }}
                        className="w-3.5 h-3.5 rounded border-2 border-gray-500 bg-navy-700 accent-blue-500 cursor-pointer"
                      />
                    </th>
                    <th
                      className="px-3 py-2 text-left text-[10px] font-semibold text-gray-400 uppercase tracking-wider cursor-pointer hover:text-gray-200"
                      onClick={() => handleColumnSort('name')}
                    >
                      Name{sortArrow('name')}
                    </th>
                    <th className="px-3 py-2 text-left text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
                      Description
                    </th>
                    <th
                      className="px-3 py-2 text-left text-[10px] font-semibold text-gray-400 uppercase tracking-wider cursor-pointer hover:text-gray-200"
                      onClick={() => handleColumnSort('priority')}
                    >
                      Priority{sortArrow('priority')}
                    </th>
                    <th className="px-3 py-2 text-left text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-3 py-2 text-right text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
                      Entities
                    </th>
                    <th className="px-3 py-2 text-right text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
                      Rels
                    </th>
                    <th className="px-3 py-2 text-right text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
                      Docs
                    </th>
                    <th className="px-3 py-2 text-right text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
                      Colls
                    </th>
                    <th
                      className="px-3 py-2 text-left text-[10px] font-semibold text-gray-400 uppercase tracking-wider cursor-pointer hover:text-gray-200"
                      onClick={() => handleColumnSort('created')}
                    >
                      Created{sortArrow('created')}
                    </th>
                    <th
                      className="px-3 py-2 text-left text-[10px] font-semibold text-gray-400 uppercase tracking-wider cursor-pointer hover:text-gray-200"
                      onClick={() => handleColumnSort('modified')}
                    >
                      Modified{sortArrow('modified')}
                    </th>
                    <th className="px-3 py-2 text-right text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-navy-700">
                  {sortedProjects.map((project) => (
                    <tr key={project.id} className={`hover:bg-navy-700/30 transition-colors ${
                      activeProject?.id === project.id ? 'bg-accent-blue/5' : ''
                    }`}>
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={checkedIds.has(project.id)}
                          onChange={() => toggleChecked(project.id)}
                          className="w-3.5 h-3.5 rounded border-2 border-gray-500 bg-navy-700 accent-blue-500 cursor-pointer"
                        />
                      </td>
                      <td className="px-3 py-2 font-medium text-gray-200 max-w-[160px] truncate">
                        {project.name}
                      </td>
                      <td className="px-3 py-2 text-gray-400 text-xs max-w-[200px] truncate">
                        {project.description || '--'}
                      </td>
                      <td className="px-3 py-2">
                        <span className={`text-[10px] px-2 py-0.5 rounded ${
                          project.priority === 'critical' ? 'bg-threat-critical/20 text-threat-critical' :
                          project.priority === 'high' ? 'bg-threat-high/20 text-threat-high' :
                          'bg-navy-600 text-gray-400'
                        }`}>
                          {project.priority}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <span className="text-[10px] px-2 py-0.5 rounded bg-green-900/30 text-green-400">
                          {project.status}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right text-xs text-gray-400">{project.entity_count}</td>
                      <td className="px-3 py-2 text-right text-xs text-gray-400">{project.relationship_count}</td>
                      <td className="px-3 py-2 text-right text-xs text-gray-400">{project.document_count}</td>
                      <td className="px-3 py-2 text-right text-xs text-gray-400">{project.collection_count ?? 0}</td>
                      <td className="px-3 py-2 text-[10px] text-gray-500 whitespace-nowrap">{formatDate(project.created_at)}</td>
                      <td className="px-3 py-2 text-[10px] text-gray-500 whitespace-nowrap">{formatDate(project.updated_at)}</td>
                      <td className="px-3 py-2 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => selectProject(project)}
                            className="bg-accent-blue hover:bg-blue-600 text-white px-2.5 py-1 rounded text-[10px] font-medium transition-colors"
                          >
                            View
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); deleteProject(project); }}
                            className="text-gray-500 hover:text-red-400 px-1.5 py-1 rounded text-xs transition-colors"
                            title="Delete project"
                          >
                            &times;
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {projects.length === 0 && (
              <div className="px-4 py-8 text-center text-gray-500 text-sm">
                No projects yet. Create one to get started.
              </div>
            )}
          </div>
        )}

        {activeProject && watchedEntities.length > 0 && (
          <div className="mt-8">
            <h3 className="text-lg font-semibold mb-3">Watched Entities</h3>
            <div className="bg-navy-800 border border-navy-600 rounded-lg divide-y divide-navy-700">
              {watchedEntities.map((entity: { id: string; name: string; entity_type: string; relationship_count?: number }) => (
                <div key={entity.id} className="flex items-center justify-between px-4 py-3">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-medium text-gray-200">{entity.name}</span>
                    <span className="text-xs px-2 py-0.5 rounded bg-navy-600 text-gray-400">{entity.entity_type}</span>
                    {entity.relationship_count !== undefined && (
                      <span className="text-xs text-gray-500">{entity.relationship_count} relationships</span>
                    )}
                  </div>
                  <button
                    onClick={() => router.push(`/network?entity=${entity.id}`)}
                    className="text-xs text-accent-blue hover:text-blue-400 transition-colors"
                  >
                    View in Graph
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {toast && (
          <div className="fixed bottom-6 right-6 bg-accent-blue text-white px-4 py-2 rounded-lg shadow-lg text-sm animate-pulse">
            {toast}
          </div>
        )}
      </main>
    </div>
  );
}
