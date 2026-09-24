"""Audio: decoding, generative music, sound effects and the final mix.

All music and SFX are synthesised from scratch (seeded per episode), so the
channel owns every sound and never gets a Content ID claim.
"""

from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 44100


def ffmpeg_exe() -> str:
    import shutil

    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def load_audio(path: str | Path, sr: int = SR) -> np.ndarray:
    """Decode any audio file to mono float32 at `sr` using ffmpeg."""
    cmd = [ffmpeg_exe(), "-v", "error", "-i", str(path), "-f", "f32le",
           "-ac", "1", "-ar", str(sr), "-"]
    out = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(out, dtype=np.float32).copy()


def write_wav(path: str | Path, audio: np.ndarray, sr: int = SR) -> None:
    """Write mono or stereo (N, 2) float audio as 16-bit PCM."""
    audio = np.clip(audio, -1.0, 1.0)
    channels = 1 if audio.ndim == 1 else audio.shape[1]
    pcm = (audio * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def trim_silence(audio: np.ndarray, threshold: float = 0.01, pad: float = 0.03,
                 sr: int = SR) -> np.ndarray:
    loud = np.flatnonzero(np.abs(audio) > threshold)
    if loud.size == 0:
        return audio
    p = int(pad * sr)
    return audio[max(0, loud[0] - p): loud[-1] + p]


# --------------------------------------------------------------------------
# DSP helpers
# --------------------------------------------------------------------------

def midi_hz(note: float) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)


def _env(n: int, attack: float, decay: float, sr: int = SR) -> np.ndarray:
    t = np.arange(n) / sr
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-t / max(decay, 1e-4))


def fft_filter(x: np.ndarray, low: float | None = None, high: float | None = None,
               sr: int = SR) -> np.ndarray:
    """Zero-phase band filter with soft edges (fine for noise shaping)."""
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / sr)
    g = np.ones_like(f)
    if low:
        g *= 1 / (1 + (low / np.maximum(f, 1)) ** 4)
    if high:
        g *= 1 / (1 + (f / high) ** 4)
    return np.fft.irfft(spec * g, n=len(x)).astype(np.float32)


def reverb(x: np.ndarray, seconds: float = 2.0, wet: float = 0.3, seed: int = 0,
           sr: int = SR) -> np.ndarray:
    """Cheap algorithmic reverb: FFT overlap-add with a decaying-noise impulse."""
    rng = np.random.default_rng(seed)
    n_ir = int(seconds * sr)
    ir = rng.standard_normal(n_ir).astype(np.float32) * np.exp(-np.arange(n_ir) / (sr * seconds / 6))
    ir = fft_filter(ir, high=6000)
    ir /= np.sqrt(np.sum(ir ** 2)) + 1e-9
    block = 1 << 18
    nfft = 1 << int(np.ceil(np.log2(block + n_ir)))
    H = np.fft.rfft(ir, nfft)
    out = np.zeros(len(x) + n_ir, dtype=np.float32)
    for start in range(0, len(x), block):
        seg = x[start:start + block]
        y = np.fft.irfft(np.fft.rfft(seg, nfft) * H, nfft)[: len(seg) + n_ir]
        out[start:start + len(y)] += y.astype(np.float32)
    return (1 - wet) * x + wet * out[: len(x)]


def _add(buf: np.ndarray, sig: np.ndarray, at: int) -> None:
    if at >= len(buf):
        return
    end = min(len(buf), at + len(sig))
    buf[at:end] += sig[: end - at]


# --------------------------------------------------------------------------
# Instruments
# --------------------------------------------------------------------------

def pluck(freq: float, dur: float, bright: float = 1.0, sr: int = SR) -> np.ndarray:
    """Marimba / music-box style pluck."""
    n = int(dur * sr)
    t = np.arange(n) / sr
    s = np.sin(2 * np.pi * freq * t) * _env(n, 0.004, dur * 0.35)
    s += 0.35 * bright * np.sin(2 * np.pi * freq * 4.0 * t) * _env(n, 0.002, dur * 0.06)
    s += 0.15 * bright * np.sin(2 * np.pi * freq * 3.0 * t) * _env(n, 0.002, dur * 0.1)
    return s.astype(np.float32)


def celesta(freq: float, dur: float, sr: int = SR) -> np.ndarray:
    """Glassy, slightly detuned bell for spooky music."""
    n = int(dur * sr)
    t = np.arange(n) / sr
    s = (np.sin(2 * np.pi * freq * t) + 0.6 * np.sin(2 * np.pi * freq * 1.006 * t)) * _env(n, 0.01, dur * 0.5)
    s += 0.25 * np.sin(2 * np.pi * freq * 2.76 * t) * _env(n, 0.005, dur * 0.15)
    return (0.6 * s).astype(np.float32)


