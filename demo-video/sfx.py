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


def marimba(f, dur=0.35, gain=1.0):
    t = t_axis(dur)
    tone = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 4 * f * t) * np.exp(-t / 0.03)
    return tone * env(len(t), 0.002, 0.12) * gain


def glock(f, dur=0.6, gain=1.0):
    t = t_axis(dur)
    tone = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2.76 * f * t) * np.exp(-t / 0.08)
    return tone * env(len(t), 0.001, 0.22) * gain


def bass(f, dur=0.3):
    t = t_axis(dur)
    tone = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t)
    return lowpass(tone * env(len(t), 0.004, 0.14), 600) * 0.9


def kick():
    return sweep(130, 45, 0.18, 0.4) * env(int(0.18 * SR), 0.001, 0.07) * 0.9


def clap():
    n = int(0.12 * SR)
    return band(rng.standard_normal(n), 1200, 5000) * env(n, 0.001, 0.03) * 0.5


def hat(open_=False):
    n = int((0.09 if open_ else 0.04) * SR)
    return band(rng.standard_normal(n), 7000, 14000) * env(n, 0.0005, 0.03 if open_ else 0.008) * 0.3


# Upbeat I–V–vi–IV groove in C major at 120 BPM (one bar = 2 s).
CHORDS = {"C": [60, 64, 67, 72], "G": [59, 62, 67, 71], "Am": [57, 60, 64, 69], "F": [57, 60, 65, 69]}
ROOTS = {"C": 36, "G": 43, "Am": 45, "F": 41}
BARS = ["C", "G", "Am", "F", "C", "G", "F"]
MELODY = {4: [(0, 76), (1, 79), (2, 84), (4, 79), (6, 76)],
          5: [(0, 74), (1, 79), (2, 83), (4, 86), (6, 83)],
          6: [(0, 84), (1, 81), (2, 77), (4, 79), (5, 83), (6, 86)]}


def music(duration, final_hit):
    """Light, happy 'finance explainer' groove: marimba chords, plucked bass, soft
    drums and a glockenspiel hook. Everything is short and percussive (no sustained
    tones), and the last chord lands exactly on `final_hit` (the logo chime)."""
    beat = 0.5
    start = final_hit - len(BARS) * 4 * beat
    out = np.zeros((int(duration * SR) + SR, 2))
    e = beat / 2  # eighth note

    for b, name in enumerate(BARS):
        t0 = start + b * 4 * beat
        build = b == len(BARS) - 1
        chord = CHORDS[name]
        # marimba chord stabs on a syncopated eighth pattern
        for pos in [0, 2, 3, 5, 6]:
            c = CHORDS["G"] if build and pos >= 4 else chord
            for k, m in enumerate(c):
                place(out, marimba(midi(m), gain=0.07 * (1.2 if pos == 0 else 1)), t0 + pos * e, -0.3 + 0.2 * k)
        if b >= 1:
            root = ROOTS["G"] if build else ROOTS[name]
            for pos, off in [(0, 0), (3, 0), (4, 12), (6, 0)]:
                if build and pos >= 4:
                    root = ROOTS["G"]
                place(out, bass(midi(root + 12 + off)) * 0.22, t0 + pos * e)
            for pos in [0, 4]:
                place(out, kick() * 0.28, t0 + pos * e)
            for pos in [2, 6]:
                place(out, clap() * 0.16, t0 + pos * e, 0.1)
        for pos in range(8):
            if b >= 1 or pos % 2:
                place(out, hat(open_=pos % 2 == 1) * (0.12 if pos % 2 else 0.07), t0 + pos * e, 0.35)
        if build:  # snare-roll lift into the logo
            for i in range(8):
                place(out, clap() * (0.05 + 0.02 * i), t0 + 4 * beat * 0.5 + i * e / 2, -0.1)
        for pos, m in MELODY.get(b, []):
            place(out, glock(midi(m), gain=0.08), t0 + pos * e, 0.2)

    # final chord on the logo
    for k, m in enumerate(CHORDS["C"] + [76, 79]):
        place(out, marimba(midi(m), 1.2, 0.08), final_hit, -0.3 + 0.12 * k)
    place(out, bass(midi(48), 0.8) * 0.3, final_hit)
    place(out, kick() * 0.3, final_hit)
    fade_in = np.clip(np.arange(out.shape[0]) / SR / 0.6, 0, 1)
    return out * fade_in[:, None]


# ---------- mix ----------

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
