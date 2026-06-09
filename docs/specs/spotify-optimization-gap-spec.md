# Spotify Optimization — Gap Analysis & Closure Spec

Maps the show ("Señora Freedom") against the **Spotify for Creators Optimization Playbook**
(`docs/Spotify for Creators Optimization Playbook.pdf`, 43pp), identifies gaps, and specifies
how to close the ones we control.

**Initiative:** Distribution & discovery
**Status:** draft
**Inputs reviewed:** the playbook; `generate_rss.py`; published `freeist-podcast/feed.xml`; `episodes.json` (110 entries); `freeist-podcast/audio/`.

## 0. The key framing: RSS-hosted vs Spotify-hosted

The show is **self-hosted via RSS** (MP3s + `feed.xml` on GitHub Pages, ingested by Spotify).
That splits every playbook recommendation into two tracks:

- **Track A — deliverable in our RSS feed / pipeline (code + assets).** Cover art, titles,
  descriptions, transcripts, episode/season metadata, GUIDs. *We own these.* This spec is
  mostly about Track A.
- **Track B — Spotify-platform features that RSS cannot carry.** Best-place-to-start, host
  recommendations, "In this episode," comments, polls, video, clips, auto-transcripts/auto-
  chapters, analytics. These require **claiming the show in Spotify for Creators** (and, for
  video/clips, hosting media on Spotify). *No code closes these* — they are operational.

Calling these out separately prevents wasted engineering on things RSS can't do.

## 1. Gap analysis

| # | Playbook recommendation | Current state | Gap | Track |
|---|---|---|---|---|
| G1 | **Show cover art** — square, high-res, title on art, legible at thumbnail | **Exists** at show level (set on Spotify). The RSS `feed.xml` itself carries no `itunes:image`, so other directories ingesting this feed (Apple, Overcast) get no show art. | Minor: host the existing show art in the publish repo and reference it in the feed so non-Spotify clients render it too | A (code + host asset) |
| G1b | **Per-episode cover art** — art can also be set per episode | **Missing** — no per-item `itunes:image`; episodes inherit the show art only | The gap you flagged: episodes have no distinct artwork in "Episodes for you" / Now Playing | A (code, optional asset) |
| G2 | Clean, complete show metadata | `itunes:owner` has **no email**; no `itunes:type`; single category; generic show description | Feed is technically incomplete; `itunes:type=episodic` missing (matters for "Always-On" treatment) | A (code) |
| G3 | Stable identity per episode | **`<guid>` = the MP3 URL**; `isPermaLink` unset | **Bug.** If `--base-url` ever changes, every GUID changes → Spotify treats the whole catalog as new episodes (duplicate show) | A (code) |
| G4 | Accurate, non-colliding catalog | **Two different episodes both numbered `ep122`** (ai-layoff-trap and history-taxation); some `Links:` blobs dumped raw into descriptions | Feed hygiene: duplicate numbering, raw URLs mid-description | A (data + code) |
| G5 | Episode-level richness | No per-item `itunes:image`, `itunes:episode`/`season`, `itunes:episodeType`, `itunes:explicit`; `content:encoded` namespace declared but unused | Missing standard episode metadata; no rich (HTML) descriptions | A (code) |
| G6 | **Transcripts** (Spotify auto-generates; playbook pushes them for discovery) | Per-episode `.podcast.txt` exist on disk and are published, but **not linked** in the feed | `podcast:transcript` tags absent — we already have the text, just not wired | A (code) |
| G7 | **SEO**: titles with topics/guests; descriptions hook in first 2 lines, cover all topics, **links/ads last**; show desc names host + nicknames; avoid generic terms/clickbait/special chars | Titles are decent; descriptions hook reasonably but **end with raw `Links: https://…`**; show description is generic ("Short-form podcast covering technology, finance, and global affairs") and **never names the host or the persona** | Show description weak for search; episode descriptions dump raw URLs; "Señora Freedom" / agorist angle absent from metadata | A (pipeline + config) |
| G8 | **Opening 30–60s hook** (autoplay = first impression) | Hooks were strengthened in the recent close/hook work; openings are concrete | Largely **met** — keep enforcing via the structure check | A (already in train) |
| G9 | Chapters (timestamps + titles) | None | Low value: episodes are ~5 min. `podcast:chapters` is cheap to add but optional at this length | A (optional) |
| G10 | **Video podcast** (72% prefer video; +30% retention) | Audio-only (synthetic OmniVoice voice) | Strategic: real video is a large lift and an odd fit for a TTS show; a static-image/waveform "video" is possible but low-ROI | B (decision) |
| G11 | Short-form **clips** (vertical ≤90s teasers) | None | Generatable from existing audio + a static card, but it's a new asset pipeline | B (later) |
| G12 | **Community**: comments, polls, follower CTA | No follower CTA in audio; comments/polls are platform features | Add a follower call-to-action; comments/polls need the claimed show | A (CTA) + B |
| G13 | Show-page curation: best-place-to-start, host recommendations, "In this episode" | Not set | Dashboard-only | B |
| G14 | **Consistency / cadence** | Publishes in frequent batches (many share one `pubDate`) | Batch-dating weakens the "Always-On warmth" signal; a steady cadence with spread `pubDate`s is better | A (publish process) |
| G15 | Analytics-driven iteration | No use of Spotify analytics | Dashboard-only | B |

