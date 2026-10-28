"""Reusable paper-cut pieces for underwater films."""

from __future__ import annotations

import math

import numpy as np
from PIL import Image

from .paper import Canvas, blob, hexrgb, mix, premul_blur, wavy_top
from .world import Layer, Sprite

WATER_DEEP = (18, 58, 110)


def tint(rgb, z: float, water=WATER_DEEP) -> tuple[int, int, int]:
    """Atmospheric perspective: far things fade into the water colour."""
    f = 1 - 1 / max(z, 1.0) ** 0.9
    return mix(rgb, water, min(0.85, f * 1.05))


class LayerBuilder:
    """Paint a layer in world coordinates; it is stored at q px per world unit."""

    def __init__(self, name: str, z: float, bounds, q: float | None = None, seed: int = 0, shadow=0.3):
        self.name, self.z = name, z
        self.x0, self.y0, self.x1, self.y1 = bounds
        self.q = q if q is not None else 1.0 / z
        w = int((self.x1 - self.x0) * self.q) + 2
        h = int((self.y1 - self.y0) * self.q) + 2
        sb = 7 * self.q * z if z < 2 else 4
        self.c = Canvas(w, h, seed, shadow=shadow, shadow_offset=(int(5 * self.q * z), int(8 * self.q * z)),
                        shadow_blur=sb)

    def P(self, x, y):
        return ((x - self.x0) * self.q, (y - self.y0) * self.q)

    def _c(self, rgb, tinted):
        return tint(rgb, self.z) if tinted else tuple(rgb)

    def poly(self, pts, rgb, tinted=True, **kw):
        self.c.poly([self.P(x, y) for x, y in pts], self._c(rgb, tinted), **kw)

    def ellipse(self, cx, cy, rx, ry, rgb, tinted=True, **kw):
        x, y = self.P(cx, cy)
        self.c.ellipse(x, y, rx * self.q, ry * self.q, self._c(rgb, tinted), **kw)

    def lines(self, segs, rgb, tinted=True, **kw):
        self.c.lines([(*self.P(a, b), *self.P(c, d), w * self.q) for a, b, c, d, w in segs],
                     self._c(rgb, tinted), **kw)

    def build(self, blur: float = 0.0) -> Layer:
        img = premul_blur(self.c.img, blur) if blur else self.c.img
        ox, oy = self.x0, self.y0
        bb = img.getchannel("A").getbbox()          # crop to what was painted: far less to resample
        if bb:
            img = img.crop(bb)
            ox, oy = self.x0 + bb[0] / self.q, self.y0 + bb[1] / self.q
        return Layer(self.name, self.z, img, ox, oy, self.q, blur)


# --------------------------------------------------------------------------
# Pieces
# --------------------------------------------------------------------------

ROCK = [hexrgb("#6E6A8C"), hexrgb("#5D5A7E"), hexrgb("#7C7598"), hexrgb("#8A7F9E")]
SAND = hexrgb("#E8C98E")
SAND_DARK = hexrgb("#D9B274")
CORAL = [hexrgb("#FF7AA2"), hexrgb("#FFB25B"), hexrgb("#B98CFF"), hexrgb("#FF8C6B")]
KELP = [hexrgb("#3BAF6B"), hexrgb("#2E9A5E"), hexrgb("#56C27A")]
GRASS = [hexrgb("#47B36F"), hexrgb("#5CC47F")]


def rock(L: LayerBuilder, cx, cy, rx, ry, seed, color=None, moss=True):
    rng = np.random.default_rng(seed)
    col = color or ROCK[int(rng.integers(len(ROCK)))]
    L.poly(blob(cx, cy, rx, ry, seed, rough=0.1, flat_bottom=True), col)
    # a lighter top face and a few pebbly bumps
    L.poly(blob(cx - rx * 0.12, cy - ry * 0.35, rx * 0.62, ry * 0.42, seed + 1, rough=0.12), mix(col, (255, 255, 255), 0.16),
           shadow=0)
    if moss:
        for k in range(int(rng.integers(2, 5))):
            mx = cx + rng.uniform(-0.6, 0.6) * rx
            L.ellipse(mx, cy - ry * rng.uniform(0.55, 0.85), rx * rng.uniform(0.1, 0.18), ry * 0.12,
                      mix(KELP[0], (255, 255, 255), 0.2), shadow=0.15)


