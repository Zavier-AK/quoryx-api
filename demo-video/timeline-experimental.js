// Scene timing (seconds) for experimental.html. Edit and re-run
// `npm run render -- --page experimental`; animation and sound both read from here.
window.TL = {
  fps: 60,
  duration: 20.2,
  music: 'cinematic',
  prompt: "Hey Quoryx, run the month-end close and give me a report",
  reply: "Running the month-end close with Quoryx.",
  question: "I found 3 discrepancies. Should I resolve them?",
  answer: "Yes",

  intro: { line: 0.1, window: 0.55 },
  type: { start: 1.35, charDelay: 0.03, seed: 7 },
  lift: 6.35,          // report card lifts out of the chat into 3D
  discrepancies: 7.3,  // "3 discrepancies found" + rows
  focus: [7.85, 8.6, 9.35], // rack focus on each discrepancy row
  flyBack: 10.3,       // card returns to the chat
  ask: 10.85,          // Quoryx asks to resolve
  yes: { start: 11.55, charDelay: 0.09, seed: 3 },
  resolve: 12.35,      // camera pulls back, Xero + e-conomic panels arrive
  flash: 15.65,        // whip-pans through other AI clients
  logo: 17.55,
};
