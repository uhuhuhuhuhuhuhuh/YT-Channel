"""Episode scripts: loading and validating `episodes/<slug>/episode.yaml`."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .config import EPISODES, load_config

FORMATS = {"short", "long"}
MOTIONS = {
    "none", "bounce", "float", "pop", "wiggle", "spin", "pulse", "shake",
    "walk", "grow", "peek", "sway",
}
ENTRANCES = {"pop", "fade", "slide_left", "slide_right", "slide_up", "none"}


class EpisodeError(ValueError):
    pass


@dataclass
class Sprite:
    name: str
    x: float = 0.5                # centre, as a fraction of frame width
    y: float = 0.45               # centre, as a fraction of frame height
    size: float = 0.45            # width, as a fraction of frame width
    motion: str = "float"
    enter: str = "pop"
    delay: float = 0.0            # seconds after the segment starts
    flip: bool = False
    rotate: float = 0.0           # degrees, static tilt
    to: tuple[float, float] | None = None   # end position for "walk"
    shadow: bool = False
    label: str | None = None

    def key(self) -> tuple:
        """Identity used to keep a sprite on screen across segments."""
        return (self.name, round(self.x, 3), round(self.y, 3), round(self.size, 3),
                self.motion, self.flip, self.to)


@dataclass
class Segment:
    say: str                      # narration, also used for captions
    bg: str = "sunny"
    bg_params: dict = field(default_factory=dict)
    sprites: list[Sprite] = field(default_factory=list)
    headline: str | None = None   # big text shown during the segment
    spoken: str | None = None     # optional TTS override (e.g. pronunciation)
    pause: float | None = None    # silence after this segment (defaults to config)


@dataclass
class Episode:
    slug: str
    title: str
    series: str
    format: str
    description: str
    tags: list[str]
    segments: list[Segment]
    voice: str
    music: str
    accent: str
    thumbnail: dict
    sources: list[str]
    seed: int
    publish_at: str | None
    path: Path

    @property
    def size(self) -> tuple[int, int]:
        r = load_config()["render"][self.format]
        return r["width"], r["height"]

    @property
    def narration(self) -> str:
        return " ".join(s.say for s in self.segments)


def _sprite(raw, where: str) -> Sprite:
    if isinstance(raw, str):
        raw = {"name": raw}
    if "name" not in raw:
        raise EpisodeError(f"{where}: sprite needs a name")
    data = dict(raw)
    if data.get("to") is not None:
        data["to"] = tuple(data["to"])
    unknown = set(data) - set(Sprite.__dataclass_fields__)
    if unknown:
        raise EpisodeError(f"{where}: unknown sprite keys {sorted(unknown)}")
    s = Sprite(**data)
    if s.motion not in MOTIONS:
        raise EpisodeError(f"{where}: motion {s.motion!r} not in {sorted(MOTIONS)}")
    if s.enter not in ENTRANCES:
        raise EpisodeError(f"{where}: enter {s.enter!r} not in {sorted(ENTRANCES)}")
    return s


def load_episode(path: str | Path) -> Episode:
    """Load an episode from its folder, its YAML file, or its slug."""
    p = Path(path)
    if not p.exists() and (EPISODES / str(path)).exists():
        p = EPISODES / str(path)
    if not p.exists():
        matches = sorted(EPISODES.glob(f"*{path}*"))
        if len(matches) == 1:
            p = matches[0]
    if p.is_dir():
        p = p / "episode.yaml"
    if not p.exists():
        raise EpisodeError(f"episode not found: {path}")

    with open(p, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    cfg = load_config()
    series = raw.get("series", "facts")
    if series not in cfg["series"]:
        raise EpisodeError(f"{p}: unknown series {series!r}")
    series_cfg = cfg["series"][series]
    fmt = raw.get("format", "short")
    if fmt not in FORMATS:
        raise EpisodeError(f"{p}: format must be one of {sorted(FORMATS)}")

    default_bg = raw.get("bg", "sunny")
    default_params = raw.get("bg_params") or {}
    segments = []
    for i, seg in enumerate(raw.get("segments") or []):
        where = f"{p.parent.name} segment {i + 1}"
        if not seg.get("say"):
            raise EpisodeError(f"{where}: missing 'say'")
        bg = seg.get("bg", default_bg)
        # episode-level bg_params apply to segments using the episode's default background
        params = seg["bg_params"] if "bg_params" in seg else (default_params if bg == default_bg else {})
        segments.append(Segment(
            say=" ".join(str(seg["say"]).split()),
            bg=bg,
            bg_params=params or {},
            sprites=[_sprite(s, where) for s in seg.get("sprites") or []],
            headline=seg.get("headline"),
            spoken=seg.get("spoken"),
            pause=seg.get("pause"),
        ))
    if not segments:
        raise EpisodeError(f"{p}: no segments")

    voice = raw.get("voice", series_cfg["voice"])
    if voice not in cfg["voices"]:
        raise EpisodeError(f"{p}: unknown voice {voice!r}")

    title = raw.get("title") or p.parent.name
    if len(title) > 100:
        raise EpisodeError(f"{p}: YouTube titles must be 100 characters or fewer")

    return Episode(
        slug=raw.get("slug", p.parent.name),
        title=title,
        series=series,
        format=fmt,
        description=(raw.get("description") or "").strip(),
        tags=list(raw.get("tags") or []),
        segments=segments,
        voice=voice,
        music=raw.get("music", series_cfg["music"]),
        accent=raw.get("accent", series_cfg["accent"]),
        thumbnail=raw.get("thumbnail") or {},
        sources=list(raw.get("sources") or []),
        seed=int(raw.get("seed", sum(map(ord, p.parent.name)))),
        publish_at=raw.get("publish_at"),
        path=p.parent,
    )


def list_episodes() -> list[Path]:
    return sorted(d for d in EPISODES.iterdir() if (d / "episode.yaml").exists())
