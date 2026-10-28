"""Olive the octopus: a paper-cut character drawn fresh every frame.

Everything is parametric (`Pose`), so the screenplay animates her by keyframing
numbers: how spread her arms are, how fast they wave, how stretched her mantle
is for jetting, her skin colour (camouflage ↔ orange), and an x-ray view that
reveals her three hearts and blue blood.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .paper import SS, cut, heart_points, mix, ribbon

CAMO = dict(body=(132, 120, 100), dark=(98, 88, 74), light=(168, 154, 130), under=(156, 142, 120),
            spot=(104, 94, 80))
ORANGE = dict(body=(255, 122, 72), dark=(226, 86, 54), light=(255, 172, 122), under=(255, 200, 164),
              spot=(222, 92, 58))
INK = (46, 30, 52)
EYE_WHITE = (250, 246, 238)
HEART = (255, 74, 108)
HEART_OFF = (150, 150, 168)
BLUE = (90, 186, 255)

SPOTS = [(-0.42, -1.25, 0.11), (0.3, -1.45, 0.09), (0.5, -0.95, 0.1), (-0.12, -1.7, 0.08),
         (-0.55, -0.75, 0.07), (0.1, -1.05, 0.06), (0.62, -1.3, 0.06)]


@dataclass
class Pose:
    spread: float = 0.7       # 0 tucked … 1.3 flat on the ground
    wave: float = 0.35        # arm wave amplitude
    wspeed: float = 0.45      # arm wave speed (Hz)
    curl: float = 0.55        # how much arm tips curl
    stretch: float = 1.0      # mantle elongation (jetting ≈ 1.35)
    heading: float = 0.0      # degrees; 0 = head up
    color: float = 1.0        # 0 camouflage … 1 bright orange
    xray: float = 0.0
    blink: float = 0.0        # 0 open … 1 shut
    look: float = 0.0         # pupils -1 left … 1 right
    crawl: float = 0.0        # stepping amplitude
    tuck: float = 0.0         # pull arms in
    big_on: float = 1.0       # systemic heart beating (1) or stopped (0)
    focus: float = 0.0        # 0 all hearts, 1 gill hearts, 2 big heart
    count: float = 0.0        # >0: light hearts one by one (counting along), others dim
    hearts: float = 1.0       # 0..1 heart reveal (pops them in)
    bpm: float = 54.0
    alpha: float = 1.0


def beat(t: float, bpm: float, phase: float = 0.0) -> float:
    """Double-thump 'ba-dum' envelope, 0..~1."""
    ph = (t * bpm / 60 + phase) % 1.0
    return math.exp(-((ph - 0.05) / 0.045) ** 2) + 0.55 * math.exp(-((ph - 0.26) / 0.05) ** 2)


def _part(canvas: Image.Image, m: Image.Image, rgb, seed: int, grain: float, emboss: float,
          alpha: float = 1.0) -> None:
    """Cut and composite one body part, processing only its bounding box."""
    bb = m.getbbox()
    if not bb:
        return
    pad = 4 * SS
    x0 = max(0, (bb[0] - pad) // SS * SS)
    y0 = max(0, (bb[1] - pad) // SS * SS)
    x1 = min(m.width, (bb[2] + pad + SS - 1) // SS * SS)
    y1 = min(m.height, (bb[3] + pad + SS - 1) // SS * SS)
    piece = cut(m.crop((x0, y0, x1, y1)), rgb, seed, grain, emboss)
    if alpha < 0.999:
        piece.putalpha(piece.getchannel("A").point(lambda v: int(v * alpha)))
    canvas.alpha_composite(piece, (x0 // SS, y0 // SS))


def _rot(points, ang_deg):
    th = math.radians(ang_deg)
    c, s = math.cos(th), math.sin(th)
    return [(x * c - y * s, x * s + y * c) for x, y in points]


class Octopus:
    def __init__(self, seed: int = 3):
        self.seed = seed
        self.arm_len = [2.15 + 0.28 * math.cos(i * 1.7 + 0.4) for i in range(8)]

    # -- geometry (local units of R; y down; origin between the eyes) -------
    def arms(self, p: Pose, t: float):
        out = []
        for i in range(8):
            u = (i - 3.5) / 3.5
            base = (u * 0.5, 0.32)
            ang = 90 - u * (22 + 60 * p.spread)
            n = 22
            L = self.arm_len[i] * (1 - 0.38 * p.tuck)
            step = L / n
            x, y = base
            pts = [base]
            sgn = 1 if u > 0 else -1
            for k in range(1, n + 1):
                s = k / n
                th = ang
                th -= sgn * p.curl * 140 * s ** 2.2
                th += p.wave * 38 * math.sin(2 * math.pi * p.wspeed * t + i * 1.31 - s * 3.6) * s
                if p.crawl:
                    th += p.crawl * 14 * math.sin(2 * math.pi * 0.9 * t + (i % 2) * math.pi) * (1 - s) * sgn
                x += step * math.cos(math.radians(th))
                y += step * math.sin(math.radians(th))
                pts.append((x, y))
            widths = [0.31 * (1 - k / n) ** 0.85 + 0.035 for k in range(n + 1)]
            out.append((pts, widths))
        return out

    def mantle(self, p: Pose, t: float, breath: float):
        st = p.stretch * (1 + 0.025 * breath)
        cx, cy = 0.0, -0.98 * st
        rx, ry = 0.9 / math.sqrt(p.stretch) * (1 - 0.02 * breath), 1.06 * st
        pts = []
        for k in range(72):
            a = 2 * math.pi * k / 72
            # a slightly pointed, droopy bulb
            r = 1 + 0.06 * math.cos(2 * a) - 0.05 * math.sin(a)
            pts.append((cx + rx * r * math.cos(a), cy + ry * r * math.sin(a)))
        face = [(0.78 * math.cos(a), -0.02 + 0.5 * math.sin(a))
                for a in np.linspace(0, 2 * math.pi, 48, endpoint=False)]
        return pts, face, (cx, cy, rx, ry)

    # -- drawing --------------------------------------------------------------
    def render(self, p: Pose, t: float, R: float) -> tuple[Image.Image, tuple[float, float]]:
        """Return (RGBA image, anchor px of the head centre). R = mantle radius in screen px."""
        E = R * (3.3 + 1.4 * max(0.0, p.stretch - 1))
        size = int(2 * E) + 8
        o = size / 2
        col = {k: mix(CAMO[k], ORANGE[k], p.color) for k in CAMO}

        def P(pts):
            return [(o + x * R, o + y * R) for x, y in _rot(pts, p.heading)]

        def mask():
            return Image.new("L", (size * SS, size * SS), 0)

        def S(pts):
            return [(x * SS, y * SS) for x, y in P(pts)]

        breath = math.sin(2 * math.pi * 0.35 * t)
        arms = self.arms(p, t)
        mantle, face, (mcx, mcy, mrx, mry) = self.mantle(p, t, breath)

        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))

        # arms (back half slightly darker for depth)
        for group, shade in ((range(1, 8, 2), 0.86), (range(0, 8, 2), 1.0)):
            m = mask()
            d = ImageDraw.Draw(m)
            for i in group:
                pts, widths = arms[i]
                d.polygon(S(ribbon(pts, widths)), fill=255)
                tip = pts[-1]
                r = widths[-1] / 2 * R * SS
                tx, ty = S([tip])[0]
                d.ellipse((tx - r, ty - r, tx + r, ty + r), fill=255)
            _part(canvas, m, tuple(int(c * shade) for c in col["body"]), self.seed, 0.9, 1.0)

        # suckers along the inner edge of the front arms
        m = mask()
        d = ImageDraw.Draw(m)
        for i in range(8):
            pts, widths = arms[i]
            u = (i - 3.5) / 3.5
            for k in range(4, len(pts) - 3, 3):
                x, y = pts[k]
                x1, y1 = pts[k + 1]
                nx, ny = -(y1 - y), (x1 - x)
                ln = math.hypot(nx, ny) or 1
                side = 1 if u < 0 else -1
                ox_, oy_ = x + side * nx / ln * widths[k] * 0.28, y + side * ny / ln * widths[k] * 0.28
                rr = widths[k] * 0.2 * R * SS
                cx_, cy_ = S([(ox_, oy_)])[0]
                d.ellipse((cx_ - rr, cy_ - rr, cx_ + rr, cy_ + rr), fill=255)
        _part(canvas, m, col["under"], self.seed + 1, 0.6, 0.6)

        # head: mantle + face
        m = mask()
        d = ImageDraw.Draw(m)
        d.polygon(S(mantle), fill=255)
        d.polygon(S(face), fill=255)
        _part(canvas, m, col["body"], self.seed + 2, 1.0, 1.3)

        # spots + highlight
        m = mask()
        d = ImageDraw.Draw(m)
        for sx, sy, sr in SPOTS:
            cx_, cy_ = S([(sx / math.sqrt(p.stretch), sy * p.stretch)])[0]
            rr = sr * R * SS
            d.ellipse((cx_ - rr, cy_ - rr * 0.8, cx_ + rr, cy_ + rr * 0.8), fill=255)
        _part(canvas, m, col["spot"], self.seed + 3, 0.8, 0.5)
        m = mask()
        d = ImageDraw.Draw(m)
        hl = [(mcx - mrx * 0.35 + 0.3 * mrx * math.cos(a), mcy - mry * 0.35 + 0.38 * mry * math.sin(a))
              for a in np.linspace(0, 2 * math.pi, 32, endpoint=False)]
        d.polygon(S(hl), fill=255)
        _part(canvas, m, col["light"], self.seed + 4, 0.6, 0.4)

        if p.xray > 0.01:
            self._xray(canvas, p, t, R, P, S, mask, arms, (mcx, mcy, mrx, mry))

        # face details stay solid
        self._face(canvas, p, t, R, P, S, mask, col)

        if p.alpha < 0.999:
            a = canvas.getchannel("A").point(lambda v: int(v * p.alpha))
            canvas.putalpha(a)
        return canvas, (o, o)

    def _face(self, canvas, p, t, R, P, S, mask, col):
        m_white = mask()
        dw = ImageDraw.Draw(m_white)
        m_ink = mask()
        di = ImageDraw.Draw(m_ink)
        m_pink = mask()
        dp = ImageDraw.Draw(m_pink)
        er = 0.25
        for side in (-1, 1):
            ex, ey = side * 0.4, -0.08
            cx_, cy_ = S([(ex, ey)])[0]
            r = er * R * SS
            if p.blink < 0.5:
                dw.ellipse((cx_ - r, cy_ - r * 1.05, cx_ + r, cy_ + r * 1.05), fill=255)
                # horizontal-slit pupil, like a real octopus
                pw, ph = r * 0.58, r * 0.4
                px = cx_ + p.look * r * 0.3
                di.rounded_rectangle((px - pw, cy_ - ph + r * 0.08, px + pw, cy_ + ph + r * 0.08),
                                     radius=ph, fill=255)
            else:
                di.arc((cx_ - r, cy_ - r * 0.6, cx_ + r, cy_ + r * 0.9), 200, 340, fill=255,
                       width=max(2, int(r * 0.22)))
            # rosy cheeks
            ccx, ccy = S([(side * 0.6, 0.16)])[0]
            rr = 0.12 * R * SS
            dp.ellipse((ccx - rr * 1.3, ccy - rr * 0.8, ccx + rr * 1.3, ccy + rr * 0.8), fill=255)
        mx_, my_ = S([(0, 0.16)])[0]
        mr = 0.11 * R * SS
        di.arc((mx_ - mr, my_ - mr, mx_ + mr, my_ + mr), 20, 160, fill=255, width=max(2, int(mr * 0.35)))
        _part(canvas, m_pink, (255, 150, 150), 9, 0.3, 0, 0.55)
        _part(canvas, m_white, EYE_WHITE, 7, 0.4, 0.8)
        _part(canvas, m_ink, INK, 8, 0.2, 0)
        if p.blink < 0.5:
            m = mask()
            d = ImageDraw.Draw(m)
            for side in (-1, 1):
                cx_, cy_ = S([(side * 0.4 + 0.08 + p.look * 0.05, -0.17)])[0]
                r = 0.05 * R * SS
                d.ellipse((cx_ - r, cy_ - r, cx_ + r, cy_ + r), fill=255)
            _part(canvas, m, (255, 255, 255), 10, 0, 0)

    def _xray(self, canvas, p, t, R, P, S, mask, arms, mantle_geom):
        x = p.xray
        arr = np.asarray(canvas).astype(np.float32)
        ghost = np.array((178, 222, 255), np.float32)
        arr[..., :3] = arr[..., :3] * (1 - 0.55 * x) + ghost * 0.55 * x
        arr[..., 3] *= 1 - 0.45 * x
        canvas.paste(Image.fromarray(arr.astype(np.uint8), "RGBA"))
        mcx, mcy, mrx, mry = mantle_geom
        big = (0.0, mcy - 0.05 * mry)
        gills = [(-0.55 * mrx, mcy + 0.42 * mry), (0.55 * mrx, mcy + 0.42 * mry)]
        # vessels: big heart → every arm, and gill hearts ↔ big heart
        vessels = []
        for pts, _ in arms:
            vessels.append([big, (pts[0][0] * 0.6, (big[1] + pts[0][1]) / 2)] + pts[:10])
        for g in gills:
            vessels.append([g, ((g[0] + big[0]) / 2, g[1] - 0.15), big])
            vessels.append([g, (g[0] * 1.25, g[1] - 0.35)])
        vessels.append([big, (0.0, mcy - 0.6 * mry)])
        glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        dg = ImageDraw.Draw(glow)
        core = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        dc = ImageDraw.Draw(core)
        flow = (t * 0.55) % 1.0
        for v in vessels:
            pts = P(v)
            dg.line(pts, fill=(*BLUE, int(120 * x)), width=max(2, int(0.16 * R)), joint="curve")
            dc.line(pts, fill=(*mix(BLUE, (255, 255, 255), 0.35), int(255 * x)), width=max(1, int(0.05 * R)),
                    joint="curve")
            # flowing blood cells
            seg = [math.hypot(b[0] - a_[0], b[1] - a_[1]) for a_, b in zip(pts, pts[1:])]
            total = sum(seg) or 1
            for k in range(int(total / (0.5 * R)) + 1):
                dist = ((k + flow) * 0.5 * R) % total
                acc = 0.0
                for (ax, ay), (bx, by), sl in zip(pts, pts[1:], seg):
                    if acc + sl >= dist:
                        f = (dist - acc) / (sl or 1)
                        cx_, cy_ = ax + (bx - ax) * f, ay + (by - ay) * f
                        r = 0.045 * R
                        dc.ellipse((cx_ - r, cy_ - r, cx_ + r, cy_ + r), fill=(235, 248, 255, int(255 * x)))
                        break
                    acc += sl
        canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(max(1, R * 0.06))))
        canvas.alpha_composite(core)

        # gills: soft feathery shapes
        m = mask()
        d = ImageDraw.Draw(m)
        for g in gills:
            for k in range(5):
                gx, gy = S([(g[0] * 1.45, g[1] - 0.3 + k * 0.07)])[0]
                r = 0.05 * R * SS
                d.ellipse((gx - r * 1.6, gy - r, gx + r * 1.6, gy + r), fill=255)
        _part(canvas, m, (255, 190, 210), 12, 0.4, 0.4, x * 0.7)

        # hearts
        hearts = [(gills[0], 0.5, 0.0, True, 1), (gills[1], 0.5, 0.08, True, 1), (big, 0.86, 0.5, False, 2)]
        for idx, ((hx, hy), size, phase, small, group) in enumerate(hearts):
            on = 1.0 if small else p.big_on
            pulse = beat(t, p.bpm, phase) * on
            dim = 1.0 if p.focus in (0, group) else 0.45
            if p.count > 0:
                lit = min(1.0, max(0.0, p.count - idx))
                dim = 0.35 + 0.65 * lit
                pulse = pulse * (0.4 + 0.6 * lit) + 0.25 * lit * max(0.0, 1 - abs(p.count - idx - 1) * 3)
            if p.hearts < 0.999:
                # pop in one after another
                reveal = min(1.0, max(0.0, p.hearts * 3 - idx * 0.9))
                if reveal <= 0.01:
                    continue
                c1 = 1.7
                q = reveal - 1
                size *= 1 + (c1 + 1) * q ** 3 + c1 * q ** 2
            sc = size * (1 + 0.17 * pulse)
            colr = mix(HEART_OFF, HEART, on)
            pts = heart_points(hx, hy, sc)
            m = mask()
            ImageDraw.Draw(m).polygon(S(pts), fill=255)
            # glow, computed only around this heart
            g = int(R * 0.4)
            bb = m.getbbox()
            if bb:
                gx0, gy0 = max(0, bb[0] // SS - g), max(0, bb[1] // SS - g)
                gx1, gy1 = min(canvas.width, bb[2] // SS + g), min(canvas.height, bb[3] // SS + g)
                small = m.reduce(SS).crop((gx0, gy0, gx1, gy1))
                gl = Image.new("RGBA", small.size, (*colr, 0))
                gl.putalpha(small.filter(ImageFilter.GaussianBlur(R * 0.12))
                            .point(lambda v: int(v * x * dim * (0.55 + 0.45 * pulse))))
                canvas.alpha_composite(gl, (gx0, gy0))
            _part(canvas, m, colr, 13, 0.5, 1.0, x * (0.35 + 0.65 * dim))
