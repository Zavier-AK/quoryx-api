// Render individual frames as PNGs for review: node stills.mjs 2 4.5 6 ...
import { chromium } from 'playwright-core';
const b = await chromium.launch({ executablePath: process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
await p.goto('file://' + new URL('index.html', import.meta.url).pathname);
await p.evaluate(() => window.ready);
await p.waitForTimeout(200);
for (const t of process.argv.slice(2)) {
  await p.evaluate(t => render(t), +t);
  await p.screenshot({ path: `out/still-${t}.png` });
}
await b.close();
