# Plan: Clear the 8 episodes held by the publish gate

*Authored 2026-06-14. Persisted for later execution; not yet implemented.*

## Context

The publish gate (introduced 2026-06-10) requires a `<slug>.quality_report.json` next to each
MP3 in `freeist-podcast/audio/`. Right now **135 MP3s exist but only 26 reports**, so 8 episodes
are held out of the feed. This is not a bug in the gate — it is a coverage gap with three causes.
Goal: get every legitimate episode publishing, delete the junk, and leave the gate green with no
silent overrides.

Investigation classified each held slug into **orphan** (not in `episodes.json`, no Spanish track,
incomplete/junk → delete) vs **real** (in `episodes.json` → backfill a report):

| Slug | Class | Problem | Action |
|---|---|---|---|
| `ep130-how-build-agentic-systems-that-prompt-themselves` | **orphan** | no report, not in episodes.json | delete |
| `ep131-video-themaxdose` | **orphan** | causes ep131 collision; not in episodes.json | delete (resolves collision) |
| `ep134-boris-cherny-claude-code-setup-tips` | **orphan** | duplicate of ep136 (which passed) | delete |
| `ep134-beyond-basics-…prompt-themselves.podcast.txt` | **orphan** | stray .txt, no MP3 | delete |
| `ep131-anthropic-self-service-data-analytics` | **real** | pronunciation: 1 uncovered `CI` | fix lexicon + backfill |
| `ep133-beyond-basics-claude-code-systems-that-prompt-themselves` | **real** | pronunciation: 1 uncovered `ED` | fix lexicon + backfill |
| `ep132-video-themaxdose` | **real** | no report | backfill |
| `ep138-rody-anthropic-engineer-james-brady-every-agent-production` | **real** | no report | backfill |
| `ep139-stanislav-krapivnik-war-will-last-couple-decades-we` | **real** | no report | backfill |

**Pronunciation context (confirmed in the scripts):**
- `ep131` "CI" = Continuous Integration ("…a single repository with CI checks…") → spoken "C I".
- `ep133` "ED" = the 1970s Unix line editor `ed` ("…an old text editor from the nineteen seventies called ED…") → spoken "E D".

Both are real terms, not false positives, so they get spoken forms in the shared lexicon.

## Architecture notes (from exploration)

- **Shared lexicon**: `checks/risky_terms.json` (`{lowercase_term: spoken_form}`) is the single
  source for *both* `checks/check_pronunciation.py` (coverage check, case-insensitive, key at
  `check_pronunciation.py:136-141`) *and* `_omnivoice_fixups`/`_load_risky_lexicon()` in
  `video_downloader.py:1682-1719` (TTS substitution). One edit satisfies both.
- **Report generation**: `checks/quality_gate.py:run_quality_gate(script_text, audio_path)`
  + `write_quality_report(report, path)`. Runs loudness/pronunciation/substance/structure/dialogue.
  Loudness is skipped (passes) when no `audio_path`; all others are deterministic checks on the
  script text — **so a report can be regenerated from the existing `.podcast.txt` + `.podcast.mp3`
  without re-running TTS.** This is the backfill primitive.
- **Two repos**: the lexicon + backfill script live in **podcast-forge**; the orphan deletions +
  generated reports land in **freeist-podcast** (git-tracked, so deletions are recoverable).

## Plan

### Phase 1 — Pronunciation lexicon (podcast-forge)
Add two entries to `checks/risky_terms.json`:
```json
"ci": "C I",
"ed": "E D"
```
(Existing entries are `{"tmux": "tee-mux", …}`; insert alphabetically / grouped with the rest.)
Commit + PR to `main` (branch `fix/pronunciation-ci-ed`).

### Phase 2 — Backfill script (podcast-forge)
New `tools/backfill_quality_reports.py` — takes a list of slugs (or `--all` for every MP3 lacking a
report), and for each:
1. reads `freeist-podcast/audio/<slug>.podcast.txt`
2. `report = run_quality_gate(script_text, audio_path="<slug>.podcast.mp3")`
3. `write_quality_report(report, "freeist-podcast/audio/<slug>.quality_report.json")`
4. prints `slug → passed/failed (failures)`

Reusable: the gate is new, so legacy backfill is a recurring need. Commit + PR with Phase 1 or its
own.

### Phase 3 — Delete orphans (freeist-podcast)
Remove from `freeist-podcast/audio/` (all `*.*` variants per slug):
- `ep130-how-build-agentic-systems-that-prompt-themselves.*`
- `ep131-video-themaxdose.*`
- `ep134-boris-cherny-claude-code-setup-tips.*`
- `ep134-beyond-basics-claude-code-systems-that-prompt-themselves.podcast.txt`

This removes the ep131 collision at the source — no renumbering, no GUID churn.

### Phase 4 — Backfill reports (freeist-podcast, via the script)
Run the Phase 2 script over the 5 real episodes:
`ep131-anthropic`, `ep132-video-themaxdose`, `ep133-beyond-basics`, `ep138`, `ep139`.
ep131 + ep133 should now **pass** (lexicon fix from Phase 1). The other three pass or surface their
real failures.

### Phase 5 — Triage (freeist-podcast)
- Episodes that pass → done, will publish.
- Any of ep132/ep138/ep139 that **still fail** on a non-pronunciation check (substance/structure/
  loudness) → these are legacy episodes; allowlist in `publish_overrides.json` with a dated, specific
  reason (e.g. `"ep138-…": "legacy backfill: structure gate, pre-gate episode (2026-06-14)"`). No
  silent blanket overrides. (`publish_overrides.json` is also copied to freeist-podcast.)

### Phase 6 — Publish + verify
1. `publish_feed()` → regenerate RSS, push. Expect **0 needs-review** (or only documented overrides).
2. `python -m checks.run` → green.
3. Commit the new reports + overrides in freeist-podcast.

## Known limitation (flag, don't fix now)
`ep131` and `ep133` audio was rendered *before* the `ci`/`ed` spoken forms existed, so the existing
MP3s may pronounce those two tokens sub-optimally. Adding the lexicon makes the **report** pass and
fixes **future** renders, but does not alter existing audio. Re-rendering EN audio is an optional
follow-up only if the pronunciation sounds wrong on listen. Note: `ep131`/`ep133` are not currently
in the live feed (they were held), so there is no published-audio regression.

## Verification
- Run the backfill script on a sample slug; confirm the report writes and `passed` reflects the
  lexicon fix.
- `publish_feed()` output lists **0 held episodes** (or only Phase 5 overrides).
- Feed diff confirms the 5 real episodes now appear in `feed.xml`; the 3 orphans are gone.
- `python -m checks.run` exits 0.
