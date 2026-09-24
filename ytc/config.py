"""Repo paths and the channel config (config.yaml)."""

from __future__ import annotations

import functools
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FONTS = ASSETS / "fonts"
SPRITES = ASSETS / "sprites"
EPISODES = ROOT / "episodes"
BUILD = ROOT / "build"
OUTPUT = ROOT / "output"
VOICES = ROOT / "voices"
SECRETS = ROOT / "secrets"


@functools.lru_cache(maxsize=1)
def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def color(name_or_hex: str) -> tuple[int, int, int]:
    """Resolve a palette name ("sunshine") or a hex string ("#FFD23F")."""
    palette = load_config().get("palette", {})
    return hex_to_rgb(palette.get(name_or_hex, name_or_hex))
