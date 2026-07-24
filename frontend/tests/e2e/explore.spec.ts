import { test, expect, type Page } from '@playwright/test';

/**
 * Exploratory "guided monkey" crawl for the soak loop. For each view it navigates,
 * then clicks a SEED-varied subset of SAFE (non-destructive) controls — tabs,
 * expandable rows, filter chips, layer toggles, graph nodes, drawers — re-checking
 * for runtime errors after each click. Destructive / externally-expensive controls
 * (delete, ingest, investigate, generate, resolve, crawl, …) are never clicked.
 *
 * Vary the run with SEED (each soak iteration passes a different one). A test fails
 * on an uncaught error, a 5xx, or a React hydration mismatch — a real bug — and
 * records the clickpath that triggered it.
 */

const HYDRATION_RE = /Minified React error #(4(1[89]|2[0-5]))|hydrat|did not match|Text content does not match/i;

// Never click these — mutating, expensive, external, or auth-exiting.
const UNSAFE_RE = /\b(delete|remove|clear|reset|log ?out|sign ?out|ingest|investigate|enrich|geolocate|generate|resolve|map ttps|re-?sync|crawl|execute|run\b|start\b|send|submit|save|create|update|merge|discard|purge|drop|embed|upload|import|export|download|pull|fetch)\b/i;

const ROUTES = ['/', '/collections', '/collection-plans', '/data-sources', '/network', '/geo',
  '/timeline', '/search', '/watchlist', '/products', '/cyber', '/llm-hub', '/admin'];

// Deterministic PRNG so a SEED reproduces a run.
function rng(seed: number) {
  let s = seed >>> 0;
  return () => { s = (s + 0x6d2b79f5) >>> 0; let t = Math.imul(s ^ (s >>> 15), 1 | s); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

type Errs = { pageErrors: string[]; serverErrors: string[]; hydration: string[] };
function instrument(page: Page): Errs {
  const e: Errs = { pageErrors: [], serverErrors: [], hydration: [] };
  page.on('pageerror', (x) => (HYDRATION_RE.test(x.message) ? e.hydration : e.pageErrors).push(x.message));
  page.on('console', (m) => { if (m.type() === 'error' && HYDRATION_RE.test(m.text())) e.hydration.push(m.text()); });
  page.on('response', (r) => { if (r.status() >= 500) e.serverErrors.push(`${r.status()} ${r.request().method()} ${r.url()}`); });
  return e;
}

const SEED = Number(process.env.SEED || 1);

test(`exploratory crawl (seed ${SEED})`, async ({ page, context }, testInfo) => {
  test.setTimeout(120_000); // a full 13-route crawl-with-clicks runs longer than a smoke test
  const rand = rng(SEED);
  const e = instrument(page);
  const trail: string[] = [];
  const navNotes: string[] = [];
  // Auto-close any popup/new tab (external links) so they don't accumulate or steal focus.
  context.on('page', (p) => { if (p !== page) p.close().catch(() => {}); });

  // A seeded subset per run keeps each iteration fast (~30-45s); variety comes from
  // the seed changing every soak iteration, so all routes get covered many times over.
  const routes = [...ROUTES].sort(() => rand() - 0.5).slice(0, 7);
  const deadline = Date.now() + 40_000; // hard per-run budget so no iteration drags
  for (const route of routes) {
    if (page.isClosed() || Date.now() > deadline) break;
    trail.push(`goto ${route}`);
    try {
      await page.goto(route, { waitUntil: 'domcontentloaded', timeout: 15_000 });
      // Cap the settle wait — polling views (StatusBar health, etc.) never reach true networkidle.
      await page.waitForLoadState('networkidle', { timeout: 2500 }).catch(() => {});
    } catch (err) {
      navNotes.push(`goto ${route} threw: ${(err as Error).message.slice(0, 80)}`);
      break;
    }
    expect(page.url(), `bounced to /login on ${route}`).not.toContain('/login');

    const candidates = page.locator(
      'button:visible, [role="tab"]:visible, [role="button"]:visible, a[href^="/"]:visible, svg circle:visible, .leaflet-interactive:visible',
    );
    const n = Math.min(await candidates.count().catch(() => 0), 40);
    const idxs = Array.from({ length: n }, (_, i) => i).sort(() => rand() - 0.5).slice(0, 3);

    for (const i of idxs) {
      if (page.isClosed() || Date.now() > deadline) break;
      const el = candidates.nth(i);
      let label = '';
      let href = '';
      try {
        const O = { timeout: 1500 };
        label = ((await el.getAttribute('aria-label', O)) || (await el.innerText(O).catch(() => '')) || '').trim().slice(0, 40);
        href = (await el.getAttribute('href', O).catch(() => '')) || '';
        if ((await el.getAttribute('target', O).catch(() => '')) === '_blank') continue; // new-tab link
      } catch { continue; }
      if (UNSAFE_RE.test(label)) continue;                       // destructive/expensive
      if (/^https?:\/\//i.test(href) || /\/login/.test(href)) continue; // external / auth-exit
      trail.push(`click «${label || '·'}» on ${route}`);
      await el.click({ timeout: 1500 }).catch(() => {});
      await page.waitForTimeout(200).catch(() => {});
      if (e.pageErrors.length || e.serverErrors.length) break;   // a real bug surfaced
      if (!page.isClosed() && !page.url().includes(route) && route !== '/') break; // navigated away; next route resets
    }
    if (e.pageErrors.length || e.serverErrors.length) break;
  }

  if (e.hydration.length) testInfo.annotations.push({ type: 'hydration', description: e.hydration.slice(0, 5).join('\n') });
  if (navNotes.length) testInfo.annotations.push({ type: 'nav-note', description: navNotes.join('\n') });
  const trailStr = trail.slice(-12).join('\n  ');
  expect(e.pageErrors, `uncaught error. clickpath:\n  ${trailStr}`).toEqual([]);
  expect(e.hydration, `hydration mismatch. clickpath:\n  ${trailStr}`).toEqual([]);
  expect(e.serverErrors, `5xx. clickpath:\n  ${trailStr}`).toEqual([]);
});
