import { test } from '@playwright/test';
import fs from 'fs';
import path from 'path';

/**
 * Generates the evidence-chain design-system card FROM THE RUNNING APP.
 *
 * The other cards in docs/design-system are hand-authored against the real
 * tokens; this one goes further — it renders the live EvidenceChain component
 * with real relationship data pulled from the API, then captures the resulting
 * markup. The card therefore cannot describe a component that no longer exists,
 * or values the app does not actually produce.
 *
 *   CAPTURE_PROJECT_ID=<uuid> CAPTURE_ENTITY=<id> \
 *     npx playwright test generate-ds-card.spec.ts
 */

const OUT = path.resolve(__dirname, '../../../docs/design-system/components/evidence-chain.html');
const PROJECT_ID = process.env.CAPTURE_PROJECT_ID || '';
const ENTITY_ID = process.env.CAPTURE_ENTITY || '';

test('derive the evidence-chain card from the live component', async ({ page }) => {
  test.skip(!PROJECT_ID || !ENTITY_ID, 'needs CAPTURE_PROJECT_ID and CAPTURE_ENTITY');

  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.evaluate(async (id) => {
    const token = localStorage.getItem('auth_token');
    const res = await fetch(`/api/projects/${id}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (res.ok) localStorage.setItem('activeProject', JSON.stringify(await res.json()));
  }, PROJECT_ID);

  // Pull the real relationship the card will document.
  const rel = await page.evaluate(async (eid) => {
    const token = localStorage.getItem('auth_token');
    const res = await fetch(`/api/entities/${eid}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) return null;
    const data = await res.json();
    const rels = data.relationships || [];
    // Prefer one that actually carries evidence — that is the point of the card.
    return rels.find((r: { evidence?: string }) => r.evidence) || rels[0] || null;
  }, ENTITY_ID);

  if (!rel) throw new Error('No relationship found to derive the card from');

  // Render the component in the app's own styling context, then lift its markup.
  await page.goto(`/network?select=${ENTITY_ID}`, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(3500);
  await page.getByRole('button', { name: /Show Evidence/i }).first().click({ timeout: 8000 });
  await page.waitForTimeout(1200);

  const markup = await page.evaluate(() => {
    // The chain is the block containing the "Claim" eyebrow.
    const eyebrows = Array.from(document.querySelectorAll('div'));
    const claim = eyebrows.find(d => d.textContent?.trim() === 'Claim');
    const root = claim?.closest('div.rounded-lg');
    return root ? root.outerHTML : '';
  });

  if (!markup) throw new Error('Could not locate the rendered EvidenceChain');

  const rendered = new Date().toISOString().slice(0, 10);
  const card = `<!-- @dsCard group="Components" -->
<!--
  GENERATED — do not hand-edit.
  Produced by frontend/tests/e2e/generate-ds-card.spec.ts, which renders the live
  EvidenceChain component against real API data and lifts the resulting markup.
  Regenerate after changing the component so this card cannot drift from it.
  Derived ${rendered} from relationship ${rel.rel_type} on entity ${ENTITY_ID}.
-->
<style>
  .ds { background:#0f1219; color:#e6ecf7; font-family:Inter,"SF Pro Display",system-ui,sans-serif;
        padding:28px; margin:0; }
  .ds h1 { font-size:15px; letter-spacing:.18em; text-transform:uppercase; color:#adc6ff;
           margin:0 0 4px; font-weight:800; }
  .ds .sub { font-size:12.5px; color:#8a95ab; margin:0 0 20px; max-width:66ch; }
  .ds .live { display:inline-block; font-size:9.5px; letter-spacing:.12em; text-transform:uppercase;
              font-weight:800; color:#4ade80; border:1px solid rgba(34,197,94,.4);
              background:rgba(20,83,45,.2); padding:2px 8px; border-radius:4px; margin-bottom:14px; }
  .ds .note { font-size:11.5px; color:#67748f; margin-top:18px; font-style:italic; max-width:66ch; }
  /* Minimal shims for the app utility classes used inside the lifted markup. */
  .rounded-lg { border-radius:9px } .border { border-width:1px; border-style:solid }
  .border-navy-600 { border-color:#313849 } .bg-navy-800 { background:#1a1f2e }
  .border-navy-700 { border-color:#252b3d } .bg-navy-700 { background:#252b3d }
  .overflow-hidden { overflow:hidden } .px-4 { padding-left:16px; padding-right:16px }
  .py-3 { padding-top:12px; padding-bottom:12px } .border-b { border-bottom-width:1px; border-bottom-style:solid }
  .mb-1 { margin-bottom:4px } .mb-1\\.5 { margin-bottom:6px } .mt-3 { margin-top:12px }
  .flex { display:flex } .items-center { align-items:center } .items-baseline { align-items:baseline }
  .flex-wrap { flex-wrap:wrap } .gap-2 { gap:8px } .gap-x-5 { column-gap:20px } .gap-y-2 { row-gap:8px }
  .font-mono { font-family:"JetBrains Mono","Fira Code",monospace }
  .font-medium { font-weight:500 } .font-semibold { font-weight:600 } .font-bold { font-weight:700 }
  .text-sm { font-size:13px } .text-xs { font-size:11.5px }
  .text-gray-100 { color:#f3f4f6 } .text-gray-200 { color:#e5e7eb } .text-gray-300 { color:#d1d5db }
  .text-gray-400 { color:#9ca3af } .text-gray-500 { color:#6b7280 }
  .text-accent-periwinkle { color:#adc6ff } .italic { font-style:italic }
  .uppercase { text-transform:uppercase } .tracking-wide { letter-spacing:.025em }
  .leading-relaxed { line-height:1.625 } .tabular-nums { font-variant-numeric:tabular-nums }
  .pl-3 { padding-left:12px } .border-l-2 { border-left-width:2px; border-left-style:solid }
  .border-accent-periwinkle\\/40 { border-color:rgba(173,198,255,.4) }
  blockquote { margin:0 }
  mark { background:rgba(168,85,247,.3); color:#e9d5ff; padding:0 2px; border-radius:2px }
  .truncate { overflow:hidden; text-overflow:ellipsis; white-space:nowrap }
  button { background:none; border:0; color:inherit; font:inherit; cursor:pointer; padding:0 }
</style>
<div class="ds">
  <h1>Evidence chain</h1>
  <span class="live">Generated from the live component</span>
  <p class="sub">The provenance behind a single graph claim: what was asserted, how sure the system
    is, how many sources agree, how the source is graded, and the verbatim sentence it came from.
    This is the differentiator — every claim in the product can be walked back to its origin.</p>

  ${markup}

  <p class="note">It renders only what the data contains. An ungraded source reads
    <em>Ungraded</em> rather than being given a flattering default; a single-source claim is never
    dressed up as corroborated; and a conflict between sources is the one state coloured to
    interrupt. A claim whose extraction captured no sentence says so, instead of showing an empty
    quotation.</p>
</div>
`;

  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, card, 'utf8');
  console.log(`GENERATED ${OUT} (${card.length} bytes) from ${rel.rel_type}`);
});
