"""Episode → MP4.

1. `build_timeline` synthesises the narration, times every segment and word,
   generates music + SFX, and writes the mixed soundtrack.
2. `Composer` draws any frame at time t (background → sprites → headline →
   captions). It is deterministic, so frames render in parallel processes.
3. `render` pipes the frames into ffmpeg together with the soundtrack.
"""

from __future__ import annotations

import json
import math
import multiprocessing as mp
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import audio, scenes, sprites, text, tts
from .captions import Chunk, chunk_words, to_srt
from .config import BUILD, OUTPUT, color, load_config
from .episode import Episode, Sprite

# --------------------------------------------------------------------------
# Timeline
# --------------------------------------------------------------------------


@dataclass
class SegTime:
    start: float          # when this segment's visuals begin
    end: float            # when the next segment's visuals begin
    speech_start: float
    speech_end: float


@dataclass
class Timeline:
    episode: Episode
    width: int
    height: int
    fps: int
    duration: float
    segs: list[SegTime]
    words: list[tts.Word]
    audio_path: Path
    scale: float = 1.0    # preview renders use < 1
    extra: dict = field(default_factory=dict)

    @property
    def n_frames(self) -> int:
        return int(math.ceil(self.duration * self.fps))


def build_timeline(ep: Episode, scale: float = 1.0, fps: int | None = None,
                   log=print) -> Timeline:
    cfg = load_config()
    rcfg, acfg = cfg["render"], cfg["audio"]
    sr = audio.SR
    w, h = ep.size
    w, h = int(w * scale) // 2 * 2, int(h * scale) // 2 * 2

    speeches = []
    for i, seg in enumerate(ep.segments):
        log(f"  voice {i + 1}/{len(ep.segments)}: {seg.say[:60]}")
        speeches.append(tts.speak(seg.say, ep.voice, seg.spoken))

    segs: list[SegTime] = []
    words: list[tts.Word] = []
    t = rcfg["lead_in"]
    vis_start = 0.0
    for seg, sp in zip(ep.segments, speeches):
        s0, s1 = t, t + sp.duration
        pause = seg.pause if seg.pause is not None else acfg["segment_pause"]
        segs.append(SegTime(vis_start, s1 + pause, s0, s1))
        words += [tts.Word(wd.text, wd.start + s0, wd.end + s0) for wd in sp.words]
        t = s1 + pause
        vis_start = t
    duration = t + rcfg["tail"]
    segs[-1].end = duration

    # --- soundtrack -------------------------------------------------------
    n = int(duration * sr) + 1
    narration = np.zeros(n, np.float32)
    for st, sp in zip(segs, speeches):
        audio._add(narration, sp.audio, int(st.speech_start * sr))

    narration *= 0.9 / (np.max(np.abs(narration)) + 1e-9)
    sfx = np.zeros(n, np.float32)
    pop_times: list[float] = []
    prev_keys: set = set()
    for i, (seg, st) in enumerate(zip(ep.segments, segs)):
        if i > 0 and _bg_key(seg) != _bg_key(ep.segments[i - 1]):
            audio._add(sfx, audio.sfx_whoosh(ep.seed + i) * 0.8, int(max(0, st.start - 0.2) * sr))
        keys = {s.key() for s in seg.sprites}
        for s in seg.sprites:
            if s.key() in prev_keys or s.enter == "none":
                continue
            at = st.start + s.delay + 0.02
            if all(abs(at - p) > 0.15 for p in pop_times):
                pop_times.append(at)
                audio._add(sfx, audio.sfx_pop(ep.seed + len(pop_times)), int(at * sr))
        prev_keys = keys
    if ep.segments[0].headline:
        audio._add(sfx, audio.sfx_ding() * 0.6, int(0.1 * sr))

    music = audio.MUSIC[ep.music](duration, seed=ep.seed)
    mixed = audio.mix(narration, music, sfx, acfg["music_volume"], acfg["duck"], acfg["sfx_volume"])

    out_dir = BUILD / ep.slug
    out_dir.mkdir(parents=True, exist_ok=True)
    wav = out_dir / "soundtrack.wav"
    audio.write_wav(wav, mixed)
    (out_dir / "captions.srt").write_text(to_srt(words), encoding="utf-8")
    return Timeline(ep, w, h, fps or rcfg["fps"], duration, segs, words, wav, scale)


def _bg_key(seg) -> str:
    return seg.bg + json.dumps(seg.bg_params, sort_keys=True)


# --------------------------------------------------------------------------
# Easing & motion
# --------------------------------------------------------------------------


