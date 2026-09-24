"""Optional: draft a new episode with Claude.

    export ANTHROPIC_API_KEY=...        (or `ant auth login`)
    ytc draft "why do cats purr"  --series facts

The draft is written to episodes/NNN-<slug>/episode.yaml. It is a *draft*: a
human must fact-check it against the listed sources, and watch the render,
before anything is published. See channel/content-guidelines.md.
"""

from __future__ import annotations

import json
import re

import yaml

from .config import EPISODES, ROOT, SPRITES
from .episode import MOTIONS, list_episodes
from .scenes import BACKGROUNDS

MODEL = "claude-opus-5"

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


def draft(topic: str, series: str = "facts") -> str:
    """Ask Claude for an episode; return the path of the new YAML file."""
    import anthropic

    client = anthropic.Anthropic()
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=_system_prompt(series),
        messages=[{"role": "user", "content": f"Write an episode about: {topic}"}],
    )
    if response.stop_reason == "refusal":
        raise SystemExit(f"Claude declined this topic: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise SystemExit("Draft was cut off (max_tokens); try a narrower topic.")
    data = json.loads(next(b.text for b in response.content if b.type == "text"))
    return write_episode(data, series)


def write_episode(data: dict, series: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", data["slug"].lower()).strip("-")[:40] or "draft"
    num = 1 + max((int(p.name[:3]) for p in list_episodes() if p.name[:3].isdigit()), default=0)
    folder = EPISODES / f"{num:03d}-{slug}"
    folder.mkdir(parents=True, exist_ok=False)
    known = {p.stem for p in SPRITES.glob("*.png")}
    episode = {
        "title": data["title"],
        "series": series,
        "format": "short",
        "status": "draft - fact-check before rendering",
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
