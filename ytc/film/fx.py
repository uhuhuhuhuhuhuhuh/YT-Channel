"""Screen effects: light rays, marine snow, bubbles, grain, vignette, word cards."""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .. import text as ytext
from .paper import Canvas, blit, hexrgb
from .world import Camera, to_screen


def light_rays(W: int, H: int, seed: int = 0, n: int = 9) -> Image.Image:
    rng = np.random.default_rng(seed)
    img = Image.new("RGBA", (int(W * 1.3), H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for _ in range(n):
        x = rng.uniform(0, img.width)
        w0, w1 = rng.uniform(20, 70), rng.uniform(120, 320)
        lean = rng.uniform(0.15, 0.35) * H
        d.polygon([(x - w0, 0), (x + w0, 0), (x + w1 + lean, H), (x - w1 + lean, H)],
                  fill=(255, 255, 240, int(rng.uniform(16, 34))))
    img = img.filter(ImageFilter.GaussianBlur(24))
    fade = (np.linspace(1, 0, H, dtype=np.float32) ** 1.3)[:, None]
    arr = np.asarray(img).copy()
    arr[..., 3] = (arr[..., 3] * fade).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def vignette(W: int, H: int, strength: float = 0.55) -> Image.Image:
    yy, xx = np.mgrid[-1:1:H * 1j, -1:1:W * 1j]
    r = np.sqrt((xx * 0.85) ** 2 + yy ** 2)
    a = np.clip((r - 0.55) / 0.75, 0, 1) ** 1.6 * 255 * strength
    arr = np.zeros((H, W, 4), np.uint8)
    arr[..., :3] = (6, 14, 30)
    arr[..., 3] = a.astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def grain_frames(W: int, H: int, n: int = 6, strength: int = 14, seed: int = 0) -> list[Image.Image]:
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        g = rng.integers(0, 2, (H // 2, W // 2), dtype=np.uint8) * 255
        a = rng.integers(0, strength, (H // 2, W // 2), dtype=np.uint8)
        arr = np.stack([g, g, g, a], -1)
        out.append(Image.fromarray(arr, "RGBA").resize((W, H), Image.NEAREST))
    return out


def soft_dot(r: int, rgb=(235, 245, 255), alpha: float = 0.8) -> Image.Image:
    size = max(3, int(r * 4))
    yy, xx = np.mgrid[-1:1:size * 1j, -1:1:size * 1j]
    d = np.sqrt(xx ** 2 + yy ** 2)
    a = np.clip(1 - d, 0, 1) ** 1.5 * 255 * alpha
    arr = np.zeros((size, size, 4), np.uint8)
    arr[..., :3] = rgb
    arr[..., 3] = a.astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


class MarineSnow:
    """Drifting specks at a given depth (world space, so they parallax)."""

    def __init__(self, z, bounds, count, seed=0, size=2.2):
        rng = np.random.default_rng(seed)
        self.z = z
        self.x0, self.y0, self.x1, self.y1 = bounds
        self.x = rng.uniform(self.x0, self.x1, count)
        self.y = rng.uniform(self.y0, self.y1, count)
        self.vx = rng.uniform(-4, 6, count)
        self.vy = rng.uniform(-3, 5, count)
        self.ph = rng.uniform(0, 6.28, count)
        self.dots = [soft_dot(size * k / z ** 0.5, alpha=0.6) for k in (0.7, 1.0, 1.4)]
        self.kind = rng.integers(0, 3, count)

    def draw(self, frame, cam: Camera, t: float):
        W, H = frame.size
        wx = (self.x1 - self.x0)
        wy = (self.y1 - self.y0)
        xs = self.x0 + (self.x - self.x0 + self.vx * t + 6 * np.sin(t * 0.7 + self.ph)) % wx
        ys = self.y0 + (self.y - self.y0 + self.vy * t) % wy
        for x, y, k in zip(xs, ys, self.kind):
            sx, sy, _ = to_screen(x, y, self.z, cam, W, H)
            if -10 < sx < W + 10 and -10 < sy < H + 10:
                dot = self.dots[k]
                blit(frame, dot, sx - dot.width / 2, sy - dot.height / 2)


def bubble_image(r: float) -> Image.Image:
    size = int(r * 2) + 4
    img = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size * 2
    d.ellipse((2, 2, s - 3, s - 3), fill=(220, 245, 255, 50), outline=(235, 250, 255, 200), width=max(2, int(r * 0.25)))
    d.ellipse((s * 0.25, s * 0.22, s * 0.45, s * 0.38), fill=(255, 255, 255, 230))
    return img.resize((size, size), Image.LANCZOS)


class Bubbles:
    """Bubble puffs: spawn(t, x, y, n) at world points on depth z."""

    def __init__(self, z: float = 1.0, seed: int = 0):
        self.z = z
        self.rng = np.random.default_rng(seed)
        self.items: list[tuple] = []
        self.imgs = [bubble_image(r) for r in (4, 6, 9, 13)]

    def spawn(self, t, x, y, n=8, spread=40):
        for _ in range(n):
            self.items.append((t + self.rng.uniform(0, 0.4), x + self.rng.uniform(-spread, spread),
                               y + self.rng.uniform(-spread / 2, spread / 2), int(self.rng.integers(0, 4)),
                               self.rng.uniform(70, 140), self.rng.uniform(0, 6.28)))

    def draw(self, frame, cam: Camera, t: float):
        W, H = frame.size
        for t0, x, y, k, speed, ph in self.items:
            age = t - t0
            if age < 0 or age > 4:
                continue
            by = y - speed * age
            bx = x + 10 * math.sin(age * 5 + ph)
            sx, sy, s = to_screen(bx, by, self.z, cam, W, H)
            im = self.imgs[k]
            if s > 1.15:
                im = im.resize((max(2, int(im.width * s)), max(2, int(im.height * s))), Image.BILINEAR)
            fade = min(1.0, (4 - age) / 1.0)
            if fade < 1:
                im = im.copy()
                im.putalpha(im.getchannel("A").point(lambda v: int(v * fade)))
            blit(frame, im, sx - im.width / 2, sy - im.height / 2)


def word_card(text: str, height: int = 120, rgb="#FFF6E3", ink="#2B2140", seed: int = 0) -> Image.Image:
    """A hand-cut paper tag with a word on it."""
    f = ytext.font(int(height * 0.52), ytext.BODY, "Bold")
    tw = f.getlength(text)
    w = int(tw + height * 0.9)
    c = Canvas(w + 40, height + 40, seed, shadow=0.35, shadow_offset=(6, 9), shadow_blur=8)
    c.poly([(20, 24), (w + 16, 20), (w + 20, height + 14), (24, height + 20)], hexrgb(rgb))
    img = c.img
    d = ImageDraw.Draw(img)
    d.text(((w + 40) / 2, (height + 40) / 2 + 2), text, font=f, fill=hexrgb(ink), anchor="mm")
    return img


def title_card(lines: list[str], height: int = 150, seed: int = 0) -> Image.Image:
    """Stacked paper strips with the film's title."""
    f = ytext.font(int(height * 0.55), ytext.BODY, "Bold")
    strips = []
    for k, ln in enumerate(lines):
        tw = f.getlength(ln)
        w = int(tw + height * 0.8)
        c = Canvas(w + 40, height + 40, seed + k, shadow=0.4, shadow_offset=(7, 10), shadow_blur=9)
        col = hexrgb("#FFF6E3") if k % 2 == 0 else hexrgb("#FFD23F")
        c.poly([(20, 22 + k * 2), (w + 18, 20), (w + 20, height + 16), (22, height + 20 - k * 2)], col)
        d = ImageDraw.Draw(c.img)
        d.text(((w + 40) / 2, (height + 40) / 2 + 3), ln, font=f, fill=hexrgb("#2B2140"), anchor="mm")
        strips.append(c.img.rotate((-2.5, 2, -1.5)[k % 3], resample=Image.BICUBIC, expand=True))
    W = max(s.width for s in strips)
    H = sum(int(s.height * 0.82) for s in strips) + 30
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    y = 0
    for s in strips:
        out.alpha_composite(s, ((W - s.width) // 2, y))
        y += int(s.height * 0.82)
    return out


def place(frame: Image.Image, img: Image.Image, cx: float, cy: float, scale: float = 1.0, angle: float = 0.0,
          alpha: float = 1.0) -> None:
    if alpha <= 0.01 or scale <= 0.01:
        return
    im = img
    if abs(scale - 1) > 0.01:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BILINEAR)
    if abs(angle) > 0.2:
        im = im.rotate(angle, resample=Image.BICUBIC, expand=True)
    if alpha < 0.999:
        im = im.copy()
        im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
    blit(frame, im, cx - im.width / 2, cy - im.height / 2)
