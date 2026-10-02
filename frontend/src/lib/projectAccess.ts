/**
 * Per-project access for the UI (plan 2026-10-02, contract 1).
 *
 * The backend enforces every rule here; this module only decides what to
 * offer, so an analyst is not shown a control that can only fail, and how to
 * word the backend's answers.
 */
import axios from 'axios';
import type { ProjectAccess, ProjectRole } from './api';
import { getErrorMessage } from './errorMessages';

/** Strongest first: the order the role pickers list them in. */
export const PROJECT_ROLES: readonly ProjectRole[] = ['owner', 'editor', 'viewer'];

export const ROLE_LABEL: Record<ProjectRole, string> = {
  owner: 'Owner',
  editor: 'Editor',
  viewer: 'Viewer',
};

export const ROLE_DESCRIPTION: Record<ProjectRole, string> = {
  owner: 'Can read and change the project, manage its members, and delete it',
  editor: 'Can read and change the project data',
  viewer: 'Can read the project, not change it',
};

/** What a view says when a project-scoped call is refused. */
export const NO_ACCESS_MESSAGE = "You don't have access to this project";

/** The HTTP status the backend answered with, if it answered. Local rather
 *  than `isHttpStatus` from `./api`, so a test that mocks the API client
 *  still gets the real check. */
function statusOf(error: unknown): number | undefined {
  return axios.isAxiosError(error) ? error.response?.status : undefined;
}

/**
 * True when a project-scoped call was refused with 403.
 *
 * On a read (loading a project or anything in it) that means the analyst is
 * not a member of a restricted project, and the view shows the no-access state
 * instead of a generic error. A refused write is different: the analyst may
 * still read, so it is reported through a notification, not this state.
 */
export function isNoProjectAccess(error: unknown): boolean {
  return statusOf(error) === 403;
}

/**
 * Whether to offer member management. Owners manage members; so does anyone
 * on an open project, where every signed-in analyst has full rights and
 * someone has to add the first owner. An admin's `my_role` is already `owner`.
 */
export function canManageMembers(
  myRole: ProjectRole | null | undefined,
  access: ProjectAccess | null | undefined,
): boolean {
  return myRole === 'owner' || access === 'open';
}

/**
 * The analyst-facing reason a member change was refused: the backend's
 * `detail` when it sent one ("A project must keep at least one owner", "No
 * such user", ...), otherwise a reason for the status rather than a bare code.
 */
export function memberChangeError(error: unknown): string {
  const data = axios.isAxiosError(error) ? (error.response?.data as { detail?: unknown } | undefined) : undefined;
  const detail = data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail.trim();
  const status = statusOf(error);
  if (status === 403) return 'Only an owner of this project can change its members.';
  if (status === 409) return 'A project must keep at least one owner.';
  return getErrorMessage(error);
}