def sand(L: LayerBuilder, y, seed, amp=18, waves=6):
    L.poly(wavy_top(L.x0, L.x1, y, amp, waves, seed, bottom=L.y1), SAND, shadow=0.15)
    rng = np.random.default_rng(seed)
    for _ in range(int((L.x1 - L.x0) / 70)):
        x = rng.uniform(L.x0, L.x1)
        yy = y + rng.uniform(30, (L.y1 - y) * 0.8)
        L.ellipse(x, yy, rng.uniform(6, 16), rng.uniform(3, 7), SAND_DARK, shadow=0, emboss=0.5)
    # ripples
    for _ in range(int((L.x1 - L.x0) / 160)):
        x = rng.uniform(L.x0, L.x1)
        yy = y + rng.uniform(40, (L.y1 - y) * 0.7)
        L.lines([(x - 40, yy, x + 40, yy + rng.uniform(-4, 4), 4)], mix(SAND, (255, 255, 255), 0.25), shadow=0, emboss=0)


def seagrass(L: LayerBuilder, x, y, seed, height=120, blades=7):
    rng = np.random.default_rng(seed)
    for b in range(blades):
        bx = x + rng.uniform(-30, 30)
        h = height * rng.uniform(0.6, 1.1)
        lean = rng.uniform(-0.5, 0.5)
        pts = [(bx + lean * h * (k / 10) ** 1.6 * 0.5, y - h * k / 10) for k in range(11)]
        L.lines([(a[0], a[1], b_[0], b_[1], 9 * (1 - k / 10) + 3) for k, (a, b_) in enumerate(zip(pts, pts[1:]))],
                GRASS[b % 2], shadow=0.2)


def coral_branch(L: LayerBuilder, x, y, seed, height=160, color=None):
    rng = np.random.default_rng(seed)
    col = color or CORAL[int(rng.integers(len(CORAL)))]
    segs = []

    def grow(x0, y0, ang, length, width, depth):
        if depth == 0:
            return
        x1 = x0 + length * math.cos(ang)
        y1 = y0 - length * math.sin(ang)
        segs.append((x0, y0, x1, y1, width))
        for da in (-0.45, 0.4):
            grow(x1, y1, ang + da + rng.uniform(-0.2, 0.2), length * rng.uniform(0.62, 0.8), width * 0.75, depth - 1)

    grow(x, y, math.pi / 2 + rng.uniform(-0.2, 0.2), height * 0.38, height * 0.11, 4)
    L.lines(segs, col)
    for (_, _, x1, y1, w) in segs[-8:]:
        L.ellipse(x1, y1, w * 0.9, w * 0.9, mix(col, (255, 255, 255), 0.35), shadow=0)


def fan_coral(L: LayerBuilder, x, y, seed, size=150, color=None):
    rng = np.random.default_rng(seed)
    col = color or CORAL[int(rng.integers(len(CORAL)))]
    L.poly([(x + size * 0.9 * math.cos(a), y - size * math.sin(a) * 0.95) for a in np.linspace(0.15, math.pi - 0.15, 30)]
           + [(x + 12, y), (x - 12, y)], col)
    segs = [(x, y, x + size * 0.85 * math.cos(a), y - size * 0.85 * math.sin(a), 5) for a in np.linspace(0.35, math.pi - 0.35, 7)]
    L.lines(segs, mix(col, (255, 255, 255), 0.3), shadow=0, emboss=0.4)


def kelp_sprite(z: float, x: float, y: float, height: float, seed: int, q: float | None = None,
                sway: float = 3.5) -> Sprite:
    """A kelp stalk that sways from its holdfast."""
    rng = np.random.default_rng(seed)
    q = q if q is not None else 1.0 / z
    w, h = int(height * 0.5 * q) + 20, int(height * q) + 20
    c = Canvas(w, h, seed, shadow=0.22, shadow_offset=(int(4 * q * z), int(6 * q * z)), shadow_blur=5)
    base = (w / 2, h - 8)
    col = tint(KELP[int(rng.integers(len(KELP)))], z)
    n = 16
    stem = []
    for k in range(n + 1):
        f = k / n
        stem.append((base[0] + math.sin(f * 3 + seed) * w * 0.12, base[1] - f * (h - 24)))
    c.lines([(a[0], a[1], b[0], b[1], (7 - 3 * k / n) * q * z) for k, (a, b) in enumerate(zip(stem, stem[1:]))],
            mix(col, (0, 0, 0), 0.12))
    for k in range(2, n, 1):
        sx, sy = stem[k]
        side = 1 if k % 2 else -1
        L = w * rng.uniform(0.28, 0.42)
        leaf = [(sx, sy)]
        for j in range(1, 12):
            f = j / 11
            leaf.append((sx + side * L * f, sy - L * 0.55 * f + math.sin(f * math.pi) * -L * 0.12))
        for j in range(11, -1, -1):
            f = j / 11
            leaf.append((sx + side * L * f, sy - L * 0.55 * f + math.sin(f * math.pi) * L * 0.18))
        c.poly(leaf, mix(col, (255, 255, 255), rng.uniform(0, 0.12)))
    return Sprite(c.img, base, x, y, z, q, sway=sway * rng.uniform(0.7, 1.2), sway_hz=rng.uniform(0.1, 0.17),
                  phase=rng.uniform(0, 6.28))


