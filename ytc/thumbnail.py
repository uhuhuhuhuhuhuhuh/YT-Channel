"""1280×720 thumbnails: bright background, big hero sprite, huge outlined text."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import scenes, sprites, text
from .config import OUTPUT, color, load_config
from .episode import Episode

W, H = 1280, 720


def outline_sprite(img: Image.Image, width: int, rgb=(255, 255, 255)) -> Image.Image:
    """Sticker look: a solid outline around the sprite's silhouette."""
    pad = width * 2
    canvas = Image.new("RGBA", (img.width + 2 * pad, img.height + 2 * pad), (0, 0, 0, 0))
    canvas.paste(img, (pad, pad), img)
    alpha = canvas.getchannel("A").filter(ImageFilter.GaussianBlur(width * 0.6)).point(lambda v: 255 if v > 10 else 0)
    sticker = Image.new("RGBA", canvas.size, (*rgb, 0))
    sticker.putalpha(alpha)
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow.putalpha(alpha.point(lambda a: a * 0.45))
    shadow = shadow.filter(ImageFilter.GaussianBlur(width))
    out = Image.new("RGBA", (canvas.width + width, canvas.height + width), (0, 0, 0, 0))
    out.paste(shadow, (width, width), shadow)
    out.alpha_composite(sticker)
    out.alpha_composite(canvas)
    return out


def make_thumbnail(ep: Episode, out: Path | None = None) -> Path:
    th = ep.thumbnail
    bg_name = th.get("bg") or ep.segments[0].bg
    params = th.get("bg_params") or (ep.segments[0].bg_params if bg_name == ep.segments[0].bg else {})
    img = scenes.make(bg_name, W, H, params, ep.seed).frame(2.0).convert("RGBA")

    # soften the left side so the text pops
    grad = np.linspace(0.45, 0, W, dtype=np.float32)[None, :].repeat(H, 0)
    shade = Image.fromarray((grad * 255).astype(np.uint8), "L")
    dark = Image.new("RGBA", (W, H), (*color("ink"), 0))
    dark.putalpha(shade)
    img.alpha_composite(dark)

    sprite_names = th.get("sprites") or [th.get("sprite") or (ep.segments[0].sprites[0].name
                                                              if ep.segments[0].sprites else "sparkles")]
    main = sprites.load(sprite_names[0])
    target_h = int(H * 0.68)
    target_w = min(int(main.width * target_h / main.height), int(W * 0.46))
    target_h = int(main.height * target_w / main.width)
    hero = main.resize((target_w, target_h), Image.LANCZOS)
    hero = outline_sprite(hero, 12).rotate(-6, resample=Image.BICUBIC, expand=True)
    img.alpha_composite(hero, (int(W * 0.985 - hero.width), int(H * 0.52 - hero.height / 2)))
    for k, name in enumerate(sprite_names[1:3]):
        extra = sprites.load(name)
        eh = int(H * 0.28)
        extra = outline_sprite(extra.resize((int(extra.width * eh / extra.height), eh), Image.LANCZOS), 8)
        img.alpha_composite(extra, (int(W * (0.52 + 0.14 * k)), int(H * (0.05 + 0.6 * k))))

    words = (th.get("text") or ep.title).upper()
    f, lines = text.fit_font(words, int(W * 0.54), 3, 150)
    accent = color(ep.accent)
    runs = [[(ln, accent if i % 2 == 0 else (255, 255, 255))] for i, ln in enumerate(lines)]
    block = text.render_block(runs, f, stroke_ratio=0.12, align="left")
    block = block.rotate(4, resample=Image.BICUBIC, expand=True)
    img.alpha_composite(block, (int(W * 0.04), int(H * 0.47 - block.height / 2)))

    series = "SPOOKY BITES" if ep.series == "spooky" else load_config()["channel"]["name"].upper()
    pf = text.font(34, text.BODY)
    pw = int(pf.getlength(series)) + 44
    pill = Image.new("RGBA", (pw, 58), (0, 0, 0, 0))
    ImageDraw.Draw(pill).rounded_rectangle((0, 0, pw - 1, 57), radius=29,
                                           fill=(*color("grape" if ep.series != "spooky" else "ink"), 255),
                                           outline=(255, 255, 255, 255), width=4)
    ImageDraw.Draw(pill).text((pw / 2, 30), series, font=pf, fill=(255, 255, 255), anchor="mm")
    img.alpha_composite(pill, (28, H - 58 - 26))

    out = out or OUTPUT / f"{ep.slug}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out, quality=92)
    return out
