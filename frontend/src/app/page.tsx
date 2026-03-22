'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Sidebar from '@/components/Sidebar';
import { projectsApi, watchlistApi, type Project } from '@/lib/api';
import { useProject } from '@/lib/ProjectContext';

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

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-8">
        <div className="flex justify-between items-center mb-8">
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

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((project) => (
            <div key={project.id} className={`bg-navy-800 border rounded-lg p-5 transition-colors ${
              activeProject?.id === project.id ? 'border-accent-blue' : 'border-navy-600 hover:border-accent-blue'
            }`}>
              <div className="flex items-start gap-3">
                <input
                  type="checkbox"
                  checked={checkedIds.has(project.id)}
                  onChange={() => toggleChecked(project.id)}
                  className="mt-1.5 rounded border-navy-600 bg-navy-700 text-accent-blue focus:ring-accent-blue cursor-pointer"
                />
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-lg mb-1">{project.name}</h3>
                  <p className="text-gray-400 text-sm mb-4">{project.description || 'No description'}</p>
                  <div className="flex gap-4 text-xs text-gray-500">
                    <span>{project.entity_count} entities</span>
                    <span>{project.relationship_count} relationships</span>
                    <span>{project.document_count} documents</span>
                  </div>
                  <div className="mt-3 flex gap-2 items-center">
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
