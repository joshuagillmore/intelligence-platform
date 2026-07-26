import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';

/**
 * Captures the six screenshots the root README links from docs/screenshots/.
 *
 * Not part of the normal suite — run deliberately when the docs images need
 * refreshing, against a stack with representative data:
 *
 *   CAPTURE_PROJECT_ID=<uuid> npx playwright test capture-docs.spec.ts
 *
 * Each shot performs the interaction the docs/screenshots/README.md checklist
 * asks for (select an entity, expand an enrichment panel, ...) rather than
 * grabbing an empty view.
 */

const OUT = path.resolve(__dirname, '../../../docs/screenshots');
const PROJECT_ID = process.env.CAPTURE_PROJECT_ID || '';

test.use({ viewport: { width: 1600, height: 1000 } });

test.beforeAll(() => fs.mkdirSync(OUT, { recursive: true }));

// Point the app at the project that has the richest data before each capture.
test.beforeEach(async ({ page }) => {
  if (!PROJECT_ID) return;
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.evaluate(async (id) => {
    const token = localStorage.getItem('auth_token');
    const res = await fetch(`/api/projects/${id}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (res.ok) localStorage.setItem('activeProject', JSON.stringify(await res.json()));
  }, PROJECT_ID);
});

const settle = async (page: import('@playwright/test').Page, ms = 3500) => {
  await page.waitForLoadState('networkidle', { timeout: ms }).catch(() => {});
  await page.waitForTimeout(1200);
};

test('network-graph', async ({ page }) => {
  // Deep-link to a meaningful entity rather than clicking whatever node happens
  // to be first — an unfocused 500-node crawl graph reads as noise, and the ego
  // highlight is what makes this look like analysis.
  const focus = process.env.CAPTURE_FOCUS_ENTITY;
  await page.goto(focus ? `/network?select=${focus}` : '/network', { waitUntil: 'domcontentloaded' });
  await settle(page, 8000);
  await page.waitForTimeout(3000);

  // Raise the island/degree filter so the crawled single-link URL leaves drop
  // out and the connected analytic core is legible. React owns the input, so
  // set through the native setter and fire a real input event.
  const island = Number(process.env.CAPTURE_ISLAND_DEGREE || 2);
  await page.evaluate((deg) => {
    const ranges = Array.from(document.querySelectorAll('input[type=range]')) as HTMLInputElement[];
    const el = ranges.find((r) => r.max === '5');
    if (!el) return;
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
    setter?.call(el, String(deg));
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }, island);

  await page.waitForTimeout(5000); // force simulation re-settles after filtering
  await page.screenshot({ path: path.join(OUT, 'network-graph.png') });
});

test('geo-aoi', async ({ page }) => {
  await page.goto('/geo', { waitUntil: 'domcontentloaded' });
  await settle(page, 8000);
  await page.waitForTimeout(3000);

  // Run the area-of-interest query over the visible extent.
  await page.getByRole('button', { name: /query visible area/i }).click({ timeout: 3000 }).catch(() => {});
  await page.waitForTimeout(2000);

  // Click an actual location marker, not a connection polyline — both carry
  // .leaflet-interactive, so pick the smallest element (a circle marker) to get
  // the entity profile rather than a relationship popup.
  const handle = await page.evaluateHandle(() => {
    const els = Array.from(document.querySelectorAll('.leaflet-interactive')) as SVGElement[];
    let best: SVGElement | null = null;
    let bestArea = Infinity;
    for (const el of els) {
      const r = el.getBoundingClientRect();
      const area = r.width * r.height;
      if (area > 4 && area < bestArea) { bestArea = area; best = el; }
    }
    return best;
  });
  const marker = handle.asElement();
  if (marker) await marker.click({ force: true }).catch(() => {});
  await page.waitForTimeout(2500);
  await page.screenshot({ path: path.join(OUT, 'geo-aoi.png') });
});

test('cyber-enrichment', async ({ page }) => {
  await page.goto('/cyber', { waitUntil: 'domcontentloaded' });
  await settle(page);
  // Expand a specific, already-enriched observable so the EnrichmentPanel shows
  // real provider results rather than "no enrichment yet".
  const target = process.env.CAPTURE_IOC || '';
  const row = target
    ? page.locator('tbody tr').filter({ hasText: target }).first()
    : page.locator('tbody tr').first();
  if (await row.count()) await row.click({ force: true }).catch(() => {});
  await page.waitForTimeout(1500);

  // Run the investigation the way an analyst would, so the panel shows real
  // WHOIS / DNS / GeoIP / ASN results instead of its empty prompt.
  await page.getByRole('button', { name: /^investigate$/i }).first().click({ timeout: 4000 }).catch(() => {});
  await page.waitForTimeout(9000); // external keyless providers

  await page.screenshot({ path: path.join(OUT, 'cyber-enrichment.png') });
});

test('products-intsum', async ({ page }) => {
  await page.goto('/products', { waitUntil: 'domcontentloaded' });
  await settle(page);
  // Open the SAVED report, not the report-type card of the same name — the point
  // of this shot is the rendered product with its evidence, not an empty form.
  const savedPanel = page.locator('div').filter({ hasText: /^SAVED REPORTS/ }).last();
  const saved = savedPanel.getByText(/INTSUM/i).last();
  if (await saved.count()) {
    await saved.click({ force: true }).catch(() => {});
  } else {
    await page.getByText(/INTSUM/i).last().click({ force: true }).catch(() => {});
  }
  await page.waitForTimeout(3000);
  // Scroll the rendered product into view so the body, not the generator, leads.
  await page.getByText(/Generated Report|Saved:/i).first().scrollIntoViewIfNeeded().catch(() => {});
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT, 'products-intsum.png') });
});

test('topic-mindmap', async ({ page }) => {
  await page.goto('/data-sources', { waitUntil: 'domcontentloaded' });
  await settle(page, 8000);
  await page.waitForTimeout(4000);
  await page.screenshot({ path: path.join(OUT, 'topic-mindmap.png') });
});

test('collection-plan', async ({ page }) => {
  await page.goto('/collection-plans', { waitUntil: 'domcontentloaded' });
  await settle(page);
  // Open the PIR-derived plan to show objective → sources → run status.
  const plan = page.getByText(/PIR:/i).first();
  if (await plan.count()) await plan.click({ force: true }).catch(() => {});
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(OUT, 'collection-plan.png') });
});

test('all six files exist and are non-trivial', async () => {
  for (const f of ['network-graph', 'geo-aoi', 'cyber-enrichment', 'products-intsum', 'topic-mindmap', 'collection-plan']) {
    const p = path.join(OUT, `${f}.png`);
    expect(fs.existsSync(p), `${f}.png missing`).toBe(true);
    expect(fs.statSync(p).size, `${f}.png suspiciously small`).toBeGreaterThan(20_000);
  }
});
