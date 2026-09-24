"""Upload to YouTube with the Data API v3.

One-time setup (see channel/setup-checklist.md):
  1. Google Cloud project → enable "YouTube Data API v3".
  2. OAuth consent screen (External, add yourself as a test user).
  3. Create an OAuth client ID of type "Desktop app" and save the JSON as
     secrets/client_secret.json.
  4. `pip install -e ".[upload]"`, then the first `ytc upload` opens a browser
     to sign in; the token is cached in secrets/token.json.

Videos go up as PRIVATE by default. Pass --publish-at to schedule, or
--privacy public to publish immediately.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .config import OUTPUT, SECRETS, load_config
from .episode import Episode

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",   # thumbnails + captions
]


def build_description(ep: Episode) -> str:
    parts = [ep.description.strip()]
    if ep.sources:
        parts.append("📚 Sources:\n" + "\n".join(f"• {s}" for s in ep.sources))
    parts.append("🎙️ Narrated with a text-to-speech voice. Every fact is checked by a human.\n"
                 "🎨 Characters: Microsoft Fluent Emoji (MIT licence). Music & backgrounds made by Wonder Bites.")
    tags = ["#shorts"] if ep.format == "short" else []
    tags += ["#kids", "#funfacts", "#spookybites" if ep.series == "spooky" else "#wonderbites"]
    parts.append(" ".join(tags))
    return "\n\n".join(p for p in parts if p)[:5000]


def build_body(ep: Episode, privacy: str = "private", publish_at: str | None = None) -> dict:
    ch = load_config()["channel"]
    tags, total = [], 0
    for t in ep.tags:                           # YouTube caps tags at ~500 characters
        if total + len(t) + 2 > 480:
            break
        tags.append(t)
        total += len(t) + 2
    status = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": bool(ch.get("made_for_kids", True)),
        # Disclosure is for realistic synthetic content (e.g. a real person saying
        # something they didn't). Cartoon emoji + a narrator voice don't need it,
        # but flip this on if an episode ever uses realistic AI imagery.
        "containsSyntheticMedia": False,
    }
    publish_at = publish_at or ep.publish_at
    if publish_at:
        status["privacyStatus"] = "private"      # required for scheduled publishing
        status["publishAt"] = publish_at
    return {
        "snippet": {
            "title": ep.title,
            "description": build_description(ep),
            "tags": tags,
            "categoryId": ch.get("category_id", "27"),
            "defaultLanguage": ch.get("default_language", "en"),
            "defaultAudioLanguage": ch.get("default_language", "en"),
        },
        "status": status,
    }


def _service():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as e:  # pragma: no cover
        raise SystemExit('Upload extras missing: pip install -e ".[upload]"') from e

    token = SECRETS / "token.json"
    secret = SECRETS / "client_secret.json"
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not secret.exists():
                raise SystemExit(f"Missing {secret}. See channel/setup-checklist.md step 4.")
            creds = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES).run_local_server(port=0)
        SECRETS.mkdir(exist_ok=True)
        token.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def upload(ep: Episode, privacy: str = "private", publish_at: str | None = None,
           video: Path | None = None, force: bool = False) -> dict:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    record_path = ep.path / "upload.json"
    if record_path.exists() and not force:
        rec = json.loads(record_path.read_text())
        raise SystemExit(f"Already uploaded: {rec['url']} (use --force to upload again)")

    video = video or OUTPUT / f"{ep.slug}.mp4"
    if not video.exists():
        raise SystemExit(f"Render first: {video} not found (ytc render {ep.slug})")
    yt = _service()
    body = build_body(ep, privacy, publish_at)
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True))
    response, retries = None, 0
    while response is None:
        try:
            status, response = req.next_chunk()
            if status:
                print(f"  uploaded {int(status.progress() * 100)}%")
        except HttpError as e:
            if e.resp.status not in (500, 502, 503, 504) or retries >= 5:
                raise
            retries += 1
            time.sleep(2 ** retries)
    vid = response["id"]
    print(f"✔ uploaded https://youtu.be/{vid}")

    thumb = OUTPUT / f"{ep.slug}.jpg"
    if thumb.exists():
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumb))).execute()
            print("  thumbnail set")
        except HttpError as e:
            print(f"  thumbnail skipped ({e.resp.status}): custom thumbnails need a phone-verified channel")
    srt = OUTPUT / f"{ep.slug}.srt"
    if srt.exists():
        try:
            yt.captions().insert(part="snippet", body={"snippet": {"videoId": vid, "language": "en", "name": "English"}},
                                 media_body=MediaFileUpload(str(srt), mimetype="application/octet-stream")).execute()
            print("  captions uploaded")
        except HttpError as e:
            print(f"  captions skipped ({e.resp.status})")

    rec = {"video_id": vid, "url": f"https://youtu.be/{vid}", "privacy": body["status"]["privacyStatus"],
           "publish_at": body["status"].get("publishAt"), "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    record_path.write_text(json.dumps(rec, indent=2) + "\n")
    return rec
