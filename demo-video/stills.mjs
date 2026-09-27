// Render individual frames as PNGs for review: node stills.mjs [--page experimental] 2 4.5 6 ...
import { chromium } from 'playwright-core';
const b = await chromium.launch({ executablePath: process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
const args = process.argv.slice(2);
const pi = args.indexOf('--page');
const pageName = pi >= 0 ? args.splice(pi, 2)[1] : 'index';
await p.goto('file://' + new URL(`${pageName}.html`, import.meta.url).pathname);
await p.evaluate(() => window.ready);
await p.waitForTimeout(200);
for (const t of args) {
  await p.evaluate(t => render(t), +t);
  await p.screenshot({ path: `out/${pageName === 'index' ? '' : pageName + '-'}still-${t}.png` });
}
await b.close();
