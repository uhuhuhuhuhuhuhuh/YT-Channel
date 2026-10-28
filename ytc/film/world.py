"""2.5D world: depth layers, sprites, a camera, and keyframed tracks.

World units are pixels on the hero plane (z = 1) at 1080p. An object at
depth z appears 1/(z - d) times its world size, where d is the camera's dolly
(positive = pushed in). Far layers therefore move less (parallax) and grow less
when the camera pushes in.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from .paper import premul_blur


# --------------------------------------------------------------------------
# Tracks: keyframed values
# --------------------------------------------------------------------------


def ease(p: float, kind: str) -> float:
    p = min(max(p, 0.0), 1.0)
    if kind == "linear":
        return p
    if kind == "in":
        return p * p * p
    if kind == "out":
        return 1 - (1 - p) ** 3
    if kind == "step":
        return 0.0 if p < 1 else 1.0
    if kind == "back":                       # overshoot, for pops
        c = 1.7
        return 1 + (c + 1) * (p - 1) ** 3 + c * (p - 1) ** 2
    return p * p * (3 - 2 * p) if kind == "smooth" else (4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2)


class Track:
    """value(t): holds `default` before the first key; eases into each key."""

    def __init__(self, default):
        self.default = default
        self.keys: list[tuple[float, object, str, float]] = []

    def key(self, t: float, value, ease_kind: str = "inout", dur: float | None = None) -> "Track":
        """Arrive at `value` at time t. With `dur`, start moving at t - dur (hold before)."""
        self.keys.append((t, value, ease_kind, dur if dur is not None else -1))
        self.keys.sort(key=lambda k: k[0])
        return self

    def move(self, t0: float, t1: float, value, ease_kind: str = "inout") -> "Track":
        return self.key(t1, value, ease_kind, dur=t1 - t0)

    def set(self, t: float, value) -> "Track":
        return self.key(t, value, "step", dur=0.0)

    def __call__(self, t: float):
        prev_t, prev_v = -1e9, self.default
        for kt, kv, ek, dur in self.keys:
            if t < kt:
                start = prev_t if dur < 0 else max(prev_t, kt - dur)
                if t <= start or ek == "step":
                    return prev_v
                p = ease((t - start) / max(kt - start, 1e-6), ek)
                return _lerp(prev_v, kv, p)
            prev_t, prev_v = kt, kv
        return prev_v


def _lerp(a, b, p):
    if isinstance(a, (tuple, list)):
        return tuple(x + (y - x) * p for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a + (b - a) * p
    return b if p >= 1 else a


# --------------------------------------------------------------------------
# Scene objects
# --------------------------------------------------------------------------


@dataclass
class Camera:
    x: float
    y: float
    d: float = 0.0          # dolly: 0 = normal, 0.4 = pushed in (hero plane 1.67x)
    k: float = 1.0          # output scale (0.5 for half-size previews)


@dataclass
class Layer:
    """A painted plane. img pixel (0, 0) sits at world (ox, oy); q = img px per world unit."""
    name: str
    z: float
    img: Image.Image
    ox: float
    oy: float
    q: float
    blur: float = 0.0
    sprites: list["Sprite"] = field(default_factory=list)


@dataclass
class Sprite:
    """A cut-out that moves on its own (kelp sway, fish, shark)."""
    img: Image.Image
    anchor: tuple[float, float]          # pivot in image px
    x: float
    y: float
    z: float
    q: float                             # image px per world unit
    sway: float = 0.0                    # degrees
    sway_hz: float = 0.15
    phase: float = 0.0
    visible: object = None               # optional callable t -> bool / alpha
    path: object = None                  # optional callable t -> (x, y, angle_deg, flip)


def prepare_blur(layer_or_sprite, blur: float):
    layer_or_sprite.img = premul_blur(layer_or_sprite.img, blur)
    return layer_or_sprite


# --------------------------------------------------------------------------
# Projection + drawing
# --------------------------------------------------------------------------


def scale_at(z: float, cam: Camera) -> float:
    return cam.k / max(z - cam.d, 0.05)


def to_screen(x: float, y: float, z: float, cam: Camera, W: int, H: int) -> tuple[float, float, float]:
    s = scale_at(z, cam)
    return (x - cam.x) * s + W / 2, (y - cam.y) * s + H / 2, s


def paste_affine(frame: Image.Image, img: Image.Image, M: tuple, alpha: float = 1.0) -> None:
    """Composite img onto frame through forward affine M=(a,b,c,d,e,f): screen = M · img."""
    a, b, c, d, e, f = M
    W, H = frame.size
    corners = [(0, 0), (img.width, 0), (0, img.height), (img.width, img.height)]
    xs = [a * u + b * v + c for u, v in corners]
    ys = [d * u + e * v + f for u, v in corners]
    x0, y0 = max(0, int(math.floor(min(xs)))), max(0, int(math.floor(min(ys))))
    x1, y1 = min(W, int(math.ceil(max(xs)))), min(H, int(math.ceil(max(ys))))
    if x1 <= x0 or y1 <= y0:
        return
    det = a * e - b * d
    if abs(det) < 1e-9:
        return
    ia, ib, id_, ie = e / det, -b / det, -d / det, a / det
    # input = inv(M) · (out + offset)
    ic = -(ia * c + ib * f) + ia * x0 + ib * y0
    if_ = -(id_ * c + ie * f) + id_ * x0 + ie * y0
    patch = img.transform((x1 - x0, y1 - y0), Image.AFFINE, (ia, ib, ic, id_, ie, if_),
                          resample=Image.BILINEAR)
    if alpha < 0.999:
        r, g, bb, aa = patch.split()
        patch = Image.merge("RGBA", (r, g, bb, aa.point(lambda v: int(v * alpha))))
    frame.alpha_composite(patch, (x0, y0))


def draw_layer(frame: Image.Image, L: Layer, cam: Camera) -> None:
    W, H = frame.size
    s = scale_at(L.z, cam)
    k = s / L.q                                   # screen px per image px
    # screen = (ox + u/q - cam.x) * s + W/2
    c = (L.ox - cam.x) * s + W / 2
    f = (L.oy - cam.y) * s + H / 2
    paste_affine(frame, L.img, (k, 0, c, 0, k, f))


def draw_sprite(frame: Image.Image, sp: Sprite, cam: Camera, t: float) -> None:
    W, H = frame.size
    x, y, ang, flip = sp.x, sp.y, 0.0, False
    if sp.path is not None:
        x, y, ang, flip = sp.path(t)
    alpha = 1.0
    if sp.visible is not None:
        alpha = float(sp.visible(t))
        if alpha <= 0.01:
            return
    ang += sp.sway * math.sin(2 * math.pi * sp.sway_hz * t + sp.phase)
    sx, sy, s = to_screen(x, y, sp.z, cam, W, H)
    k = s / sp.q
    th = math.radians(-ang)
    ct, st = math.cos(th) * k, math.sin(th) * k
    fx = -1 if flip else 1
    au, av = sp.anchor
    # screen = R·S·(img - anchor) + (sx, sy), with optional horizontal flip
    a, b = ct * fx, -st
    d, e = st * fx, ct
    c = sx - (a * au + b * av)
    f = sy - (d * au + e * av)
    paste_affine(frame, sp.img, (a, b, c, d, e, f), alpha)


def water_gradient(W: int, H: int, stops: list[tuple[float, tuple]], y_top: float, y_bottom: float,
                   par: float = 0.25) -> tuple[np.ndarray, float, float]:
    """Tall background colour strip; returns (rows RGB, y_top, step) for cheap per-frame crops."""
    n = int((y_bottom - y_top) * par) + H * 2
    ys = np.linspace(0, 1, n)
    pos = [p for p, _ in stops]
    cols = np.array([c for _, c in stops], float)
    rgb = np.stack([np.interp(ys, pos, cols[:, i]) for i in range(3)], 1)
    return rgb.astype(np.uint8), y_top, (y_bottom - y_top) / n