## 2. Requirements (Track A)

| # | Requirement | Closes |
|---|---|---|
| R1 | The feed carries the **existing show cover art** (`itunes:image` + RSS `<image>`) for non-Spotify directories, and every item has a **per-episode `itunes:image`** (defaulting to the show cover). | G1, G1b |
| R2 | The feed is **metadata-complete**: `itunes:type=episodic`, owner email (configurable), `<link>`, `itunes:explicit` per item, and a stable show `podcast:guid`. | G2 |
| R3 | Each item has a **stable GUID** independent of hosting URL (`isPermaLink="false"`), derived from the episode slug or a persisted UUID. | G3 |
| R4 | The catalog has **no duplicate episode numbers**; descriptions carry no raw URL blobs (sources move to a clean field / HTML). | G4 |
| R5 | Each item carries `itunes:episode`, `itunes:episodeType=full`, optional `itunes:image`, and a rich `content:encoded` description. | G5 |
| R6 | Each item links its **transcript** via `podcast:transcript` (the existing `.podcast.txt`; emit `.vtt` later). | G6 |
| R7 | **Show + episode SEO**: show description names the host "Señora Freedom" and the show's angle/keywords; episode descriptions hook in the first two sentences, cover the topics, and place sources last (clean links, not raw `Links:`). | G7 |
| R8 | Episodes include a brief **follower call-to-action** consistent with the voice. | G12 |

## 3. Phases

### Phase 1 — Cover art in the feed + per-episode art (G1, G1b; R1)

Show art already exists (set on Spotify). This phase (a) carries it in the RSS feed for
non-Spotify directories and (b) adds the missing per-episode artwork.

- **Host the show art:** export the existing cover and commit it to the publish repo (e.g. `/cover.png`, 1400–3000px square) so it has a stable GitHub Pages URL. (No new design needed — reuse the current art.)
- **Channel code (`generate_rss.py`, `generate_rss()`):** add `itunes:image href="<site>/cover.png"` and the RSS `<image><url/><title/><link/></image>`.
- **Per-episode art (the flagged gap):** add a per-item `itunes:image`. Two options:
  1. **Default to the show cover** — one line, zero new assets; immediately closes the "no per-episode image" gap and is valid everywhere.
  2. **Templated episode card** — show cover + episode number/title overlay, generated per episode for visual distinction in "Episodes for you" / Now Playing.
  Recommend shipping (1) now; add (2) only if the distinct thumbnails prove worth the render.
- **Verify:** channel `itunes:image` + `<image>` present and resolve (200); every item has an `itunes:image`; feed validates (cast feed validator); Apple/Spotify preview shows art.

### Phase 2 — Feed correctness & stable identity (G2, G3, G4; R2, R3, R4)

