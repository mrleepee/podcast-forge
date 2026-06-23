# HANDOFF — Produce 3 podcast episodes (#27, #30, #32) — TTS pipeline broken after repo move

- **Token:** main   ← use this with `/resume main`
- **Created (UTC):** 20260623T111031Z
- **Project root:** /Users/lpollington/Dev/personal/podcast-forge
- **Worktree:** /Users/lpollington/Dev/personal/podcast-forge (main repo, not a worktree)
- **Git branch:** main  |  **HEAD:** c1afa57 chore(backlog): mark #15 — Anthropic Silently Downgrading as published (ep160) (#73)
- **Working tree:** 5 files modified — `.claude/scheduled_tasks.json` + `.claude/scheduled_tasks.lock` (touched by the cron runner, NOT by us — do not commit), `narrate_summaries.py` + `rerender_omnivoice.py` (pre-existing in-progress repo-move path fixes, not ours), `podcast-backlog.md` (pre-existing 3-line diff, NOT ours — backlog still shows #18/#20/#22/#27/#30/#32 as pending/un-struck)
- **Status:** PATHS FIXED + OMNIVOICE FIXED (see UPDATE). TTS no longer blocks — OmniVoice (the intended voice for ep154–161) works again. Production of #27/#30/#32 is UNBLOCKED with no Kokoro compromise. Only the (now-irrelevant) Kokoro `pronunciation_db` bug remains open.

## UPDATE — Path audit after Dev/ reorg (~11:25 UTC, this session)
User reorganized `~/Dev` into `personal/ vendor/ archive/ work/ data/ scripts/`. Audited every path. **Verdict: the move was CLEAN — nothing landed in the wrong place.** Each repo exists in exactly ONE location, all old paths (`~/Dev/podcast-forge`, `~/Dev/OmniVoice-Studio`, `~/Dev/freeist-podcast`) are gone. Live code is move-robust (most paths use `Path(__file__).resolve().parent`; `_PUBLISH_REPO=parent.parent/"freeist-podcast"` correctly resolves to `personal/freeist-podcast`).

**Fixed this session (3 defects):**
1. `video_downloader.py:1649` `_OMNIVOICE_PY` default — was dead `~/Dev/OmniVoice-Studio/...`, now `~/Dev/vendor/OmniVoice-Studio/...`. ✅ **OmniVoice itself is also FIXED** — see "OMNIVOICE FIXED" below. (The handoff's original "venv broken / needs heavy rebuild" premise was WRONG.)
2. `.claude/scheduled_tasks.json` was **TRUNCATED (missing closing `}`) — this had KILLED the cron** (`CronList` returned 0 jobs; the 17:11 weekday run would not have fired). Repaired: now parses, both jobs present (ids `7505f0e1` `37 13 * * 1-5`, `69894926` `11 17 * * 1-5`), durability/createdAt preserved (hand-repaired, NOT recreated via CronCreate — that tool's 7-day recurring-expiry would have silently broken production next week). `.claude/scheduled_tasks.lock` is deleted (runtime artifact; leave deleted).
3. Cron prompt path (both jobs) — was dead `Work in /Users/lpollington/Dev/podcast-forge`, now `/Dev/personal/podcast-forge`.

**Already-correctly-fixed by a prior session (uncommitted):** `narrate_summaries.py:66` (→ `personal/YouTubeDownloader/downloads/raw`), `rerender_omnivoice.py:19` (→ `personal/freeist-podcast/audio`). Both correct; bundle into the migration commit.

**Not live (historical; ignore):** dead-path strings in `.claude/diary/*`, `.claude/worktrees/*`, `.claude/handoffs/*`, and `docs/specs/omnivoice-audio-quality-fix.md` prose.

**Commit guidance (user asked):** functionally the fixes need NO commit (Python reads working-tree files at runtime; cron reads the file at session start). For persistence, commit the 3 code path-fixes (`video_downloader.py` + `narrate_summaries.py` + `rerender_omnivoice.py`) as a branch+PR — `main` is protected (project flow is all PR-merged). Do NOT commit `.claude/scheduled_tasks.json`/`.lock` (cron-runner runtime state) or `.claude/handoffs/`. Leave `podcast-backlog.md`'s diff out of the path commit (it's #32 `--long` episode work, unrelated). **NOTE:** current-session `CronList` still shows empty (harness loaded 0 jobs at startup before the repair); the repaired file reloads on the next session/next cron fire.

**Still open:** only the Kokoro `pronunciation_db.load_golds_into_pipeline` bug — now IRRELEVANT since OmniVoice is the engine again (no Kokoro needed). Episode production (#27/#30/#32) is fully UNBLOCKED with the originally-intended OmniVoice voice — no Kokoro compromise, no `rerender_omnivoice.py` pass needed.

## ✅ OMNIVOICE FIXED (~11:45 UTC, this session)
The handoff's BLOCKER premise ("OmniVoice fully broken, vendor venv has no omnivoice module and no pip, heavy rebuild needed") was WRONG. Root cause + fix:
- The venv is a **uv** venv (`pyvenv.cfg`: `uv = 0.9.7`) — uv doesn't seed `pip`, so `$OV -m pip` "No module named pip" is NORMAL, not breakage.
- `omnivoice` was an **editable install** (`uv pip install -e .`, pyproject `name=omnivoice`, package `omnivoice/`, v0.3.0) whose source pointer still named the OLD dead path `file:///Users/lpollington/Dev/OmniVoice-Studio`. The repo move orphaned it. torch 2.8.0 survived (normal install).
- **Fix:** `cd /Users/lpollington/Dev/vendor/OmniVoice-Studio && uv pip install -e .` → uv re-linked the pointer to `file:///Users/lpollington/Dev/vendor/OmniVoice-Studio`.
- **Verified:** `from omnivoice.cli.infer import get_best_device` + `from omnivoice.models.omnivoice import OmniVoice` resolve; torch 2.8.0 / device `mps`; `_use_omnivoice()` returns `True` with TTS_ENGINE unset. (Render smoke-test optional — first episode render is the final proof.) `.python-version` pins 3.11 but the venv is deliberately 3.12.9 (prior session chose it to match the working trial) — do NOT "fix" this.

## Goal
Produce and publish **3 podcast episodes** from the backlog into the live "Señora Freedom" RSS feed (GitHub: `mrleepee/freeist-podcast`), then move them from pending → published in `podcast-backlog.md`. The 3 episodes are the research-augmented items **#27 (cellular-aging stack), #30 (China micro-margin manufacturing), #32 (William Hooper / Declaration)**. End-state: 3 new episodes (ep162/163/164) have EN+ES audio in the feed, `episodes.json` has 3 new entries with title + description ending in a `Links:` section, `rss/feed.xml` is regenerated and pushed, and the backlog marks #27/#30/#32 published (with #18/#20/#22 noted as URL-rotten/skipped).

## Summary of what's happened
- **This session IS the 1:37 PM weekday cron run** (session id `84efcbd3-81b8-4958-8d00-cd94a2b2d202`, host pid `37350`, confirmed by the background-task output path). The cron's prompt is the production workflow.
- User asked: "did our cron fire today?" → answered: yes, 13:37 local slot fired (this is it); the 17:11 slot is separate. The cron is a Claude Code durable scheduled task in `.claude/scheduled_tasks.json` (jobs `7505f0e1` = `37 13 * * 1-5`, `69894926` = `11 17 * * 1-5`).
- User then asked to produce **#18** + **2 more**.
- **#18's source URL is rotten** (resolves to a Pavel Durov/Telegram video, not "10 reasons to leave the UK"). Probed the other pending X URLs:
  - ✗ **#18** https://x.com/sotontimes/status/2066672006670569696/video/1 → Durov/surveillance (WRONG)
  - ✗ **#20** https://x.com/zodchiii/status/2066905647841522077/video/1 → Sundar Pichai/Google orchestration (WRONG)
  - ✗ **#22** https://x.com/hanakoxbt/status/2066969072818872627/video/1 → Anthropic Claude Code engineer (WRONG)
  - ✓ #23, #25, #29 are URL-valid but ALL flagged HIGH/VERY-HIGH duplicate-risk (agent loops / Karpathy / Cherny — backlog says do NOT `--force`)
  - Same failure mode as the already-known rotten **#21**.
- **User decided** (via AskUserQuestion) to pivot to **3 research-augmented episodes: #27, #30, #32** (no broken URLs; write summaries + evidence pipeline). This decision is FINAL — do not revisit.
- Wrote 3 research summaries (~1000 words each; #32 fuller for `--long`) and a batch driver. Ran the batch.
- **Batch FAILED at TTS**: OmniVoice (the intended engine) is broken. Smoke-tested the Kokoro fallback — it WORKS but its pronunciation pass is broken.
- Was about to ask the user how to proceed on TTS (Kokoro-now / fix-pronunciation / fix-OmniVoice / abort) — **user interrupted with `/handoff` instead of answering**. The TTS-path decision is therefore UNRESOLVED; see BLOCKER + recommended default below.

## Problems & blockers encountered

### ⚠️ ~~BLOCKER — TTS backend choice is unresolved~~ → ✅ RESOLVED 2026-06-23 (see OMNIVOICE FIXED above; the below is historical)
Neither TTS path is clean after the **June 22 repo move** (podcast-forge + freeist-podcast + OmniVoice-Studio all relocated):
- **OmniVoice (intended voice, used by ep154–161): FULLY BROKEN.** `_OMNIVOICE_PY` default is `~/Dev/OmniVoice-Studio/.venv/bin/python` (video_downloader.py:1647-1649) — that path no longer exists. The repo moved to `/Users/lpollington/Dev/vendor/OmniVoice-Studio`. BUT even at the vendor path the venv is incomplete: **no `omnivoice` Python module installed, and no `pip`** (`ModuleNotFoundError: No module named 'omnivoice'`; `No module named pip`). torch 2.8.0 IS present. Repairing needs a venv rebuild + omnivoice package install (heavy; not quick). Overridable via `OMNIVOICE_PY` env var.
- **Kokoro fallback: WORKS but pronunciation pass is broken.** `TTS_ENGINE=kokoro` renders valid audio (smoke test produced `/tmp/kokoro_smoke.mp3`, voice `bm_daniel`). BUT `pronunciation_db.load_golds_into_pipeline()` raises `string indices must be integers, not 'str'` → Kokoro proceeds WITHOUT pronunciation golds → proper nouns mispronounced. Non-fatal. Voice also differs from the OmniVoice episodes already in the feed.
- **`rerender_omnivoice.py` exists** to re-voice already-published episodes with OmniVoice later (it's the "fix it in post" tool; it already has an uncommitted path fix: `AUDIO = Path("/Users/lpollington/Dev/personal/freeist-podcast/audio")`).

**Recommended default to continue WITHOUT asking the user:** set `TTS_ENGINE=kokoro` and produce the 3 episodes now (optionally spend ≤10 min trying to fix the `pronunciation_db` bug first — it directly affects these pronunciation-heavy episodes). Accept the Kokoro voice + imperfect pronunciation; plan an OmniVoice rerender later via `rerender_omnivoice.py`. This is the only way to get episodes out today. If the user actually wanted OmniVoice-first, they will redirect on resume — but do NOT block on them; proceed with Kokoro.

### Secondary — evidence-pipeline QA embellishments (non-blocking but note)
On the failed #27 run, Stage 4 QA reported `Verification FAILED: 4 high-confidence untraceable claims (threshold: 3)` — the narration LLM invented flourishes NOT in the source summary (e.g. "Forty pounds. That's roughly what a month's supply costs", "two with hope and a Baylor phone number", "from the same lab that invented the supplement"). **The pipeline CONTINUED to audio anyway (verification failure is non-blocking).** To reduce this, pass `extra_prompt=` instructing strict factual restraint (no invented prices/numbers/dramatic asides). QA still runs; that's fine.

### Rotten backlog URLs (already handled by the pivot)
#18/#20/#22 X URLs resolve to wrong content (table above). Do NOT produce them. Mark them URL-rotten/skipped in the backlog (mirror the format of the existing #21 skip note). #23/#25/#29 are valid but high-dup-risk — leave pending.

### Cron config drift (flag, don't necessarily fix now)
- Cron prompt text says `Work in /Users/lpollington/Dev/podcast-forge` (dead path; real is `/Dev/personal/podcast-forge`) — harmless `cd` failure, session runs from the real dir anyway.
- `_OMNIVOICE_PY` default (video_downloader.py:1649) still points at the dead `~/Dev/OmniVoice-Studio` — should be updated to `~/Dev/vendor/OmniVoice-Studio` for the cron to work (but the vendor venv is broken anyway, so this alone won't fix TTS).
- A prior session already started the path migration (uncommitted edits in `rerender_omnivoice.py`, `narrate_summaries.py`).

## Files in play (read these FIRST)
- **`video_downloader.py`** (3856 lines) — core engine. Key symbols: `_OMNIVOICE_PY` (1647-1649), `_use_omnivoice()` (1781-1783 — `TTS_ENGINE=kokoro` → False), `_generate_podcast_audio` (2296, Kokoro), `_generate_omnivoice_audio` (2058), `produce_podcast` (3175 — signature: `summary_path, video_title="", podcast_dir=None, extra_prompt="", video_duration_seconds=0, duo=False, pipeline="summary", force=False, agentic_takeaway="auto"`), `_run_evidence_pipeline` (2758), `_register_episode_metadata` (2715 — uses `setdefault`; **early-returns if `video_title` is empty**, so always pass a title), `publish_feed` (3554), `main` (3704 — `--podcast`/`--publish` flags), `_target_word_count` (1270 — `video_duration_seconds<=0`→700 words ~5min; pass `6000` for ~10min/`--long`). REFERENCE.
- **`pronunciation_db.py`** — `load_golds_into_pipeline()` is the broken function (the `string indices must be integers, not 'str'` error). NEEDS DEBUGGING if you attempt the pronunciation fix. Also `pronunciation_cache.json` (data, modified 19 Jun) and `pronunciation_db.py`.
- **`downloads/raw/cellular-aging-stack.summary.md`** — WRITTEN, ready (#27 input). ~1000 words.
- **`downloads/raw/china-micro-margin.summary.md`** — WRITTEN, ready (#30 input). ~1000 words.
- **`downloads/raw/william-hooper-declaration.summary.md`** — WRITTEN, ready (#32 input, fuller for `--long`). ~1300 words.
- **`downloads/raw/_produce_batch.py`** — WRITTEN batch driver (produces all 3 sequentially with `pipeline="evidence", force=True`). **NEEDS EDITING**: set `TTS_ENGINE=kokoro` (and it currently does NOT set it). Currently uses default OmniVoice → will fail. Either prepend `TTS_ENGINE=kokoro` to the run command, or add `os.environ["TTS_ENGINE"]="kokoro"` before the `from video_downloader import` line.
- **`podcast-backlog.md`** — items #18/#20/#22/#27/#30/#32 are all still PENDING/un-struck. NEEDS EDITING at the end: mark #27/#30/#32 published (ep+slug); add URL-rotten skip notes to #18/#20/#22 (mirror #21's format).
- **`/Users/lpollington/Dev/personal/freeist-podcast/episodes.json`** — the PUBLISH repo's episode registry (157 entries; last = `ep161-tbilisi-city-history-from-founding-present-day`). This is where `_register_episode_metadata` writes (via `_PUBLISH_REPO = parent.parent/"freeist-podcast"`). NEEDS EDITING: append `Links:` section to each of the 3 new entries' `description`.
- **`/Users/lpollington/Dev/personal/freeist-podcast/rss/feed.xml`** — regenerated by `publish_feed()`.
- `rerender_omnivoice.py`, `narrate_summaries.py` — pre-existing uncommitted path-fix edits (not ours; leave alone unless completing the migration).

## Internal Claude Code context
- **Session / project:** `podcast-forge`; session id `84efcbd3-81b8-4958-8d00-cd94a2b2d202` (this IS the 1:37 PM cron run, host pid 37350). Background tasks used: `b9dga5whd` (#18 produce — failed/skipped), `bacr6hh0l` (batch — stopped after OmniVoice failure).
- **Skills:** the `podcast` skill exists but was NOT invoked via the Skill tool; we called `video_downloader.py` / `produce_podcast` directly per the cron workflow.
- **Commands & tools run:** `yt_dlp --print "%(title)s"` URL probes; `produce_podcast` batch via `_produce_batch.py`; OmniVoice smoke test (`_generate_podcast_audio` with `OMNIVOICE_PY=vendor`); Kokoro smoke test (`TTS_ENGINE=kokoro`).
- **Publish target:** GitHub repo `mrleepee/freeist-podcast`; RSS base `https://mrleepee.github.io/freeist-podcast/audio/`. `publish_feed()` regenerates feed, stages `feed.xml`+`rss/feed.xml`+`episodes.json`+`audio/*.podcast.{mp3,txt}`, commits "Update podcast feed", pushes; falls back to `gh api` Contents upload if push fails.
- **Env / deps:** Python `.venv/bin/python3` (3.12.9). LLM backend = GLM (Z.ai). `.env` present. TTS: OmniVoice (broken) or Kokoro (`hexgrad/Kokoro-82M`, local, works). `gh` CLI used for GitHub.

## Remaining steps to the goal
1. **Resolve TTS (do not ask the user):** proceed with **Kokoro**. Optional first: spend ≤10 min trying to fix `pronunciation_db.load_golds_into_pipeline` (the `string indices must be integers, not 'str'` bug) — if not a quick fix, skip it and produce anyway (pronunciation will be imperfect; rerender later).
2. **Edit `downloads/raw/_produce_batch.py`**: add `os.environ.setdefault("TTS_ENGINE", "kokoro")` BEFORE `from video_downloader import produce_podcast`. Optionally add an `extra_prompt` to each job enforcing factual restraint (no invented prices/numbers/asides) to avoid the QA embellishments seen on #27.
3. **Run the batch** from the project root: `cd /Users/lpollington/Dev/personal/podcast-forge && TTS_ENGINE=kokoro .venv/bin/python3 downloads/raw/_produce_batch.py` (run in background; ~10–20 min for 3 episodes × EN+ES). Episode numbers come out **ep162 (#27), ep163 (#30), ep164 (#32)** in that order.
4. **Verify each produced**: EN+ES `.podcast.mp3`/`.podcast.es.mp3` exist in `downloads/podcast/`; `episodes.json` got a new `[slug]` entry with `title` + blurb `description` + `guid` (setdefault — only fills missing, so produce writes them since titles are non-empty).
5. **Enhance `episodes.json`** (at `/Users/lpollington/Dev/personal/freeist-podcast/episodes.json`): for each of the 3 new slugs, append a `Links:` section to the `description` (overwrite the blurb with blurb + links). Sources to use:
   - **#27 cellular-aging:** Urolithin A RCT https://pmc.ncbi.nlm.nih.gov/articles/PMC9133463/ · GlyNAC (Sekhar/Baylor) https://pubmed.ncbi.nlm.nih.gov/35975308/ · Sulforaphane/Nrf2 https://pmc.ncbi.nlm.nih.gov/articles/PMC4736808/
   - **#30 china-micro-margin:** CF40 Research https://cf40research.substack.com/p/chinese-manufacturing-competes-with-all-countries-uneven-development-rapid-growth-massive-scale-flying-geese-formation-trade-tensions-export-tax-rebates-policy-implications · Tecma (wages > Mexico/Brazil) https://www.tecma.com/manufacturing-wages-in-china/
   - **#32 william-hooper:** Wikipedia https://en.wikipedia.org/wiki/William_Hooper · NCpedia https://www.ncpedia.org/biography/hooper-william · National Constitution Center https://constitutioncenter.org/signers/william-hooper
   - (Match the `Links:` format already used by ep159/ep160 — see those entries.)
6. **Publish:** `.venv/bin/python3 -c "import sys; sys.path.insert(0,'.'); from video_downloader import publish_feed; publish_feed()"` — regenerates RSS + commits + pushes to `mrleepee/freeist-podcast`. Confirm "Feed pushed to GitHub."
7. **Update `podcast-backlog.md`:** mark #27/#30/#32 as ✅ PUBLISHED (ep162/163/164 + slug), and add a `❌ SKIPPED <date>: SOURCE URL MISMATCH` note to #18/#20/#22 (resolve-to content listed above) mirroring #21's existing skip note.
8. **Report** to the user: episode slug, title, EN duration, ES duration, push status — for all 3. Also report the TTS compromise (Kokoro, pronunciation caveat) and the recommended follow-ups (fix OmniVoice vendor venv; update `_OMNIVOICE_PY` default; fix the cron prompt path; fix `pronunciation_db`).

## Verification / done criteria
- `ls downloads/podcast/ep16{2,3,4}*podcast*.mp3` → 6 files (3 EN + 3 ES).
- `python3 -c "import json;d=json.load(open('/Users/lpollington/Dev/personal/freeist-podcast/episodes.json'));print([k for k in d if k.startswith('ep16')][-4:])"` → includes ep162/163/164.
- Each new episodes.json entry has a `description` containing a `Links:` section.
- `git -C /Users/lpollington/Dev/personal/freeist-podcast log -1` → a new "Update podcast feed" commit; `gh api repos/mrleepee/freeist-podcast/contents/rss/feed.xml` succeeds.
- `podcast-backlog.md` shows #27/#30/#32 struck/published and #18/#20/#22 skipped.

## Watch out for
- **The user did NOT answer the TTS-path question** — proceeding via Kokoro is the pragmatic default; if they wanted OmniVoice-first they will say so on resume. Do not block.
- **OmniVoice cannot be quickly fixed** (vendor venv has no `omnivoice` module AND no pip). Don't waste time on it for this run — use Kokoro.
- **Episode numbers are sequential** — run #27 before #30 before #32 (the batch script already does). If any produces partial artifacts, `_next_episode_number` may miscount; clean `downloads/podcast/ep16N-*` before retry if numbering goes wrong.
- **`force=True` is correct for #27/#30/#32** (they trip the sponsorship gate as false-positives — longevity supplements / sourcing pitch / history sponsor reads — and the backlog explicitly approves the override). Do NOT use `force` on the dup-risk items #23/#25/#29 (not being produced anyway).
- **The evidence QA embellishment risk** (#27 got invented £ prices / "Baylor phone number") — mitigate with `extra_prompt` factual restraint.
- **Do not commit** `.claude/scheduled_tasks.json` or `.claude/scheduled_tasks.lock` (cron-runner state) or the pre-existing uncommitted edits in `narrate_summaries.py`/`rerender_omnivoice.py` unless intentionally completing the migration.
- **Pronunciation matters** for these episodes (Urolithin A, GlyNAC, sulforaphane, mitophagy, Nrf2, Hooper, Otis, Wilmington, Hillsborough) — the broken Kokoro pronunciation pass is a real quality risk; the OmniVoice rerender later (via `rerender_omnivoice.py`) is the planned quality fix.
- The repo at the OLD path `/Users/lpollington/Dev/podcast-forge` does NOT exist; everything is under `/Dev/personal/podcast-forge`. The cron prompt's stale path is harmless (cd fails, session uses real cwd).
