"""Sound design for films: everything synthesised, so the channel owns it."""

from __future__ import annotations

import numpy as np

from ..audio import SR, _env, fft_filter, midi_hz, pluck, reverb, sfx_whoosh


def heartbeat(strength: float = 1.0, pitch: float = 1.0) -> np.ndarray:
    """A soft 'ba-dum'."""
    out = np.zeros(int(0.5 * SR), np.float32)
    for k, (at, amp) in enumerate(((0.0, 1.0), (0.2, 0.62))):
        n = int(0.16 * SR)
        t = np.arange(n) / SR
        f = (62 + 30 * np.exp(-t * 30)) * pitch
        s = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.004, 0.06)
        s += 0.3 * fft_filter(np.random.default_rng(k).standard_normal(n).astype(np.float32), high=300) * _env(n, 0.002, 0.03)
        i = int(at * SR)
        out[i:i + n] += (s * amp).astype(np.float32)
    return out * strength


def bubbles(n: int = 6, seed: int = 0, dur: float = 1.2) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = np.zeros(int(dur * SR), np.float32)
    for _ in range(n):
        m = int(rng.uniform(0.05, 0.11) * SR)
        t = np.arange(m) / SR
        f0 = rng.uniform(500, 1100)
        f = f0 * (1 + 1.2 * t / t[-1])
        blip = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(m, 0.003, 0.03)
        i = int(rng.uniform(0, dur - 0.12) * SR)
        out[i:i + m] += blip.astype(np.float32) * rng.uniform(0.25, 0.6)
    return out


def chime(note: int = 84) -> np.ndarray:
    return (0.45 * pluck(midi_hz(note), 1.6, 0.6) + 0.3 * pluck(midi_hz(note + 7), 1.6, 0.4)
            + 0.2 * pluck(midi_hz(note + 12), 1.6, 0.3))


def shimmer(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = np.zeros(int(1.4 * SR), np.float32)
    for k, note in enumerate((88, 91, 95, 100)):
        sig = pluck(midi_hz(note + int(rng.integers(-1, 2))), 1.0, 0.5) * 0.18
        i = int(k * 0.06 * SR)
        out[i:i + len(sig)] += sig
    return out


def swell(dur: float = 7.0, note: int = 38) -> np.ndarray:
    """A low, curious cello-like swell for a passing shadow (not scary)."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = sum(np.sin(2 * np.pi * midi_hz(note) * h * t + h) / h for h in (1, 2, 3, 4))
    s += 0.5 * sum(np.sin(2 * np.pi * midi_hz(note + 7) * h * t) / h for h in (1, 2, 3))
    env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 2
    return (0.18 * s * env).astype(np.float32)


def paper(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(0.18 * SR)
    s = fft_filter(rng.standard_normal(n).astype(np.float32), low=1500, high=7000) * _env(n, 0.002, 0.04)
    return 0.35 * s / (np.max(np.abs(s)) + 1e-9)


def whoosh(seed: int = 0) -> np.ndarray:
    return sfx_whoosh(seed, dur=0.9)


def ambience(dur: float, seed: int = 0) -> np.ndarray:
    """Underwater bed: deep filtered rumble with slow swells."""
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    noise = rng.standard_normal(n).astype(np.float32)
    deep = fft_filter(noise, low=30, high=260)
    t = np.arange(n) / SR
    deep *= (0.65 + 0.35 * np.sin(2 * np.pi * 0.05 * t + 1.0)).astype(np.float32)
    deep /= np.max(np.abs(deep)) + 1e-9
    return 0.5 * deep


def score(dur: float, seed: int = 0) -> np.ndarray:
    """Gentle, wondering music box + pads in a major key."""
    rng = np.random.default_rng(seed)
    n = int((dur + 4) * SR)
    out = np.zeros(n, np.float32)
    root = 60 + int(rng.integers(-2, 3))
    prog = [0, 9, 5, 7]                      # I – vi – IV – V
    bar = 60 / 76 * 4
    melody_steps = [0, 2, 4, 7, 9, 12, 14, 16]
    t = 0.0
    b = 0
    while t < dur + 1:
        c = root + prog[b % 4]
        tt = np.arange(int(bar * 1.4 * SR)) / SR
        pad = sum(np.sin(2 * np.pi * midi_hz(c + iv - 12) * d * tt) for iv in (0, 4 if prog[b % 4] in (0, 5, 7) else 3, 7)
                  for d in (0.998, 1.002))
        fade = np.clip(tt / (bar * 0.4), 0, 1) * np.clip((bar * 1.4 - tt) / (bar * 0.4), 0, 1)
        seg = (pad * fade / 6 * 0.35).astype(np.float32)
        i = int(t * SR)
        out[i:i + len(seg)] += seg[: n - i]
        for k in range(8):
            if rng.random() < 0.62:
                note = root + 12 + int(rng.choice(melody_steps))
                sig = pluck(midi_hz(note), 1.4, 0.45) * rng.uniform(0.25, 0.45)
                j = int((t + k * bar / 8) * SR)
                out[j:j + len(sig)] += sig[: max(0, n - j)]
        t += bar
        b += 1
    out = reverb(out, 2.4, 0.35, seed)[: int(dur * SR)]
    f = int(2 * SR)
    out[:f] *= np.linspace(0, 1, f)
    out[-f:] *= np.linspace(1, 0, f)
    return out / (np.max(np.abs(out)) + 1e-9) * 0.8


SFX = {"heartbeat": heartbeat, "bubbles": bubbles, "chime": chime, "shimmer": shimmer, "swell": swell,
       "paper": paper, "whoosh": whoosh}

