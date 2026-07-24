import { request, type FullConfig } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'fs';
import { dirname } from 'path';

/**
 * Log in ONCE with the dev admin credentials (a non-secret placeholder; override
 * with E2E_ADMIN_* in real environments) and persist the JWT as the same
 * localStorage keys the app uses (auth_token / auth_user / auth_role). Every test
 * then starts already authenticated via `storageState` — no login-form typing.
 */
const AUTH_FILE = 'tests/e2e/.auth/state.json';

async function globalSetup(_config: FullConfig) {
  const baseURL = process.env.E2E_BASE_URL || 'http://localhost:3000';
  const username = process.env.E2E_ADMIN_USER || 'admin';
  const password = process.env.E2E_ADMIN_PASSWORD || 'admin';

  const ctx = await request.newContext({ baseURL });
  const res = await ctx.post('/api/auth/login', { data: { username, password } });
  if (!res.ok()) {
    throw new Error(
      `E2E auth setup: login failed (${res.status()}) at ${baseURL}/api/auth/login. ` +
        `Is the stack up? Set E2E_ADMIN_PASSWORD if the admin password is non-default.`,
    );
  }
  const { access_token, username: user, role } = await res.json();

  // Select the deterministic demo project if it's been seeded (see
  // backend/scripts/seed_demo.py) so data-backed views render their content.
  // Graceful when unseeded — views just show empty states and smoke still passes.
  const localStorage: { name: string; value: string }[] = [
    { name: 'auth_token', value: access_token },
    { name: 'auth_user', value: user ?? username },
    { name: 'auth_role', value: role ?? 'admin' },
  ];
  const proj = await ctx.get('/api/projects/demo-sentinel', {
    headers: { Authorization: `Bearer ${access_token}` },
  });
  if (proj.ok()) {
    localStorage.push({ name: 'activeProject', value: JSON.stringify(await proj.json()) });
  }
  await ctx.dispose();

  const storageState = {
    cookies: [],
    origins: [{ origin: baseURL, localStorage }],
  };
  mkdirSync(dirname(AUTH_FILE), { recursive: true });
  writeFileSync(AUTH_FILE, JSON.stringify(storageState, null, 2));
}

export default globalSetup;
