// Renders index.html frame-by-frame to out/quoryx-mcp-demo.mp4 with synced sound.
// Usage: npm run render            (full 1080p60 video)
//        npm run render -- --fast  (540p30 draft for quick timing checks)
import { chromium } from 'playwright-core';
import { spawn, execFileSync } from 'node:child_process';
import { writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import ffmpeg from 'ffmpeg-static';

const here = p => fileURLToPath(new URL(p, import.meta.url));
const fast = process.argv.includes('--fast');
mkdirSync(here('out'), { recursive: true });

const browser = await chromium.launch({ executablePath: process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: fast ? 0.5 : 1 });
await page.goto('file://' + here('index.html'));
await page.evaluate(() => window.ready);

const { fps: baseFps, duration, cues } = await page.evaluate(() => ({ fps: TL.fps, duration: TL.duration, cues: getCues() }));
const fps = fast ? 30 : baseFps;
writeFileSync(here('out/cues.json'), JSON.stringify({ duration, cues }, null, 1));
execFileSync('python3', [here('sfx.py'), here('out/cues.json'), here('out/sfx.wav')], { stdio: 'inherit' });

const out = here(fast ? 'out/quoryx-mcp-demo-draft.mp4' : 'out/quoryx-mcp-demo.mp4');
const enc = spawn(ffmpeg, ['-y', '-loglevel', 'error',
  '-f', 'image2pipe', '-framerate', String(fps), '-i', '-',
  '-i', here('out/sfx.wav'),
  '-c:v', 'libx264', '-preset', fast ? 'veryfast' : 'slow', '-crf', fast ? '23' : '16', '-pix_fmt', 'yuv420p',
  '-c:a', 'aac', '-b:a', '256k', '-shortest', '-movflags', '+faststart', out], { stdio: ['pipe', 'inherit', 'inherit'] });

const frames = Math.round(duration * fps);
const t0 = Date.now();
for (let i = 0; i < frames; i++) {
  await page.evaluate(t => render(t), i / fps);
  const buf = await page.screenshot({ type: 'png' });
  if (!enc.stdin.write(buf)) await new Promise(r => enc.stdin.once('drain', r));
  if (i % 60 === 0) process.stdout.write(`\rframe ${i}/${frames}  (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
}
enc.stdin.end();
await new Promise((res, rej) => enc.on('close', c => c === 0 ? res() : rej(new Error('ffmpeg exited ' + c))));
await browser.close();
console.log(`\nwrote ${out}`);
