import { request, type FullConfig } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'fs';
import { dirname } from 'path';

/**
 * Log in ONCE through the API with the dev admin credentials (a non-secret
 * placeholder; override with E2E_ADMIN_* in real environments) and persist the
 * resulting `sentinel_session` cookie in `storageState`, exactly as a browser
 * that signed in through the form would hold it. Every test then starts
 * already authenticated, with no login-form typing. Nothing token-shaped goes
 * into localStorage: the app no longer reads one.
 */
const AUTH_FILE = 'tests/e2e/.auth/state.json';

async function globalSetup(_config: FullConfig) {
  const baseURL = process.env.E2E_BASE_URL || 'http://localhost:3000';
  const username = process.env.E2E_ADMIN_USER || 'admin';
  const password = process.env.E2E_ADMIN_PASSWORD || 'admin';

  // Every request the app makes carries this; state-changing ones need it.
  const ctx = await request.newContext({ baseURL, extraHTTPHeaders: { 'X-Requested-With': 'sentinel' } });
  const res = await ctx.post('/api/auth/login', { data: { username, password } });
  if (!res.ok()) {
    throw new Error(
      `E2E auth setup: login failed (${res.status()}) at ${baseURL}/api/auth/login. ` +
        `Is the stack up? Set E2E_ADMIN_PASSWORD if the admin password is non-default.`,
    );
  }
  // The cookie jar now holds the session; prove it before every test relies on it.
  const me = await ctx.get('/api/auth/me');
  if (!me.ok()) {
    throw new Error(
      `E2E auth setup: login succeeded but /api/auth/me answered ${me.status()}. ` +
        'The session cookie was not kept (a Secure cookie over plain http?).',
    );
  }
  const { username: user, role } = await me.json();

  // The identity cache the UI reads before its own /me call answers, and the
  // deterministic demo project if it has been seeded (see
  // backend/scripts/seed_demo.py) so data-backed views render their content.
  // Graceful when unseeded: views just show empty states and smoke still passes.
  const localStorage: { name: string; value: string }[] = [
    { name: 'auth_user', value: user ?? username },
    { name: 'auth_role', value: role ?? 'admin' },
  ];
  const proj = await ctx.get('/api/projects/demo-sentinel');
  if (proj.ok()) {
    localStorage.push({ name: 'activeProject', value: JSON.stringify(await proj.json()) });
  }

  const { cookies } = await ctx.storageState();
  await ctx.dispose();
  if (!cookies.length) throw new Error('E2E auth setup: the login response set no cookie.');

  mkdirSync(dirname(AUTH_FILE), { recursive: true });
  writeFileSync(AUTH_FILE, JSON.stringify({ cookies, origins: [{ origin: baseURL, localStorage }] }, null, 2));
}

export default globalSetup;