def fish_image(length: float, rgb, seed: int, z: float = 1.0) -> Image.Image:
    w, h = int(length * 1.25) + 16, int(length * 0.7) + 16
    c = Canvas(w, h, seed, shadow=0.15, shadow_offset=(2, 3), shadow_blur=2)
    cx, cy = w * 0.45, h / 2
    col = tint(rgb, z)
    c.poly([(cx + length * 0.55, cy - length * 0.08), (cx + length * 0.8, cy - length * 0.28),
            (cx + length * 0.76, cy), (cx + length * 0.8, cy + length * 0.28), (cx + length * 0.55, cy + length * 0.08)],
           mix(col, (0, 0, 0), 0.1))
    c.ellipse(cx, cy, length * 0.45, length * 0.25, col)
    c.ellipse(cx - length * 0.06, cy - length * 0.02, length * 0.08, length * 0.2, mix(col, (255, 255, 255), 0.4), shadow=0)
    c.ellipse(cx - length * 0.27, cy - length * 0.05, length * 0.06, length * 0.06, (250, 248, 240), shadow=0)
    c.ellipse(cx - length * 0.28, cy - length * 0.05, length * 0.03, length * 0.03, (40, 30, 50), shadow=0, emboss=0)
    return c.img


def shark_image(length: float, z: float, seed: int = 5) -> Image.Image:
    w, h = int(length * 1.1) + 20, int(length * 0.55) + 20
    c = Canvas(w, h, seed, shadow=0)
    col = mix(tint(hexrgb("#2A3F66"), z), (10, 24, 52), 0.35)
    x0, cy = 10, h * 0.55
    body = []
    for k in range(41):
        f = k / 40
        body.append((x0 + f * length, cy - length * 0.13 * math.sin(math.pi * f ** 0.8)))
    for k in range(40, -1, -1):
        f = k / 40
        body.append((x0 + f * length, cy + length * 0.09 * math.sin(math.pi * f ** 0.8)))
    c.poly(body, col, emboss=0.3)
    c.poly([(x0 + length * 0.42, cy - length * 0.1), (x0 + length * 0.55, cy - length * 0.34),
            (x0 + length * 0.62, cy - length * 0.09)], col, emboss=0.3)                      # dorsal fin
    c.poly([(x0 + length * 0.95, cy - length * 0.02), (x0 + length * 1.08, cy - length * 0.24),
            (x0 + length * 1.04, cy), (x0 + length * 1.08, cy + length * 0.2), (x0 + length * 0.95, cy + length * 0.03)],
           col, emboss=0.3)                                                                    # tail
    c.poly([(x0 + length * 0.35, cy + length * 0.05), (x0 + length * 0.45, cy + length * 0.22),
            (x0 + length * 0.5, cy + length * 0.06)], col, emboss=0.3)
    return c.img


def surface_layer(z: float, y: float, bounds, seed: int = 0) -> Layer:
    """The bright, rippling underside of the sea surface, seen from below."""
    L = LayerBuilder("surface", z, bounds, seed=seed, shadow=0)
    top = hexrgb("#BFF3FF")
    L.poly([(L.x0, L.y0)] + [(x, yy) for x, yy in wavy_top(L.x0, L.x1, y, 22, 14, seed)[:-2]] + [(L.x1, L.y0)],
           top, tinted=False, emboss=0.6, shadow=0)
    rng = np.random.default_rng(seed)
    for _ in range(int((L.x1 - L.x0) / 60)):
        x = rng.uniform(L.x0, L.x1)
        L.ellipse(x, y + rng.uniform(-30, 40), rng.uniform(20, 70), rng.uniform(4, 9), (240, 255, 255), tinted=False,
                  shadow=0, emboss=0)
    return L.build(blur=1.5)


def glow_disc(radius: int, rgb, alpha: float = 1.0, power: float = 2.0) -> Image.Image:
    yy, xx = np.mgrid[-1:1:radius * 2j, -1:1:radius * 2j]
    r = np.sqrt(xx ** 2 + yy ** 2)
    a = (np.clip(1 - r, 0, 1) ** power * 255 * alpha).astype(np.uint8)
    arr = np.zeros((radius * 2, radius * 2, 4), np.uint8)
    arr[..., :3] = rgb
    arr[..., 3] = a
    return Image.fromarray(arr, "RGBA")


def dark_hole(L: LayerBuilder, cx, cy, rx, ry, seed):
    """The shadowy opening of a den, cut into a rock."""
    L.poly(blob(cx, cy, rx, ry, seed, rough=0.08), (28, 30, 58), shadow=0, emboss=-0.6, grain=0.6)
