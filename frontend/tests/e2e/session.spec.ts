import { test, expect } from '@playwright/test';

/**
 * The cookie session (httpOnly `sentinel_session`) and its CSRF guard.
 *
 * A cookie rides along on any request the browser makes to the site, including
 * a form another site posts. The backend therefore refuses a
 * cookie-authenticated state-changing request that lacks
 * `X-Requested-With: sentinel`, which a cross-site page cannot add.
 */
const USER = process.env.E2E_ADMIN_USER || 'admin';
const PASSWORD = process.env.E2E_ADMIN_PASSWORD || 'admin';
const CSRF = { 'X-Requested-With': 'sentinel' };

test.describe('cookie session', () => {
  test('a state-changing request without the custom header is refused', async ({ page }) => {
    // page.request shares the browser context's cookie jar (the storageState
    // session) and sends no custom header unless told to.
    const bare = await page.request.post('/api/projects', { data: {} });
    expect(bare.status(), 'cookie-only POST must be refused').toBe(403);

    // With the header the same request reaches validation (422: the empty body
    // creates nothing), proving the 403 above was the CSRF guard, not auth.
    const withHeader = await page.request.post('/api/projects', { data: {}, headers: CSRF });
    expect(withHeader.status()).toBe(422);
  });

  test('reads still work with the cookie alone', async ({ page }) => {
    const me = await page.request.get('/api/auth/me');
    expect(me.status()).toBe(200);
    expect(await me.json()).toMatchObject({ username: expect.any(String), role: expect.any(String) });
  });
});

test.describe('sign-in form', () => {
  // A fresh, signed-out browser: no storageState session.
  test.use({ storageState: { cookies: [], origins: [] } });

  test('signs in with an httpOnly cookie, stores no token, and signs out', async ({ page, context }) => {
    await page.goto('/login', { waitUntil: 'domcontentloaded' });
    await page.getByPlaceholder('Enter username').fill(USER);
    await page.getByPlaceholder('Enter password').fill(PASSWORD);
    await page.getByRole('button', { name: 'Sign In' }).click();
    await expect(page).toHaveURL((url) => url.pathname === '/', { timeout: 15_000 });

    const session = (await context.cookies()).find((c) => c.name === 'sentinel_session');
    expect(session, 'login must set the session cookie').toBeTruthy();
    expect(session?.httpOnly, 'script must not be able to read the session').toBe(true);
    expect(session?.sameSite).toBe('Lax');

    const stored = await page.evaluate(() => ({
      token: localStorage.getItem('auth_token'),
      user: localStorage.getItem('auth_user'),
    }));
    expect(stored.token, 'no bearer token in storage').toBeNull();
    expect(stored.user).toBe(USER);

    const out = await page.request.post('/api/auth/logout', { headers: CSRF });
    expect(out.ok()).toBe(true);
    expect((await page.request.get('/api/auth/me')).status()).toBe(401);
  });
});
