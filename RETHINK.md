# Rethink: from emoji Shorts to tiny films

The first version of Wonder Bites worked, but watching the renders back, it was
the wrong product. This note records what was wrong, what changed, and what's
still to do.

## What was wrong with v1

| Problem | Why it matters |
|---|---|
| **Generic look.** Emoji stickers bouncing on gradient backgrounds with text on top. | It looks like hundreds of other templated kids' channels. YouTube's *inauthentic content* policy specifically demonetises mass-produced, template-driven videos. Nothing about it was ownable. |
| **A slideshow, not a film.** Every segment was "sticker + headline + captions". | No camera, no acting, no reason to keep watching. The same 3-element layout for every fact. |
| **Too much text.** Headline and captions on screen at once. | A big part of the audience can't read yet. The words competed with the pictures. |
| **Robotic narration.** Piper's medium-quality voices. | Kids' content lives or dies on a warm, expressive narrator. |
| **Fact lists.** "Did you know… did you know… quiz." | No character, no stakes, no feelings. Children remember stories, not lists. |
| **Shorts-first economics.** | Made-for-kids Shorts earn very little per view. Long-form watch time is where a kids' channel's revenue comes from. |

## What changed

**Format: tiny films.** 1½–4 minute 16:9 films, each following one character
through a true story. Facts aren't listed; they *happen*: we see Olive's big
heart stop when she swims, and that's why she'd rather crawl. Shorts become
trailers cut from the films, not the product.

**Look: a paper-cut diorama.** A new renderer (`ytc/film/`) builds every scene
from layers of hand-cut paper:

- real depth: layers sit at different distances, so camera pans and push-ins
  have true parallax, with depth-of-field blur and atmospheric tint
- paper grain and embossed cut edges on every piece, soft cast shadows, film
  grain and a vignette over the frame
- kelp that sways, fish schools, marine snow drifting at several depths,
  bubbles, light rays from the surface

**Characters that act.** Olive the octopus is drawn fresh every frame from
parameters, not pasted. Eight tapered arms with travelling waves and curled
tips, suckers, horizontal-slit pupils (like a real octopus), blinks, cheeks,
colour change from camouflage to orange, jetting, crawling, and an x-ray view
where her three hearts pulse and blue blood flows.

**Voice: Kokoro.** An open, Apache-2.0 TTS model (82M parameters) that runs
offline on a CPU and sounds far more natural than Piper. Voice `af_heart`,
slightly slowed for storytelling.

**Sound designed to picture.** Heartbeats you hear exactly when the hearts
beat on screen (lighter when the big heart stops), bubbles, a whoosh for the
jet, a soft swell for the passing shadow, chimes as the hearts are counted, an
underwater ambience bed and a gentle score. All synthesised, all owned.

**Almost no on-screen text.** One title card, a few paper word tags ("3
HEARTS", "BLUE BLOOD") and the end card. Captions go up as a proper closed
caption file (`.srt`) instead of being burned in.

**Hand-directed, on purpose.** Each film has a screenplay
(`films/<name>/screenplay.py`): narration beats, plus camera moves and
character actions placed on the narrator's words, e.g.
`O["big_on"].move(C(11, "stops"), …, 0.0)` stops the heart exactly when the
narrator says "stops". This takes more work per film than the old YAML, and
that's the point: every film is individually directed, which is both what makes
it good and what keeps it clear of "templated content".

## The example film

`films/olive-three-hearts/` (about 90 seconds):

> Deep down, where the sunlight turns blue, a little octopus called Olive is
> hiding in her den. She pops out, changes colour, and shows us her secret: an
> x-ray reveals three hearts and blue blood. A big shadow glides by, so she
> jets away, and her big heart stops beating while she swims. Tired, she lands
> and crawls to a cozy new den as dusk falls, and we count her three hearts
> together.

Render it: `ytc film olive` → `output/film-olive-three-hearts.mp4` (+ `.srt`).
Preview: `ytc film olive --preview`. One frame: `ytc film olive --still 30`.

## What's kept from v1

The brand (Wonder Bites, Bitsy), the content-safety guidelines, the
fact-checking rule (sources in `film.yaml`), the upload pipeline, the
any-model `ytc ask` / `ytc draft` tools, and the old Short pipeline (`ytc render`),
which still works for quick experiments.

## What's not done yet

- **Shorts cut-downs.** A vertical reframe of a film's best 30–45 s, to act as a
  trailer. The renderer already supports any output size; it needs a
  "reframe" camera track.
- **More characters.** Only the octopus exists. Each new animal (a honeybee,
  a sea otter) is a new character module, about a day of work each.
- **More worlds.** Only the reef exists (`ytc/film/reef.py`). A meadow, a night
  sky and a forest would cover most of the backlog.
- **Upload for films.** `ytc upload` still expects an episode. Films need the
  same metadata hookup.
- **Human review.** Nobody has watched the example film with a child yet.
  That's the real test.

## Cadence, revised

| | Before | Now |
|---|---|---|
| Main format | 5 Shorts / week | 1 film / week (1½–4 min, 16:9) |
| Shorts | the product | 2–3 trailers cut from each film |
| Audience | 6–12, reading captions | 4–10, no reading needed |
| Production | ~10 min/Short, templated | ~1 day/film, directed |