def soft_bass(freq: float, dur: float, sr: int = SR) -> np.ndarray:
    n = int(dur * sr)
    t = np.arange(n) / sr
    s = np.sin(2 * np.pi * freq * t) + 0.2 * np.sin(4 * np.pi * freq * t)
    env = np.clip(t / 0.02, 0, 1) * np.clip((dur - t) / 0.08, 0, 1) * np.exp(-t / (dur * 0.8))
    return (s * env).astype(np.float32)


def pad(freqs: list[float], dur: float, sr: int = SR) -> np.ndarray:
    n = int(dur * sr)
    t = np.arange(n) / sr
    s = np.zeros(n, dtype=np.float64)
    for f in freqs:
        for det in (0.997, 1.0, 1.003):
            s += np.sin(2 * np.pi * f * det * t + det * 7)
    fade = np.clip(t / (dur * 0.3), 0, 1) * np.clip((dur - t) / (dur * 0.3), 0, 1)
    return (s * fade / (3 * len(freqs))).astype(np.float32)


# --------------------------------------------------------------------------
# Music generators
# --------------------------------------------------------------------------

MAJOR_PENTA = [0, 2, 4, 7, 9]
MINOR_PENTA = [0, 3, 5, 7, 10]


def _scale_notes(root: int, steps: list[int], lo: int, hi: int) -> list[int]:
    return [n for n in range(lo, hi + 1) if (n - root) % 12 in steps]


def music_playful(duration: float, seed: int = 0, sr: int = SR) -> np.ndarray:
    """Bouncy marimba + bass + shaker loop. Always different, always ours."""
    rng = np.random.default_rng(seed)
    bpm = rng.uniform(100, 116)
    beat = 60 / bpm
    root = 60 + int(rng.integers(-3, 4))
    # I – V – vi – IV (or a shuffle of it) in semitones from the root
    progs = [[0, 7, 9, 5], [0, 5, 7, 5], [0, 9, 5, 7], [0, 4, 5, 7]]
    prog = progs[int(rng.integers(len(progs)))]
    n = int((duration + 2) * sr)
    melody = np.zeros(n, np.float32)
    bass = np.zeros(n, np.float32)
    perc = np.zeros(n, np.float32)
    pads = np.zeros(n, np.float32)
    notes = _scale_notes(root, MAJOR_PENTA, root, root + 19)
    idx = len(notes) // 2
    bar = 0
    t = 0.0
    shaker = fft_filter(rng.standard_normal(int(0.05 * sr)).astype(np.float32), low=6000)
    shaker *= _env(len(shaker), 0.002, 0.012)
    while t < duration + 1:
        chord = root + prog[bar % 4]
        pads_sig = pad([midi_hz(chord - 12), midi_hz(chord - 5), midi_hz(chord - 8 + (4 if prog[bar % 4] in (0, 5, 7) else 3))], beat * 4.2)
        _add(pads, pads_sig, int(t * sr))
        for b in range(4):
            bt = t + b * beat
            if b in (0, 2):
                _add(bass, soft_bass(midi_hz(chord - 24 + (7 if b == 2 and rng.random() < 0.4 else 0)), beat * 1.6), int(bt * sr))
            for half in (0, 1):
                st = bt + half * beat / 2
                _add(perc, shaker * (1.0 if half else 0.55), int(st * sr))
                if rng.random() < (0.72 if half == 0 else 0.45):
                    idx = int(np.clip(idx + rng.choice([-2, -1, -1, 0, 1, 1, 2]), 0, len(notes) - 1))
                    _add(melody, pluck(midi_hz(notes[idx]), beat * 1.5) * rng.uniform(0.55, 0.9), int(st * sr))
        t += beat * 4
        bar += 1
    mix = 0.55 * melody + 0.5 * bass + 0.12 * perc + 0.25 * pads
    mix = reverb(mix, 1.2, 0.18, seed)
    return _finish(mix[: int(duration * sr)])


def music_spooky(duration: float, seed: int = 0, sr: int = SR) -> np.ndarray:
    """Mysterious-but-not-scary: slow celesta over a soft minor drone and wind."""
    rng = np.random.default_rng(seed)
    beat = 60 / rng.uniform(66, 76)
    root = 57 + int(rng.integers(-2, 3))           # around A3
    n = int((duration + 3) * sr)
    tt = np.arange(n) / sr
    drone = (np.sin(2 * np.pi * midi_hz(root - 24) * tt) + 0.5 * np.sin(2 * np.pi * midi_hz(root - 17) * tt))
    drone *= 0.6 + 0.4 * np.sin(2 * np.pi * 0.11 * tt)
    wind = fft_filter(rng.standard_normal(n).astype(np.float32), low=300, high=1400)
    wind *= (0.5 + 0.5 * np.sin(2 * np.pi * 0.07 * tt + 1.3)) ** 2
    wind /= np.max(np.abs(wind)) + 1e-9
    bells = np.zeros(n, np.float32)
    notes = _scale_notes(root, [0, 2, 3, 7, 8], root + 12, root + 26)  # natural-minor flavour
    t = 0.0
    idx = len(notes) // 2
    while t < duration + 1:
        if rng.random() < 0.62:
            idx = int(np.clip(idx + rng.choice([-2, -1, 1, 2, 3]), 0, len(notes) - 1))
            _add(bells, celesta(midi_hz(notes[idx]), beat * 3) * rng.uniform(0.5, 0.9), int(t * sr))
        t += beat * rng.choice([1, 1, 2])
    mix = 0.35 * drone.astype(np.float32) + 0.12 * wind + 0.6 * bells
    mix = reverb(mix, 3.0, 0.4, seed)
    return _finish(mix[: int(duration * sr)])


