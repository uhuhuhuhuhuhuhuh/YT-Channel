"""Optional: draft a new episode with any AI model.

    ytc draft "why do cats purr"                         # default model (config.yaml → ai.default)
    ytc draft "why do cats purr" --model openai:gpt-5
    ytc draft "glowing jellyfish" --series spooky --model ollama:llama3.2

The draft is written to episodes/NNN-<slug>/episode.yaml. It is a *draft*: a
human must fact-check it against the listed sources, and watch the render,
before anything is published. See channel/content-guidelines.md.
"""

from __future__ import annotations

import difflib
import re
import unicodedata

import yaml

from . import ai
from .config import EPISODES, ROOT, SPRITES
from .episode import MOTIONS, list_episodes
from .scenes import BACKGROUNDS

SPRITE_IDEAS = (
    "octopus, red heart, blue heart, whale, spouting whale, shark, fish, tropical fish, crab, lobster, "
    "dolphin, jellyfish, snail, butterfly, honeybee, lady beetle, ant, spider, bat, owl, eagle, penguin, "
    "flamingo, parrot, chicken, cow, pig, ewe, dog, cat, lion, tiger, elephant, giraffe, zebra, gorilla, "
    "sloth, otter, koala, panda, polar bear, frog, turtle, crocodile, snake, t-rex, sauropod, mushroom, deciduous tree, evergreen tree, cactus, sunflower, rock, volcano, snowflake, "
    "cloud, sun, full moon, crescent moon, ringed planet, globe showing americas, rocket, "
    "flying saucer, star, glowing star, sparkles, fire, droplet, water wave, rainbow, high voltage, "
    "brain, bone, tooth, eye, ear, nose, footprints, flexed biceps, test tube, microscope, telescope, "
    "light bulb, magnifying glass tilted left, books, trophy, party popper, red question mark, "
    "exclamation question mark, hourglass done, alarm clock, ghost, jack-o-lantern, candle, "
    "crystal ball, spider web, house, castle, old key, diya lamp, bed, teddy bear, "
    "pizza, banana, strawberry, honey pot, ice, bitsy (the channel mascot), bitsy_wink"
)

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "slug", "description", "tags", "thumbnail_text", "thumbnail_sprite",
                 "segments", "sources"],
    "properties": {
        "title": {"type": "string"},
        "slug": {"type": "string"},
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "thumbnail_text": {"type": "string"},
        "thumbnail_sprite": {"type": "string"},
        "sources": {"type": "array", "items": {"type": "string"}},
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["say", "headline", "bg", "sprites"],
                "properties": {
                    "say": {"type": "string"},
                    "headline": {"type": "string"},
                    "bg": {"type": "string", "enum": sorted(BACKGROUNDS)},
                    "sprites": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["name", "x", "y", "size", "motion"],
                            "properties": {
                                "name": {"type": "string"},
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                                "size": {"type": "number"},
                                "motion": {"type": "string", "enum": sorted(MOTIONS)},
                            },
                        },
                    },
                },
            },
        },
    },
}


def _system_prompt(series: str) -> str:
    guidelines = (ROOT / "channel" / "content-guidelines.md").read_text(encoding="utf-8")
    example = (list_episodes()[0] / "episode.yaml").read_text(encoding="utf-8") if list_episodes() else ""
    return f"""You write scripts for Wonder Bites, a faceless YouTube channel of 30–55 second vertical \
Shorts for curious kids aged 6–12. Series for this script: {series!r}.

Follow the channel's content guidelines exactly:

{guidelines}

Format rules:
- 6–9 segments. Each segment's `say` is one or two short sentences (under 12 words each) read aloud
  by a text-to-speech narrator, so write numbers and words the way they should be spoken.
- Total narration 90–140 words.
- `headline` is 1–3 punchy words shown huge on screen (empty string for none). No emoji in headlines.
- Sprites are Microsoft Fluent Emoji names (lowercase, e.g. "octopus", "red heart"). Good options:
  {SPRITE_IDEAS}. Use 1–3 sprites per segment. x/y are the centre as fractions of a 1080×1920 frame
  (keep y between 0.28 and 0.6 so captions at y≈0.72 and the headline at y≈0.15 stay clear);
  size is width as a fraction of frame width (0.12–0.6).
- Repeat a sprite with identical name/x/y/size/motion in consecutive segments to keep it on screen.
- Backgrounds: {", ".join(sorted(BACKGROUNDS))}. Spooky Bites uses night or deepsea.
- End with the out-loud quiz and a friendly sign-off.
- Only include facts you are confident are true, and list 2–3 reputable sources (NASA, NOAA,
  Smithsonian, National Geographic, Britannica, museums, universities) as "Name: URL".
- Title ≤ 70 characters plus " #shorts".

Here is a finished episode to match in tone and structure:

{example}"""


def draft(topic: str, series: str = "facts", model: str | None = None) -> str:
    """Ask the chosen model for an episode; return the path of the new YAML file."""
    target = ai.resolve(model)
    print(f"drafting with {target} …")
    data = ai.ask_json(f"Write an episode about: {topic}", _system_prompt(series), SCHEMA,
                       model=model, validate=clean)
    return write_episode(data, series, str(target))


