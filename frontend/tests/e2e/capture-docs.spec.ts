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

  // Two sliders decide whether this reads as a network or as a starfield:
  //
  //   Island (degree) drops nodes below a degree threshold. This project is
  //   4,858 isolated nodes out of 5,486 — mostly URLs the crawler lifted from
  //   page furniture — so at 0 the view is overwhelmingly unconnected dots.
  //
  //   Ego Highlight dims everything outside N hops of the selected entity,
  //   edges included. At 1 hop a fully connected 500-node graph renders as a
  //   handful of lit nodes in a grey field: the graph looked empty because it
  //   was faded, not because it was sparse.
  //
  // Selecting them by `max` was the original bug — it looked for max === '5'
  // and no slider has that (Confidence is 1, Ego is 4, Island's max is the
  // graph's own maximum degree). The lookup missed, returned undefined, and
  // the early return made a no-op look like a successful filter. Address them
  // by their label instead, and fail loudly if one cannot be found.
  const setSliderByLabel = async (label: string, value: number) => {
    const ok = await page.evaluate(([text, val]) => {
      const labels = Array.from(document.querySelectorAll('label'));
      const match = labels.find((l) => l.textContent?.trim().startsWith(text as string));
      const input = match?.closest('div')?.parentElement?.querySelector('input[type=range]')
        ?? match?.parentElement?.parentElement?.querySelector('input[type=range]');
      if (!(input instanceof HTMLInputElement)) return false;
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
      setter?.call(input, String(val));
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    }, [label, value] as [string, number]);
    expect(ok, `could not find the "${label}" slider — has the network control panel changed?`).toBe(true);
  };

  // Light the whole connected component rather than one hop of it, so the
  // selected entity still drives the detail panel without blacking out the graph.
  await setSliderByLabel('Ego Highlight', Number(process.env.CAPTURE_EGO_HOPS || 4));
  await setSliderByLabel('Island', Number(process.env.CAPTURE_ISLAND_DEGREE || 1));

  await page.waitForTimeout(6000); // force simulation re-settles after filtering
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
  //
  // The timeout is the point. Without it this action inherits the 45s test
  // timeout (playwright.config sets no actionTimeout), so when the text was
  // absent it consumed the entire budget and the run failed on the *next*
  // line — `waitForTimeout(800)` reported as "Target page has been closed",
  // one line after the actual cause. The trailing .catch() made the call look
  // optional while it was in fact the longest wait in the test.
  await page.getByText(/Generated Report|Saved:/i).first()
    .scrollIntoViewIfNeeded({ timeout: 5000 })
    .catch(() => {});
  await page.waitForTimeout(800);

  // Say so if there is no rendered product. This shot goes into the README, and
  // a bounded wait alone would have turned the failure into a green run that
  // silently replaced a real product with a screenshot of an empty form.
  await expect(
    page.getByText(/Generated Report|Saved:/i).first(),
    'no rendered product to capture — does seed_demo.py still create the Report node?',
  ).toBeVisible();

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

  // Open a named plan rather than whichever happens to sort first. "First" is
  // not a property of the plan worth photographing: several plans on this
  // project carry titles the refiner left as raw markdown ("PIR: (Actionable,
  // Specific, Measurable, Time-bounded)**  >"), and one of those leading is how
  // a shot of the collection story becomes a shot of a formatting bug.
  const wanted = process.env.CAPTURE_PLAN;
  const plan = wanted
    ? page.getByText(new RegExp(wanted, 'i')).first()
    : page.getByText(/PIR:/i).first();
  if (await plan.count()) await plan.click({ force: true }).catch(() => {});
  await page.waitForTimeout(2500);

  // A plan that never opened leaves the list view, which looks enough like a
  // successful capture to ship. Require the detail to be on screen.
  await expect(
    page.getByText(/Sources|Objective|Requirement/i).first(),
    `plan detail did not open${wanted ? ` for /${wanted}/i` : ''} — has the plan list changed?`,
  ).toBeVisible();

  await page.screenshot({ path: path.join(OUT, 'collection-plan.png') });
});

test('all six files exist and are non-trivial', async () => {
  for (const f of ['network-graph', 'geo-aoi', 'cyber-enrichment', 'products-intsum', 'topic-mindmap', 'collection-plan']) {
    const p = path.join(OUT, `${f}.png`);
    expect(fs.existsSync(p), `${f}.png missing`).toBe(true);
    expect(fs.statSync(p).size, `${f}.png suspiciously small`).toBeGreaterThan(20_000);
  }
});