- Add `itunes:type=episodic`, channel `<link>` (the GitHub Pages site), `itunes:owner > itunes:email` (configurable `--owner-email`, **not** hardcoded), and a generated `podcast:guid` (stable UUID stored in feed config).
- **Stable per-item GUID:** replace `guid = mp3_url` with `guid = "freeist:" + stem` (the `epNN-…` slug) and `isPermaLink="false"`. Document that this is permanent.
- **Dedupe:** fix the two `ep122` entries (renumber one); add a build-time assertion in `find_podcast_episodes` that episode numbers are unique, failing the build on collision.
- **Verify:** changing `--base-url` no longer changes any GUID; build fails if two stems share an `epNN`.

### Phase 3 — Episode richness + transcripts (G5, G6; R5, R6)

- Per item: `itunes:episode` (parse `epNN`), `itunes:episodeType=full`, `itunes:explicit=false`, and `content:encoded` containing an HTML description (paragraph + a "Sources" list of real `<a>` links).
- `podcast:transcript url="<base>/<stem>.podcast.txt" type="text/plain"` (the file is already published alongside the MP3). Add the `xmlns:podcast` namespace. *Stretch:* convert `.txt` → `.vtt` and prefer `type="text/vtt"`.
- **Verify:** each item has an episode number and a transcript URL that returns 200; rich description renders in Apple/Spotify.

### Phase 4 — Metadata SEO in the pipeline (G7; R7)

- **Show description (config/default in `generate_rss.py`):** rewrite the generic default to name the host and angle and carry search keywords, e.g. *"Señora Freedom — short, skeptical episodes on sovereignty, tax, money, crypto, AI and global affairs. An agorist's take: specific numbers, named sources, no hype."* Mention any nickname.
- **Episode description format (where `episodes.json` descriptions are produced):** enforce — first two sentences hook and name the topic/guest; cover the main topics; **no raw URLs in the body**; sources go to a trailing clean list (and to `content:encoded` as links). Strip the `Links: https://…` pattern from existing entries on next build.
- **Titles:** keep topic/guest-forward titles; lint against ALL-CAPS, special characters, and generic "podcast/pod" filler (extend the existing checks).
- **Verify:** show description names the host and ≥5 angle keywords; no episode description contains a bare `http`-blob in its first 200 chars; titles pass the lint.

### Phase 5 — Follower CTA (G12; R8)  *(small content change)*

- Add a short, voice-consistent follower CTA — e.g. a one-line tag near the open or close ("Follow Señora Freedom so the next dispatch finds you"). Keep it out of the **first** 30–60s (the playbook wants the opening to hook, not ad). Wire it as an optional intro/outro line, not baked into every script's hook.
- **Verify:** the CTA appears once per episode, not within the first 30 seconds.

### Phase 6 — Operational track (Track B; G10–G15)  *(non-code, for the owner)*

Document, don't build:

1. **Claim the RSS show in Spotify for Creators.** Unlocks auto-transcripts, auto-chapters, comments, polls, Q&A, "best place to start," host recommendations, "In this episode," and analytics — none of which RSS can carry.
2. **Set best-place-to-start** to the strongest evergreen episode; pin two **host recommendations**.
3. **Engage:** seed a comment/poll prompt per episode; reply within 24h (commenters retain 2×).
4. **Cadence:** publish on a steady weekly/bi-weekly schedule with spread `pubDate`s rather than batches (Always-On shows get ~75% of listening; batching weakens the signal).
5. **Video/clips (decision):** real video is a poor fit for a synthetic-voice show; if pursued, start with one vertical ≤90s **clip** per episode (static card + waveform + captions) before committing to full 16:9 video.

## 4. Constraints

- Don't break the existing feed: it's live and ingested. Validate before publishing.
- GUID change is one-time and must be done **once, carefully** — emit both old and new only if Spotify shows duplicates; otherwise switch to stable GUIDs before the catalog grows further.
- Owner email and any personal URLs are configuration, never hardcoded.
- Cover art must respect image copyright (playbook note) — original artwork only.
- Keep EN and ES feeds in sync (apply all changes to both `feed.xml` and `feed-es.xml`).

