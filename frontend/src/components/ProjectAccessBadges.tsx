import type { ProjectAccess, ProjectRole } from '@/lib/api';
import { ROLE_DESCRIPTION, ROLE_LABEL } from '@/lib/projectAccess';

const ROLE_CLASS: Record<ProjectRole, string> = {
  owner: 'bg-accent-periwinkle/15 text-accent-periwinkle',
  editor: 'bg-accent-cyan/15 text-accent-cyan',
  viewer: 'bg-navy-600 text-gray-300',
};

/**
 * The analyst's role on a project, as `my_role` reports it. Renders nothing
 * when they hold none (a non-member on an open project): `OpenAccessBadge`
 * says why they can still work in it.
 */
export function RoleChip({ role, prefix }: { role: ProjectRole | null | undefined; prefix?: string }) {
  if (!role || !(role in ROLE_LABEL)) return null;
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded whitespace-nowrap ${ROLE_CLASS[role]}`}
      title={ROLE_DESCRIPTION[role]}
    >
      {prefix ? `${prefix} ${ROLE_LABEL[role]}` : ROLE_LABEL[role]}
    </span>
  );
}

/**
 * Marks a project with no members: every signed-in analyst can read and
 * change it until an owner is added. Renders nothing for a restricted project.
 */
export function OpenAccessBadge({ access }: { access: ProjectAccess | null | undefined }) {
  if (access !== 'open') return null;
  return (
    <span
      className="text-xs px-2 py-0.5 rounded whitespace-nowrap bg-amber-900/30 text-amber-400"
      title="This project has no members, so every signed-in analyst can read and change it. Adding an owner restricts it to its members."
    >
      Open to all analysts
    </span>
  );
}
