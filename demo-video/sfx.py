"""Synthesize the demo's sound design from the cue list exported by the page.

Usage: python3 sfx.py out/cues.json out/sfx.wav
Every sound is generated in code (no samples), so the mix is reproducible and
each effect lands on the exact frame its animation starts.
"""
import json
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

SR = 48000
rng = np.random.default_rng(42)


def t_axis(dur):
    return np.arange(int(dur * SR)) / SR


def env(n, attack=0.002, decay=0.1):
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-t / decay)


def band(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], btype="band", fs=SR, output="sos"), x)


def lowpass(x, f, order=2):
    return sosfilt(butter(order, f, btype="low", fs=SR, output="sos"), x)


def sweep(f0, f1, dur, curve=1.0):
    t = t_axis(dur)
    f = f0 + (f1 - f0) * (t / dur) ** curve
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


# ---------- individual sounds (mono) ----------

def key(space=False):
    n = int(0.045 * SR)
    noise = rng.standard_normal(n)
    lo, hi = (800, 2200) if space else (1800, 4800)
    lo *= rng.uniform(0.85, 1.15)
    hi *= rng.uniform(0.85, 1.15)
    click = band(noise, lo, hi) * env(n, 0.0005, 0.006)
    thump = np.sin(2 * np.pi * rng.uniform(150, 210) * t_axis(0.045)) * env(n, 0.001, 0.01) * 0.4
    return (click * 0.8 + thump) * rng.uniform(0.04, 0.065) * (1.2 if space else 1)


def pop(f0=420, f1=900, dur=0.09, gain=0.35):
    s = sweep(f0, f1, dur, 0.5) * env(int(dur * SR), 0.002, dur / 3)
    return s * gain


def send():
    s = sweep(700, 320, 0.08) * env(int(0.08 * SR), 0.001, 0.025) * 0.35
    return s + np.pad(key() * 1.5, (0, len(s) - int(0.045 * SR)))


def swoosh(dur=0.32, lo=500, hi=3500, gain=0.12):
    n = int(dur * SR)
    noise = rng.standard_normal(n)
    out = np.zeros(n)
    # sweep a band-pass across the noise in short chunks
    chunks = 24
    for i in range(chunks):
        a, b = i * n // chunks, (i + 1) * n // chunks
        f = lo * (hi / lo) ** (i / chunks)
        out[a:b] = band(noise, f * 0.7, min(f * 1.4, SR / 2 - 100))[a:b]
    shape = np.sin(np.pi * np.linspace(0, 1, n)) ** 1.6
    return out * shape * gain


def check(i):
    f = 880 * [1.0, 1.2599, 1.4983][i % 3]  # rising major triad
    t = t_axis(0.35)
    n = len(t)
    tone = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t) + 0.12 * np.sin(2 * np.pi * 3 * f * t))
    return tone * env(n, 0.002, 0.07) * 0.16


def card():
    t = t_axis(0.45)
    n = len(t)
    body = sweep(170, 95, 0.45) * env(n, 0.004, 0.1) * 0.22
    shimmer = (np.sin(2 * np.pi * 1318.5 * t) + np.sin(2 * np.pi * 1760 * t)) * env(n, 0.003, 0.09) * 0.06
    return body + shimmer + swoosh(0.45, 300, 1600, 0.06)


def tick(i):
    t = t_axis(0.08)
    f = 2093 * (1 + 0.06 * i)
    return np.sin(2 * np.pi * f * t) * env(len(t), 0.001, 0.018) * 0.07


def pluck(freq, dur=0.9, gain=0.22):
    # Karplus-Strong string
    n = int(dur * SR)
    period = int(SR / freq)
    buf = rng.uniform(-1, 1, period)
    out = np.zeros(n)
    for i in range(n):
        out[i] = buf[i % period]
        buf[i % period] = 0.5 * (buf[i % period] + buf[(i + 1) % period]) * 0.996
    return lowpass(out, 5000) * gain * env(n, 0.001, 0.45)


