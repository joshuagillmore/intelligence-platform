'use client';
import Link from 'next/link';

/**
 * Empty state shown by project-scoped views when no project is active.
 *
 * Replaces a bare "Select a project first." dead-end: an analyst landing here
 * had no way forward from the page itself. Says what to do and links to the
 * project list.
 */
export default function SelectProjectPrompt({ action = 'work in' }: { action?: string }) {
  return (
    <div className="bg-navy-800 border border-navy-600 rounded-lg p-10 text-center">
      <span className="material-symbols-outlined text-4xl text-gray-600 mb-3 block">folder_open</span>
      <h3 className="text-base font-semibold text-gray-300 mb-1">No project selected</h3>
      <p className="text-sm text-gray-500 mb-5 max-w-md mx-auto">
        Choose a project to {action}. Documents, entities, and analysis all live inside a project.
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
