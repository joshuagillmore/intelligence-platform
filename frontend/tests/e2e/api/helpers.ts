import { expect, request, type APIRequestContext, type APIResponse } from '@playwright/test';

/**
 * Shared plumbing for the API-level specs in this folder. They drive the
 * backend through the same origin the UI uses (the Next server rewrites /api
 * and /health to it), each caller in its own request context with its own
 * cookie jar, so an analyst's session never leaks into the admin's.
 *
 * Nothing here needs a model: the CI stack has no provider key, and where a
 * flow would need one the specs assert the honest failure shape instead.
 */
export const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3000';

// The CSRF guard refuses a cookie-authenticated state-changing request without
// it; the UI sends it on every request, and so do these contexts.
export const CSRF = { 'X-Requested-With': 'sentinel' };

export const ADMIN_USER = process.env.E2E_ADMIN_USER || 'admin';
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD || 'admin';

/** A short id unique to this run, for names that must not collide with earlier runs. */
export function runId(): string {
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
}

/**
 * A request context with no session at all. The empty storageState matters:
 * inside a test run, `request.newContext()` inherits the config's `use` options,
 * whose storageState is the admin session global-setup saved.
 */
export async function anonymous(): Promise<APIRequestContext> {
  return request.newContext({ baseURL: BASE_URL, extraHTTPHeaders: CSRF, storageState: { cookies: [], origins: [] } });
}

/** Sign in through the login route; the context then holds that user's session cookie. */
export async function signIn(username: string, password: string): Promise<APIRequestContext> {
  const ctx = await anonymous();
  const res = await ctx.post('/api/auth/login', { data: { username, password } });
  if (!res.ok()) {
    await ctx.dispose();
    throw new Error(`login as ${username} failed: ${res.status()} ${await res.text()}`);
  }
  // Prove the session is this user's before any spec relies on it.
  const me = await (await ctx.get('/api/auth/me')).json();
  if (me?.username !== username) {
    await ctx.dispose();
    throw new Error(`signed in as ${username} but the session belongs to ${JSON.stringify(me)}`);
  }
  return ctx;
}

export function signInAdmin(): Promise<APIRequestContext> {
  return signIn(ADMIN_USER, ADMIN_PASSWORD);
}

export interface Analyst {
  username: string;
  ctx: APIRequestContext;
}

/** Register a new analyst through the admin API, with a per-run name, and sign them in. */
export async function newAnalyst(admin: APIRequestContext, label: string): Promise<Analyst> {
  const username = `e2e-${label}-${runId()}`;
  const password = `pw-${runId()}-${runId()}`;
  const res = await admin.post('/api/auth/register', { data: { username, password, role: 'analyst' } });
  expect(res.status(), await res.text()).toBe(200);
  return { username, ctx: await signIn(username, password) };
}

/** Assert the status (with the body in the failure message) and parse the JSON body. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function json<T = any>(res: APIResponse, status = 200): Promise<T> {
  expect(res.status(), `${res.url()} answered ${res.status()}: ${await res.text()}`).toBe(status);
  return (await res.json()) as T;
}

/** The `detail` of an error response. */
export async function detail(res: APIResponse): Promise<string> {
  const body = await res.json().catch(() => ({}));
  return typeof body?.detail === 'string' ? body.detail : JSON.stringify(body?.detail ?? body);
}

/** Create a project as `ctx` with a per-run name; returns its id. */
export async function createProject(ctx: APIRequestContext, label: string): Promise<string> {
  const project = await json(await ctx.post('/api/projects', { data: { name: `e2e ${label} ${runId()}` } }));
  expect(project.id).toBeTruthy();
  return project.id as string;
}

/** Best-effort cleanup: delete each project (as an admin) and dispose every context. */
export async function cleanUp(
  admin: APIRequestContext | undefined,
  projectIds: (string | undefined)[],
  contexts: (APIRequestContext | undefined)[],
): Promise<void> {
  if (admin) {
    for (const id of projectIds) {
      if (id) await admin.delete(`/api/projects/${id}`).catch(() => undefined);
    }
  }
  await Promise.all(contexts.map((c) => c?.dispose().catch(() => undefined)));
}
