'use client';

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { projectsApi, type ProjectAccess, type ProjectMember, type ProjectRole } from '@/lib/api';
import { useNotifications } from '@/components/NotificationProvider';
import { useSession } from '@/lib/SessionContext';
import { getErrorMessage } from '@/lib/errorMessages';
import {
  NO_ACCESS_MESSAGE,
  PROJECT_ROLES,
  ROLE_DESCRIPTION,
  ROLE_LABEL,
  canManageMembers,
  isNoProjectAccess,
  memberChangeError,
} from '@/lib/projectAccess';
import { OpenAccessBadge, RoleChip } from '@/components/ProjectAccessBadges';

interface Props {
  projectId: string;
  /** Each time the members load: the project's access and the analyst's
   *  role, so the page header follows a change made here (adding the first
   *  owner restricts an open project; an owner may demote themselves). */
  onAccessChange?: (access: ProjectAccess, myRole: ProjectRole | null) => void;
  /** Loading the members was refused with 403: the analyst has no access to
   *  the project (for instance, they just removed themselves). */
  onNoAccess?: () => void;
}

/** "an owner", "an editor", "a viewer". */
function withArticle(role: ProjectRole): string {
  const label = ROLE_LABEL[role].toLowerCase();
  return `${/^[aeiou]/.test(label) ? 'an' : 'a'} ${label}`;
}

function formatAdded(member: ProjectMember): string | null {
  const parts: string[] = [];
  if (member.added_by) parts.push(`added by ${member.added_by}`);
  if (member.added_at) {
    const d = new Date(member.added_at);
    if (!isNaN(d.getTime())) parts.push(d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }));
  }
  return parts.length ? parts.join(' · ') : null;
}

const ADDING = Symbol('adding');

/**
 * Who can open a project, and (for its owners) the controls to change that:
 * add an analyst by username with a role, change a member's role, remove one.
 *
 * Owner-only controls are hidden from editors and viewers. A new project
 * starts with its creator as owner, so only older projects are open (no
 * members yet). There every analyst has full rights, so anyone may add the
 * first member, who must be an owner; the panel says so before the first add
 * and offers no other role. The backend enforces all of it: a refused change
 * (403, the 409 for removing or demoting the last owner, "No such user")
 * reports the backend's own reason through a notification, and the list is
 * re-read after every change rather than patched optimistically.
 */
