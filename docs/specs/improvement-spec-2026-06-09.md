# Improvement Spec — Quality Loop Integrity, Gates That Gate, and Distribution

The most important fixes and improvements to the show, found in a full project review
on 2026-06-09. The headline: the quality system is well-built but **disconnected at the
joints** — revised scripts never reach the audio, failing gates never block anything, and
the gates that exist are bypassed exactly where production actually runs (non-interactive
scheduled jobs).

**Initiative:** Podcast quality upgrade — pipeline integrity
**Status:** ready to implement
**Owner:** Claude Code
**Inputs reviewed:** `video_downloader.py`, `pipeline_stages.py`, `checks/` (all),
`generate_rss.py`, `tests/` (90 passed / 6 env-only failures), `SOUL.md`,
`podcast-backlog.md`, all five existing specs, `docs/reviews/evidence-first-pipeline-review.md`,
the tmux mispronunciation incident file (`2026-05-31-150933-tmux-episode-…`).

---

## Verdict

Since the 2026-05-31 review, the showstoppers it named are fixed: the LLM stages now send
their real prompts (`pipeline_stages.py` `_call_minimax`), `_build_opening_avoidance` uses
`group(0)`, and the checks from PR #3 are merged and wired. Good.

But the loop is still open in four places. An episode can fail QA three times, fail
verification, fail the publish gate — and still ship, rendered from the **pre-revision**
draft. Every priority below is listener-facing: what they hear (P0, P2), whether they can
find and trust the feed (P3), and whether the catalog stays coherent (P1, P4).

---

## P0 — Close the loop: revisions must reach the audio, failures must block

### Finding 0.1 — QA-revised scripts never reach verification, opening check, or audio (critical)

`_run_qa_revision_loop` (`video_downloader.py:2536`) writes each revised draft to
`script_path` and updates its **local** `script_text` — but the caller
`_run_evidence_pipeline` (`:2420–2449`) keeps using the original `en_narrative` variable
afterwards. Consequences, in order:

- Stage 4b opening check runs on the stale draft.
- Stage 4c verification runs on the stale draft.
- **Stage 5 renders audio from the stale draft.** Up to three rounds of QA revision are
  silently discarded from the published MP3.
- The later `_run_quality_gate` (`:2752`) re-reads the script from disk, so the quality
  report describes the *revised* text while the audio carries the *unrevised* one — the
  report and the episode disagree.

**Fix:** `_run_qa_revision_loop` returns the final script text; `_run_evidence_pipeline`
reassigns `en_narrative` before stages 4b/4c/5.

**Test (deterministic):** end-to-end run with a stubbed drafter whose first draft fails the
substance check and whose revision passes → assert the text sent to audio generation equals
the revision, and `quality_report.json` matches the rendered script. This is exactly the
end-to-end test shape the 2026-05-31 review asked for and that `tests/` still lacks.

### Finding 0.2 — The publish gate doesn't gate

`docs/podcast-quality-plan.md` defines the contract: *"publishing is blocked unless Items
1–5 tests pass."* Today:

- `_run_quality_gate` (`:2592–2599`) prints "episode produced but review recommended" and
  the pipeline continues regardless.
- Verification failure (`_run_verification_stage`, `:2516`) prints "FAILED" and continues.
- `publish_feed()` (`:2852`) never reads any `quality_report.json` — it pushes whatever
  MP3s exist.

**Fix:** add a gate at publish time. `publish_feed()` (or a pre-publish step) refuses to
include any episode whose `quality_report.json` is missing, has `passed: false`, or whose
verification report has `passed: false` — unless the episode is explicitly allowlisted in a
`publish_overrides.json` with a reason. Failing episodes land in a `needs-review` list
printed at the end of the run.

**Test:** known-bad fixture (quiet audio or vague script) → `publish_feed()` excludes it and
names the failing check; known-good → included. Override file admits it with a logged reason.

### Finding 0.3 — Non-interactive runs bypass the similarity and sponsorship gates

Both gates (`produce_podcast`, `:2633–2657`) print "(non-interactive mode — proceeding
anyway)" when `sys.stdin` is not a TTY. Production runs from scheduled tasks — i.e. always
non-interactive — so the duplicate-episode gate is a no-op precisely where it matters.
Backlog item 9 (Karpathy) explicitly relies on "the similarity gate should catch this." It
won't.

