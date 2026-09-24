"""Procedural, animated backgrounds.

Every background builds its static art once (gradients, hills, moon…) and then
animates cheap layers per frame (particles, clouds, fog, rays). Nothing here
uses outside footage, so every frame belongs to the channel.

Add a background: subclass `Background`, implement `build()` and optionally
`animate()`, and register it in `BACKGROUNDS`.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .config import color

# --------------------------------------------------------------------------
# Art helpers
# --------------------------------------------------------------------------


def gradient(w: int, h: int, stops: list[tuple[float, str]]) -> Image.Image:
    """Vertical gradient. stops = [(0.0, "#hex"), ..., (1.0, "#hex")]."""
    ys = np.linspace(0, 1, h)
    pos = [s[0] for s in stops]
    cols = np.array([color(s[1]) for s in stops], dtype=float)
    rgb = np.stack([np.interp(ys, pos, cols[:, c]) for c in range(3)], axis=1)
    arr = np.repeat(rgb[:, None, :], w, axis=1)
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def radial(size: int, rgb, alpha: float = 1.0, power: float = 2.0) -> Image.Image:
    """Soft round glow sprite."""
    yy, xx = np.mgrid[-1:1:size * 1j, -1:1:size * 1j]
    r = np.sqrt(xx ** 2 + yy ** 2)
    a = np.clip(1 - r, 0, 1) ** power * 255 * alpha
    arr = np.zeros((size, size, 4), np.uint8)
    arr[..., :3] = rgb
    arr[..., 3] = a.astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def disc(size: int, rgb, alpha: int = 255, blur: float = 0) -> Image.Image:
    pad = int(blur * 3)
    img = Image.new("RGBA", (size + 2 * pad, size + 2 * pad), (*rgb, 0))
    ImageDraw.Draw(img).ellipse((pad, pad, pad + size, pad + size), fill=(*rgb, alpha))
    return img.filter(ImageFilter.GaussianBlur(blur)) if blur else img


def bubble(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    lw = max(2, size // 14)
    d.ellipse((0, 0, size - 1, size - 1), fill=(255, 255, 255, 40), outline=(255, 255, 255, 170), width=lw)
    s = size * 0.22
    d.ellipse((size * 0.22, size * 0.2, size * 0.22 + s, size * 0.2 + s * 0.8), fill=(255, 255, 255, 200))
    return img


def cloud(width: int, rng: np.random.Generator, rgb=(255, 255, 255), alpha: int = 235) -> Image.Image:
    h = int(width * 0.55)
    img = Image.new("RGBA", (width, h), (*rgb, 0))
    d = ImageDraw.Draw(img)
    base = h * 0.78
    d.rounded_rectangle((width * 0.08, base - h * 0.28, width * 0.92, base), radius=int(h * 0.14), fill=(*rgb, alpha))
    for _ in range(5):
        r = rng.uniform(0.18, 0.3) * width
        cx = rng.uniform(0.25, 0.75) * width
        cy = base - r * rng.uniform(0.5, 0.95)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*rgb, alpha))
    return img.filter(ImageFilter.GaussianBlur(width * 0.006))


def value_noise(w: int, h: int, scale: int, rng: np.random.Generator, octaves: int = 3) -> np.ndarray:
    out = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        cells = max(2, scale * 2 ** o)
        small = rng.random((max(2, cells * h // max(w, 1)), cells)).astype(np.float32)
        layer = Image.fromarray((small * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
        out += np.asarray(layer, np.float32) / 255 * amp
        total += amp
        amp *= 0.5
    return out / total


def fog_strip(w: int, h: int, rng: np.random.Generator, rgb=(200, 190, 255), alpha: float = 0.45) -> Image.Image:
    n = value_noise(w, h, 6, rng, 3)
    ys = np.linspace(0, 1, h)[:, None]
    fade = np.sin(np.pi * ys) ** 1.5
    xs = np.linspace(0, 1, w)[None, :]
    edge = np.clip(np.minimum(xs, 1 - xs) * 8, 0, 1)
    a = np.clip((n - 0.35) * 2.2, 0, 1) * fade * edge * alpha * 255
    arr = np.zeros((h, w, 4), np.uint8)
    arr[..., :3] = rgb
    arr[..., 3] = a.astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def star_shape(size: int, rgb, points: int = 5, inner: float = 0.45) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    c = size / 2
    pts = []
    for i in range(points * 2):
        r = c * (1 if i % 2 == 0 else inner)
        a = math.pi * i / points - math.pi / 2
        pts.append((c + r * math.cos(a), c + r * math.sin(a)))
    ImageDraw.Draw(img).polygon(pts, fill=(*rgb, 255))
    return img


def hills(img: Image.Image, y: float, amp: float, waves: float, rgb, phase: float = 0.0) -> None:
    w, h = img.size
    xs = np.linspace(0, w, 60)
    top = h * y + amp * h * np.sin(xs / w * math.pi * waves + phase)
    poly = [(float(x), float(t)) for x, t in zip(xs, top)] + [(w, h), (0, h)]
    ImageDraw.Draw(img).polygon(poly, fill=tuple(rgb))


def with_alpha(img: Image.Image, factor: float) -> Image.Image:
    if factor >= 0.999:
        return img
    r, g, b, a = img.split()
    a = a.point(lambda v: int(v * max(0.0, factor)))
    return Image.merge("RGBA", (r, g, b, a))


# --------------------------------------------------------------------------
# Particles
# --------------------------------------------------------------------------


class Particles:
    """Sprites drifting with constant velocity + wobble, wrapping at the edges."""

    def __init__(self, w: int, h: int, rng: np.random.Generator, sprites: list[Image.Image],
                 count: int, vx=(0, 0), vy=(0, 0), wobble=(0.0, 0.0), region=(0.0, 1.0),
                 twinkle: float = 0.0, spin: bool = False):
        self.w, self.h = w, h
        self.twinkle = twinkle
        if spin:
            sprites = [s.rotate(a, resample=Image.BICUBIC, expand=True) for s in sprites for a in range(0, 360, 45)]
        self.sprites = sprites
        if twinkle:
            self.faded = [[with_alpha(s, f) for f in (0.25, 0.5, 0.75, 1.0)] for s in sprites]
        self.x0 = rng.uniform(0, w, count)
        self.y0 = rng.uniform(region[0] * h, region[1] * h, count)
        self.vx = rng.uniform(*vx, count) * w
        self.vy = rng.uniform(*vy, count) * h
        self.amp = rng.uniform(0.3, 1.0, count) * wobble[0] * w
        self.freq = rng.uniform(0.6, 1.4, count) * wobble[1]
        self.phase = rng.uniform(0, 2 * math.pi, count)
        self.idx = rng.integers(0, len(sprites), count)
        self.spin = spin
        self.region = region

    def draw(self, img: Image.Image, t: float) -> None:
        m = max(s.width for s in self.sprites)
        span_x = self.w + 2 * m
        y_lo, y_hi = self.region[0] * self.h - m, self.region[1] * self.h + m
        span_y = y_hi - y_lo
        xs = (self.x0 + self.vx * t + self.amp * np.sin(self.freq * t + self.phase) + m) % span_x - m
        ys = (self.y0 + self.vy * t - y_lo) % span_y + y_lo
        for i in range(len(xs)):
            k = int(self.idx[i])
            if self.spin:
                k = (k // 8) * 8 + int((t * 2 + self.phase[i]) % 8)
            if self.twinkle:
                lvl = 0.5 + 0.5 * math.sin(t * self.twinkle * self.freq[i] + self.phase[i])
                spr = self.faded[k][min(3, int(lvl * 4))]
            else:
                spr = self.sprites[k]
            img.paste(spr, (int(xs[i] - spr.width / 2), int(ys[i] - spr.height / 2)), spr)


# --------------------------------------------------------------------------
# Backgrounds
# --------------------------------------------------------------------------


class Background:
    ground = 0.8            # y (fraction) where sprite shadows sit

    def __init__(self, w: int, h: int, params: dict | None = None, seed: int = 0):
        self.w, self.h = w, h
        self.p = params or {}
        self.rng = np.random.default_rng(seed)
        self.u = min(w, h) / 1080           # unit scale: 1.0 at 1080p
        self.base = self.build()

    def build(self) -> Image.Image:
        raise NotImplementedError

    def animate(self, img: Image.Image, t: float) -> None:
        pass

    def frame(self, t: float) -> Image.Image:
        img = self.base.copy()
        self.animate(img, t)
        return img

    def S(self, v: float) -> int:
        return max(1, int(v * self.u))


class Sunny(Background):
    ground = 0.86

    def build(self):
        img = gradient(self.w, self.h, [(0, "#3EB6F2"), (0.6, "#8FDcFF"), (1, "#D6F6FF")])
        hills(img, 0.83, 0.02, 3, color("#7BD66A"), 0.5)
        hills(img, 0.88, 0.015, 2, color("#4FBF5A"), 2.0)
        sx, sy = int(self.w * 0.84), int(self.h * 0.09)
        glow = radial(self.S(520), color("#FFF1A8"), 0.8)
        img.paste(glow, (sx - glow.width // 2, sy - glow.height // 2), glow)
        self.sun_pos = (sx, sy)
        rays = Image.new("RGBA", (self.S(460),) * 2, (0, 0, 0, 0))
        d = ImageDraw.Draw(rays)
        c = rays.width / 2
        for i in range(12):
            a = i * math.pi / 6
            pts = [(c, c), (c + c * math.cos(a - 0.1), c + c * math.sin(a - 0.1)),
                   (c + c * math.cos(a + 0.1), c + c * math.sin(a + 0.1))]
            d.polygon(pts, fill=(255, 226, 90, 150))
        self.rays = rays
        self.sun = disc(self.S(190), color("sunshine"))
        self.clouds = Particles(self.w, self.h, self.rng, [cloud(self.S(w), self.rng) for w in (300, 380, 460)],
                                count=5, vx=(0.012, 0.03), region=(0.05, 0.5))
        return img

    def animate(self, img, t):
        r = self.rays.rotate(t * 12, resample=Image.BILINEAR)
        sx, sy = self.sun_pos
        img.paste(r, (sx - r.width // 2, sy - r.height // 2), r)
        img.paste(self.sun, (sx - self.sun.width // 2, sy - self.sun.height // 2), self.sun)
        self.clouds.draw(img, t)


class Ocean(Background):
    ground = 0.9

    def build(self):
        img = gradient(self.w, self.h, [(0, "#29C5E6"), (0.35, "#1477C9"), (1, "#0A2F73")])
        hills(img, 0.92, 0.012, 4, color("#E9C98B"), 1.0)
        rays = Image.new("RGBA", (self.w, int(self.h * 0.8)), (0, 0, 0, 0))
        d = ImageDraw.Draw(rays)
        for i in range(7):
            x = self.w * (i + 0.5) / 7 + self.rng.uniform(-40, 40) * self.u
            wd = self.S(self.rng.uniform(40, 110))
            d.polygon([(x - wd, 0), (x + wd, 0), (x + wd * 2.2 + self.w * 0.15, rays.height), (x - wd * 0.2 + self.w * 0.15, rays.height)],
                      fill=(255, 255, 255, 34))
        rays = rays.filter(ImageFilter.GaussianBlur(self.S(18)))
        fade = np.linspace(1, 0, rays.height, dtype=np.float32)[:, None] ** 1.5
        arr = np.asarray(rays).copy()
        arr[..., 3] = (arr[..., 3] * fade).astype(np.uint8)
        self.rays = Image.fromarray(arr, "RGBA")
        self.bubbles = Particles(self.w, self.h, self.rng, [bubble(self.S(s)) for s in (18, 26, 36, 50)],
                                 count=26, vy=(-0.06, -0.025), wobble=(0.01, 2.0))
        self.weed_x = [self.w * f for f in (0.06, 0.13, 0.88, 0.95)]
        return img

    def animate(self, img, t):
        off = int(math.sin(t * 0.6) * 30 * self.u)
        img.paste(self.rays, (off, 0), self.rays)
        d = ImageDraw.Draw(img)
        for k, x0 in enumerate(self.weed_x):
            pts = []
            height = self.h * (0.2 + 0.05 * (k % 2))
            for j in range(12):
                f = j / 11
                y = self.h * 0.95 - f * height
                x = x0 + math.sin(t * 1.4 + k + f * 3) * 30 * self.u * f
                pts.append((x, y))
            d.line(pts, fill=color("#2FBF71") if k % 2 else color("#1E9E5A"), width=self.S(22), joint="curve")
        self.bubbles.draw(img, t)


class DeepSea(Ocean):
    """Dark water with glowing specks: for the creepy-but-true deep-sea facts."""

    def build(self):
        img = gradient(self.w, self.h, [(0, "#0B2A5B"), (0.5, "#06163A"), (1, "#020816")])
        specks = [radial(self.S(s), color(c), 1.0, 1.2) for s in (30, 46, 64) for c in ("#6CF2FF", "#9BE564")]
        self.specks = Particles(self.w, self.h, self.rng, specks, count=40, vx=(-0.004, 0.004),
                                vy=(-0.01, 0.004), wobble=(0.01, 0.8), twinkle=1.5)
        self.bubbles = Particles(self.w, self.h, self.rng, [bubble(self.S(s)) for s in (14, 20, 28)],
                                 count=10, vy=(-0.04, -0.02), wobble=(0.008, 2.0))
        return img

    def animate(self, img, t):
        self.specks.draw(img, t)
        self.bubbles.draw(img, t)


class Space(Background):
    ground = 0.85

    def build(self):
        img = gradient(self.w, self.h, [(0, "#140F3D"), (0.55, "#35206E"), (1, "#5A2A8A")])
        neb = value_noise(self.w // 4, self.h // 4, 3, self.rng, 4)
        tint = np.array(color("bubblegum"), np.float32)
        a = (np.clip((neb - 0.45) * 2.5, 0, 1) * 70).astype(np.uint8)
        layer = np.zeros((*neb.shape, 4), np.uint8)
        layer[..., :3] = tint
        layer[..., 3] = a
        nimg = Image.fromarray(layer, "RGBA").resize((self.w, self.h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(8))
        img.paste(nimg, (0, 0), nimg)
        d = ImageDraw.Draw(img)
        for _ in range(int(260 * self.w * self.h / (1080 * 1920))):
            x, y = self.rng.uniform(0, self.w), self.rng.uniform(0, self.h)
            r = self.rng.uniform(1, 3) * self.u
            d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255))
        if self.p.get("planets", True):
            # keep clear of the headline (top) and caption (lower-middle) zones
            if self.h > self.w:
                self._planet(img, 0.15, 0.9, 120, "#FF9F1C", ring=True)
                self._planet(img, 0.88, 0.58, 70, "#3DDC97")
            else:
                self._planet(img, 0.1, 0.2, 110, "#FF9F1C", ring=True)
                self._planet(img, 0.92, 0.6, 80, "#3DDC97")
        sparkle = [star_shape(self.S(s), (255, 255, 230)) for s in (26, 38, 52)]
        self.twinkles = Particles(self.w, self.h, self.rng, sparkle, count=18, twinkle=3.0)
        return img

    def _planet(self, img, fx, fy, r, hexcol, ring=False):
        r = self.S(r)
        x, y = int(self.w * fx), int(self.h * fy)
        rgb = color(hexcol)
        d = ImageDraw.Draw(img)
        d.ellipse((x - r, y - r, x + r, y + r), fill=rgb)
        dark = tuple(int(c * 0.72) for c in rgb)
        for k in (-0.35, 0.1, 0.45):
            d.line((x - r * 0.9, y + k * r, x + r * 0.9, y + k * r), fill=dark, width=max(2, r // 7))
        if ring:
            d.ellipse((x - r * 1.8, y - r * 0.45, x + r * 1.8, y + r * 0.45), outline=(255, 230, 170), width=max(3, r // 8))
            d.pieslice((x - r, y - r, x + r, y + r), 180, 360, fill=rgb)

    def animate(self, img, t):
        self.twinkles.draw(img, t)
        # a shooting star every ~5 seconds
        cycle, dur = 5.0, 0.8
        k = int(t // cycle)
        ph = (t % cycle) / dur
        if ph < 1:
            rng = np.random.default_rng(k + 99)
            x0, y0 = rng.uniform(0.1, 0.7) * self.w, rng.uniform(0.05, 0.4) * self.h
            L = 0.35 * self.w
            x1, y1 = x0 + L * ph, y0 + L * 0.45 * ph
            d = ImageDraw.Draw(img)
            for j in range(8):
                f = j / 8
                d.line((x1 - L * 0.25 * f, y1 - L * 0.11 * f, x1 - L * 0.25 * (f + 0.12), y1 - L * 0.11 * (f + 0.12)),
                       fill=(255, 255, int(255 - 120 * f)), width=max(1, int(self.S(8) * (1 - f))))


class Night(Background):
    """Spooky-but-cosy: big moon, wobbly trees, drifting fog, fireflies."""

    ground = 0.9

    def build(self):
        img = gradient(self.w, self.h, [(0, "#0E0A2E"), (0.55, "#2A1B5C"), (1, "#18323F")])
        d = ImageDraw.Draw(img)
        for _ in range(int(120 * self.w * self.h / (1080 * 1920))):
            x, y = self.rng.uniform(0, self.w), self.rng.uniform(0, self.h * 0.55)
            r = self.rng.uniform(1, 2.5) * self.u
            d.ellipse((x - r, y - r, x + r, y + r), fill=(230, 230, 255))
        mx, my = self.p.get("moon", (0.78, 0.3) if self.h > self.w else (0.72, 0.16))
        mx, my, mr = int(self.w * mx), int(self.h * my), self.S(120 if self.h > self.w else 150)
        glow = radial(mr * 6, color("#FFF3C4"), 0.55, 1.6)
        img.paste(glow, (mx - glow.width // 2, my - glow.height // 2), glow)
        d.ellipse((mx - mr, my - mr, mx + mr, my + mr), fill=color("#FFF3C4"))
        for cx, cy, cr in ((-0.35, -0.2, 0.22), (0.3, 0.25, 0.16), (0.1, -0.45, 0.1), (-0.1, 0.45, 0.12)):
            d.ellipse((mx + (cx - cr) * mr, my + (cy - cr) * mr, mx + (cx + cr) * mr, my + (cy + cr) * mr), fill=color("#EADFA8"))
        if self.p.get("sea", False):
            sea_y = int(self.h * 0.8)
            ImageDraw.Draw(img).rectangle((0, sea_y, self.w, self.h), fill=color("#141A45"))
            self.sea_y = sea_y
        else:
            hills(img, 0.9, 0.015, 3, color("#0B0820"), 0.3)
        self.moon_xy = (mx, mr)
        if self.p.get("trees", True):
            for side in (0, 1):
                self._tree(d, self.w * (0.04 if side == 0 else 0.96), self.h * 0.93, self.S(900), side)
        if self.p.get("house", False):
            self._house(d, self.w * 0.5, self.h * 0.9, self.S(330))
        self.lamp = None
        if self.p.get("lighthouse", False):
            self.lamp = self._lighthouse(d, self.w * self.p.get("lighthouse_x", 0.78), self.h * 0.83, self.S(620))
            self.lamp_on = self.p.get("lamp_on", True)
        self.fog = [fog_strip(int(self.w * 1.6), int(self.h * 0.22), self.rng) for _ in range(2)]
        glow_bug = [radial(self.S(s), color("slime"), 1.0, 1.3) for s in (26, 36, 48)]
        self.flies = Particles(self.w, self.h, self.rng, glow_bug, count=14, vx=(-0.01, 0.01),
                               vy=(-0.008, 0.008), wobble=(0.03, 0.9), region=(0.45, 0.95), twinkle=2.2)
        return img

    def _tree(self, d, x, y, height, side):
        col = color("#0A0718")

        def branch(x, y, length, angle, width, depth):
            if depth == 0 or length < 8:
                return
            x2 = x + length * math.cos(angle)
            y2 = y - length * math.sin(angle)
            d.line((x, y, x2, y2), fill=col, width=max(1, int(width)))
            d.ellipse((x2 - width / 2, y2 - width / 2, x2 + width / 2, y2 + width / 2), fill=col)
            for da in (-0.5, 0.45):
                branch(x2, y2, length * self.rng.uniform(0.6, 0.75), angle + da + self.rng.uniform(-0.15, 0.15), width * 0.62, depth - 1)

        lean = math.pi / 2 + (0.18 if side == 0 else -0.18)
        branch(x, y, height * 0.42, lean, height * 0.07, 6)

    def _house(self, d, cx, base, s):
        col = color("#0A0718")
        d.rectangle((cx - s * 0.5, base - s * 0.7, cx + s * 0.5, base), fill=col)
        d.polygon([(cx - s * 0.62, base - s * 0.68), (cx, base - s * 1.15), (cx + s * 0.62, base - s * 0.68)], fill=col)
        d.rectangle((cx + s * 0.22, base - s * 1.1, cx + s * 0.34, base - s * 0.8), fill=col)
        for wx in (-0.28, 0.12):
            d.rectangle((cx + wx * s, base - s * 0.52, cx + (wx + 0.16) * s, base - s * 0.34), fill=color("#FFD23F"))

    def _lighthouse(self, d, cx, base, s):
        col = color("#0A0718")
        d.polygon([(cx - s * 0.5, base + s * 0.05), (cx + s * 0.5, base + s * 0.05), (cx + s * 0.3, base - s * 0.1),
                   (cx - s * 0.3, base - s * 0.1)], fill=col)                        # rocks
        d.polygon([(cx - s * 0.16, base - s * 0.08), (cx + s * 0.16, base - s * 0.08),
                   (cx + s * 0.1, base - s * 0.85), (cx - s * 0.1, base - s * 0.85)], fill=col)   # tower
        d.rectangle((cx - s * 0.14, base - s * 0.88, cx + s * 0.14, base - s * 0.85), fill=col)
        d.rectangle((cx - s * 0.08, base - s * 1.0, cx + s * 0.08, base - s * 0.88), fill=col)
        d.polygon([(cx - s * 0.11, base - s * 1.0), (cx, base - s * 1.1), (cx + s * 0.11, base - s * 1.0)], fill=col)
        return (cx, base - s * 0.94, s)

    def animate(self, img, t):
        if getattr(self, "sea_y", None):
            d = ImageDraw.Draw(img)
            mx, mr = self.moon_xy
            for k in range(14):
                y = self.sea_y + (k + 1) * (self.h - self.sea_y) / 15
                wobble = math.sin(t * 1.3 + k * 1.7) * 18 * self.u
                half = mr * (0.25 + 0.05 * k) * (0.7 + 0.3 * math.sin(t * 2 + k))
                d.line((mx - half + wobble, y, mx + half + wobble, y), fill=(255, 243, 196), width=self.S(4))
        if self.lamp is not None:
            lx, ly, s = self.lamp
            d = ImageDraw.Draw(img)
            if self.lamp_on:
                layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
                ld = ImageDraw.Draw(layer)
                sweep = math.cos(t * 1.2)                  # -1..1: beam swings left↔right
                length = self.w * 0.9 * abs(sweep)
                spread = s * 0.12
                end_x = lx + length * (1 if sweep > 0 else -1)
                ld.polygon([(lx, ly - s * 0.02), (end_x, ly - spread), (end_x, ly + spread), (lx, ly + s * 0.02)],
                           fill=(255, 240, 170, 70))
                img.paste(layer, (0, 0), layer)
                d.rectangle((lx - s * 0.07, ly - s * 0.05, lx + s * 0.07, ly + s * 0.05), fill=color("sunshine"))
            else:
                d.rectangle((lx - s * 0.07, ly - s * 0.05, lx + s * 0.07, ly + s * 0.05), fill=color("#3A3355"))
        for k, f in enumerate(self.fog):
            travel = f.width - self.w
            # ping-pong so the strip never runs out; layers drift opposite ways
            off = (t * (18 + 12 * k) * self.u) % (2 * travel)
            off = off if off < travel else 2 * travel - off
            x = -int(off) if k % 2 == 0 else -int(travel - off)
            img.paste(f, (x, int(self.h * (0.72 + 0.1 * k))), f)
        self.flies.draw(img, t)


class Meadow(Background):
    ground = 0.84

    def build(self):
        img = gradient(self.w, self.h, [(0, "#7FD8FF"), (0.7, "#DDF7FF"), (1, "#EFFFF0")])
        hills(img, 0.74, 0.03, 2.5, color("#9BE08A"), 1.2)
        hills(img, 0.8, 0.02, 3.5, color("#6FCF63"), 0.2)
        hills(img, 0.87, 0.012, 2, color("#4DB851"), 2.4)
        d = ImageDraw.Draw(img)
        for _ in range(int(60 * self.w / 1080)):
            x = self.rng.uniform(0, self.w)
            y = self.rng.uniform(0.84, 0.99) * self.h
            r = self.S(self.rng.uniform(7, 12))
            c = color(self.rng.choice(["bubblegum", "sunshine", "white", "grape"]))
            d.ellipse((x - r, y - r, x + r, y + r), fill=c)
            d.ellipse((x - r / 3, y - r / 3, x + r / 3, y + r / 3), fill=color("sunshine"))
        self.clouds = Particles(self.w, self.h, self.rng, [cloud(self.S(w), self.rng) for w in (280, 360)],
                                count=4, vx=(0.01, 0.025), region=(0.04, 0.4))
        self.pollen = Particles(self.w, self.h, self.rng, [radial(self.S(s), (255, 255, 220), 0.9) for s in (14, 22)],
                                count=20, vx=(0.005, 0.02), vy=(-0.01, 0.005), wobble=(0.02, 1.2), twinkle=2.0)
        return img

    def animate(self, img, t):
        self.clouds.draw(img, t)
        self.pollen.draw(img, t)


class Party(Background):
    """Colour-shifting background with confetti, for general facts & quizzes."""

    ground = 0.85
    SCHEMES = {
        "grape": ["#7B4DFF", "#B14DFF", "#FF5DA2"],
        "sky": ["#3EC1F3", "#4D7BFF", "#7B4DFF"],
        "sunset": ["#FF9F1C", "#FF5DA2", "#7B4DFF"],
        "mint": ["#3DDC97", "#3EC1F3", "#4D7BFF"],
    }

    def build(self):
        cols = self.SCHEMES.get(self.p.get("scheme", "grape"), self.SCHEMES["grape"])
        tall = self.h * 2
        stops = [(0, cols[0]), (0.25, cols[1]), (0.5, cols[2]), (0.75, cols[1]), (1, cols[0])]
        self.tall = gradient(self.w, tall, stops)
        dots = Image.new("RGBA", (self.w, tall), (0, 0, 0, 0))
        d = ImageDraw.Draw(dots)
        step = self.S(90)
        for yy in range(0, tall, step):
            for xx in range((yy // step % 2) * step // 2, self.w, step):
                r = self.S(7)
                d.ellipse((xx - r, yy - r, xx + r, yy + r), fill=(255, 255, 255, 40))
        self.tall.paste(dots, (0, 0), dots)
        conf = []
        for c in ("sunshine", "bubblegum", "sky", "mint", "white"):
            piece = Image.new("RGBA", (self.S(26), self.S(14)), (*color(c), 255))
            conf.append(piece)
        self.confetti = Particles(self.w, self.h, self.rng, conf, count=34, vx=(-0.01, 0.01),
                                  vy=(0.04, 0.09), wobble=(0.02, 2.0), spin=True)
        return self.tall.crop((0, 0, self.w, self.h))

    def frame(self, t):
        off = int((t * 60 * self.u) % self.h)
        img = self.tall.crop((0, off, self.w, off + self.h))
        self.confetti.draw(img, t)
        return img


class Body(Background):
    """Soft pink 'inside the body' background with drifting blood cells."""

    def build(self):
        img = gradient(self.w, self.h, [(0, "#FFB3C7"), (0.6, "#FF7A9C"), (1, "#E0476F")])
        cells = []
        for s in (60, 80, 110):
            c = disc(self.S(s), color("#E0243F"))
            inner = disc(self.S(s * 0.5), color("#FF5A6E"), blur=self.S(4))
            c.paste(inner, ((c.width - inner.width) // 2, (c.height - inner.height) // 2), inner)
            cells.append(c)
        self.cells = Particles(self.w, self.h, self.rng, cells, count=16, vx=(0.02, 0.05), vy=(-0.01, 0.01),
                               wobble=(0.01, 1.0), spin=True)
        return img

    def animate(self, img, t):
        self.cells.draw(img, t)


class Snow(Background):
    ground = 0.86

    def build(self):
        img = gradient(self.w, self.h, [(0, "#9ED8FF"), (0.7, "#E4F4FF"), (1, "#FFFFFF")])
        hills(img, 0.8, 0.025, 2, color("#F4FBFF"), 0.4)
        hills(img, 0.87, 0.015, 3, color("#FFFFFF"), 2.2)
        flakes = [disc(self.S(s), (255, 255, 255), blur=self.S(1)) for s in (10, 16, 22)]
        self.snow = Particles(self.w, self.h, self.rng, flakes, count=60, vx=(-0.005, 0.01), vy=(0.03, 0.07), wobble=(0.02, 1.5))
        return img

    def animate(self, img, t):
        self.snow.draw(img, t)


class Desert(Background):
    ground = 0.86

    def build(self):
        img = gradient(self.w, self.h, [(0, "#FFB35C"), (0.55, "#FFD98A"), (1, "#FFE9B5")])
        sun = radial(self.S(600), color("#FFF6D0"), 0.9, 1.4)
        img.paste(sun, (int(self.w * 0.2) - sun.width // 2, int(self.h * 0.12) - sun.height // 2), sun)
        hills(img, 0.78, 0.03, 1.5, color("#F2B55E"), 0.9)
        hills(img, 0.86, 0.02, 2.2, color("#E39A43"), 2.0)
        self.sand = Particles(self.w, self.h, self.rng, [disc(self.S(6), (255, 240, 210), 180)], count=30,
                              vx=(0.08, 0.16), wobble=(0.01, 3), region=(0.6, 1.0))
        return img

    def animate(self, img, t):
        self.sand.draw(img, t)


class Plain(Background):
    """Flat colour. Handy for title cards: bg_params {color: "grape"}."""

    def build(self):
        c = self.p.get("color", "grape")
        return gradient(self.w, self.h, [(0, c), (1, c)])


BACKGROUNDS: dict[str, type[Background]] = {
    "sunny": Sunny,
    "ocean": Ocean,
    "deepsea": DeepSea,
    "space": Space,
    "night": Night,
    "meadow": Meadow,
    "party": Party,
    "body": Body,
    "snow": Snow,
    "desert": Desert,
    "plain": Plain,
}


def make(name: str, w: int, h: int, params: dict | None = None, seed: int = 0) -> Background:
    if name not in BACKGROUNDS:
        raise ValueError(f"unknown background {name!r}; choose from {sorted(BACKGROUNDS)}")
    return BACKGROUNDS[name](w, h, params, seed)