def ease_out_back(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    c1 = 1.9
    return 1 + (c1 + 1) * (p - 1) ** 3 + c1 * (p - 1) ** 2


def ease_out_cubic(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    return 1 - (1 - p) ** 3


def smoothstep(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    return p * p * (3 - 2 * p)


@dataclass
class Pose:
    x: float
    y: float
    sx: float = 1.0
    sy: float = 1.0
    angle: float = 0.0
    alpha: float = 1.0
    lift: float = 0.0     # height above the ground (for shadows), px


def sprite_pose(s: Sprite, tau: float, seg_len: float, W: int, H: int, entering: bool = True) -> Pose:
    """Where a sprite is `tau` seconds after it appeared."""
    x, y = s.x * W, s.y * H
    size = s.size * W
    p = Pose(x, y, angle=s.rotate)
    m = s.motion
    if m == "float":
        p.y += math.sin(tau * 1.7) * 0.012 * H
        p.angle += math.sin(tau * 1.1) * 4
    elif m == "bounce":
        hop = abs(math.sin(math.pi * tau / 0.75))
        p.lift = hop * 0.045 * H
        p.y -= p.lift
        squash = (1 - hop) ** 6
        p.sy, p.sx = 1 - 0.14 * squash, 1 + 0.1 * squash
    elif m == "wiggle":
        p.angle += math.sin(tau * 7) * 9
    elif m == "spin":
        p.angle -= tau * 80
    elif m == "pulse":
        beat = max(0.0, math.sin(tau * 2 * math.pi * 1.1)) ** 6
        p.sx = p.sy = 1 + 0.1 * beat
    elif m == "shake":
        p.x += math.sin(tau * 38) * 0.006 * W
        p.angle += math.sin(tau * 29) * 2
    elif m == "sway":
        p.angle += math.sin(tau * 1.6) * 11
    elif m == "walk":
        tx, ty = s.to or (s.x, s.y)
        f = min(1.0, tau / max(seg_len, 0.1))
        p.x = (s.x + (tx - s.x) * f) * W
        p.y = (s.y + (ty - s.y) * f) * H
        hop = abs(math.sin(tau * 7))
        p.lift = hop * 0.012 * H
        p.y -= p.lift
        p.angle += math.sin(tau * 7) * 4
    elif m == "grow":
        g = 0.35 + 0.65 * ease_out_cubic(tau / max(seg_len * 0.8, 0.1))
        p.sx = p.sy = g
    elif m == "peek":
        f = ease_out_back(tau / 0.8)
        p.y += (1 - f) * size * 0.9
        p.alpha = min(1.0, tau / 0.3)

    if entering and tau < 0.6:
        e = s.enter
        if e == "pop":
            k = ease_out_back(tau / 0.4)
            p.sx *= k
            p.sy *= k
        elif e == "fade":
            p.alpha *= min(1.0, tau / 0.5)
        elif e in ("slide_left", "slide_right", "slide_up"):
            f = ease_out_cubic(tau / 0.55)
            if e == "slide_left":
                p.x = -size + (p.x + size) * f
            elif e == "slide_right":
                p.x = W + size - (W + size - p.x) * f
            else:
                p.y = H + size - (H + size - p.y) * f
    return p


# --------------------------------------------------------------------------
# Composer
# --------------------------------------------------------------------------


class Composer:
    EXIT = 0.25

    def __init__(self, tl: Timeline):
        self.tl = tl
        self.ep = tl.episode
        self.W, self.H = tl.width, tl.height
        self.short = self.H > self.W
        self.accent = color(self.ep.accent)
        self.xf = load_config()["render"]["transition"]
        self._bgs: dict[str, scenes.Background] = {}
        self._text_cache: dict = {}
        self.chunks: list[Chunk] = chunk_words(tl.words, max_words=3 if self.short else 4,
                                               max_chars=16 if self.short else 26)
        segs = self.ep.segments
        # background blocks: consecutive segments sharing a background share its clock
        self.block_start = []
        for i, seg in enumerate(segs):
            same = i > 0 and _bg_key(seg) == _bg_key(segs[i - 1])
            self.block_start.append(self.block_start[-1] if same else tl.segs[i].start)
        # sprite birth times, carried across segments when a sprite stays put
        self.births: list[dict] = []
        for i, seg in enumerate(segs):
            prev = self.births[-1] if i else {}
            self.births.append({s.key(): prev.get(s.key(), tl.segs[i].start + s.delay) for s in seg.sprites})
        shadow = Image.new("RGBA", (200, 60), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).ellipse((10, 10, 190, 50), fill=(0, 0, 0, 90))
        self.shadow = shadow.filter(ImageFilter.GaussianBlur(7))
        self.watermark = None
        if not self.short and load_config()["render"].get("watermark"):
            from .config import ASSETS
            wm = ASSETS / "brand" / "watermark.png"
            if wm.exists():
                img = Image.open(wm).convert("RGBA")
                s = int(self.H * 0.09)
                self.watermark = scenes.with_alpha(img.resize((s, s), Image.LANCZOS), 0.7)

    # -- helpers -------------------------------------------------------------
    def bg(self, i: int) -> scenes.Background:
        seg = self.ep.segments[i]
        key = _bg_key(seg)
        if key not in self._bgs:
            self._bgs[key] = scenes.make(seg.bg, self.W, self.H, seg.bg_params, self.ep.seed + len(self._bgs))
        return self._bgs[key]

    def seg_index(self, t: float) -> int:
        for i, st in enumerate(self.tl.segs):
            if t < st.end:
                return i
        return len(self.tl.segs) - 1

    # -- layers --------------------------------------------------------------
    def draw_background(self, i: int, t: float) -> Image.Image:
        img = self.bg(i).frame(t - self.block_start[i])
        st = self.tl.segs[i]
        if i > 0 and self.block_start[i] == st.start and t - st.start < self.xf:
            prev = self.bg(i - 1).frame(t - self.block_start[i - 1])
            img = Image.blend(prev, img, smoothstep((t - st.start) / self.xf))
        return img

    def draw_sprite(self, img: Image.Image, s: Sprite, pose: Pose) -> None:
        base = sprites.load(s.name)
        w = s.size * self.W * pose.sx
        h = s.size * self.W * base.height / base.width * pose.sy
        if w < 2 or h < 2 or pose.alpha <= 0.01:
            return
        if s.shadow or s.motion in ("bounce", "walk"):
            sw = int(s.size * self.W * 0.8 * (1 - 0.5 * pose.lift / (0.05 * self.H + 1)) * min(pose.sx, 1.2))
            if sw > 4:
                sh = self.shadow.resize((sw, max(2, sw // 4)), Image.BILINEAR)
                ground_y = pose.y + pose.lift + s.size * self.W * base.height / base.width / 2
                img.paste(sh, (int(pose.x - sw / 2), int(ground_y - sh.height / 2)), sh)
        spr = base.resize((max(1, int(w)), max(1, int(h))), Image.BILINEAR)
        if s.flip:
            spr = spr.transpose(Image.FLIP_LEFT_RIGHT)
        if abs(pose.angle) > 0.3:
            spr = spr.rotate(pose.angle, resample=Image.BICUBIC, expand=True)
        if pose.alpha < 1:
            spr = scenes.with_alpha(spr, pose.alpha)
        img.paste(spr, (int(pose.x - spr.width / 2), int(pose.y - spr.height / 2)), spr)
        if s.label:
            lab = self._label(s.label)
            img.paste(lab, (int(pose.x - lab.width / 2), int(pose.y + h / 2 + self.W * 0.005)), lab)

    def _label(self, label: str) -> Image.Image:
        key = ("label", label)
        if key not in self._text_cache:
            f = text.font(int(self.W * (0.06 if self.short else 0.03)), text.BODY)
            self._text_cache[key] = text.render_block([label], f, stroke_ratio=0.14)
        return self._text_cache[key]

    def draw_sprites(self, img: Image.Image, i: int, t: float) -> None:
        segs = self.ep.segments
        st = self.tl.segs[i]
        seg_len = st.end - st.start
        # sprites leaving from the previous segment shrink away
        if i > 0 and t - st.start < self.EXIT:
            keep = {s.key() for s in segs[i].sprites}
            k = 1 - smoothstep((t - st.start) / self.EXIT)
            pst = self.tl.segs[i - 1]
            for s in segs[i - 1].sprites:
                if s.key() in keep:
                    continue
                born = self.births[i - 1][s.key()]
                pose = sprite_pose(s, t - born, pst.end - pst.start, self.W, self.H)
                pose.sx *= k
                pose.sy *= k
                self.draw_sprite(img, s, pose)
        for s in segs[i].sprites:
            born = self.births[i][s.key()]
            if t < born:
                continue
            first_seg = next(j for j in range(i, -1, -1)
                             if j == 0 or s.key() not in {x.key() for x in segs[j - 1].sprites})
            span = self.tl.segs[i].end - self.tl.segs[first_seg].start
            pose = sprite_pose(s, t - born, span if s.motion in ("walk", "grow") else seg_len, self.W, self.H)
            self.draw_sprite(img, s, pose)

    def draw_headline(self, img: Image.Image, i: int, t: float) -> None:
        segs = self.ep.segments
        head = segs[i].headline
        if not head:
            return
        j = i
        while j > 0 and segs[j - 1].headline == head:
            j -= 1
        tau = t - self.tl.segs[j].start
        key = ("head", head)
        if key not in self._text_cache:
            max_w = int(self.W * (0.88 if self.short else 0.8))
            f, lines = text.fit_font(head.upper(), max_w, 3 if self.short else 2,
                                     int(self.W * (0.12 if self.short else 0.075)))
            self._text_cache[key] = text.render_block(lines, f, fill=self.accent, stroke_ratio=0.1)
        block = self._text_cache[key]
        k = ease_out_back(tau / 0.4)
        bob = math.sin(tau * 2.2) * self.H * 0.004
        if k < 0.999:
            block = block.resize((max(1, int(block.width * k)), max(1, int(block.height * k))), Image.BILINEAR)
        cy = self.H * (0.15 if self.short else 0.14) + bob
        img.paste(block, (int(self.W / 2 - block.width / 2), int(cy - block.height / 2)), block)

    def draw_captions(self, img: Image.Image, t: float) -> None:
        idx = next((k for k, c in enumerate(self.chunks) if c.start <= t < c.end), None)
        if idx is None:
            return
        c = self.chunks[idx]
        active = max((k for k, w in enumerate(c.words) if w.start <= t), default=0)
        key = ("cap", idx, active)
        if key not in self._text_cache:
            f = text.font(int(self.W * (0.095 if self.short else 0.052)))
            runs = [(w.text.upper(), self.accent if k == active else (255, 255, 255))
                    for k, w in enumerate(c.words)]
            max_w = self.W * 0.9
            lines, cur = [], []
            for r in runs:
                if cur and f.getlength(" ".join(x[0] for x in cur + [r])) > max_w:
                    lines.append(cur)
                    cur = []
                cur.append(r)
            lines.append(cur)
            self._text_cache[key] = text.render_block(lines, f, stroke_ratio=0.12)
        block = self._text_cache[key]
        k = 1 + 0.12 * (1 - ease_out_cubic((t - c.start) / 0.12))
        if k > 1.001:
            block = block.resize((int(block.width * k), int(block.height * k)), Image.BILINEAR)
        cy = self.H * (0.72 if self.short else 0.86)
        img.paste(block, (int(self.W / 2 - block.width / 2), int(cy - block.height / 2)), block)

    def frame(self, t: float) -> Image.Image:
        i = self.seg_index(t)
        img = self.draw_background(i, t)
        self.draw_sprites(img, i, t)
        self.draw_headline(img, i, t)
        self.draw_captions(img, t)
        if self.watermark is not None:
            m = int(self.H * 0.03)
            img.paste(self.watermark, (self.W - self.watermark.width - m, self.H - self.watermark.height - m), self.watermark)
        return img


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

_COMPOSER: Composer | None = None


def _init_worker(tl: Timeline) -> None:
    global _COMPOSER
    _COMPOSER = Composer(tl)


def _render_frame(i: int) -> bytes:
    assert _COMPOSER is not None
    return _COMPOSER.frame(i / _COMPOSER.tl.fps).tobytes()


def render(ep: Episode, out: Path | None = None, scale: float = 1.0, fps: int | None = None,
           workers: int | None = None, log=print) -> Path:
    t0 = time.time()
    log(f"▶ {ep.slug}: building soundtrack")
    tl = build_timeline(ep, scale, fps, log)
    rcfg = load_config()["render"]
    out = out or OUTPUT / f"{ep.slug}{'' if scale == 1 else '-preview'}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    lufs = load_config()["audio"]["loudness_lufs"]
    cmd = [
        audio.ffmpeg_exe(), "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{tl.width}x{tl.height}", "-r", str(tl.fps), "-i", "-",
        "-i", str(tl.audio_path),
        "-c:v", "libx264", "-preset", rcfg["preset"] if scale == 1 else "veryfast",
        "-crf", str(rcfg["crf"]), "-pix_fmt", "yuv420p",
        "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-shortest", "-movflags", "+faststart", str(out),
    ]
    n = tl.n_frames
    log(f"▶ rendering {n} frames ({tl.duration:.1f}s, {tl.width}x{tl.height}@{tl.fps}) with {workers} workers")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    step = max(1, n // 20)

    def frames():
        if workers == 1:
            _init_worker(tl)
            for i in range(n):
                yield _render_frame(i)
        else:
            with mp.get_context("spawn" if sys.platform != "linux" else "fork").Pool(
                    workers, initializer=_init_worker, initargs=(tl,)) as pool:
                yield from pool.imap(_render_frame, range(n), chunksize=4)

    try:
        for i, data in enumerate(frames()):
            proc.stdin.write(data)
            if i % step == 0:
                log(f"  {i * 100 // n:3d}%  frame {i}/{n}")
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode:
        raise RuntimeError("ffmpeg failed")
    srt = BUILD / ep.slug / "captions.srt"
    if scale == 1 and srt.exists():
        out.with_suffix(".srt").write_text(srt.read_text(encoding="utf-8"), encoding="utf-8")
    log(f"✔ {out}  ({time.time() - t0:.0f}s)")
    return out


def still(ep: Episode, t: float, scale: float = 1.0) -> Image.Image:
    """Render a single frame (handy for checking layouts)."""
    tl = build_timeline(ep, scale, log=lambda *_: None)
    return Composer(tl).frame(t)