**Fix:** fail closed when non-interactive. On similarity ≥ threshold or sponsorship score
≥ 6, skip production, write the episode to a `skipped-pending-review.json` queue with the
match table, and continue with the next backlog item. An explicit `--force` flag preserves
the manual override.

**Test:** run `produce_podcast` non-interactively against a near-duplicate fixture → no
audio produced, queue entry written. With `--force` → proceeds.

---

## P1 — Bugs that will bite the next episode

### Finding 1.1 — `_gen_fn` NameError on the evidence path (latent crash)

`_gen_fn` is defined only inside the summary-pipeline branch (`:2696`). When
`pipeline="evidence"` and the Spanish narration is not in bilingual `EN:/ES:` format (any
duo episode, or any es draft that drops the labels), line `:2728` raises `NameError` and
kills the run after the expensive English production. Define `_gen_fn = _generate_duo_audio
if duo else _generate_podcast_audio` once, before the branch.

**Test:** evidence-path duo episode with a plain Spanish narration fixture → no NameError.

### Finding 1.2 — Verifier "no JSON array" silently passes

`verify_script` (`pipeline_stages.py:241–244`): if the verifier returns prose with no JSON
array, `claims = []` → printed as "all claims traceable ✓". A malformed verifier response
is indistinguishable from a clean bill of health. Return a distinct `skipped`/`error`
status instead, and have the publish gate treat it as "verification not performed", not as
a pass.

**Test:** stub verifier returning prose → report status is `error`, not `passed: true`.

### Finding 1.3 — `soul_text if 'soul_text' in dir()` loses the persona on resume

`_run_evidence_pipeline:2423`: when outline and script artifacts already exist (resume
path), `soul_text` is never bound, so QA revisions draft **without SOUL.md**. Load
`soul_text` once at the top of the function, unconditionally.

### Finding 1.4 — Episode numbering can collide again

`_next_episode_number` scans only the local audio dir; the feed already shipped two
different episodes both numbered ep122 (documented in the Spotify gap spec, G4). Derive the
next number from the union of the local dir **and** the publish repo's `episodes.json`, and
add a duplicate-number assertion to the publish gate.

**Test:** local dir at ep127, episodes.json containing an ep128 → next number is 129.
Gate fails on a feed fixture with a duplicated number.

---

## P2 — What listeners hear: pronunciation, seam artifacts, the Spanish track

### Finding 2.1 — Lowercase technical terms escape the risky-token detector

The tmux episode shipped with "t-max" spoken throughout — a whole-episode, title-level
mispronunciation (see the incident file in the repo root). Root cause:
`checks/check_pronunciation.py` detects only ALL-CAPS acronyms (`[A-Z]{2,6}`),
letter+digit codes (`x402`), HTTP codes, and ISO currencies. `tmux`, `nginx`, `systemd`,
`kubectl`, `ffmpeg`, `pytest` — the vocabulary of half the AI/dev episodes — match nothing,
so the coverage check passes while the TTS guesses.

**Fix (two parts):**

1. Add a curated risky-lexicon file (`checks/risky_terms.json`) of lowercase technical
   terms with expected spoken forms ("tmux" → "tee-mux", etc.), checked alongside the
   regexes; seed it from all published scripts (one-off scan).
2. Detection coverage must actually reach the synthesis: `_prepare_pronunciation`
   (`video_downloader.py:2029`) enriches the cache from Wiktionary, but Wiktionary lacks
   most of these terms, and a cache *entry* (IPA) is not the same as a *spoken-form
   substitution* in the text sent to OmniVoice. For lexicon terms, substitute the spoken
   form into the TTS text (the proven fix from the tmux incident — the title literally had
   to be respelled "t m u x").

**Test:** script fixture containing `tmux`, `nginx`, `kubectl` with lexicon entries →
check passes and the TTS-bound text contains the spoken forms; remove one entry → exit 1.

### Finding 2.2 — The seam-artifact root cause (reference clip) is still live

Commit e424c69 implemented Phases 1 and 3 of `omnivoice-audio-quality-fix.md` — per-chunk
trim + de-click fades are wired into `_omnivoice_render` (`:1776`), and the adjacent-number
and tmux fixups are in. But the documented **root cause is untouched**: measured on
2026-06-09, `voice_ref/senora_freedom_en_ref.wav` still ends mid-speech (6.90 s, **0 ms
trailing silence**), and the auto-generated `_clean.wav` is identical — `_validate_ref_clip`
can only trim silence, and there is none to trim. Every render conditions every chunk on a
misaligned clip (the documented echo condition) and prints the same "RE-CUT the clip"
warning, then proceeds. The Phase 1 trim masks residue only if the leak sits below −40 dB
or inside the 300 ms trim budget.

