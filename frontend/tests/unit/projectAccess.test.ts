import { describe, it, expect } from 'vitest';
import { AxiosError } from 'axios';
import { canManageMembers, isNoProjectAccess, memberChangeError } from '@/lib/projectAccess';

function refused(status: number, data: unknown = {}): AxiosError {
  return new AxiosError('Request failed', 'ERR_BAD_REQUEST', undefined, null, {
    status,
    statusText: String(status),
    data,
    headers: {},
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    config: {} as any,
  });
}

describe('projectAccess', () => {
  it('reads a 403 as no access, and nothing else', () => {
    expect(isNoProjectAccess(refused(403, { detail: 'No access to this project' }))).toBe(true);
    expect(isNoProjectAccess(refused(404))).toBe(false);
    expect(isNoProjectAccess(refused(500))).toBe(false);
    expect(isNoProjectAccess(new Error('Network Error'))).toBe(false);
    expect(isNoProjectAccess(undefined)).toBe(false);
  });

  it('offers member management to owners and, on an open project, to anyone', () => {
    expect(canManageMembers('owner', 'restricted')).toBe(true);
    expect(canManageMembers('editor', 'restricted')).toBe(false);
    expect(canManageMembers('viewer', 'restricted')).toBe(false);
    expect(canManageMembers(null, 'restricted')).toBe(false);
    expect(canManageMembers(null, 'open')).toBe(true);
    expect(canManageMembers(undefined, undefined)).toBe(false);
  });

  it("prefers the backend's reason for a refused member change", () => {
    expect(memberChangeError(refused(409, { detail: 'A project must keep at least one owner' }))).toBe(
      'A project must keep at least one owner',
    );
    expect(memberChangeError(refused(409, { detail: 'The first member of a project must be an owner' }))).toBe(
      'The first member of a project must be an owner',
    );
    expect(memberChangeError(refused(404, { detail: 'No such user' }))).toBe('No such user');
  });

  it('words a refusal that carries no reason by its status', () => {
    expect(memberChangeError(refused(403))).toBe('Only an owner of this project can change its members.');
    expect(memberChangeError(refused(409))).toBe('A project must keep at least one owner.');
    // A validation error's detail is a list: fall back, never print [object Object].
    expect(memberChangeError(refused(422, { detail: [{ msg: 'field required' }] }))).toBe('Request failed (422).');
  });
});
