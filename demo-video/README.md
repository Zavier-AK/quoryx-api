# Quoryx MCP demo video

A ~15s 1080p60 promo showing a user ask "Hey Quoryx, run the month-end close and give me a report" in a Claude-style chat, then a ChatGPT-style chat. Both windows then fold into a "One connection. Every AI." network and the quoryx.net end card.

The final render is `quoryx-mcp-demo.mp4`.

## How it's made
Every frame is rendered deterministically from HTML, and there are no screen recordings.

- `index.html` holds all scenes. A single `render(t)` function sets every element's state for time `t` (seconds).
- `timeline.js` holds scene timings, the prompt text and typing speed. **Edit this to retime.**
- `sfx.py` synthesizes all sound effects in code (key clicks, pops, checks, whooshes, plucks, end chime and a soft pad) from the cue list the page exports, so the audio lands on the exact frames.
- `render.mjs` uses headless Chromium to take a PNG of each frame, which ffmpeg (bundled via `ffmpeg-static`) muxes to H.264/AAC MP4.
- `assets/quoryx-mark.svg` is the logo, vector-traced from the brand JPG.
- `fonts/` bundles Inter, Montserrat and Source Serif 4 (OFL, from Google Fonts), so renders work offline.

## Re-rendering
Requirements: Node 18+, Python 3 with `numpy` and `scipy`, and a Chromium. Set `CHROME=/path/to/chrome` if it isn't at the default Playwright location.

```bash
npm install
npm run draft            # 960x540 @30fps draft in ~1 min -> out/quoryx-mcp-demo-draft.mp4
npm run render           # full 1920x1080 @60fps        -> out/quoryx-mcp-demo.mp4
npm run stills -- 2 7 13 # PNG stills at given seconds  -> out/still-<t>.png
```

You can also open `index.html?t=6.5` in a browser to preview any moment.

The chat UIs are stylized lookalikes identified by text labels only. They do not use official Claude or ChatGPT logos.
