# 🌟 Wonder Bites: a faceless YouTube channel for curious kids

**Wonder Bites** serves bite-sized, *true* facts for kids aged 6–12, plus
**Spooky Bites** every Friday: gentle campfire stories and creepy-but-true
nature facts. This repo holds the channel's plan, brand and scripts, and
`ytc`, a toolkit that turns a script into a finished video **offline, for
free**:

- narration from an offline neural voice (Piper, public-domain voices)
- animated procedural backgrounds with 3D emoji characters
- bouncy word-by-word captions timed to the voice
- original generated music and sound effects
- a thumbnail, a `.srt` caption file, and upload metadata

**Start here:** [PLAN.md](PLAN.md) → [channel/setup-checklist.md](channel/setup-checklist.md)
→ the quick start below.

| Doc | What's in it |
|---|---|
| [PLAN.md](PLAN.md) | Concept, formats, pipeline, roadmap |
| [channel/brand.md](channel/brand.md) | Name, mascot, colours, fonts, About text, playlists |
| [channel/strategy.md](channel/strategy.md) | Pillars, schedule, made-for-kids trade-offs, SEO, analytics loop, monetisation |
| [channel/content-guidelines.md](channel/content-guidelines.md) | **Safety rules for kids' content and Spooky Bites** |
| [channel/setup-checklist.md](channel/setup-checklist.md) | Creating the channel and API credentials (human-only steps) |
| [channel/backlog.yaml](channel/backlog.yaml) | 50 topic ideas |

## Quick start

Needs Python 3.10+. ffmpeg is bundled through `imageio-ffmpeg`, so there's
nothing else to install.

```bash
git clone <this repo> && cd YT-Channel
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e .

ytc voices download                  # ~130 MB of Piper voice models → voices/
ytc brand                            # avatar, banner, watermark, mascot sprites
ytc list                             # the 12 ready-made episodes
ytc preview 001                      # fast half-size render → output/…-preview.mp4
ytc render 001                       # full 1080×1920 video + thumbnail → output/
```

A 45-second Short renders in about a minute on a 4-core laptop.

## Publishing workflow

```bash
ytc draft "why do cats purr"         # optional: Claude writes a first draft (needs API key)
# …edit episodes/NNN-*/episode.yaml and open every source to check the facts…
ytc check 013                        # validates sprites, layout, length, sources
ytc preview 013                      # quick look
ytc render 013                       # final MP4 + JPG thumbnail + SRT captions
# watch output/013-*.mp4 start to finish
ytc meta 013                         # the title/description/tags that will be used
ytc upload 013                       # uploads as PRIVATE (see setup checklist, part B)
```

Without API upload, drag the MP4 into YouTube Studio, paste the text from
`ytc meta`, and set **Audience → Yes, it's made for kids**.

## Writing an episode

Each episode is one YAML file: `episodes/NNN-slug/episode.yaml`. The shortest
useful example:

```yaml
title: "An Octopus Has THREE Hearts?! 🐙 #shorts"
series: facts            # facts | spooky (sets voice, music, accent colour)
format: short            # short = 1080×1920, long = 1920×1080
bg: ocean                # default background for every segment
description: |
  An octopus has three hearts AND blue blood!
tags: [octopus, animal facts for kids]
thumbnail: {text: "3 HEARTS?!", sprite: octopus}

segments:
  - say: Did you know an octopus has three hearts?     # narration + captions
    headline: "3 HEARTS?!"                             # big text (optional)
    sprites:
      - {name: octopus, x: 0.5, y: 0.45, size: 0.55, motion: bounce}

  - say: Quick quiz! How many hearts does an octopus have?
    bg: party
    bg_params: {scheme: sky}
    pause: 1.2                                         # extra thinking time
    sprites:
      - {name: red question mark, x: 0.8, y: 0.3, size: 0.16, motion: wiggle, delay: 0.5}

sources:
  - "Smithsonian Magazine: https://…"
```

### Segment fields

| Field | Meaning |
|---|---|
| `say` | What the narrator says. Also becomes the captions. |
| `spoken` | Optional: what the voice actually reads, to fix a pronunciation. |
| `headline` | Big text near the top (keep it to 28 characters or fewer, no emoji). |
| `bg` / `bg_params` | Background for this segment (see below). |
| `sprites` | Characters on screen (see below). |
| `pause` | Silence after the segment, in seconds (default 0.35). |

### Sprites