def known_sprites() -> list[str]:
    names = {n.strip() for n in SPRITE_IDEAS.split(",")}
    names |= {p.stem.replace("_", " ") for p in SPRITES.glob("*.png")}
    return sorted(names)


def sprite_name(raw: str, known: list[str]) -> str:
    """Map a model's sprite guess ("cat_girl", "Heart Eyes") onto a real sprite name."""
    n = re.sub(r"\s+", " ", str(raw).lower().replace("_", " ").replace("-", " ")).strip()
    lookup = {k.replace("-", " "): k for k in known}
    if n in lookup:
        return lookup[n]
    words = n.split()
    contained = [k for k in lookup if set(k.split()) <= set(words)]
    if contained:
        # most specific match first; on a tie, the earliest word is usually the subject
        return lookup[min(contained, key=lambda k: (-len(k.split()), words.index(k.split()[0])))]
    close = difflib.get_close_matches(n, list(lookup), n=1, cutoff=0.6)
    return lookup[close[0]] if close else "bitsy"


def speakable(text: str) -> str:
    """Drop emoji and other symbols the narrator would stumble over."""
    kept = "".join(ch for ch in str(text)
                   if unicodedata.category(ch) not in ("So", "Sk", "Cs", "Co")
                   and ch not in "\u200d\ufe0f")
    return " ".join(kept.split())


def _num(v, lo: float, hi: float, default: float) -> float:
    try:
        return min(hi, max(lo, float(v)))
    except (TypeError, ValueError):
        return default


def clean(data: dict) -> dict:
    """Repair the small mistakes models make, especially smaller local ones."""
    if not isinstance(data.get("segments"), list) or not data["segments"]:
        raise ValueError("the JSON must include a non-empty 'segments' list")
    known = known_sprites()
    default_bg = next((seg.get("bg") for seg in data["segments"] if isinstance(seg, dict)
                       and seg.get("bg") in BACKGROUNDS), "sunny")
    segments = []
    for seg in data["segments"]:
        if not isinstance(seg, dict) or not speakable(seg.get("say", "")):
            continue
        sprites = []
        for sp in seg.get("sprites") or []:
            if not isinstance(sp, dict) or not sp.get("name"):
                continue
            sprites.append({
                "name": sprite_name(sp["name"], known),
                "x": _num(sp.get("x"), 0.08, 0.92, 0.5),
                "y": _num(sp.get("y"), 0.25, 0.62, 0.45),
                "size": _num(sp.get("size"), 0.08, 0.6, 0.35),
                "motion": sp.get("motion") if sp.get("motion") in MOTIONS else "float",
            })
        segments.append({
            "say": speakable(seg["say"]),
            "headline": speakable(seg.get("headline") or "")[:28],
            "bg": seg.get("bg") if seg.get("bg") in BACKGROUNDS else default_bg,
            "sprites": sprites[:3],
        })
    if not segments:
        raise ValueError("every segment needs a non-empty 'say' line")
    title = str(data.get("title") or "Untitled draft")[:100]
    first_sprite = next((sp["name"] for seg in segments for sp in seg["sprites"]), "bitsy")
    return {
        "title": title,
        # the title is a more reliable source for the folder name than a model's slug
        "slug": re.sub(r"#\w+", "", speakable(title)) or str(data.get("slug") or "draft"),
        "description": str(data.get("description") or ""),
        "tags": [str(t) for t in data.get("tags") or []][:15],
        "thumbnail_text": speakable(data.get("thumbnail_text") or title)[:30],
        "thumbnail_sprite": sprite_name(data["thumbnail_sprite"], known) if data.get("thumbnail_sprite")
        else first_sprite,
        "segments": segments,
        "sources": [str(x) for x in data.get("sources") or []],
    }


def write_episode(data: dict, series: str, drafted_by: str = "") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", data["slug"].lower()).strip("-")[:40] or "draft"
    num = 1 + max((int(p.name[:3]) for p in list_episodes() if p.name[:3].isdigit()), default=0)
    folder = EPISODES / f"{num:03d}-{slug}"
    folder.mkdir(parents=True, exist_ok=False)
    known = {p.stem for p in SPRITES.glob("*.png")}
    episode = {
        "title": data["title"],
        "series": series,
        "format": "short",
        "status": f"draft by {drafted_by or 'AI'}: fact-check before rendering",
        "description": data["description"],
        "tags": data["tags"],
        "thumbnail": {"text": data["thumbnail_text"], "sprite": data["thumbnail_sprite"]},
        "segments": [],
        "sources": data["sources"],
    }
    for seg in data["segments"]:
        entry = {"say": seg["say"], "bg": seg["bg"]}
        if seg["headline"].strip():
            entry["headline"] = seg["headline"].strip()
        entry["sprites"] = [{k: s[k] for k in ("name", "x", "y", "size", "motion")} for s in seg["sprites"]]
        episode["segments"].append(entry)
    path = folder / "episode.yaml"
    path.write_text(yaml.safe_dump(episode, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")
    new_sprites = {s["name"] for seg in data["segments"] for s in seg["sprites"]} - known
    if new_sprites:
        print(f"note: new sprites will be downloaded on render: {sorted(new_sprites)}")
    return str(path)
