// Shared animation helpers for the demo pages (loaded as a classic script, so these are globals).
// ---------- math helpers ----------
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp = (a, b, p) => a + (b - a) * p;
const prog = (t, a, b) => clamp((t - a) / (b - a));
const easeOut = p => 1 - Math.pow(1 - p, 3);
const easeOutQuint = p => 1 - Math.pow(1 - p, 5);
const easeInOut = p => p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
const easeInOutSine = p => -(Math.cos(Math.PI * p) - 1) / 2;
// damped spring 0 -> 1 with a gentle overshoot
const spring = p => p <= 0 ? 0 : p >= 1 ? 1 : 1 - Math.exp(-6.5 * p) * Math.cos(9 * p);
const bump = (t, a, b) => { const p = prog(t, a, b); return Math.sin(Math.PI * p); };
function rng(seed) { return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
  t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

const set = (e, css) => { for (const k in css) e.style[k] = css[k]; };

// Per-character timestamps for natural-looking typing.
function typingTimes(text, start, charDelay, seed) {
  const r = rng(seed), times = [];
  let t = start;
  for (const ch of text) {
    times.push(t);
    let gap = charDelay * (0.55 + r() * 0.9);
    if (ch === ',') gap += charDelay * 4;
    if (ch === ' ' && r() < 0.25) gap += charDelay * 1.5;
    t += gap;
  }
  return times;
}

// Resolves once every weight of the bundled fonts is loaded.
function fontsReady() {
  return Promise.all(['Inter', 'Montserrat', 'Source Serif 4'].flatMap(f => [400, 500, 600, 700, 800].map(w => document.fonts.load(`${w} 20px '${f}'`))))
    .then(() => document.fonts.ready);
}