`name` is any [Fluent Emoji](https://github.com/microsoft/fluentui-emoji/tree/main/assets)
name in lower case ("octopus", "red heart", "ghost"), or `bitsy` / `bitsy_wink`
for the mascot. Missing sprites download automatically into `assets/sprites/`.
You can also drop any PNG in there and use its filename.

| Key | Default | Meaning |
|---|---|---|
| `x`, `y` | 0.5, 0.45 | Centre, as a fraction of width/height. In Shorts keep `y` between 0.2 and 0.66 (headline sits at ~0.15, captions at ~0.72). |
| `size` | 0.45 | Width as a fraction of frame width |
| `motion` | `float` | `none` `float` `bounce` `pop` `wiggle` `spin` `pulse` `shake` `sway` `walk` `grow` `peek` |
| `enter` | `pop` | `pop` `fade` `slide_left` `slide_right` `slide_up` `none` |
| `delay` | 0 | Seconds after the segment starts |
| `to` | | `[x, y]` end point for `walk` |
| `flip`, `rotate` | | Mirror horizontally; tilt in degrees |
| `shadow`, `label` | | Ground shadow; small text under the sprite |

A sprite repeated with the same name, position, size and motion in the next
segment **stays on screen**. It doesn't pop in again.

### Backgrounds

| `bg` | Look | `bg_params` |
|---|---|---|
| `sunny` | Blue sky, spinning sun, clouds, hills | |
| `meadow` | Flowery hills, pollen sparkles | |
| `ocean` | Light rays, bubbles, swaying seaweed | |
| `deepsea` | Dark water, glowing specks | |
| `space` | Nebula, twinkling stars, shooting stars, cartoon planets | `planets: false` |
| `night` | Moon, twisty trees, fog, fireflies | `house`, `trees`, `lighthouse`, `lamp_on`, `sea`, `moon: [x, y]` |
| `party` | Scrolling gradient + confetti | `scheme: grape / sky / sunset / mint` |
| `body` | Pink with drifting blood cells | |
| `snow`, `desert` | Falling snow / blowing sand | |
| `plain` | Flat colour | `color: grape` |

## Commands

| Command | Does |
|---|---|
| `ytc list` | Episodes, with ▶ rendered and ↑ uploaded markers |
| `ytc check <ep…> \| --all` | Validate sprites, layout, headline glyphs, length, sources |
| `ytc preview <ep>` | Half-size, 15 fps render for a quick look |
| `ytc render <ep…> \| --all` | Final MP4 + thumbnail + SRT into `output/` |
| `ytc still <ep> -t 3.5` | One frame as PNG |
| `ytc thumb <ep…>` | Thumbnails only |
| `ytc meta <ep>` | Print upload title/description/tags |
| `ytc brand` | Regenerate avatar, banner, watermark, mascot |
| `ytc voices download` | Fetch the Piper voices |
| `ytc sprites fetch --all` | Pre-download every sprite used by episodes |
| `ytc draft "<topic>" [--series spooky]` | Claude drafts a new episode (`pip install -e ".[draft]"`) |
| `ytc upload <ep> [--publish-at …]` | Upload through the YouTube Data API (`pip install -e ".[upload]"`) |

Channel-wide settings (voices, speed, music volume, fps, colours) are in
[config.yaml](config.yaml).

## Repo layout

```
PLAN.md                 the channel plan
config.yaml             channel + render settings
channel/                brand, strategy, guidelines, setup checklist, backlog
episodes/NNN-slug/      one episode.yaml per video (+ upload.json once uploaded)
assets/fonts/           Luckiest Guy (Apache 2.0), Fredoka (OFL) + licences
assets/sprites/         cached Fluent Emoji PNGs + mascot
assets/brand/           avatar, banner, watermark (from `ytc brand`)
ytc/                    the toolkit
  tts.py                Piper/edge TTS, caching, word timings
  scenes.py             procedural backgrounds
  render.py             timeline, compositor, parallel ffmpeg render
  audio.py              music generators, SFX, ducking mix
  captions.py thumbnail.py brand.py sprites.py text.py
  writer.py             Claude drafting (optional)
  upload.py             YouTube Data API upload (optional)
tests/                  `pytest`
output/ build/ voices/ secrets/   git-ignored
```

## Licences and credits

- Code: this repo (add a LICENSE file if you open-source it).
- Characters: [Microsoft Fluent Emoji](https://github.com/microsoft/fluentui-emoji), MIT licence (credited in every description).
- Voices: Piper [`kristin`](https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0/en/en_US/kristin) and
  [`norman`](https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0/en/en_US/norman), trained on public-domain LibriVox recordings.
  (Avoid voices trained on non-commercial datasets such as `ryan` or `hfc_*` on a monetised channel.)
- Fonts: Luckiest Guy (Apache 2.0), Fredoka (SIL OFL). Licence files are in `assets/fonts/`.
- Music, SFX, backgrounds, mascot: generated by this code.

## Troubleshooting

- **`Voice model missing`**: run `ytc voices download`.
- **`Sprite 'x' not found`**: the name must match a folder in the Fluent Emoji
  repo (sentence case, e.g. "Red heart" → `red heart`). Some have odd names:
  sheep is `ewe`.
- **A headline shows boxes**: Luckiest Guy has no emoji. `ytc check` flags these.
- **Rendering is slow**: use `ytc preview` while iterating, or pass `--workers N`.
