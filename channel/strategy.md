# Wonder Bites: strategy

## 1. Positioning

Kids' fact channels are crowded, and many are low-effort, error-filled, or
mass-produced. Wonder Bites competes on three things:

1. **Trust.** Every fact is sourced, the sources are in the description, and
   the tone is calm. Parents are the real gatekeepers of what kids watch.
2. **Craft.** Word-by-word captions for early readers, a friendly mascot,
   consistent visuals, and a quiz payoff that makes kids talk back.
3. **A reason to come back on Fridays.** *Spooky Bites* is a recurring series
   kids look forward to, which facts channels usually don't have.

## 2. Content pillars

| Pillar | Share | Example topics |
|---|---|---|
| 🐙 Animals | 40% | octopus hearts, sea otters holding hands, butterflies tasting with their feet |
| 🪐 Space | 20% | Venus day vs year, Saturn floating, footprints on the Moon |
| 🧠 Your body | 15% | taller in the morning, goosebumps, why we yawn |
| 🌋 Earth & everyday science | 15% | honey never spoils, bananas are berries, lightning |
| 👻 Spooky Bites | 1 per week | campfire stories, creepy-but-true nature |

The backlog of 40+ researched ideas is in [`backlog.yaml`](backlog.yaml).

## 3. Weekly schedule

| Day | Upload | Time (viewer's local) |
|---|---|---|
| Mon | Animal fact Short | 15:30 (after school) |
| Tue | Space or body Short | 15:30 |
| Wed | Animal fact Short | 15:30 |
| Thu | Earth/science Short | 15:30 |
| Fri | **Spooky Bites** Short | 17:00 |
| Sat | Long-form (from month 2): compilation or story | 09:00 |

Batch-produce on one day: draft or write 5 scripts, fact-check, render,
watch, then schedule the whole week.

## 4. Made for kids: what it means

The channel is **made for kids** (required by COPPA and YouTube policy for
content aimed at children). Knowing the trade-offs up front:

| Feature | Status on made-for-kids videos | What we do instead |
|---|---|---|
| Comments | Off | Quiz answered *out loud* |
| Personalised ads | Off (contextual ads only, so lower RPM) | Volume + long-form watch time |
| Notification bell, cards, end screens | Off | Consistent schedule, playlists, series names |
| YouTube's branding watermark | Hidden | Mascot burned into long-form videos |
| Memberships, Super Thanks, merch shelf | Off | Not part of the model |
| Eligible for YouTube Kids app | Yes | Great discovery surface |

**Never** mark kids' content as "not made for kids" to get those features back.
That is a policy violation with FTC fines behind it.

## 5. Titles, thumbnails, SEO

- **Title formula:** `<Surprising claim>?! <emoji> #shorts`, e.g.
  "An Octopus Has THREE Hearts?! 🐙". Put the searchable noun first.
- **Descriptions:** 2–3 kid/parent-friendly lines, then sources, then credits
  and hashtags. `ytc meta <episode>` shows exactly what gets uploaded.
- **Tags:** the topic, "<topic> facts", "facts for kids", "science for kids".
- **Thumbnails:** one huge character, 2–3 words of text, bright background.
  `ytc thumb` makes these to a consistent template.

## 6. The analytics loop (every Monday, 20 minutes)

1. YouTube Studio → Analytics → Content → Shorts, last 28 days.
2. For each Short, note **views**, **average % viewed**, and **"viewed vs
   swiped away"**.
3. The top 10% by % viewed are **winners**. Make a sequel or a deeper Short on
   the same topic within 2 weeks ("More weird octopus facts").
4. If a Short is under 50% "viewed", the hook failed. Rewrite the first line
   for the next similar topic.
5. Once three winners share a pillar, make a long-form compilation of that
   pillar (the renderer supports `format: long`).

## 7. Monetisation (realistic)

- **YouTube Partner Program:** 1,000 subscribers **plus** either 4,000 public
  watch hours in 12 months, *or* 10 million public Shorts views in 90 days.
- Made-for-kids ads are contextual only, so expect lower RPM than general
  channels. Long-form watch time pays noticeably better than Shorts; add
  weekly long-form from month 2.
- YouTube reviews channels for **inauthentic (mass-produced/repetitive)
  content** before and after monetisation. See
  [content-guidelines.md §6](content-guidelines.md#6-being-an-honest-automated-channel).
  Human review of every video is non-negotiable.
- Cost to run: $0. Everything is offline and free. The only optional paid
  piece is `ytc draft` (Claude API) for first drafts.

## 8. 90-day targets

| By day | Uploads | Goal |
|---|---|---|
| 14 | 10 Shorts | Pipeline routine is under 1 hour per Short, end to end |
| 45 | 30 Shorts + 2 long | First "winner" pillar identified |
| 90 | 60 Shorts + 8 long | 1,000 subscribers; sequel system running |
