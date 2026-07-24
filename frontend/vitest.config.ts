import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'node:path';

/**
 * Vitest unit/component test layer for the SENTINEL analyst UI. This is the
 * component-test complement to the Playwright E2E harness in `tests/e2e/` —
 * `test.include` is scoped to `tests/unit/**` so Vitest never tries to run the
 * Playwright specs (which import `@playwright/test`).
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    // Mirror the tsconfig `@/*` -> `./src/*` path alias so imports resolve here.
    alias: { '@': path.resolve(__dirname, './src') },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/unit/setup.ts'],
    include: ['tests/unit/**/*.test.{ts,tsx}'],
  },
});
