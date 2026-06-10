# Feature: Pipeline Integrity (Podcast Quality Upgrade)

Tracking doc for the multi-phase initiative implementing
[`docs/specs/improvement-spec-2026-06-09.md`](../specs/improvement-spec-2026-06-09.md).

**Goal:** close the quality loop so revised scripts reach the audio, failing
gates actually block, and the catalog/feed stay coherent — *nothing ships unless
it earned it*.

**Owner:** Claude Code · **Started:** 2026-06-09

---

## Phase breakdown

| Phase | Scope | Status |
|-------|-------|--------|
| **1 — Close the loop** | P0.1, P0.2, P0.3, P1.1, P1.3, lazy `yt_dlp` import | ✅ done |
| **2 — Bugs & registry** | P1.2 (verifier `error` status), P1.4 (episode-number registry) | ✅ done |
| **3 — Pronunciation** | P2.1 (lowercase risky-lexicon + spoken-form substitution) | ✅ done |
| **4 — Audio integrity** | P2.2 (ref-clip hard-fail + Phase 4 QC harness) | ✅ done (re-cut = open asset task) |
| 5 — Spanish track | P2.3 (gate vs drop — **decision deferred by owner**) | ⬜ pending |
| 6 — Distribution | P3 (stable GUIDs, itunes:image/type, owner email, transcripts) | ⬜ pending |
| 7 — Hygiene | remaining P4 items | ⬜ pending |

---

## Phase 1 — Close the loop (done)

**Branch:** `feature/pipeline-integrity-phase1-close-the-loop`

### What's included
- **P0.1** — `_run_qa_revision_loop` now returns the final script text;
  `_run_evidence_pipeline` reassigns `en_narrative` so the opening check (4b),
  verification (4c), and **audio (5)** all run on the revised draft. The on-disk
  script (which the later quality gate re-reads) matches the rendered audio.
- **P0.2** — New `checks/publish_gate.py`. `publish_feed()` runs the gate before
  generating the feed: episodes without a passing `quality_report.json` (or with
  a failed verification report) are excluded via `generate_rss --exclude` and
  listed as `needs-review`, unless allowlisted in `publish_overrides.json`.
  The existing 116-episode catalog is grandfathered in that file so the live feed
  is preserved while the gate enforces forward for new episodes.
- **P0.3** — The similarity and sponsorship gates **fail closed** when
  non-interactive (production = scheduled tasks). A trip skips production, writes
  the episode to `skipped-pending-review.json` with the match table, and returns.
  A new `--force` flag preserves the manual override.
- **P1.1** — `_gen_fn` is resolved once before the pipeline branch, fixing the
  `NameError` on the evidence path with a non-bilingual Spanish narration.
- **P1.3** — `soul_text` is loaded once at the top of `_run_evidence_pipeline`,
  so QA revisions on the resume path no longer drop the persona.
- **P4 (prerequisite)** — `yt_dlp` is imported lazily inside the download
  functions, so the module is importable without it (fixes the 6 env-only test
  failures and makes the P0.1 end-to-end test possible).

### Tests added
- `tests/test_publish_gate.py` — 11 tests: gate verdicts (missing/failing/passing
  report, failing verification, override), partitioning, and `generate_rss --exclude`.
- `tests/test_close_the_loop.py` — 9 tests: revised script reaches audio (P0.1),
  QA loop return value, fail-closed similarity/sponsorship gates + `--force` +
  queue (P0.3), each with a known-bad twin.

### Acceptance criteria — met
- Revised script is the text rendered to MP3 ✅
- `publish_feed()` excludes failing episodes and names the failing check ✅
- Non-interactive duplicate → no audio, queue entry written; `--force` proceeds ✅
- Full suite: 134 passed, 1 skipped (was 114) ✅

### Known issues / deferred
- `checks/run.py` has **pre-existing** failures (`tech-jargon` substance,
  audio-less loudness fixtures) unrelated to this phase — to be addressed in a
  later hygiene phase. The pytest suite is green.

## Phase 2 — Bugs & registry (done)

**Branch:** `feature/pipeline-integrity-phase2-verifier-numbering`

### What's included
- **P1.2** — `verify_script` now returns a `status` field. A verifier response
  with no JSON array (prose, not a verdict) returns `status: "error"`,
  `passed: false` instead of silently reporting "all claims traceable ✓".
  `_run_verification_stage` records a failing report for both the no-array and
  unparseable-JSON cases, and the publish gate treats it as "verification not
  performed", not a pass.