def bell(freqs, dur=2.8, gain=0.12, decay=0.9):
    t = t_axis(dur)
    n = len(t)
    out = np.zeros(n)
    for j, f in enumerate(freqs):
        for ratio, amp, dk in [(1, 1.0, 1.0), (2.0, 0.35, 0.6), (2.76, 0.18, 0.4), (5.4, 0.06, 0.2)]:
            out += amp * np.sin(2 * np.pi * f * ratio * t + j) * env(n, 0.004, decay * dk)
    return out / len(freqs) * gain


def riser(dur=0.9):
    t = t_axis(dur)
    n = len(t)
    noise = swoosh(dur, 400, 6000, 0.05)
    tone = sweep(220, 660, dur, 2.0) * 0.03
    shape = (t / dur) ** 2.2
    return (noise + tone) * shape * np.linspace(1, 1, n)


def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def keys_ep(f, dur=0.9, gain=1.0):
    """Soft electric-piano tone: warm fundamental, a touch of bell on the attack."""
    t = t_axis(dur)
    tone = (np.sin(2 * np.pi * f * t) + 0.18 * np.sin(2 * np.pi * 2 * f * t)
            + 0.12 * np.sin(2 * np.pi * 7 * f * t) * np.exp(-t / 0.02))
    return lowpass(tone * env(len(t), 0.006, 0.35), 2800) * gain


def pluck_synth(f, dur=0.18, gain=1.0):
    """Short filtered-saw pluck for the arpeggio."""
    t = t_axis(dur)
    saw = sum(np.sin(2 * np.pi * f * h * t) / h for h in range(1, 7))
    return lowpass(saw * env(len(t), 0.002, 0.05), 2200) * gain


def bass(f, dur=0.22):
    t = t_axis(dur)
    tone = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t) + 0.15 * np.sin(2 * np.pi * 3 * f * t)
    return lowpass(tone * env(len(t), 0.004, 0.09), 450)


def kick():
    return sweep(110, 42, 0.2, 0.35) * env(int(0.2 * SR), 0.001, 0.08) * 0.9


def snap():
    n = int(0.08 * SR)
    body = np.sin(2 * np.pi * 1800 * t_axis(0.08)) * env(n, 0.0005, 0.008) * 0.3
    return (band(rng.standard_normal(n), 2000, 6000) * env(n, 0.0005, 0.018) + body) * 0.4


def hat():
    n = int(0.05 * SR)
    return band(rng.standard_normal(n), 8000, 15000) * env(n, 0.0005, 0.012) * 0.3


# Modern, confident "fintech product" groove at 116 BPM: lush 9th chords on a
# soft electric piano, a quiet 16th-note pluck arpeggio, a pulsing muted bass
# and restrained drums. No lead melody.
BPM = 116
CHORDS = {"Am9": [57, 60, 64, 67, 71], "Fmaj9": [53, 57, 60, 64, 67], "Cmaj9": [48, 55, 59, 62, 64],
          "G6": [55, 59, 62, 64, 69]}
ROOTS = {"Am9": 33, "Fmaj9": 29, "Cmaj9": 36, "G6": 31}
BARS = ["Am9", "Fmaj9", "Cmaj9", "G6", "Am9", "Fmaj9", "G6"]


