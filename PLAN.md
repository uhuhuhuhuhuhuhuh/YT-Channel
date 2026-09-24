# Channel Plan: **Wonder Bites**

> *Bite-sized facts for curious kids.*

## 1. The concept

**Wonder Bites** is a faceless channel for curious kids (roughly ages 6–12, and
the grown-ups watching with them). A friendly narrator serves up one amazing,
*true* fact per Short: an octopus has three hearts, a day on Venus is longer
than its year, you are a tiny bit taller in the morning.

A second recurring series, **Spooky Bites** (every Friday), covers the "scary
stories" side in a kid-safe way:

- **Spooky Stories**: gentle campfire tales. Spooky atmosphere, zero gore, no
  jump-scares, and every story ends with a reassuring or funny twist (the
  "ghost" turns out to be the cat, the "monster" is lonely and wants a friend).
- **Creepy-but-True**: real facts that sound spooky but teach something:
  glowing mushrooms, the anglerfish's lantern, "zombie" ants, why owls turn
  their heads so far.

Why this format:

| Requirement for a faceless channel | How Wonder Bites fits |
|---|---|
| No presenter on camera | Narration plus animated characters is normal for kids' content |
| Visuals we're allowed to use | Characters are **Microsoft Fluent Emoji 3D** (MIT licence). Backgrounds are **procedurally generated** by our code. No stock footage and no copyright claims |
| Evergreen demand | "Fun facts for kids" and "animal facts" are searched every day, all year |
| Short hooks | Every fact is a one-line hook |
| Parent-friendly | Educational, positive, safe; sources listed for every episode |
| Grows into long-form | Shorts from one topic compile into 5–10 min long-form videos ("25 Ocean Facts") |

## 2. Formats

| Format | Aspect | Length | Cadence | Purpose |
|---|---|---|---|---|
| **Fact Short** | 1080×1920 | 30–50 s | Mon–Thu | Discovery and growth |
| **Spooky Bites Short** | 1080×1920 | 40–58 s | Fri | Series viewers come back for |
| **Story / Compilation** | 1920×1080 | 3–10 min | 1 per week (from month 2) | Watch time and ad revenue |

Every Fact Short follows the same retention skeleton:

1. **Hook (0–3 s)**: the "WHOA" claim, in big on-screen text *and* voice.
2. **Explain (3–25 s)**: why it's true, in kid-level words (under 12 words per sentence).
3. **Compare (25–40 s)**: relate it to something a kid knows (school bus, bathtub, a pizza).
4. **Quiz / payoff (last 5–10 s)**: a question kids answer out loud ("Can you guess…?"), which prompts rewatches.

## 3. The pipeline (this repo)

Everything runs locally, offline, for free. The repo is a Python package
(`ytc`, the "YouTube channel" toolkit) plus the channel's content.

```
idea ──► script (YAML) ──► voice (Piper TTS, offline) ──► scenes (procedural backgrounds + animated sprites)
                                   │                                 │
                                   └──► timed word-by-word captions ◄┘
                                                   │
      music (generative, seeded per episode) ──► mix ──► ffmpeg ──► MP4 + thumbnail + metadata ──► YouTube API upload
```

| Stage | Module | Tech | Cost |
|---|---|---|---|
| Idea backlog | `channel/backlog.yaml` | curated list | free |
| Script drafting (optional) | `ytc/writer.py` | Claude API → episode YAML, then a human review | API key |
| Voice | `ytc/tts.py` | **Piper** offline TTS. Public-domain voices `kristin` (facts) and `norman` (Spooky storyteller) | free |
| Characters | `ytc/sprites.py` | Fluent Emoji 3D, cached in `assets/sprites/` | free (MIT) |
| Backgrounds | `ytc/scenes.py` | numpy + Pillow procedural scenes (sunny, ocean, space, jungle, night…) | free |
| Captions | `ytc/captions.py` | big bouncy word-by-word captions timed to the voice | free |
| Music & SFX | `ytc/audio.py` | generative music box / spooky music + "pop" and "whoosh" SFX | free, owned by us |
| Assembly | `ytc/render.py` | frames rendered in parallel and piped to ffmpeg (bundled) | free |
| Thumbnails | `ytc/thumbnail.py` | Pillow | free |
| Branding | `ytc/brand.py` | avatar, banner and watermark generator | free |
| Upload | `ytc/upload.py` | YouTube Data API v3, **made-for-kids flag set**, scheduled publishing | free quota |

CLI commands: `ytc render`, `ytc preview`, `ytc thumb`, `ytc brand`, `ytc draft`,
`ytc upload`, `ytc voices`, `ytc sprites`, `ytc list`.

## 4. Deliverables in this repo

- `PLAN.md`: this document
- `channel/brand.md`: name, personality, colours, fonts, About text
- `channel/strategy.md`: pillars, schedule, SEO, growth loop, monetisation, and **kids' policy compliance (COPPA / made for kids)**
- `channel/content-guidelines.md`: safety rules for kids' content and Spooky Bites
- `channel/setup-checklist.md`: the steps only a human can do (create the account and channel, API credentials)
- `channel/backlog.yaml`: 40+ topic ideas
- `episodes/`: first batch of fact-checked Shorts plus Spooky Bites episodes, with sources
- `ytc/`: the full render and upload pipeline
- `tests/`: unit tests
- `README.md`: quick start for running it locally

## 5. What a human still has to do

An AI can't create a Google account, pass phone verification, or accept
YouTube's terms. Those steps (about 15 minutes) are in
[`channel/setup-checklist.md`](channel/setup-checklist.md). After that, the
publish loop is `ytc render`, then **watch it yourself**, then `ytc upload`.

## 6. Roadmap

| Phase | Weeks | Goal |
|---|---|---|
| Launch | 1–2 | Channel set up, first 10 Shorts scheduled |
| Find the hook | 3–6 | 5 Shorts per week; double down on the topics in the top 10% (see the analytics loop in strategy) |
| Long-form | 7+ | 1 compilation or story per week, built from the best-performing topics |
| Monetise | when eligible | YouTube Partner Program: 1k subs + 4k watch hours, *or* 10M Shorts views in 90 days |
