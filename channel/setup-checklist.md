# Setup checklist (the steps only a human can do)

About 15 minutes for the channel and 15 for API uploads. Do these once.

## A. Create the channel

- [ ] **1. Google account.** Create a fresh account for the channel (don't
      use your personal one). Turn on 2-step verification.
- [ ] **2. Create the channel.** youtube.com → avatar → *Create a channel*.
      Name: **Wonder Bites**. Handle: **@WonderBitesKids** (backups are in
      `brand.md`).
- [ ] **3. Verify with a phone.** youtube.com/verify. This unlocks custom
      thumbnails and videos longer than 15 minutes.
- [ ] **4. Mark the channel as made for kids.** Studio → Settings → Channel →
      Advanced settings → Audience → *Yes, set this channel as made for kids*.
- [ ] **5. Branding.** Studio → Customization → Branding. Run `ytc brand` first, then upload:
  - Picture: `assets/brand/avatar.png`
  - Banner: `assets/brand/banner.png`
  - Video watermark: `assets/brand/watermark.png` (hidden on made-for-kids
    videos, but it shows on the channel page)
- [ ] **6. Basic info.** Customization → Basic info: paste the *About* text
      from `brand.md`. Add the playlists listed there (Content → Playlists).
- [ ] **7. Upload defaults.** Settings → Upload defaults: category
      *Education*, language *English*, audience *made for kids*.

You can now publish by dragging `output/*.mp4` into YouTube Studio and pasting
the text from `ytc meta <episode>`. The steps below automate that.

## B. Enable uploads from the command line (optional)

- [ ] **8. Google Cloud project.** console.cloud.google.com → New project
      "wonder-bites".
- [ ] **9. Enable the API.** APIs & Services → Library → **YouTube Data API v3** → Enable.
- [ ] **10. OAuth consent screen.** User type *External*. App name "Wonder
      Bites uploader". Add the channel's Google account under **Test users**.
- [ ] **11. Credentials.** Create credentials → OAuth client ID →
      **Desktop app**. Download the JSON and save it as
      `secrets/client_secret.json` (the `secrets/` folder is git-ignored).
- [ ] **12. Install and sign in.**
      ```bash
      pip install -e ".[upload]"
      ytc upload 001 --dry-run     # shows the metadata
      ytc upload 001               # opens a browser to sign in (pick the channel's account)
      ```

### Two API limits to know about

1. **New API projects upload as private only.** YouTube locks videos uploaded
   through an *unaudited* API project to private. Either:
   - upload with `ytc upload` (private), then set visibility or schedule in
     Studio (≈10 seconds per video), **or**
   - apply for the free API compliance audit
     (support.google.com/youtube/contact/yt_api_form). After approval,
     `--publish-at` and `--privacy public` work directly.
2. **Testing-mode tokens expire after 7 days.** While the consent screen is in
   "Testing", delete `secrets/token.json` and sign in again weekly, or publish
   the consent screen.

The default quota (10,000 units per day) comfortably covers this channel's
cadence. Check Google's quota calculator for current per-call costs.

## C. Optional: AI script drafting

- [ ] Get a Claude API key (console.anthropic.com), then run
      `pip install -e ".[draft]"` and `export ANTHROPIC_API_KEY=...`.
- [ ] `ytc draft "why do cats purr"` writes a draft episode. **Always fact-check
      it** against the sources before rendering.
