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
| 2 — Bugs & registry | P1.2 (verifier `error` status), P1.4 (episode-number registry) | ⬜ pending |
| 3 — Pronunciation | P2.1 (lowercase risky-lexicon + spoken-form substitution) | ⬜ pending |
| 4 — Audio integrity | P2.2 (ref-clip hard-fail + Phase 4 QC harness) | ⬜ pending |
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
- The publish gate treats a *missing* verification report as non-blocking; P1.2
  (Phase 2) tightens this to "verification not performed" ≠ pass.
