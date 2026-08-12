/**
 * Render docs/screenshots/hero.html to hero.png at exact banner size.
 *
 *   node docs/screenshots/make-hero.js
 *
 * Reuses the frontend's Playwright install rather than adding a dependency —
 * run `npm install` in frontend/ first if it complains.
 *
 * The backdrop screenshot is inlined as a data URI: a file:// subresource is
 * blocked from a setContent() document, and a silently missing image renders
 * as an empty panel that still looks like a successful hero. It is asserted
 * below for the same reason.
 */
const fs = require('fs');
const path = require('path');

const HERE = __dirname;
const REPO = path.resolve(HERE, '../..');
const { chromium } = require(path.join(REPO, 'frontend/node_modules/@playwright/test'));

// Which view forms the backdrop. The geo map is the default because a
// 2400x840 banner is 2.9:1 and an app window is portrait — any crop that
// removes the sidebar makes it *more* portrait. A world map is landscape
// already, and its connection arcs survive being darkened to a texture.
const SHOT = process.env.HERO_SHOT || path.join(HERE, 'geo-aoi.png');
const POS = process.env.HERO_POS || '46% 22%';
const OUT = process.env.HERO_OUT || path.join(HERE, 'hero.png');

const WIDTH = 2400;
const HEIGHT = 840;

(async () => {
  const html = fs
    .readFileSync(path.join(HERE, 'hero.html'), 'utf8')
    .replace('OBJ_POS', POS)
    .replace('SHOT_PATH', `data:image/png;base64,${fs.readFileSync(SHOT).toString('base64')}`);

  const browser = await chromium.launch();
  const page = await browser.newPage({
    viewport: { width: WIDTH, height: HEIGHT },
    deviceScaleFactor: 1,
  });
  await page.setContent(html, { waitUntil: 'load' });
  await page.waitForTimeout(600); // let the font fallback settle before capture

  const shot = await page.evaluate(() => {
    const img = document.querySelector('.shot img');
    return { ok: !!img && img.complete && img.naturalWidth > 0, w: img ? img.naturalWidth : 0 };
  });
  if (!shot.ok) {
    throw new Error(`backdrop did not load from ${SHOT} — refusing to write a hero with an empty panel`);
  }

  await page.screenshot({ path: OUT });
  await browser.close();
  console.log(`backdrop ${path.basename(SHOT)} (${shot.w}px) -> ${path.basename(OUT)} ` +
              `${WIDTH}x${HEIGHT}, ${(fs.statSync(OUT).size / 1024).toFixed(0)} KB`);
})();