def music_calm(duration: float, seed: int = 0, sr: int = SR) -> np.ndarray:
    """Gentle pads + occasional plucks, for story time."""
    rng = np.random.default_rng(seed)
    root = 55 + int(rng.integers(0, 5))
    n = int((duration + 6) * sr)
    out = np.zeros(n, np.float32)
    prog = [0, 5, 9, 7]
    bar_len = 5.0
    t = 0.0
    bar = 0
    notes = _scale_notes(root, MAJOR_PENTA, root + 12, root + 24)
    while t < duration + 1:
        c = root + prog[bar % 4]
        _add(out, 0.6 * pad([midi_hz(c - 12), midi_hz(c - 5), midi_hz(c)], bar_len * 1.3), int(t * sr))
        for k in range(int(rng.integers(1, 4))):
            _add(out, 0.4 * pluck(midi_hz(rng.choice(notes)), 2.5, 0.4), int((t + rng.uniform(0, bar_len)) * sr))
        t += bar_len
        bar += 1
    return _finish(reverb(out, 2.5, 0.35, seed)[: int(duration * sr)])


MUSIC = {"playful": music_playful, "spooky": music_spooky, "calm": music_calm}


def _finish(x: np.ndarray, fade: float = 1.2, sr: int = SR) -> np.ndarray:
    x = x.astype(np.float32)
    f = int(min(fade * sr, len(x) // 4))
    if f:
        x[:f] *= np.linspace(0, 1, f, dtype=np.float32)
        x[-f:] *= np.linspace(1, 0, f, dtype=np.float32)
    peak = np.max(np.abs(x)) + 1e-9
    return x / peak * 0.8


# --------------------------------------------------------------------------
# Sound effects
# --------------------------------------------------------------------------

def sfx_pop(seed: int = 0, sr: int = SR) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(0.12 * sr)
    t = np.arange(n) / sr
    f0 = rng.uniform(600, 900)
    freq = f0 * np.exp(-t * 18) + 250
    s = np.sin(2 * np.pi * np.cumsum(freq) / sr) * _env(n, 0.002, 0.035)
    return (0.8 * s).astype(np.float32)


def sfx_whoosh(seed: int = 0, dur: float = 0.55, sr: int = SR) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(dur * sr)
    noise = rng.standard_normal(n).astype(np.float32)
    lo = fft_filter(noise, low=200, high=1200)
    hi = fft_filter(noise, low=1500, high=5000)
    t = np.linspace(0, 1, n)
    shape = np.sin(np.pi * t) ** 2
    s = (lo * (1 - t) + hi * t) * shape
    return (0.6 * s / (np.max(np.abs(s)) + 1e-9)).astype(np.float32)


def sfx_ding(sr: int = SR) -> np.ndarray:
    return 0.5 * pluck(midi_hz(84), 0.9, 0.8) + 0.3 * pluck(midi_hz(91), 0.9, 0.5)


# --------------------------------------------------------------------------
# Mixing
# --------------------------------------------------------------------------

def envelope(x: np.ndarray, window: float = 0.15, sr: int = SR) -> np.ndarray:
    """Smoothed 0..1 'is somebody talking' curve."""
    w = max(1, int(window * sr))
    active = (np.abs(x) > 0.02).astype(np.float32)
    kernel = np.ones(w, np.float32) / w
    sm = np.convolve(active, kernel, mode="same")
    return np.clip(sm * 3, 0, 1)


def mix(narration: np.ndarray, music: np.ndarray, sfx: np.ndarray,
        music_volume: float, duck: float, sfx_volume: float) -> np.ndarray:
    n = max(len(narration), len(music), len(sfx))

    def fit(x):
        return np.pad(x, (0, n - len(x))) if len(x) < n else x[:n]

    narration, music, sfx = fit(narration), fit(music), fit(sfx)
    speech = envelope(narration)
    gain = music_volume * (1 - (1 - duck) * speech)
    out = narration + music * gain + sfx * sfx_volume
    peak = np.max(np.abs(out)) + 1e-9
    if peak > 0.98:
        out = np.tanh(out / peak * 1.2) * 0.95
    return out.astype(np.float32)
