"""`ytc`: command line for the Wonder Bites pipeline. Run `ytc -h` for help."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .ai import AIError
from .config import OUTPUT, load_config
from .episode import Episode, EpisodeError, list_episodes, load_episode


def _episodes(args) -> list[Episode]:
    if getattr(args, "all", False):
        return [load_episode(p) for p in list_episodes()]
    if not args.episodes:
        raise SystemExit("name at least one episode (number, slug or folder), or use --all")
    return [load_episode(e) for e in args.episodes]


def cmd_list(args):
    for p in list_episodes():
        try:
            ep = load_episode(p)
        except EpisodeError as e:
            print(f"  !! {p.name}: {e}")
            continue
        done = "▶" if (OUTPUT / f"{ep.slug}.mp4").exists() else " "
        up = "↑" if (p / "upload.json").exists() else " "
        print(f"{done}{up} {p.name:38s} {ep.series:7s} {ep.format:5s} {len(ep.narration.split()):4d} words  {ep.title}")


def estimate_seconds(ep: Episode) -> float:
    from . import tts

    cfg = load_config()
    total = cfg["render"]["lead_in"] + cfg["render"]["tail"]
    for seg in ep.segments:
        total += tts.speak(seg.say, ep.voice, seg.spoken).duration
        total += seg.pause if seg.pause is not None else cfg["audio"]["segment_pause"]
    return total


def check_episode(ep: Episode, with_voice: bool = True) -> list[str]:
    """Problems that should block publishing (empty list = good to go)."""
    from . import sprites
    from .text import DISPLAY, font

    problems = []
    if not ep.sources:
        problems.append("no sources listed: every fact must be checkable")
    if len(ep.title) > 100:
        problems.append("title longer than 100 characters")
    if ep.format == "short" and "#shorts" not in (ep.title + ep.description).lower():
        problems.append("short without #shorts in title/description (added on upload anyway)")
    f = font(40, DISPLAY)
    notdef = bytes(f.getmask("\U000F0000"))      # what the font draws for a missing glyph

    def missing_glyph(ch: str) -> bool:
        m = f.getmask(ch)
        return m.getbbox() is None or bytes(m) == notdef
    for i, seg in enumerate(ep.segments, 1):
        if seg.headline:
            if len(seg.headline) > 28:
                problems.append(f"segment {i}: headline over 28 characters")
            missing = [ch for ch in seg.headline if ch.strip() and missing_glyph(ch)]
            if missing:
                problems.append(f"segment {i}: headline characters the font can't draw: {missing}")
        for s in seg.sprites:
            try:
                sprites.load(s.name)
            except FileNotFoundError:
                problems.append(f"segment {i}: sprite {s.name!r} not found")
            if ep.format == "short" and not (0.2 <= s.y <= 0.66):
                problems.append(f"segment {i}: sprite {s.name!r} y={s.y} may collide with headline/captions")
    if with_voice:
        secs = estimate_seconds(ep)
        if ep.format == "short" and secs > 59:
            problems.append(f"runs {secs:.0f}s; keep Shorts under 60s for best retention")
    return problems


def cmd_check(args):
    bad = 0
    for ep in _episodes(args):
        problems = check_episode(ep, not args.fast)
        mark = "✔" if not problems else "✘"
        extra = "" if args.fast else f"  (~{estimate_seconds(ep):.0f}s)"
        print(f"{mark} {ep.path.name}{extra}")
        for p in problems:
            print(f"    - {p}")
        bad += bool(problems)
    sys.exit(1 if bad else 0)


def cmd_render(args):
    from .render import render
    from .thumbnail import make_thumbnail

    for ep in _episodes(args):
        if args.preview:
            render(ep, scale=0.5, fps=15, workers=args.workers)
        else:
            render(ep, workers=args.workers)
            print(f"✔ {make_thumbnail(ep)}")


def cmd_still(args):
    from .render import still

    ep = load_episode(args.episode)
    out = Path(args.out or OUTPUT / f"{ep.slug}-t{args.t:g}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    still(ep, args.t).save(out)
    print(f"✔ {out}")


def cmd_thumb(args):
    from .thumbnail import make_thumbnail

    for ep in _episodes(args):
        print(f"✔ {make_thumbnail(ep)}")


def cmd_meta(args):
    from .upload import build_body

    body = build_body(load_episode(args.episode))
    sn = body["snippet"]
    print(f"TITLE: {sn['title']}\n\nDESCRIPTION:\n{sn['description']}\n\nTAGS: {', '.join(sn['tags'])}")
    print(f"\nMADE FOR KIDS: {body['status']['selfDeclaredMadeForKids']}")


def cmd_brand(args):
    from .brand import build_all

    for p in build_all():
        print(f"✔ {p}")


def cmd_voices(args):
    from .tts import download_voices

    for p in download_voices(args.names or None):
        print(f"✔ {p}")


def cmd_sprites(args):
    from . import sprites

    names = set(args.names)
    for p in list_episodes() if args.all or not names else []:
        ep = load_episode(p)
        names |= {s.name for seg in ep.segments for s in seg.sprites}
        if ep.thumbnail.get("sprite"):
            names.add(ep.thumbnail["sprite"])
    for n in sorted(names):
        try:
            print(f"✔ {sprites.fetch(n)}")
        except FileNotFoundError as e:
            print(f"✘ {e}")


ASK_SYSTEM = ("You are a helpful assistant for Wonder Bites, a faceless YouTube channel of short, "
              "fact-checked videos for kids aged 6-12. Be accurate; say so when you are unsure.")


def cmd_ask(args):
    from . import ai

    prompt = sys.stdin.read() if args.prompt == "-" else args.prompt
    if args.episode:
        ep = load_episode(args.episode)
        yaml_text = (ep.path / "episode.yaml").read_text(encoding="utf-8")
        prompt = f"{prompt}\n\nHere is the episode script ({ep.path.name}/episode.yaml):\n\n{yaml_text}"
    if args.guidelines:
        from .config import ROOT

        rules = (ROOT / "channel" / "content-guidelines.md").read_text(encoding="utf-8")
        prompt = f"{prompt}\n\nThe channel's content guidelines:\n\n{rules}"
    for spec in args.model or [None]:
        target = ai.resolve(spec)
        if len(args.model or []) > 1:
            print(f"\n━━━ {target} ━━━")
        answer = ai.ask(prompt, system=args.system or ASK_SYSTEM, model=spec, max_tokens=args.max_tokens)
        print(answer.strip())


def cmd_models(args):
    from . import ai

    default = (load_config().get("ai") or {}).get("default")
    env = os.environ.get("YTC_MODEL")
    print(f"default: {env or default}" + ("  (from $YTC_MODEL)" if env else ""))
    for name, model, note in ai.status():
        print(f"  {name:11s} {model:28s} {note}")
    print("\nUse --model provider[:model], e.g. --model openai:gpt-5 or --model ollama:llama3.2")


def cmd_draft(args):
    from .writer import draft

    path = draft(args.topic, args.series, args.model)
    print(f"✔ draft written to {path}\n  Fact-check it, then: ytc check {Path(path).parent.name} && ytc preview {Path(path).parent.name}")


def cmd_upload(args):
    from .upload import upload

    ep = load_episode(args.episode)
    problems = check_episode(ep, with_voice=False)
    if problems and not args.force:
        raise SystemExit("Fix these first (or --force):\n  " + "\n  ".join(problems))
    if args.dry_run:
        return cmd_meta(argparse.Namespace(episode=args.episode))
    upload(ep, args.privacy, args.publish_at, force=args.force)


def main(argv=None):
    p = argparse.ArgumentParser(prog="ytc", description="Wonder Bites: script → finished YouTube video, offline.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def eps(sp):
        sp.add_argument("episodes", nargs="*", help="episode number, slug or folder")
        sp.add_argument("--all", action="store_true", help="every episode in episodes/")

    sp = sub.add_parser("list", help="list episodes (▶ rendered, ↑ uploaded)")
    sp.set_defaults(fn=cmd_list)

    sp = sub.add_parser("check", help="validate episodes before rendering/publishing")
    eps(sp)
    sp.add_argument("--fast", action="store_true", help="skip voice synthesis (no length check)")
    sp.set_defaults(fn=cmd_check)

    sp = sub.add_parser("render", help="render final MP4 + thumbnail into output/")
    eps(sp)
    sp.add_argument("--workers", type=int, default=None)
    sp.add_argument("--preview", action="store_true", help="half size, 15 fps: quick look")
    sp.set_defaults(fn=cmd_render)

    sp = sub.add_parser("preview", help="quick half-resolution render")
    eps(sp)
    sp.add_argument("--workers", type=int, default=None)
    sp.set_defaults(fn=cmd_render, preview=True)

    sp = sub.add_parser("still", help="render one frame as PNG")
    sp.add_argument("episode")
    sp.add_argument("-t", type=float, default=2.0, help="time in seconds")
    sp.add_argument("-o", "--out")
    sp.set_defaults(fn=cmd_still)

    sp = sub.add_parser("thumb", help="make thumbnails")
    eps(sp)
    sp.set_defaults(fn=cmd_thumb)

    sp = sub.add_parser("meta", help="print the title/description/tags that will be uploaded")
    sp.add_argument("episode")
    sp.set_defaults(fn=cmd_meta)

    sp = sub.add_parser("brand", help="generate avatar, banner, watermark and mascot sprites")
    sp.set_defaults(fn=cmd_brand)

    sp = sub.add_parser("voices", help="download Piper voice models")
    sp.add_argument("action", choices=["download"])
    sp.add_argument("names", nargs="*")
    sp.set_defaults(fn=cmd_voices)

    sp = sub.add_parser("sprites", help="download Fluent Emoji sprites used by episodes")
    sp.add_argument("action", choices=["fetch"])
    sp.add_argument("names", nargs="*", help="extra sprite names")
    sp.add_argument("--all", action="store_true")
    sp.set_defaults(fn=cmd_sprites)

    model_help = "provider[:model], e.g. claude, openai:gpt-5, ollama:llama3.2 (see `ytc models`)"

    sp = sub.add_parser("draft", help="draft a new episode with any AI model")
    sp.add_argument("topic")
    sp.add_argument("--series", choices=list(load_config()["series"]), default="facts")
    sp.add_argument("-m", "--model", help=model_help)
    sp.set_defaults(fn=cmd_draft)

    sp = sub.add_parser("ask", help="ask any AI model a question (optionally about an episode)")
    sp.add_argument("prompt", help='the question, or "-" to read it from stdin')
    sp.add_argument("-m", "--model", action="append",
                    help=model_help + ". Repeat to compare several models.")
    sp.add_argument("-e", "--episode", help="attach this episode's script to the question")
    sp.add_argument("-g", "--guidelines", action="store_true", help="attach channel/content-guidelines.md")
    sp.add_argument("--system", help="replace the default system prompt")
    sp.add_argument("--max-tokens", type=int, default=8000)
    sp.set_defaults(fn=cmd_ask)

    sp = sub.add_parser("models", help="list configured AI providers and whether they're ready")
    sp.set_defaults(fn=cmd_models)

    sp = sub.add_parser("upload", help="upload a rendered episode to YouTube")
    sp.add_argument("episode")
    sp.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private")
    sp.add_argument("--publish-at", help="schedule, ISO 8601 UTC e.g. 2026-10-02T15:00:00Z")
    sp.add_argument("--dry-run", action="store_true", help="show metadata, don't upload")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(fn=cmd_upload)

    args = p.parse_args(argv)
    try:
        args.fn(args)
    except (EpisodeError, AIError) as e:
        raise SystemExit(f"error: {e}")


if __name__ == "__main__":
    main()
