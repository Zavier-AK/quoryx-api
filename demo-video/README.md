# Quoryx MCP demo videos

There are two promos, both rendered from HTML with the same pipeline.

- **`quoryx-mcp-demo.mp4`** (~15s, light) shows a user ask "Hey Quoryx, run the month-end close and give me a report" in a Claude-style chat, then a ChatGPT-style chat. Both windows then fold into a "One connection. Every AI." network and the quoryx.net end card. Source: `index.html` and `timeline.js`.
- **`quoryx-mcp-experimental.mp4`** (~20s, dark and cinematic, with a moving 3D camera) runs the same prompt, then:
  1. The report card lifts out of the chat into 3D, and "3 discrepancies found" appears, with the camera focusing on each one.
  2. Quoryx asks "Should I resolve them?" and the user types "Yes".
  3. Green data streams fly out to Xero and e-conomic panels, where draft invoices drop in.
  4. Whip-pans through ChatGPT- and Cursor-style windows lead to the quoryx.net end card.

  Source: `experimental.html` and `timeline-experimental.js`.

## How it's made
Every frame is rendered deterministically from HTML, and there are no screen recordings.

- Each page has a single `render(t)` function that sets every element's state for time `t` (seconds). Shared easing, typing and font helpers live in `lib/anim.js`.
- `timeline.js` and `timeline-experimental.js` hold scene timings, prompt text and typing speed. **Edit these to retime.**
- `sfx.py` synthesizes all the audio in code from the cue list each page exports, so every sound lands on its exact frame. That covers the UI sound effects and the music:
  - `groove`: a 116 BPM electric-piano track for the light video.
  - `cinematic`: a 96 BPM track that goes from A minor to C major, steps back while the discrepancies are shown and builds after "Yes".

  Each track's final chord lands on the logo.
- `render.mjs` uses headless Chromium to take a PNG of each frame, which ffmpeg (bundled via `ffmpeg-static`) muxes to H.264/AAC MP4.
- `assets/quoryx-mark.svg` is the logo, vector-traced from the brand JPG.
- `fonts/` bundles Inter, Montserrat and Source Serif 4 (OFL, from Google Fonts), so renders work offline.

## Re-rendering
Requirements: Node 18+, Python 3 with `numpy` and `scipy`, and a Chromium. Set `CHROME=/path/to/chrome` if it isn't at the default Playwright location.

```bash
npm install
npm run draft                  # 960x540 @30fps draft          -> out/quoryx-mcp-demo-draft.mp4
npm run render                 # full 1920x1080 @60fps         -> out/quoryx-mcp-demo.mp4
npm run draft:experimental     # experimental video, draft     -> out/quoryx-mcp-experimental-draft.mp4
npm run render:experimental    # experimental video, full      -> out/quoryx-mcp-experimental.mp4
npm run stills -- 2 7 13       # PNG stills at given seconds   -> out/still-<t>.png
npm run stills -- --page experimental 8 13   #                -> out/experimental-still-<t>.png
```

You can also open `index.html?t=6.5` or `experimental.html?t=9` in a browser to preview any moment.

The chat UIs and the Xero / e-conomic panels are stylized lookalikes identified by text labels only. They do not use official logos.