- **P1.4** — `_next_episode_number` derives the next number from the **union** of
  the local audio dir and the publish repo's `episodes.json`, so a local dir out
  of sync with the feed can't reissue a published number. The publish gate gained
  a duplicate-number assertion (`find_duplicate_numbers`): two episodes sharing an
  `epNN` are both held back unless allowlisted (the 6 legacy duplicates —
  ep65/66/70/73/94/122 — are grandfathered).

### Tests added
- `tests/test_numbering_and_verifier.py` — 12 tests: numbering union, duplicate
  detection + gate blocking + override admission, verification error→block,
  `_run_verification_stage` error-report writing — each with a known-bad twin.
- `tests/test_verification.py` — updated `test_no_array_means_nothing_flagged`
  (which encoded the P1.2 bug) to assert the corrected error status.

### Acceptance criteria — met
- Local dir at ep127 + episodes.json with ep128 → next is 129 ✅
- Gate fails on a feed fixture with a duplicated number ✅
- Verifier prose response → report status `error`, not `passed: true` ✅
- Full suite: 146 passed, 1 skipped ✅

## Phase 3 — Pronunciation lexicon (done)

**Branch:** `feature/pipeline-integrity-phase3-pronunciation`

### What's included
- **P2.1** — New `checks/risky_terms.json`: a curated lowercase technical-term →
  spoken-form lexicon (tmux → "tee-mux", nginx → "engine-X", arxiv → "archive",
  …), seeded from the spec's examples and a scan of published scripts.
  - `check_pronunciation.py` now detects a core set of lowercase technical terms
    (`_CORE_RISKY_TERMS`) plus the lexicon keys, and a detected term is covered
    only if it has a non-empty spoken form in the lexicon or the pronunciation
    cache. The tmux-class whole-episode mispronunciation can no longer pass QA.
  - `_omnivoice_fixups` substitutes the spoken form into the text sent to
    OmniVoice (the proven tmux-incident fix, generalized to the whole lexicon),
    so detection actually reaches synthesis — case-insensitively, longest-term
    first.

### Tests added
- `tests/test_pronunciation_lexicon.py` — 9 tests: detection of lowercase terms,
  coverage pass, **remove-one-entry → fail** (known-bad twin), empty spoken form,
  and substitution reaching the TTS-bound text (case-insensitive). The shipped
  lexicon is asserted wired into the fixups list.

### Acceptance criteria — met
- Script with tmux/nginx/kubectl + lexicon entries → check passes and TTS text
  contains the spoken forms ✅
- Remove one entry → check fails naming the term ✅
- Full suite: 155 passed, 1 skipped ✅

## Phase 4 — Audio integrity (done; re-cut is an open asset task)

**Branch:** `feature/pipeline-integrity-phase4-refclip-qc`

### What's included
- **P2.2 part 2 — ref-clip hard-fail.** `_blocking_ref_warnings` classifies the
  mid-speech / length-mismatch / silent / unreadable conditions as fatal. When
  `OMNIVOICE_REF_STRICT` is on, `_omnivoice_render` aborts rather than cloning
  every chunk against a misaligned reference. **Defaults OFF** because the shipped
  clip is currently defective (ends mid-speech, 0 ms trailing) and re-cutting it
  is a human asset task — turning strict on first would halt production. The loud
  "RE-CUT" warning still prints every run.
- **P2.2 part 3 — Phase 4 QC harness.** New standalone `checks/seam_qc.py`
  (not wired into `run.py`; whisperx is OmniVoice-venv-only, injected via a
  callback): reports peak energy at each segment seam (clean < −60 dBFS) and
  flags a token recurring at the start of ≥ 30 % of segments (the echo
  signature, requiring count ≥ 2). Exit 0 clean / 2 artifact.
- **Docs.** `voice_ref/README.md` with the re-cut instructions; omnivoice spec
  status corrected to reflect Phases 1–4 shipped.

### Tests added
- `tests/test_refclip_and_seam_qc.py` — 16 tests: blocking-warning classification,
  strict abort vs non-strict proceed (known-bad twin), `peak_dbfs`, seam energy
  clean/leaked, echo-signature flag/no-flag, full `run_seam_qc`.

### Open asset task (cannot be done in code)
- **Re-cut `voice_ref/senora_freedom_en_ref.wav`** to end on a completed sentence
  with ≥ 150 ms trailing silence (24 kHz mono), update the matching `ref_text`,
  then set `OMNIVOICE_REF_STRICT=1`. Tracked in `voice_ref/README.md`.

### Acceptance criteria — met
- `_validate_ref_clip` on the current defective clip → blocking warning; strict
  render aborts ✅
- Phase 4 QC flags a leaked token / loud seam; clean render reports none ✅
- Full suite: 171 passed, 1 skipped ✅