def music(duration, final_hit):
    """Background track. Everything is short and percussive (no sustained drones),
    and the final chord lands exactly on `final_hit` (the logo chime)."""
    beat = 60 / BPM
    s16 = beat / 4
    start = final_hit - len(BARS) * 4 * beat
    out = np.zeros((int(duration * SR) + SR, 2))

    for b, name in enumerate(BARS):
        t0 = start + b * 4 * beat
        chord, root = CHORDS[name], ROOTS[name]
        # electric piano: on the one and a pushed "and of two"
        for pos, g in [(0, 1.0), (6, 0.75)]:
            for k, m in enumerate(chord):
                place(out, keys_ep(midi(m), gain=0.055 * g), t0 + pos * s16 + k * 0.004, -0.25 + 0.12 * k)
        # arpeggio: upper chord tones, rising through the bar
        arp = [chord[1], chord[2], chord[3], chord[4], chord[3] + 12 if b % 2 else chord[2] + 12]
        for i in range(16):
            gain = 0.018 + (0.006 if i % 4 == 0 else 0)
            place(out, pluck_synth(midi(arp[i % len(arp)] + 12), gain=gain), t0 + i * s16, 0.45 if i % 2 else -0.45)
        if b >= 1:
            # pulsing muted bass on every eighth, root with an octave pop
            for i in range(8):
                place(out, bass(midi(root + 12 + (12 if i in (3, 7) else 0))) * 0.2, t0 + i * 2 * s16)
            for i in (0, 8):
                place(out, kick() * 0.3, t0 + i * s16)
            for i in (4, 12):
                place(out, snap() * 0.14, t0 + i * s16, 0.1)
            for i in range(2, 16, 4):
                place(out, hat() * 0.12, t0 + i * s16, 0.3)
        if b == len(BARS) - 1:  # pull the drums out for the last half bar before the logo
            cut = int((t0 + 2 * beat) * SR)
            out[cut:int(final_hit * SR)] *= np.linspace(1, 0.35, int(final_hit * SR) - cut)[:, None]

    # resolve on Cmaj9 with the logo
    for k, m in enumerate(CHORDS["Cmaj9"] + [67, 71]):
        place(out, keys_ep(midi(m), 1.8, 0.06), final_hit + k * 0.006, -0.3 + 0.1 * k)
    place(out, bass(midi(36), 0.6) * 0.3, final_hit)
    place(out, kick() * 0.3, final_hit)
    fade_in = np.clip(np.arange(out.shape[0]) / SR / 0.8, 0, 1)
    return out * fade_in[:, None]


# ---------- mix ----------

# Darker, cinematic variant for experimental.html: 96 BPM, A minor that resolves to
# C major on the logo. The arrangement follows story markers exported by the page.
CINE_BPM = 96
CINE_BARS = ["Am9", "Fmaj9", "Am9", "Dm9", "Fmaj9", "Cmaj9", "Fmaj9"]
CINE_CHORDS = dict(CHORDS, Dm9=[50, 53, 57, 60, 64])
CINE_ROOTS = dict(ROOTS, Dm9=38)


def music_cinematic(duration, final_hit, marks):
    beat = 60 / CINE_BPM
    s16 = beat / 4
    bar = 4 * beat
    start = final_hit - len(CINE_BARS) * bar
    out = np.zeros((int(duration * SR) + SR, 2))
    tension = (marks.get("discrepancies", 7.3) - 0.2, marks.get("yes", 12.0))
    build = marks.get("yes", 12.0)

    for b, name in enumerate(CINE_BARS):
        t0 = start + b * bar
        last = b == len(CINE_BARS) - 1
        for half in (0, 1):
            h0 = t0 + half * 2 * beat
            chord_name = "G6" if (last or b == 4) and half == 1 else name
            chord, root = CINE_CHORDS[chord_name], CINE_ROOTS[chord_name]
            tense = tension[0] <= h0 < tension[1]
            # electric piano pad hits (short, re-struck, never sustained)
            for k, m in enumerate(chord):
                place(out, keys_ep(midi(m), 1.1, 0.05 if not tense else 0.04), h0 + k * 0.006, -0.3 + 0.15 * k)
            if tense:  # sparse clock-like pulse while the discrepancies are on screen
                for i in range(0, 8, 2):
                    place(out, pluck_synth(midi(chord[3] + 12), 0.12, 0.012), h0 + i * s16, 0.4 if i % 4 else -0.4)
                place(out, bass(midi(root + 12)) * 0.12, h0)
                continue
            full = h0 >= build or b in (1, 2)
            if b >= 1:
                for i in range(0, 8, 2):
                    place(out, bass(midi(root + 12 + (12 if i == 6 else 0))) * 0.18, h0 + i * s16)
            if full:
                place(out, kick() * 0.3, h0)
                place(out, snap() * 0.12, h0 + 4 * s16, 0.1)
                for i in range(2, 8, 4):
                    place(out, hat() * 0.12, h0 + i * s16, 0.3)
            if h0 >= build:  # arpeggio drive after "Yes"
                arp = [chord[1], chord[2], chord[3], chord[4]]
                for i in range(8):
                    place(out, pluck_synth(midi(arp[i % 4] + 12), gain=0.016), h0 + i * s16, 0.45 if i % 2 else -0.45)
            elif b == 0:
                for i in range(2, 8, 4):
                    place(out, hat() * 0.07, h0 + i * s16, 0.3)
        if last:  # pull everything back for the final half bar
            cut = int((t0 + 2 * beat) * SR)
            out[cut:int(final_hit * SR)] *= np.linspace(1, 0.3, int(final_hit * SR) - cut)[:, None]

    for k, m in enumerate(CINE_CHORDS["Cmaj9"] + [67, 71]):
        place(out, keys_ep(midi(m), 2.0, 0.06), final_hit + k * 0.006, -0.3 + 0.1 * k)
    place(out, bass(midi(48), 0.7) * 0.3, final_hit)
    place(out, kick() * 0.3, final_hit)
    fade_in = np.clip(np.arange(out.shape[0]) / SR / 0.8, 0, 1)
    return out * fade_in[:, None]


