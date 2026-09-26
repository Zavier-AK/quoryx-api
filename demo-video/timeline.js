// Scene timing (seconds). Edit these and re-run `npm run render` —
// the animation and the sound effects both read from here.
window.TL = {
  fps: 60,
  duration: 15.4,
  prompt: "Hey Quoryx, run the month-end close and give me a report",

  // Claude-style chat
  claude: { enter: 0.15, typeStart: 0.95, charDelay: 0.034, pace: 1.0, seed: 7 },
  // Claude window slides out, ChatGPT window slides in
  transition: { start: 7.35, dur: 0.7 },
  // ChatGPT-style chat (types faster, answers faster)
  gpt: { typeStart: 8.2, charDelay: 0.018, pace: 0.5, seed: 21 },
  // Both windows shrink into a row of AI platforms around a Quoryx node
  network: { start: 12.1 },
  // End card: logo + quoryx.net
  logo: { start: 13.8 },
};
