'use client';
import Link from 'next/link';
import { useProject } from '@/lib/ProjectContext';
import { NO_ACCESS_MESSAGE } from '@/lib/projectAccess';

/**
 * Empty state shown by project-scoped views when no project is active.
 *
 * Replaces a bare "Select a project first." dead-end: an analyst landing here
 * had no way forward from the page itself. Says what to do and links to the
 * project list. When the active project was just dropped because the backend
 * refused it (403), says so, rather than implying none was ever chosen.
 */
export default function SelectProjectPrompt({ action = 'work in' }: { action?: string }) {
  const { deniedProject } = useProject();
  return (
    <div className="bg-navy-800 border border-navy-600 rounded-lg p-10 text-center">
      <span className="material-symbols-outlined text-4xl text-gray-600 mb-3 block">
        {deniedProject ? 'lock' : 'folder_open'}
      </span>
      <h3 className="text-base font-semibold text-gray-300 mb-1">
        {deniedProject ? NO_ACCESS_MESSAGE : 'No project selected'}
      </h3>
      <p className="text-sm text-gray-500 mb-5 max-w-md mx-auto">
        {deniedProject ? (
          <>
            &ldquo;{deniedProject.name}&rdquo; is restricted to its members, so it is no longer selected. Ask one
            of its owners to add you, or choose another project to {action}.
          </>
        ) : (
          <>Choose a project to {action}. Documents, entities, and analysis all live inside a project.</>
        )}
      </p>
      <Link
        href="/"
        className="inline-flex items-center gap-2 bg-accent-blue hover:bg-blue-600 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors"
      >
        <span className="material-symbols-outlined text-lg">arrow_forward</span>
        Choose a project
      </Link>
    </div>
  );
}
