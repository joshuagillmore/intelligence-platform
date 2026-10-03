'use client';

import { useState } from 'react';
import { projectsApi, type Project } from '@/lib/api';
import { useNotifications } from '@/components/NotificationProvider';
import { memberChangeError } from '@/lib/projectAccess';

/**
 * Open projects (no members) are usable by everyone signed in. Projects made
 * from now on are owned by their creator, admins included, so the open ones
 * are those made before that: an admin claims them to restrict them.
 */

/** Whether to offer the claim: an admin, on an open project. */
export function mayClaim(project: Project, role: string | null | undefined): boolean {
  return role === 'admin' && project.access === 'open';
}

/**
 * Tells an admin how many projects are still open. Renders nothing when there
 * are none.
 */
export function OpenProjectsBanner({ count }: { count: number }) {
  if (count <= 0) return null;
  const one = count === 1;
  return (
    <div
      role="status"
      className="mb-6 rounded-lg border border-amber-700/50 bg-amber-900/20 px-4 py-3 text-sm text-amber-300"
    >
      {one
        ? '1 open project: anyone signed in can use it. Claim it to restrict access.'
        : `${count} open projects: anyone signed in can use them. Claim them to restrict access.`}
    </div>
  );
}

/**
 * Makes the signed-in admin the owner of an open project, which restricts it
 * to its members (and admins). `onClaimed` runs after a successful claim, so
 * the caller can re-read the list rather than patch it. A refusal (409 when
 * someone else added a member first) reports the backend's reason.
 */
export function ClaimProjectButton({
  project,
  onClaimed,
  compact = false,
}: {
  project: Project;
  onClaimed: () => void;
  compact?: boolean;
}) {
  const { addNotification } = useNotifications();
  const [busy, setBusy] = useState(false);

  async function claim() {
    if (busy) return;
    if (!confirm(`Claim "${project.name}"? You become its owner, and analysts who are not members lose access to it.`)) {
      return;
    }
    setBusy(true);
    try {
      await projectsApi.claim(project.id);
      addNotification({
        type: 'success',
        title: 'Project claimed',
        message: `You now own "${project.name}". Only its members and admins can open it.`,
      });
      onClaimed();
    } catch (err) {
      addNotification({
        type: 'error',
        title: `Could not claim "${project.name}"`,
        message: memberChangeError(err),
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      onClick={(e) => { e.stopPropagation(); claim(); }}
      disabled={busy}
      aria-label={`Claim ${project.name}`}
      title="Become this project's owner, so only its members (and admins) can open it"
      className={`${compact ? 'px-2 py-1 text-[10px]' : 'px-3 py-1 text-xs'} rounded font-medium transition-colors bg-amber-900/40 text-amber-300 hover:bg-amber-900/60 disabled:opacity-50`}
    >
      {busy ? 'Claiming…' : 'Claim'}
    </button>
  );
}