# ---------- extra sounds for experimental.html ----------

def shing():
    t = t_axis(0.7)
    n = len(t)
    tone = sweep(1800, 3600, 0.7, 0.5) * env(n, 0.01, 0.25) * 0.05
    air = band(rng.standard_normal(n), 6000, 12000) * env(n, 0.02, 0.2) * 0.05
    return tone + air


def impact(gain=0.32):
    n = int(0.7 * SR)
    boom = sweep(95, 38, 0.7, 0.4) * env(n, 0.002, 0.16) * gain
    crack = lowpass(rng.standard_normal(n), 900) * env(n, 0.001, 0.03) * gain * 0.5
    return boom + crack + swoosh(0.7, 200, 1200, gain * 0.25)


def alert():
    out = np.zeros(int(0.6 * SR))
    for k, f in enumerate([739.99, 587.33]):
        t = t_axis(0.35)
        tone = (np.sin(2 * np.pi * f * t) + 0.2 * np.sin(2 * np.pi * 2 * f * t)) * env(len(t), 0.004, 0.09) * 0.12
        i = int(k * 0.13 * SR)
        out[i:i + len(tone)] += tone
    return out


def focus_tick():
    w = swoosh(0.22, 1500, 5000, 0.035)
    w[: int(0.08 * SR)] += tick(0) * 1.2
    return w


def sparkle(dur=0.8, gain=0.05):
    n = int(dur * SR)
    out = np.zeros(n)
    for _ in range(26):
        at = int(rng.uniform(0, dur - 0.08) * SR)
        f = rng.uniform(2200, 5200) * (1 + at / n * 0.5)
        g = t_axis(0.08)
        out[at:at + len(g)] += np.sin(2 * np.pi * f * g) * env(len(g), 0.001, 0.018)
    return out * gain + swoosh(dur, 800, 6000, 0.06)


def paper():
    thud = sweep(170, 80, 0.12) * env(int(0.12 * SR), 0.002, 0.03) * 0.22
    return swoosh(0.25, 300, 2500, 0.07) + np.pad(thud, (0, int(0.25 * SR) - len(thud)))


def stamp():
    n = int(0.1 * SR)
    return (band(rng.standard_normal(n), 200, 1500) * env(n, 0.0005, 0.02) + np.sin(2 * np.pi * 130 * t_axis(0.1)) * env(n, 0.001, 0.03)) * 0.3


def place(mix, sig, at, pan=0.0):
    """Add a mono signal to the stereo mix at time `at` with equal-power pan (-1..1)."""
    i = int(round(at * SR))
    if i >= mix.shape[0]:
        return
    sig = sig[: mix.shape[0] - max(i, 0)]
    if i < 0:
        sig, i = sig[-i:], 0
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    mix[i:i + len(sig), 0] += sig * l * 1.414
    mix[i:i + len(sig), 1] += sig * r * 1.414


