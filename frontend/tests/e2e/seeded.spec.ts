import { test, expect } from '@playwright/test';

/**
 * Data-backed assertions against the deterministic demo project
 * (backend/scripts/seed_demo.py). global-setup selects "demo-sentinel" as the
 * active project when it's seeded, so these views render its content. Run the
 * seed first: `cd backend && uv run python scripts/seed_demo.py`.
 */
test.describe('seeded demo project', () => {
  test('cyber IOC dashboard lists a seeded indicator', async ({ page }) => {
    await page.goto('/cyber', { waitUntil: 'domcontentloaded' });
    await expect(page.getByText('45.83.12.7').first()).toBeVisible({ timeout: 15_000 });
  });

  test('network graph renders nodes', async ({ page }) => {
    await page.goto('/network', { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle').catch(() => {});
    await expect(page.locator('svg circle').first()).toBeVisible({ timeout: 20_000 });
  });

  test('geo map mounts with markers', async ({ page }) => {
    await page.goto('/geo', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.leaflet-container')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('.leaflet-interactive').first()).toBeVisible({ timeout: 15_000 });
  });

  test('project dashboard renders for the demo project id', async ({ page }) => {
    await page.goto('/project/demo-sentinel', { waitUntil: 'domcontentloaded' });
    await expect(page).not.toHaveURL(/\/login/);
    await expect(page.getByText('SENTINEL Demo').first()).toBeVisible({ timeout: 15_000 });
  });
});
