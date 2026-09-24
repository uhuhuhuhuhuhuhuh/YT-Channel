"""Channel art: the mascot "Bitsy" (a star with a bite taken out), avatar,
banner and watermark. Everything is drawn from code, so it's 100% ours.

    ytc brand   →  assets/brand/{avatar,banner,watermark}.png + assets/sprites/bitsy.png
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter

from . import scenes, text
from .config import ASSETS, SPRITES, color, load_config

BRAND = ASSETS / "brand"


def star_points(cx, cy, r_out, r_in, n=5, rot=-math.pi / 2):
    pts = []
    for i in range(n * 2):
        r = r_out if i % 2 == 0 else r_in
        a = rot + math.pi * i / n
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def dilate(mask: Image.Image, radius: float) -> Image.Image:
    """Fast morphological grow: blur, then keep anything the blur touched."""
    return mask.filter(ImageFilter.GaussianBlur(radius)).point(lambda v: 255 if v > 12 else 0)


def bitsy(size: int = 1024, mood: str = "happy") -> Image.Image:
    """The mascot, as a transparent RGBA image."""
    S = size * 4                                     # supersample, then shrink
    c = S / 2
    mask = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(mask)
    d.polygon(star_points(c, c * 1.06, S * 0.47, S * 0.25), fill=255)
    # round the points: blur + threshold
    mask = mask.filter(ImageFilter.GaussianBlur(S * 0.03)).point(lambda v: 255 if v > 150 else 0)
    # the bite: three circles nibbled out of the top-right arm
    bite = ImageDraw.Draw(mask)
    bx, by = c + S * 0.36, c - S * 0.2
    for dx, dy, r in ((0, 0, 0.085), (-0.07, 0.07, 0.07), (0.05, 0.1, 0.07)):
        x, y, rr = bx + dx * S, by + dy * S, r * S
        bite.ellipse((x - rr, y - rr, x + rr, y + rr), fill=0)

    ink = color("ink")
    outline = dilate(mask, S * 0.018)
    img = Image.new("RGBA", (S, S), (*ink, 0))
    img.putalpha(outline)
    body = Image.new("RGBA", (S, S), (*color("sunshine"), 0))
    body.putalpha(mask)
    img.alpha_composite(body)
    # soft highlight
    hl = Image.new("L", (S, S), 0)
    ImageDraw.Draw(hl).ellipse((c - S * 0.2, c - S * 0.24, c + S * 0.05, c - S * 0.06), fill=110)
    hl = Image.composite(hl.filter(ImageFilter.GaussianBlur(S * 0.03)), Image.new("L", (S, S), 0), mask)
    white = Image.new("RGBA", (S, S), (255, 255, 255, 0))
    white.putalpha(hl)
    img.alpha_composite(white)

    d = ImageDraw.Draw(img)
    ey = c + S * 0.02
    for ex in (c - S * 0.1, c + S * 0.1):
        rx, ry = S * 0.042, S * 0.058
        if mood == "wink" and ex > c:
            d.arc((ex - rx, ey - ry, ex + rx, ey + ry), 200, 340, fill=ink, width=int(S * 0.018))
            continue
        d.ellipse((ex - rx, ey - ry, ex + rx, ey + ry), fill=ink)
        d.ellipse((ex - rx * 0.1, ey - ry * 0.7, ex + rx * 0.55, ey - ry * 0.05), fill=(255, 255, 255))
    for ex in (c - S * 0.19, c + S * 0.19):
        d.ellipse((ex - S * 0.045, ey + S * 0.07, ex + S * 0.045, ey + S * 0.115), fill=(*color("bubblegum"), 255))
    mw = S * 0.09
    d.chord((c - mw, ey + S * 0.03, c + mw, ey + S * 0.17), 0, 180, fill=ink)
    d.ellipse((c - mw * 0.45, ey + S * 0.11, c + mw * 0.45, ey + S * 0.165), fill=(*color("bubblegum"), 255))
    return img.resize((size, size), Image.LANCZOS)


def avatar(size: int = 800) -> Image.Image:
    img = Image.new("RGB", (size, size))
    g = scenes.gradient(size, size, [(0, "grape"), (1, "bubblegum")])
    img.paste(g)
    glow = scenes.radial(int(size * 0.9), (255, 255, 255), 0.35)
    img.paste(glow, (int(size * 0.05), int(size * 0.05)), glow)
    b = bitsy(int(size * 0.78))
    img.paste(b, (int(size * 0.11), int(size * 0.1)), b)
    return img


def banner() -> Image.Image:
    """2560×1440. Everything important sits in the 1546×423 centre safe area."""
    W, H = 2560, 1440
    bg = scenes.make("party", W, H, {"scheme": "grape"}, seed=7)
    img = bg.frame(1.0).convert("RGBA")
    sx0, sy0 = (W - 1546) // 2, (H - 423) // 2
    b = bitsy(400)
    img.alpha_composite(b, (sx0 + 10, sy0 + 12))
    name = load_config()["channel"]["name"].upper()
    f, lines = text.fit_font(name, 1080, 1, 190)
    title = text.render_block(lines, f, fill=color("sunshine"), stroke_ratio=0.1)
    img.alpha_composite(title, (sx0 + 440, sy0 + 40))
    tag = text.render_block([load_config()["channel"]["tagline"]], text.font(66, text.BODY), stroke_ratio=0.12)
    img.alpha_composite(tag, (sx0 + 450, sy0 + 40 + title.height))
    sched = text.render_block(["New facts every weekday  •  Spooky Bites on Fridays"],
                              text.font(44, text.BODY), stroke_ratio=0.14)
    img.alpha_composite(sched, (sx0 + 455, sy0 + 50 + title.height + tag.height))
    return img.convert("RGB")


def watermark(size: int = 150) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((0, 0, size - 1, size - 1), fill=(255, 255, 255, 255))
    b = bitsy(int(size * 0.84))
    img.alpha_composite(b, (int(size * 0.08), int(size * 0.07)))
    return img


def build_all() -> list:
    BRAND.mkdir(parents=True, exist_ok=True)
    SPRITES.mkdir(parents=True, exist_ok=True)
    out = []
    for name, im in (("avatar.png", avatar()), ("banner.png", banner()), ("watermark.png", watermark())):
        p = BRAND / name
        im.save(p)
        out.append(p)
    for mood, name in (("happy", "bitsy.png"), ("wink", "bitsy_wink.png")):
        p = SPRITES / name
        bitsy(720, mood).save(p)
        out.append(p)
    return out
