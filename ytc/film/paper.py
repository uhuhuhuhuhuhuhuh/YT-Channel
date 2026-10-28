"""Paper-cutout art: every shape looks hand-cut from textured paper.

A piece is drawn as a supersampled mask, then given a flat colour, paper
grain, an emboss (light top-left edge, dark bottom-right edge, like card
thickness) and a soft drop shadow. Layers are built by stacking pieces on a
`Canvas`.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SS = 2          # supersampling factor for crisp, anti-aliased edges


def mix(a, b, t: float) -> tuple[int, int, int]:
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))  # type: ignore[return-value]


def hexrgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


# --------------------------------------------------------------------------
# Textures
# --------------------------------------------------------------------------

_GRAIN: dict = {}


def grain_tile(size: int = 512, seed: int = 0) -> np.ndarray:
    """Tileable paper grain multiplier around 1.0 (fibres + speckle)."""
    key = (size, seed)
    if key not in _GRAIN:
        rng = np.random.default_rng(seed)
        fine = rng.standard_normal((size, size)).astype(np.float32)
        img = Image.fromarray(np.clip(fine * 40 + 128, 0, 255).astype(np.uint8))
        soft = np.asarray(img.filter(ImageFilter.GaussianBlur(0.7)), np.float32) / 128 - 1
        coarse = rng.standard_normal((size // 16, size // 16)).astype(np.float32)
        coarse = np.asarray(Image.fromarray(np.clip(coarse * 40 + 128, 0, 255).astype(np.uint8))
                            .resize((size, size), Image.BICUBIC), np.float32) / 128 - 1
        _GRAIN[key] = 1 + 0.55 * soft * 0.12 + 0.45 * coarse * 0.1
    return _GRAIN[key]


def grain_for(w: int, h: int, seed: int = 0) -> np.ndarray:
    tile = grain_tile(512, seed % 4)
    reps = (h // 512 + 2, w // 512 + 2)
    big = np.tile(tile, reps)
    oy, ox = (seed * 97) % 512, (seed * 53) % 512
    return big[oy:oy + h, ox:ox + w]


# --------------------------------------------------------------------------
# Cutting a piece
# --------------------------------------------------------------------------


def cut(mask: Image.Image, rgb, seed: int = 0, grain: float = 1.0, emboss: float = 1.0) -> Image.Image:
    """Supersampled 'L' mask → RGBA paper piece at 1/SS size."""
    w, h = mask.size[0] // SS, mask.size[1] // SS
    m = mask.reduce(SS) if SS > 1 else mask
    a = np.asarray(m, np.float32) / 255
    col = np.empty((h, w, 3), np.float32)
    col[...] = rgb
    if grain:
        g = grain_for(w, h, seed)
        col *= (1 + (g[..., None] - 1) * grain)
    if emboss:
        e = max(1, int(round(2 * emboss)))
        shifted_dn = np.zeros_like(a)
        shifted_up = np.zeros_like(a)
        shifted_dn[e:, e:] = a[:-e, :-e]          # mask moved down-right
        shifted_up[:-e, :-e] = a[e:, e:]          # mask moved up-left
        light = np.clip(a - shifted_dn, 0, 1)     # top-left rim
        dark = np.clip(a - shifted_up, 0, 1)      # bottom-right rim
        col += light[..., None] * 38 * emboss
        col -= dark[..., None] * 34 * emboss
    out = np.empty((h, w, 4), np.uint8)
    out[..., :3] = np.clip(col, 0, 255)
    out[..., 3] = np.clip(a * 255, 0, 255)
    return Image.fromarray(out, "RGBA")


def shadow_of(piece: Image.Image, blur: float, alpha: float, rgb=(10, 20, 40)) -> Image.Image:
    a = piece.getchannel("A").filter(ImageFilter.GaussianBlur(blur))
    a = a.point(lambda v: int(v * alpha))
    sh = Image.new("RGBA", piece.size, (*rgb, 0))
    sh.putalpha(a)
    return sh


def premul_blur(img: Image.Image, radius: float) -> Image.Image:
    """Gaussian blur without dark fringes around transparent edges."""
    if radius <= 0.3:
        return img
    return img.convert("RGBa").filter(ImageFilter.GaussianBlur(radius)).convert("RGBA")


# --------------------------------------------------------------------------
# Shapes (point lists in pixel coordinates)
# --------------------------------------------------------------------------


def blob(cx, cy, rx, ry, seed=0, n=64, rough=0.07, flat_bottom=False):
    rng = np.random.default_rng(seed)
    harmonics = [(k, rng.uniform(0, 2 * math.pi), rng.uniform(0.3, 1) / k) for k in range(2, 7)]
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        r = 1 + rough * sum(amp * math.sin(k * a + ph) for k, ph, amp in harmonics)
        x, y = cx + rx * r * math.cos(a), cy + ry * r * math.sin(a)
        if flat_bottom and y > cy:
            y = cy + (y - cy) * 0.25
        pts.append((x, y))
    return pts


def wavy_top(x0, x1, y, amp, waves, seed=0, bottom=None, n=120):
    rng = np.random.default_rng(seed)
    ph = rng.uniform(0, 6, 3)
    pts = []
    for i in range(n + 1):
        f = i / n
        x = x0 + (x1 - x0) * f
        yy = y + amp * (math.sin(f * waves * 2 * math.pi + ph[0]) * 0.6
                        + math.sin(f * waves * 5.3 + ph[1]) * 0.3 + math.sin(f * waves * 11 + ph[2]) * 0.1)
        pts.append((x, yy))
    b = bottom if bottom is not None else y + 5000
    return pts + [(x1, b), (x0, b)]


def heart_points(cx, cy, size, n=60):
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + x * size / 32, cy + y * size / 32))
    return pts


def ribbon(points, widths):
    """Polygon around a centre line with per-point widths (tapered strokes)."""
    left, right = [], []
    for i, (x, y) in enumerate(points):
        x0, y0 = points[max(0, i - 1)]
        x1, y1 = points[min(len(points) - 1, i + 1)]
        dx, dy = x1 - x0, y1 - y0
        ln = math.hypot(dx, dy) or 1
        nx, ny = -dy / ln, dx / ln
        w = widths[i] / 2
        left.append((x + nx * w, y + ny * w))
        right.append((x - nx * w, y - ny * w))
    return left + right[::-1]


# --------------------------------------------------------------------------
# Canvas: build a layer piece by piece
# --------------------------------------------------------------------------


class Canvas:
    def __init__(self, w: int, h: int, seed: int = 0, shadow: float = 0.32, shadow_offset=(5, 8),
                 shadow_blur: float = 7):
        self.img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        self.seed = seed
        self.n = 0
        self.shadow = shadow
        self.shadow_offset = shadow_offset
        self.shadow_blur = shadow_blur

    def add(self, draw_fn, bbox, rgb, grain: float = 1.0, emboss: float = 1.0, shadow: float | None = None):
        """draw_fn(draw, tx) draws white shapes; tx(x, y) maps canvas px → mask px."""
        x0, y0, x1, y1 = (int(math.floor(bbox[0])) - 4, int(math.floor(bbox[1])) - 4,
                          int(math.ceil(bbox[2])) + 4, int(math.ceil(bbox[3])) + 4)
        W, H = self.img.size
        x0c, y0c, x1c, y1c = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
        if x1c <= x0c or y1c <= y0c:
            return
        mask = Image.new("L", ((x1c - x0c) * SS, (y1c - y0c) * SS), 0)

        def tx(x, y):
            return ((x - x0c) * SS, (y - y0c) * SS)

        draw_fn(ImageDraw.Draw(mask), tx)
        self.n += 1
        piece = cut(mask, rgb, self.seed * 131 + self.n, grain, emboss)
        s = self.shadow if shadow is None else shadow
        if s > 0:
            pad = int(self.shadow_blur * 3)
            big = Image.new("RGBA", (piece.width + 2 * pad, piece.height + 2 * pad), (0, 0, 0, 0))
            big.paste(piece, (pad, pad))
            sh = shadow_of(big, self.shadow_blur, s)
            ox, oy = self.shadow_offset
            blit(self.img, sh, x0c - pad + ox, y0c - pad + oy)
        blit(self.img, piece, x0c, y0c)

    def poly(self, pts, rgb, **kw):
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        self.add(lambda d, tx: d.polygon([tx(*p) for p in pts], fill=255),
                 (min(xs), min(ys), max(xs), max(ys)), rgb, **kw)

    def ellipse(self, cx, cy, rx, ry, rgb, **kw):
        self.add(lambda d, tx: d.ellipse((*tx(cx - rx, cy - ry), *tx(cx + rx, cy + ry)), fill=255),
                 (cx - rx, cy - ry, cx + rx, cy + ry), rgb, **kw)

    def lines(self, segments, rgb, **kw):
        """segments: [(x0, y0, x1, y1, width), ...] drawn as round-capped strokes."""
        xs = [v for s in segments for v in (s[0], s[2])]
        ys = [v for s in segments for v in (s[1], s[3])]
        pad = max(s[4] for s in segments)

        def fn(d, tx):
            for x0, y0, x1, y1, wd in segments:
                d.line((*tx(x0, y0), *tx(x1, y1)), fill=255, width=int(wd * SS))
                r = wd / 2
                for (x, y) in ((x0, y0), (x1, y1)):
                    d.ellipse((*tx(x - r, y - r), *tx(x + r, y + r)), fill=255)

        self.add(fn, (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad), rgb, **kw)


def blit(dst: Image.Image, src: Image.Image, x: int, y: int) -> None:
    """alpha_composite with clipping at the destination edges."""
    x, y = int(x), int(y)
    W, H = dst.size
    sx0, sy0 = max(0, -x), max(0, -y)
    sx1, sy1 = min(src.width, W - x), min(src.height, H - y)
    if sx1 <= sx0 or sy1 <= sy0:
        return
    if (sx0, sy0, sx1, sy1) != (0, 0, src.width, src.height):
        src = src.crop((sx0, sy0, sx1, sy1))
    dst.alpha_composite(src, (x + sx0, y + sy0))