def main(cue_path, out_path):
    data = json.load(open(cue_path))
    duration = data["duration"]
    mix = np.zeros((int(duration * SR) + SR, 2))
    chime_t = next(c["t"] for c in data["cues"] if c["type"] == "chime")
    if data.get("music", "groove") == "cinematic":
        marks = {c["name"]: c["t"] for c in data["cues"] if c["type"] == "marker"}
        mix += 0.4 * music_cinematic(duration, chime_t, marks)[: mix.shape[0]]
    else:
        mix += 0.4 * music(duration, chime_t)[: mix.shape[0]]  # sits under the SFX

    pluck_notes = [659.25, 783.99, 880.0, 1046.5]
    for c in data["cues"]:
        t, kind, i = c["t"], c["type"], c.get("i", 0)
        if kind in ("key", "space"):
            place(mix, key(kind == "space"), t, rng.uniform(-0.15, 0.15))
        elif kind == "send":
            place(mix, send(), t)
        elif kind == "swoosh_up":
            place(mix, swoosh(0.3, 600, 3000, 0.07), t)
        elif kind == "pop":
            place(mix, pop(), t)
        elif kind == "check":
            place(mix, check(i), t, -0.1 + 0.1 * i)
        elif kind == "card":
            place(mix, card(), t)
        elif kind == "tick":
            place(mix, tick(i), t, 0.2)
        elif kind == "whoosh":
            # Claude exits left, ChatGPT arrives from the right
            w = swoosh(0.75, 250, 2800, 0.22)
            half = len(w) // 2
            place(mix, w[:half], t, 0.5)
            place(mix, w[half:], t + half / SR, -0.3)
            place(mix, sweep(90, 55, 0.5) * env(int(0.5 * SR), 0.05, 0.2) * 0.12, t + 0.25)
        elif kind == "whoosh_soft":
            place(mix, swoosh(0.6, 200, 1500, 0.12), t)
        elif kind == "node":
            place(mix, bell([523.25, 784.0], 1.4, 0.13, 0.35), t)
        elif kind == "pluck":
            place(mix, pluck(pluck_notes[i]), t, -0.6 + 0.4 * i)
        elif kind == "riser":
            place(mix, riser(0.9), t)
        elif kind == "chime":
            place(mix, bell([523.25, 659.25, 783.99, 1046.5], 3.0, 0.2, 1.1), t)
        elif kind == "shing":
            place(mix, shing(), t)
        elif kind in ("impact", "impact_soft"):
            place(mix, impact(0.32 if kind == "impact" else 0.18), t)
        elif kind == "alert":
            place(mix, alert(), t)
        elif kind == "focus":
            place(mix, focus_tick(), t, -0.2 + 0.2 * i)
        elif kind == "confirm":
            place(mix, bell([1046.5, 1567.98], 1.0, 0.14, 0.3), t)
        elif kind == "stream":
            place(mix, sparkle(), t, -0.6 if i == 0 else 0.6)
        elif kind == "paper":
            place(mix, paper(), t, -0.5 if i == 0 else 0.5)
        elif kind == "stamp":
            place(mix, stamp(), t, -0.5 if i == 0 else 0.5)
        elif kind == "whip":
            w = swoosh(0.32, 400, 5000, 0.2)
            half = len(w) // 2
            place(mix, w[:half], t, 0.6)
            place(mix, w[half:], t + half / SR, -0.6)

    mix = mix[: int(duration * SR)]
    # gentle bus compression + soft clip, then normalise to -1 dBFS
    mix = np.tanh(mix * 1.6) / 1.6
    mix *= 10 ** (-1 / 20) / max(1e-9, np.abs(mix).max())
    # short fade at the very end so the last frame doesn't click
    fade = int(0.25 * SR)
    mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
    wavfile.write(out_path, SR, (mix * 32767).astype(np.int16))
    print(f"wrote {out_path}: {duration:.2f}s, {len(data['cues'])} cues")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
