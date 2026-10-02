'use client';
import { createContext, useCallback, useContext, useState, useEffect, ReactNode } from 'react';
import { projectsApi, PROJECT_ACCESS_DENIED_EVENT, type Project } from './api';
import { isNoProjectAccess } from './projectAccess';

interface ProjectContextType {
  activeProject: Project | null;
  setActiveProject: (project: Project | null) => void;
  /**
   * Forget `projectId` if it is the active project, because a load of it was
   * refused with 403: the analyst is not (or no longer) a member. Views then
   * fall back to "choose a project", and `deniedProject` says why.
   */
  dropProject: (projectId: string) => void;
  /** The project last dropped for a 403, until another project is chosen. */
  deniedProject: Project | null;
}

const ProjectContext = createContext<ProjectContextType>({
  activeProject: null,
  setActiveProject: () => {},
  dropProject: () => {},
  deniedProject: null,
});

interface Selection {
  active: Project | null;
  denied: Project | null;
}

export function ProjectProvider({ children }: { children: ReactNode }) {
  // Start null on BOTH the server and the first client render so the SSR markup
  // matches initial hydration; load the persisted project AFTER mount. Reading
  // localStorage in the initializer rendered null on the server but the stored
  // project on the client — an app-wide hydration mismatch (React #418/#423).
  // One state for both fields, so dropping a project and remembering it as
  // denied is a single update that only happens if it is still the active one.
  const [{ active: activeProject, denied: deniedProject }, setSelection] = useState<Selection>({
    active: null,
    denied: null,
  });
  const [loaded, setLoaded] = useState(false);

  const setActiveProject = useCallback((project: Project | null) => {
    setSelection((s) => ({ active: project, denied: project ? null : s.denied }));
  }, []);

  const dropProject = useCallback((projectId: string) => {
    setSelection((s) => (s.active?.id === projectId ? { active: null, denied: s.active } : s));
  }, []);

  useEffect(() => {
    let stored: Project | null = null;
    try {
      const raw = localStorage.getItem('activeProject');
      if (raw) stored = JSON.parse(raw);
    } catch { /* ignore malformed */ }
    if (stored) setSelection({ active: stored, denied: null });
    setLoaded(true);

    // The stored project was readable when it was chosen; it may not be now
    // (another analyst on this workstation, or an owner removed this one), and
    // every view would open on a project that only answers 403. Ask once. The
    // login page has no session to ask with.
    if (!stored?.id || window.location.pathname.startsWith('/login')) return;
    const id = stored.id;
    let cancelled = false;
    projectsApi.get(id).catch((error: unknown) => {
      if (!cancelled && isNoProjectAccess(error)) dropProject(id);
    });
    return () => { cancelled = true; };
  }, [dropProject]);

  // Any view that meets the access refusal mid-session (an owner removed this
  // analyst): drop the project once, the same way the load-time check does.
  useEffect(() => {
    const onDenied = () => {
      setSelection((s) => (s.active ? { active: null, denied: s.active } : s));
    };
    window.addEventListener(PROJECT_ACCESS_DENIED_EVENT, onDenied);
    return () => window.removeEventListener(PROJECT_ACCESS_DENIED_EVENT, onDenied);
  }, []);

  useEffect(() => {
    if (!loaded) return; // don't wipe storage on the pre-load null
    if (activeProject) {
      localStorage.setItem('activeProject', JSON.stringify(activeProject));
    } else {
      localStorage.removeItem('activeProject');
    }
  }, [activeProject, loaded]);

  return (
    <ProjectContext.Provider value={{ activeProject, setActiveProject, dropProject, deniedProject }}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject() {
  return useContext(ProjectContext);
}
