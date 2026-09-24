"""Fonts and chunky, outlined text rendering."""

from __future__ import annotations

import functools

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import FONTS

DISPLAY = "LuckiestGuy-Regular.ttf"   # headlines, captions, thumbnails
BODY = "Fredoka.ttf"                  # labels, small text


@functools.lru_cache(maxsize=64)
def font(size: int, name: str = DISPLAY, weight: str | None = "Bold") -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONTS / name), size)
    if weight and name == BODY:
        try:
            f.set_variation_by_name(weight)
        except (OSError, ValueError):
            pass
    return f


def wrap(text: str, fnt: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split():
            trial = f"{cur} {word}".strip()
            if fnt.getlength(trial) <= max_width or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def fit_font(text: str, max_width: int, max_lines: int, start: int, name: str = DISPLAY,
             min_size: int = 20) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    size = start
    while size > min_size:
        f = font(size, name)
        lines = wrap(text, f, max_width)
        if len(lines) <= max_lines and all(f.getlength(l) <= max_width for l in lines):
            return f, lines
        size = int(size * 0.92)
    f = font(min_size, name)
    return f, wrap(text, f, max_width)


def render_block(lines: list[str] | list[list[tuple[str, tuple]]], fnt: ImageFont.FreeTypeFont,
                 fill=(255, 255, 255), stroke=(43, 33, 64), stroke_ratio: float = 0.09,
                 shadow: bool = True, line_gap: float = 0.08, align: str = "center") -> Image.Image:
    """Render outlined text to a tight RGBA image.

    `lines` is either plain strings, or lists of (word, colour) runs so single
    words can be highlighted.
    """
    runs = [[(l, fill)] if isinstance(l, str) else l for l in lines]
    size = fnt.size
    sw = max(2, int(size * stroke_ratio))
    ascent, descent = fnt.getmetrics()
    lh = ascent + descent
    space = fnt.getlength(" ")
    widths = [sum(fnt.getlength(w) for w, _ in r) + space * (len(r) - 1) for r in runs]
    W = int(max(widths) + sw * 2 + size * 0.2)
    H = int(len(runs) * lh + (len(runs) - 1) * lh * line_gap + sw * 2 + size * 0.25)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = sw
    for r, width in zip(runs, widths):
        x = sw + (W - 2 * sw - width) / 2 if align == "center" else sw
        for word, col in r:
            if shadow:
                ImageDraw.Draw(sh).text((x, y + size * 0.08), word, font=fnt, fill=(0, 0, 0, 110),
                                        stroke_width=sw, stroke_fill=(0, 0, 0, 110))
            d.text((x, y), word, font=fnt, fill=col, stroke_width=sw, stroke_fill=stroke)
            x += fnt.getlength(word) + space
        y += lh * (1 + line_gap)
    if shadow:
        sh = sh.filter(ImageFilter.GaussianBlur(size * 0.05))
        sh.alpha_composite(img)
        img = sh
    return img
