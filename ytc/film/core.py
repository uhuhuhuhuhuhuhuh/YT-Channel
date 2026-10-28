"""Films: hand-directed paper-diorama stories.

A film lives in films/<name>/ with
  film.yaml       title, description, tags, sources, voice, size, fps
  screenplay.py   BEATS (the narration), INTRO/OUTRO, build(stage), direct(stage)

Timing is driven by the narration: every beat is synthesised first, then the
screenplay places camera moves, character actions and sound effects on cues
like `stage.cue(5, "three")` (the moment the narrator says "three" in beat 5).
"""

from __future__ import annotations

import importlib.util
import multiprocessing as mp
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml
from PIL import Image

from .. import audio, tts
from ..captions import to_srt
from ..config import BUILD, OUTPUT, ROOT, load_config
from .world import Camera, Track

FILMS = ROOT / "films"


@dataclass
class Beat:
    text: str
    pause: float = 0.7          # silence after the line
    lead: float = 0.0           # silence before the line


@dataclass
class Timing:
    starts: list[float]
    ends: list[float]
    words: list[list[tts.Word]]     # per beat, absolute times
    duration: float


@dataclass
class FilmSpec:
    name: str
    folder: Path
    meta: dict
    module: object

    @property
    def size(self) -> tuple[int, int]:
        w, h = self.meta.get("size", [1920, 1080])
        return int(w), int(h)

    @property
    def fps(self) -> int:
        return int(self.meta.get("fps", 24))

    @property
    def voice(self) -> str:
        return self.meta.get("voice", "heart")


def load_film(name: str) -> FilmSpec:
    folder = Path(name)
    if not folder.exists():
        folder = FILMS / name
    if not folder.exists():
        matches = sorted(FILMS.glob(f"*{name}*"))
        if len(matches) == 1:
            folder = matches[0]
    if not (folder / "screenplay.py").exists():
        raise SystemExit(f"film not found: {name} (looked in {FILMS})")
    meta = yaml.safe_load((folder / "film.yaml").read_text(encoding="utf-8")) or {}
    spec = importlib.util.spec_from_file_location(f"film_{folder.name.replace('-', '_')}", folder / "screenplay.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return FilmSpec(folder.name, folder, meta, module)


def list_films() -> list[Path]:
    return sorted(p for p in FILMS.iterdir() if (p / "screenplay.py").exists()) if FILMS.exists() else []


def time_narration(spec: FilmSpec, log=print) -> tuple[Timing, list[tts.Speech]]:
    m = spec.module
    t = float(getattr(m, "INTRO", 3.0))
    starts, ends, words, speeches = [], [], [], []
    for i, b in enumerate(m.BEATS):
        log(f"  voice {i + 1}/{len(m.BEATS)}: {b.text[:64]}")
        sp = tts.speak(b.text, spec.voice)
        t += b.lead
        starts.append(t)
        words.append([tts.Word(w.text, w.start + t, w.end + t) for w in sp.words])
        t += sp.duration
        ends.append(t)
        t += b.pause
        speeches.append(sp)
    duration = t + float(getattr(m, "OUTRO", 4.0))
    return Timing(starts, ends, words, duration), speeches


# --------------------------------------------------------------------------
# Stage
# --------------------------------------------------------------------------


def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9']", "", w.lower())


@dataclass
class Event:
    t: float
    kind: str
    gain: float = 1.0
    params: dict = field(default_factory=dict)


class Stage:
    """Everything a screenplay builds, and the compositor that draws a frame."""

    def __init__(self, spec: FilmSpec, timing: Timing, scale: float = 1.0):
        self.spec = spec
        self.timing = timing
        W, H = spec.size
        self.scale = scale
        self.W, self.H = int(W * scale) // 2 * 2, int(H * scale) // 2 * 2
        self.rng = np.random.default_rng(int(spec.meta.get("seed", 7)))
        self.stack: list = []            # drawn in order: callables (frame, cam, t) -> None
        self.post: list = []             # screen-space effects after the world
        self.cam = Track((0.0, 0.0, 0.0))
        self.tracks: dict[str, Track] = {}
        self.events: list[Event] = []
        self.assets: dict = {}
        spec.module.build(self)
        spec.module.direct(self)

    # -- timing helpers for screenplays ----------------------------------------
    @property
    def duration(self) -> float:
        return self.timing.duration

    def start(self, i: int) -> float:
        return self.timing.starts[i]

    def end(self, i: int) -> float:
        return self.timing.ends[i]

    def cue(self, i: int, word: str | None = None, offset: float = 0.0, nth: int = 1) -> float:
        """Time the narrator says `word` in beat i (start of beat if word is None)."""
        if word is None:
            return self.timing.starts[i] + offset
        target = _norm(word)
        seen = 0
        for w in self.timing.words[i]:
            if _norm(w.text) == target:
                seen += 1
                if seen == nth:
                    return w.start + offset
        raise KeyError(f"word {word!r} not found in beat {i}: {self.spec.module.BEATS[i].text!r}")

    def track(self, name: str, default=None) -> Track:
        """Get a track; the first call for a name creates it with `default`."""
        if name not in self.tracks:
            if default is None:
                raise KeyError(f"track {name!r} doesn't exist yet; create it with a default first")
            self.tracks[name] = Track(default)
        return self.tracks[name]

    def sfx(self, t: float, kind: str, gain: float = 1.0, **params) -> None:
        self.events.append(Event(t, kind, gain, params))

    # -- rendering -------------------------------------------------------------
    def camera(self, t: float) -> Camera:
        x, y, d = self.cam(t)
        # world units are 1080p pixels; previews just scale the camera
        return Camera(x, y, d, self.H / 1080)

    def px(self, v: float) -> int:
        """Screen-space size in output pixels for a value given at 1080p."""
        return max(1, int(round(v * self.H / 1080)))

    def frame(self, t: float) -> Image.Image:
        cam = self.camera(t)
        frame = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 255))
        for item in self.stack:
            item(frame, cam, t)
        for item in self.post:
            item(frame, cam, t)
        return frame.convert("RGB")