export default function ProjectMembersPanel({ projectId, onAccessChange, onNoAccess }: Props) {
  const { addNotification } = useNotifications();
  const { user } = useSession();
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [access, setAccess] = useState<ProjectAccess | null>(null);
  const [myRole, setMyRole] = useState<ProjectRole | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [denied, setDenied] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [newRole, setNewRole] = useState<ProjectRole>('editor');
  // The member a change is in flight for, or ADDING; null when idle.
  const [busy, setBusy] = useState<string | typeof ADDING | null>(null);

  // The parent's callbacks, kept out of `load`'s dependencies so an inline
  // arrow from the page does not re-run the load on every render.
  const callbacks = useRef({ onAccessChange, onNoAccess });
  useEffect(() => {
    callbacks.current = { onAccessChange, onNoAccess };
  }, [onAccessChange, onNoAccess]);

  const load = useCallback(async () => {
    try {
      const res = await projectsApi.members(projectId);
      const body = res.data;
      // A body without a member list is an error to show, not "no members":
      // read as empty, it would announce an open project that is not.
      if (!body || !Array.isArray(body.members)) throw new Error('Unexpected members response shape.');
      const role = body.my_role ?? null;
      setMembers(body.members);
      setAccess(body.access);
      setMyRole(role);
      setLoadError(null);
      setDenied(false);
      callbacks.current.onAccessChange?.(body.access, role);
    } catch (e) {
      if (isNoProjectAccess(e)) {
        setDenied(true);
        callbacks.current.onNoAccess?.();
      } else {
        setLoadError(getErrorMessage(e));
      }
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  const manage = canManageMembers(myRole, access);
  const firstMember = members.length === 0;

  async function addMember(e: FormEvent) {
    e.preventDefault();
    const username = newUsername.trim();
    if (!username || busy !== null) return;
    // The backend refuses any other role for the first member (409).
    const role: ProjectRole = firstMember ? 'owner' : newRole;
    const existing = members.some((m) => m.username === username);
    setBusy(ADDING);
    try {
      await projectsApi.setMemberRole(projectId, username, role);
      setNewUsername('');
      addNotification({
        type: 'success',
        title: existing ? 'Member updated' : 'Member added',
        message: `${username} is now ${withArticle(role)} of this project.`,
      });
      await load();
    } catch (err) {
      addNotification({ type: 'error', title: `Could not add ${username}`, message: memberChangeError(err) });
    } finally {
      setBusy(null);
    }
  }

  async function changeRole(member: ProjectMember, role: ProjectRole) {
    if (role === member.role || busy !== null) return;
    setBusy(member.username);
    try {
      await projectsApi.setMemberRole(projectId, member.username, role);
      await load();
    } catch (err) {
      // The picker shows the member's stored role, so a refused change
      // leaves it where it was; the reason goes to a notification.
      addNotification({
        type: 'error',
        title: `Could not change ${member.username}'s role`,
        message: memberChangeError(err),
      });
    } finally {
      setBusy(null);
    }
  }

  async function removeMember(member: ProjectMember) {
    if (busy !== null) return;
    const self = !!user && user.username === member.username;
    const question = self
      ? 'Remove yourself from this project? Unless you are an admin, you will lose access to it.'
      : `Remove ${member.username} from this project? They will lose access to it.`;
    if (!confirm(question)) return;
    setBusy(member.username);
    try {
      await projectsApi.removeMember(projectId, member.username);
      addNotification({ type: 'success', title: 'Member removed', message: `${member.username} was removed from this project.` });
      await load();
    } catch (err) {
      addNotification({ type: 'error', title: `Could not remove ${member.username}`, message: memberChangeError(err) });
    } finally {
      setBusy(null);
    }
  }

  return (
    <section aria-labelledby="project-members-heading" className="rounded-lg p-4 mb-8 bg-navy-800">
      <div className="flex flex-wrap items-center gap-2 mb-1">
        <h3 id="project-members-heading" className="text-sm font-semibold text-white flex items-center gap-2">
          <span className="text-accent-periwinkle" aria-hidden="true">|</span> Members
        </h3>
        <OpenAccessBadge access={access} />
        <RoleChip role={myRole} prefix="You:" />
      </div>
      <p className="text-[10px] text-gray-500 mb-3">
        {access === 'open'
          ? 'No members yet: every signed-in analyst can read and change this project.'
          : access === 'restricted'
            ? `Only members can open this project (${members.length} ${members.length === 1 ? 'member' : 'members'}).`
            : 'Who can open this project.'}{' '}
        Admins are owners of every project; one is listed only where they created or claimed it.
      </p>

      {loading && <p className="text-xs text-gray-500">Loading members...</p>}

      {!loading && denied && <p className="text-xs text-threat-high">{NO_ACCESS_MESSAGE}.</p>}

      {!loading && !denied && loadError && (
        <div>
          <p className="text-xs text-red-300">Could not load members: {loadError}</p>
          <button
            onClick={() => { setLoading(true); load(); }}
            className="mt-2 text-xs px-3 py-1.5 rounded bg-navy-700 text-accent-blue hover:bg-navy-600 transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {!loading && !denied && !loadError && (
        <>
          {members.length > 0 && (
            <ul className="divide-y divide-navy-700 mb-3" aria-label="Project members">
              {members.map((member) => {
                const added = formatAdded(member);
                const isSelf = !!user && user.username === member.username;
                const rowBusy = busy === member.username;
                return (
                  <li key={member.username} className="flex flex-wrap items-center gap-3 py-2">
                    <div className="flex-1 min-w-[10rem]">
                      <span className="text-sm text-gray-200">{member.username}</span>
                      {isSelf && <span className="ml-1.5 text-[10px] text-gray-500">(you)</span>}
                      {added && <div className="text-[10px] text-gray-500">{added}</div>}
                    </div>
                    {manage ? (
                      <select
                        aria-label={`Role for ${member.username}`}
                        value={member.role}
                        disabled={busy !== null}
                        onChange={(e) => changeRole(member, e.target.value as ProjectRole)}
                        className="bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-accent-blue disabled:opacity-50"
                      >
                        {PROJECT_ROLES.map((r) => (
                          <option key={r} value={r} title={ROLE_DESCRIPTION[r]}>{ROLE_LABEL[r]}</option>
                        ))}
                      </select>
                    ) : (
                      <RoleChip role={member.role} />
                    )}
                    {manage && (
                      <button
                        onClick={() => removeMember(member)}
                        disabled={busy !== null}
                        aria-label={`Remove ${member.username}`}
                        title={`Remove ${member.username}`}
                        className="text-gray-500 hover:text-red-400 px-2 py-1 rounded text-xs transition-colors disabled:opacity-50"
                      >
                        {rowBusy ? '…' : 'Remove'}
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}

          {!manage && (
            <p className="text-[11px] text-gray-500">Only an owner of this project can add, change or remove members.</p>
          )}

          {manage && (
            <form onSubmit={addMember} className="space-y-2">
              {firstMember && (
                <p className="text-[11px] text-amber-400" role="note">
                  The first member must be an owner. Adding one restricts this project: from then on only its
                  members (and admins) can open it.
                </p>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <input
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  placeholder="Username"
                  aria-label="Username to add"
                  autoComplete="off"
                  className="flex-1 min-w-[10rem] bg-navy-700 border border-navy-600 rounded px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-accent-blue"
                />
                <select
                  aria-label="Role for the new member"
                  value={firstMember ? 'owner' : newRole}
                  disabled={firstMember}
                  onChange={(e) => setNewRole(e.target.value as ProjectRole)}
                  className="bg-navy-700 border border-navy-600 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-accent-blue disabled:opacity-60"
                >
                  {PROJECT_ROLES.map((r) => (
                    <option key={r} value={r} title={ROLE_DESCRIPTION[r]}>{ROLE_LABEL[r]}</option>
                  ))}
                </select>
                <button
                  type="submit"
                  disabled={!newUsername.trim() || busy !== null}
                  className="bg-accent-blue hover:bg-blue-600 text-white px-3 py-1.5 rounded text-xs font-medium transition-colors disabled:opacity-50"
                >
                  {busy === ADDING ? 'Adding…' : firstMember ? 'Add owner' : 'Add member'}
                </button>
              </div>
            </form>
          )}
        </>
      )}
    </section>
  );
}