**Fix (in order):**

1. **Re-cut the reference clip** (the spec's own R2 instruction): end on a completed
   sentence with ≥ 150 ms trailing silence, 24 kHz mono, and a `ref_text` transcript that
   matches the audio exactly. This is an asset task, not code.
2. **Promote the validation warning to a hard fail** for the mid-speech/misalignment
   conditions: rendering with a known-defective clone reference should stop the run, not
   log and continue — same fail-closed principle as P0.
3. **Build the Phase 4 QC harness** from the omnivoice spec (transcribe chunk onsets,
   flag a recurring leaked token, report seam-gap energy) so "the artifact is gone" is a
   test result, not a listening impression. Until it exists, mark the omnivoice spec's
   status honestly (it still reads "ready to implement" despite Phases 1–3 shipping).

**Test:** `_validate_ref_clip` on the current defective clip → hard fail with actionable
message; on the re-cut clip → clean pass. Phase 4 QC on a pre-fix episode (ep106/ep119
class) → leak flagged; on a post-fix render → clean.

### Finding 2.3 — Spanish episodes bypass the entire quality system

The Spanish track (`produce_podcast:2700–2729`) always uses the old summary pipeline — no
evidence, no QA loop, no verification — and `_run_quality_gate` runs only on the English
script/audio. Spanish listeners get the unchecked product. Either run the gate (loudness +
structure + pronunciation at minimum) on the es script/MP3, or decide the Spanish track is
deprecated and stop producing it. Pick one; the current half-state costs synthesis time and
ships unchecked audio.

---

## P3 — Distribution: implement the already-specced RSS fixes

`docs/specs/spotify-optimization-gap-spec.md` is a good spec sitting unimplemented while
every batch publish deepens the hole. Confirmed still true in `generate_rss.py`:
`<guid>` is the MP3 URL (`:151`) — one base-URL change away from Spotify re-ingesting the
whole catalog as duplicates — plus no `itunes:image`, no owner email, no `itunes:type`, no
`podcast:transcript` despite the transcripts already being published, and raw `Links:`
blobs in descriptions.

**Do now (smallest high-value subset):** stable GUIDs (`isPermaLink="false"`, slug-derived),
show-level `itunes:image`, `itunes:type=episodic`, owner email, and `podcast:transcript`
wiring for the existing `.podcast.txt` files. The rest of the spec's Track A follows.

**Test:** feed validates (e.g. `podbase`/W3C validator fixture), GUIDs unchanged when
`--base-url` changes, every item carries a transcript URL that resolves.

---

## P4 — Hygiene (do opportunistically)

- **Tests can't run without `yt_dlp`** — 6 failures in any clean environment because
  importing `video_downloader` imports `yt_dlp` at module top. Make the import lazy
  (inside the download functions) so the 4,000-line module is importable for tests and
  for the pipeline-only entry points that never download.
- **Opening check is print-only** (`:2434–2436`): wire it into the QA revision loop as a
  revision trigger instead of a shrug. The avoidance prompt already exists.
- **`publish_feed` git fallback** resets `--hard` to origin after an API upload without
  re-verifying the feed landed; add a final fetch-and-compare of `feed.xml`.
- **`master_audio` runs before the gate but after splicing** — correct order; just add the
  measured LUFS to `episodes.json` so the feed work (P3) can expose duration/loudness
  consistently.

---

## Build order

```
P0.1 → P0.2 → P0.3   (one PR: closes the loop; highest listener impact per line changed)
P1.1 + P1.3          (trivial, same files — fold into the P0 PR)
P1.2 → P1.4          (verifier status + numbering registry)
P2.1                 (pronunciation lexicon — next most audible win)
P2.2                 (re-cut ref clip — asset task, do immediately; then hard-fail + QC)
P2.3                 (decision required: gate Spanish or drop it)
P3                   (RSS: stable GUIDs first, then metadata/transcripts)
P4                   (opportunistic)
```

## Definition of done

`python checks/run.py` green, plus the new end-to-end pipeline test (0.1), publish-gate
fixtures (0.2), non-interactive gate fixtures (0.3), and the pronunciation lexicon fixture
(2.1) — each with a known-bad twin proving the test can fail. The publish gate contract
from `podcast-quality-plan.md` is finally true: nothing ships unless it earned it.
