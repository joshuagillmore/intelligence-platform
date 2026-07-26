import { test, expect } from '@playwright/test';

/**
 * Mobile-viewport regression guard.
 *
 * Several views were built as a fixed horizontal row with 288px side columns and
 * no breakpoint, so on a phone the content was squeezed to nothing. These assert
 * the page fits its viewport — the cheapest reliable signal that a layout still
 * stacks instead of forcing the body to scroll sideways.
 */

test.use({ viewport: { width: 390, height: 844 } }); // iPhone 14-ish

const ROUTES: { name: string; path: string }[] = [
  { name: 'llm-hub', path: '/llm-hub' },
  { name: 'timeline', path: '/timeline' },
  { name: 'cyber', path: '/cyber' },
  { name: 'collections', path: '/collections' },
  { name: 'products', path: '/products' },
];

for (const route of ROUTES) {
  test(`${route.name} fits the mobile viewport`, async ({ page }) => {
    await page.goto(route.path, { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle', { timeout: 3000 }).catch(() => {});

    await page.screenshot({ path: `tests/e2e/screenshots/mobile-${route.name}.png`, fullPage: true });

    // Allow 2px for sub-pixel rounding; more than that is a real overflow.
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `${route.path} overflows horizontally by ${overflow}px`).toBeLessThanOrEqual(2);
  });
}