## 5. Not in scope

- Full 16:9 video production (Track B decision).
- Migrating hosting off RSS to Spotify/Megaphone (only needed if native video/clip hosting is desired).
- Loudness/mastering (handled in the audio-quality work; the playbook does not cover audio specs).

## 6. Priority / sequence

`Phase 1 (cover art) → Phase 2 (correctness + stable GUID) → Phase 3 (richness + transcripts) → Phase 4 (SEO) → Phase 5 (CTA)`. Phase 6 runs in parallel as an owner checklist. Phases 1–3 are the highest impact and are pure feed/asset work; the **GUID-stability bug** and the **`ep122` collision** are the two correctness items to fix first.

## Appendix A — `generate_rss.py` change sketch

```python
PODCAST_NS = "https://podcastindex.org/namespace/1.0"
rss.set("xmlns:podcast", PODCAST_NS)

# Channel-level additions
SubElement(channel, "link").text = site_url               # e.g. https://mrleepee.github.io/freeist-podcast/
SubElement(channel, "itunes:type").text = "episodic"
img_href = f"{site_url.rstrip('/')}/cover.png"
SubElement(channel, "itunes:image").set("href", img_href)
image = SubElement(channel, "image")
SubElement(image, "url").text = img_href
SubElement(image, "title").text = feed_title
SubElement(image, "link").text = site_url
owner = channel.find("itunes:owner")
SubElement(owner, "itunes:email").text = owner_email       # --owner-email
SubElement(channel, "podcast:guid").text = show_guid       # stable UUID in config

# Per item
stem = ep["stem"]                                          # carry stem through find_podcast_episodes
m = re.match(r"ep0*(\d+)", stem)
if m:
    SubElement(item, "itunes:episode").text = m.group(1)
SubElement(item, "itunes:episodeType").text = "full"
SubElement(item, "itunes:explicit").text = "false"
guid = SubElement(item, "guid"); guid.text = f"freeist:{stem}"; guid.set("isPermaLink", "false")
tr = SubElement(item, "podcast:transcript")
tr.set("url", f"{base_url}/{stem}.podcast.txt"); tr.set("type", "text/plain")
ce = SubElement(item, "content:encoded")
ce.text = f"<![CDATA[{html_description}]]>"                # hook para + <a> sources
```

Add a uniqueness guard in `find_podcast_episodes`:

```python
seen = {}
for ep in episodes:
    n = re.match(r"ep0*(\d+)", ep["stem"]).group(1)
    if n in seen:
        raise SystemExit(f"Duplicate episode number ep{n}: {seen[n]} vs {ep['stem']}")
    seen[n] = ep["stem"]
```

## Appendix B — Cover-art handling

Show art already exists — no new show design is required.

- **Show art → feed:** export the current show cover (1400–3000px square, sRGB), commit it to the publish repo root so the Pages URL (`/cover.png`) is permanent, and reference it from the channel `itunes:image` + `<image>`.
- **Per-episode art (option 1, default):** point each item's `itunes:image` at the same show cover — valid, zero assets.
- **Per-episode art (option 2, templated):** render `assets/ep_art/<stem>.png` = show cover background + episode number/title overlay (legible at ~120px, squint test). Generate in the pipeline alongside the MP3; reference per item. Original art only.

## Appendix C — Definition of Done

1. Existing show cover hosted in the publish repo and referenced by channel `itunes:image`; every item has a per-episode `itunes:image` (show cover by default).
2. Feed validates clean (cast feed validator) with channel `itunes:image`, `itunes:type`, owner email, `<link>`, `podcast:guid`.
3. Every item: stable `freeist:<stem>` GUID, `itunes:episode`, `itunes:episodeType`, `podcast:transcript` (200), `content:encoded`.
4. Build fails on duplicate episode numbers; the existing `ep122` collision is resolved.
5. Show description names the host + angle keywords; no episode description leads with a raw URL.
6. Changes applied to **both** `feed.xml` and `feed-es.xml`.
7. Owner checklist (Phase 6) handed over: claim show, set best-place-to-start, cadence plan.
