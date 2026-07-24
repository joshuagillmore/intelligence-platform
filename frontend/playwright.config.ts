import { defineConfig, devices } from '@playwright/test';

/**
 * E2E harness for the SENTINEL analyst UI. Runs against the docker-compose stack
 * (frontend :3000 + backend :8000 + datastores). Auth is injected as a JWT into
 * localStorage by global-setup — no login form, fully deterministic. Point at a
 * different instance with E2E_BASE_URL.
 */
const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3000';

export default defineConfig({
  testDir: './tests/e2e',
  globalSetup: './tests/e2e/global-setup.ts',
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  outputDir: 'test-results',
  use: {
    baseURL: BASE_URL,
    storageState: 'tests/e2e/.auth/state.json',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    video: 'off',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
