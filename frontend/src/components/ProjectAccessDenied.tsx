import Link from 'next/link';
import { NO_ACCESS_MESSAGE } from '@/lib/projectAccess';

/**
 * Shown in place of a project view when the backend refused a project-scoped
 * read with 403: the project is restricted and the analyst is not a member.
 * Deliberately not the generic "could not load" error, whose Retry cannot
 * help: only an owner of the project can let them in.
 */
export default function ProjectAccessDenied({ projectName }: { projectName?: string | null }) {
  return (
    <div role="alert" className="bg-navy-800 border border-navy-600 rounded-lg p-10 text-center">
      <span className="material-symbols-outlined text-4xl text-threat-high mb-3 block" aria-hidden="true">lock</span>
      <h3 className="text-base font-semibold text-gray-200 mb-1">{NO_ACCESS_MESSAGE}</h3>
      <p className="text-sm text-gray-400 mb-5 max-w-md mx-auto">
        {projectName ? <>&ldquo;{projectName}&rdquo; is</> : 'It is'} restricted to its members. Ask one of its
        owners to add you, or choose another project.
      </p>
      <Link
        href="/"
        className="inline-flex items-center gap-2 bg-accent-blue hover:bg-blue-600 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors"
      >
        <span className="material-symbols-outlined text-lg" aria-hidden="true">arrow_forward</span>
        Choose a project
      </Link>
    </div>
  );
}
