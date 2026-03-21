'use client';
import { createContext, useContext, useState, ReactNode } from 'react';
import type { Project } from './api';

interface ProjectContextType {
  activeProject: Project | null;
  setActiveProject: (project: Project | null) => void;
}

const ProjectContext = createContext<ProjectContextType>({ activeProject: null, setActiveProject: () => {} });

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  return (
    <ProjectContext.Provider value={{ activeProject, setActiveProject }}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject() {
  return useContext(ProjectContext);
}