# --------------------------------------------------------------------------
# Rendering + soundtrack
# --------------------------------------------------------------------------


def build_soundtrack(spec: FilmSpec, stage: Stage, timing: Timing, speeches: list[tts.Speech]) -> Path:
    from . import sound

    sr = audio.SR
    n = int(timing.duration * sr) + 1
    narration = np.zeros(n, np.float32)
    for st, sp in zip(timing.starts, speeches):
        audio._add(narration, sp.audio, int(st * sr))
    narration *= 0.9 / (np.max(np.abs(narration)) + 1e-9)

    sfx = np.zeros(n, np.float32)
    for k, ev in enumerate(sorted(stage.events, key=lambda e: e.t)):
        fn = sound.SFX[ev.kind]
        params = dict(ev.params)
        if ev.kind in ("bubbles", "paper", "whoosh", "shimmer"):
            params.setdefault("seed", k)
        sig = fn(**params) * ev.gain
        audio._add(sfx, sig.astype(np.float32), int(max(0.0, ev.t) * sr))

    acfg = load_config()["audio"]
    music = sound.score(timing.duration, seed=int(spec.meta.get("seed", 7))) * float(spec.meta.get("music", 0.6))
    bed = sound.ambience(timing.duration, seed=3) * float(spec.meta.get("ambience", 0.35))
    mixed = audio.mix(narration, music + bed, sfx, acfg["music_volume"] * 1.4, acfg["duck"], 0.55)
    out_dir = BUILD / f"film-{spec.name}"
    out_dir.mkdir(parents=True, exist_ok=True)
    wav = out_dir / "soundtrack.wav"
    audio.write_wav(wav, mixed)
    words = [w for ws in timing.words for w in ws]
    (out_dir / "captions.srt").write_text(to_srt(words), encoding="utf-8")
    return wav


_STAGE: Stage | None = None


def _init(name: str, timing: Timing, scale: float) -> None:
    global _STAGE
    _STAGE = Stage(load_film(name), timing, scale)


def _frame(args) -> bytes:
    i, fps = args
    assert _STAGE is not None
    return _STAGE.frame(i / fps).tobytes()


def render_film(name: str, preview: bool = False, workers: int | None = None, start: float = 0.0,
                end: float | None = None, log=print) -> Path:
    t0 = time.time()
    spec = load_film(name)
    log(f"▶ film {spec.name}: timing narration")
    timing, speeches = time_narration(spec, log)
    scale = 0.5 if preview else 1.0
    fps = 12 if preview else spec.fps
    stage = Stage(spec, timing, scale)
    wav = build_soundtrack(spec, stage, timing, speeches)
    W, H = stage.W, stage.H
    end = timing.duration if end is None else min(end, timing.duration)
    frames = range(int(start * fps), int(end * fps))
    out = OUTPUT / f"film-{spec.name}{'-preview' if preview else ''}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    lufs = load_config()["audio"]["loudness_lufs"]
    cmd = [audio.ffmpeg_exe(), "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
           "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(wav),
           "-c:v", "libx264", "-preset", "veryfast" if preview else "slow", "-crf", "26" if preview else "18",
           "-pix_fmt", "yuv420p", "-tune", "animation",
           "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-shortest", "-movflags", "+faststart", str(out)]
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    log(f"▶ rendering {len(frames)} frames ({end - start:.1f}s, {W}x{H}@{fps}) with {workers} workers")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    step = max(1, len(frames) // 20)
    jobs = [(i, fps) for i in frames]
    try:
        if workers == 1:
            global _STAGE
            _STAGE = stage
            it = map(_frame, jobs)
            for k, data in enumerate(it):
                proc.stdin.write(data)
                if k % step == 0:
                    log(f"  {k * 100 // max(1, len(jobs)):3d}%")
        else:
            ctx = mp.get_context("fork" if sys.platform == "linux" else "spawn")
            with ctx.Pool(workers, initializer=_init, initargs=(spec.name, timing, scale)) as pool:
                for k, data in enumerate(pool.imap(_frame, jobs, chunksize=2)):
                    proc.stdin.write(data)
                    if k % step == 0:
                        log(f"  {k * 100 // max(1, len(jobs)):3d}%")
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode:
        raise RuntimeError("ffmpeg failed")
    srt = BUILD / f"film-{spec.name}" / "captions.srt"
    if not preview:
        out.with_suffix(".srt").write_text(srt.read_text(encoding="utf-8"), encoding="utf-8")
    log(f"✔ {out}  ({time.time() - t0:.0f}s)")
    return out


def film_still(name: str, t: float, scale: float = 1.0) -> Image.Image:
    spec = load_film(name)
    timing, _ = time_narration(spec, log=lambda *a: None)
    return Stage(spec, timing, scale).frame(t)
