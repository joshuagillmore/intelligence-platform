'use client';
import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import type { Project } from './api';

interface ProjectContextType {
  activeProject: Project | null;
  setActiveProject: (project: Project | null) => void;
}

const ProjectContext = createContext<ProjectContextType>({ activeProject: null, setActiveProject: () => {} });

export function ProjectProvider({ children }: { children: ReactNode }) {
  // Start null on BOTH the server and the first client render so the SSR markup
  // matches initial hydration; load the persisted project AFTER mount. Reading
  // localStorage in the initializer rendered null on the server but the stored
  // project on the client — an app-wide hydration mismatch (React #418/#423).
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    try {
      const stored = localStorage.getItem('activeProject');
      if (stored) setActiveProject(JSON.parse(stored));
    } catch { /* ignore malformed */ }
    setLoaded(true);
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
    <ProjectContext.Provider value={{ activeProject, setActiveProject }}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject() {
  return useContext(ProjectContext);
}
