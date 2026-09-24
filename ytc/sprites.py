"""Character art: Microsoft Fluent Emoji 3D (MIT licence), cached in assets/sprites.

Refer to a sprite by its Fluent Emoji name, e.g. "octopus", "red heart",
"ghost", "thumbs up". Any PNG you drop into assets/sprites/<name>.png (spaces →
underscores) works too, which is how the channel mascot "bitsy" is provided.
"""

from __future__ import annotations

import functools
import urllib.parse
import urllib.request

from PIL import Image

from .config import SPRITES

FLUENT = "https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets"


def slug(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def path_for(name: str):
    return SPRITES / f"{slug(name)}.png"


def fluent_urls(name: str) -> list[str]:
    folder = name.strip()
    folder = folder[0].upper() + folder[1:].lower()
    q = urllib.parse.quote
    s = slug(name)
    return [
        f"{FLUENT}/{q(folder)}/3D/{s}_3d.png",
        f"{FLUENT}/{q(folder)}/Default/3D/{s}_3d_default.png",
    ]


def fetch(name: str, force: bool = False):
    """Download a Fluent Emoji sprite into assets/sprites (if missing)."""
    dest = path_for(name)
    if dest.exists() and not force:
        return dest
    SPRITES.mkdir(parents=True, exist_ok=True)
    errors = []
    for url in fluent_urls(name):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                data = r.read()
            if not data.startswith(b"\x89PNG"):
                raise ValueError("not a PNG")
            dest.write_bytes(data)
            return dest
        except Exception as e:  # noqa: BLE001 - report every URL we tried
            errors.append(f"{url}: {e}")
    raise FileNotFoundError(
        f"Sprite {name!r} not found. Use the name from "
        "https://github.com/microsoft/fluentui-emoji/tree/main/assets\n" + "\n".join(errors))


@functools.lru_cache(maxsize=256)
def load(name: str, max_px: int = 720) -> Image.Image:
    """RGBA sprite, upscaled once to `max_px` wide for cheap per-frame resizing."""
    p = path_for(name)
    if not p.exists():
        p = fetch(name)
    img = Image.open(p).convert("RGBA")
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    if img.width < max_px:
        h = round(img.height * max_px / img.width)
        img = img.resize((max_px, h), Image.LANCZOS)
    return img
