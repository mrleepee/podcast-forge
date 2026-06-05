# Code Review — Evidence-First Pipeline

**Branch:** `feature/evidence-first-pipeline`
**Reviewed at:** `b8e8fc1` ("Update evidence-first pipeline spec: all phases done")
**Date:** 2026-05-31
**Scope:** `pipeline_stages.py`, `checks/check_opening.py`, the `produce_podcast` wiring in `video_downloader.py`, and `tests/` — assessed against `docs/specs/evidence-first-pipeline.md`.

## Verdict

The spec is excellent and the scaffolding is well-shaped, but the pipeline does not work yet. There are two showstoppers — the LLM stages never use their prompts, and script drafting crashes on every run — plus the branch is missing the checks it depends on. The structure is right; the substance behind it is not realized.

## Critical

### 1. The LLM stages never use their prompts — so it isn't actually evidence-first

`_call_minimax_via_existing` builds a combined system+user prompt, then discards it and calls the old `_summarize_with_minimax(user_prompt)`, which applies its own "concise bullet points" prompt. Consequences:

- `extract_evidence` receives a bullet summary (not JSON) → JSON parse fails → falls back to `_extract_evidence_deterministic`, a regex sentence-grabber.
- `generate_outline` does the same → falls back to `_generate_outline_deterministic`, a fixed template (every episode gets the identical thesis "Analysis of the key claims…" and hook "surprising_fact").

The "forensic analyst" (Stage 2) and "podcast editor" (Stage 3) agents are effectively dead. Every episode is built from regex-grabbed sentences plus a boilerplate outline — the opposite of the goal, and arguably worse than the summary path it replaces (R1, R3 unmet).

Related defects in the same area:

- `_call_minimax_via_existing` spawns a subprocess and string-interpolates the transcript into a Python literal (`_summarize_with_minimax('''{user_prompt}''')`). This is fragile (breaks on `'''`/quotes/backslashes in source text) and an injection risk.
- `_call_minimax` (the "proper" direct call) is dead code: it is never invoked, requires a `MINIMAX_API_URL` env var the project doesn't set, and uses model `MiniMax-Text-01` while the rest of the codebase uses `MiniMax-M2.7` with a hardcoded URL list.

### 2. Script drafting crashes deterministically

`_build_opening_avoidance()` (`pipeline_stages.py:251`) calls `m.group(1)` on `re.match(r"[a-zA-Z]+", opening)`, which has no capturing group → `IndexError: no such group`. Reproduced directly during review. `checks/opening_log.json` is populated (8 entries), so this fires on every run, uncaught, aborting Stage 3 before a script is produced.

The same logic is written correctly in `check_opening.detect_first_word_repeats` (uses `group(0)`); it was copied into `pipeline_stages.py` with the wrong group index. The fix is one character (`group(1)` → `group(0)`), but as it stands the evidence path cannot produce a script.

### 3. The branch is missing PR #3, so Phase 5 is a no-op

`_run_qa_revision_loop` imports `checks.quality_gate`, which is not on this branch — `checks/` here contains only `check_opening.py`. The branch was cut from the old base and never merged the quality checks. So the loop hits `except ImportError` → "skipping QA loop", and R4 (the revision loop) does not function. There is also no substance check, no loudness normalization, no mastering, and no publish gate on this branch.

This violates the spec's own constraint: "Quality checks apply to both pipelines… the checks from PR #3 run after script generation regardless of pipeline path." The two branches are disjoint, and neither is complete on its own.

## High

### 4. Tests pass on the stubs and hide both showstoppers

The suite runs 35 passed / 4 failed in the review sandbox; the 4 failures are only `ModuleNotFoundError: No module named 'yt_dlp'` (those tests import `video_downloader`), so they will pass on a configured machine. But the green tests exercise the deterministic *fallbacks* in isolation:

- They never hit the real LLM path, so they miss finding #1.
- They never call `draft_script`/`_run_evidence_pipeline` with the populated opening log, so they miss the #2 crash.

Green here gives false confidence. An end-to-end test through `_run_evidence_pipeline` (with a stubbed-but-prompt-asserting MiniMax and the real opening log) would have caught both.

## Medium

### 5. Silent fallbacks mask total LLM failure

Because extraction and outline fall back quietly to crude deterministic versions, a completely broken LLM path still emits artifacts and looks healthy. Fallbacks should log loudly, and the canned outline should not ship as if it were a real one — prefer failing the stage over emitting boilerplate.

### 6. Spec status overstates reality

The spec is marked "Status: implemented" with "all phases done", but the verification tables are blank and the intended LLM behavior is not realized. The status should reflect that the agent stages are not yet functional.

## What's genuinely good

- Clean stage separation, with each stage persisting a human-readable artifact (`evidence_map.json`, `outline.json`) and resuming if the artifact already exists.
- `PipelineStageError` names the failed stage and the path to the last successfully written artifact.
- Flag-based coexistence with the old pipeline (default unchanged) is the correct safe-rollout shape.
- The opening-freshness idea (Phase 6) is a smart anti-repetition touch, and `check_opening.py` itself is correct and well-tested.
- The spec is well-structured and incorporated the Codex review findings.

## Recommended fixes (in order)

1. Fix the `group(0)` crash in `_build_opening_avoidance` (finding #2).
2. Make the MiniMax call actually send the system prompt: refactor `_summarize_with_minimax` to accept a custom prompt, or call the API directly using the existing `_MINIMAX_API_URLS` + key + model `MiniMax-M2.7`. Remove the subprocess hack and the dead `_call_minimax` (finding #1).
3. Cherry-pick PR #3's checks onto this branch so the QA revision loop, substance check, loudness master, and publish gate exist (finding #3).
4. Turn silent LLM fallbacks into loud failures (finding #5).
5. Add one end-to-end test through `_run_evidence_pipeline` that would catch #1 and #2 (finding #4).

## How this was verified

- Ran the suite: `python -m pytest tests/test_pipeline.py tests/test_opening.py` → 35 passed / 4 failed (the 4 are `yt_dlp` not installed in the review environment).
- Ran `_build_opening_avoidance()` directly → reproduced `IndexError: no such group` at `pipeline_stages.py:251`.
- Traced `_call_minimax_via_existing` → it calls `_summarize_with_minimax(user_prompt)` and never passes the system prompt.
- Confirmed `checks/` on this branch contains only `check_opening.py` (no `quality_gate.py`/`check_substance.py`), so the QA loop import fails at runtime.

---

## Update — 2026-05-31 (second pass, after fixes)

**Reviewed at:** `bf2446e`. Fixes landed in `afeaeab` ("Fix review findings #1 #2 #5"); PR #3's checks were cherry-picked in `6df523e`–`bf2446e`.

### Verified fixed (confirmed by reading + running)

- **#1 (LLM prompts):** `_call_minimax` now sends the stage-specific system prompt (model `MiniMax-M2.7`, `MINIMAX_API_KEY`, URL rotation). `extract_evidence`/`generate_outline` call it directly. The subprocess hack and the dead `_call_minimax` are removed. The forensic-analyst and editor agents now actually run.
- **#2 (crash):** `m.group(1)` → `m.group(0)` at `pipeline_stages.py:249`. Ran `_build_opening_avoidance()` — it returns a proper instruction string, no `IndexError`.
- **#5 (loud fallbacks):** `extract_evidence` and `generate_outline` now `raise RuntimeError` on insufficient or non-JSON output instead of emitting boilerplate; the deterministic functions are explicitly marked test-only.
- **#6 (spec status):** now honest — "review fixes applied… pending end-to-end validation".
- **#3 (cherry-pick):** all PR #3 check modules are present on the branch (`quality_gate.py`, `check_substance.py`, `master_audio.py`, etc.).

### New issue introduced by the integration

- **The QA revision loop fails on every episode — on loudness, not content.** `_run_qa_revision_loop` calls `run_quality_gate(script_text)` with no audio (`video_downloader.py:2097`), and `run_quality_gate` runs the loudness check on missing audio. Verified by running: `report.passed = False`, blocking failure `loudness: no audio file found`. So at the text stage loudness is unconditionally FAIL → the loop re-drafts up to 3 times (3 wasted MiniMax calls) → writes `qa_exhausted: true` for every episode, regardless of script quality. `run_quality_gate`'s own docstring says audio-less checks should be "skipped, not failures," but that is not implemented. **Fix:** skip loudness when `audio_path is None`; run loudness only on the final (mastered) audio.

### Still open / carried over from PR #3 (cherry-picked unfixed)

- **`master_audio` is still not wired into `video_downloader.py`** — loudness is never applied, so episodes still ship at ~-25 LUFS (and it's why the loudness check would fail even if audio were passed).
- **Publish gate is still advisory** — `_run_quality_gate(...)`'s return is discarded (`video_downloader.py:2282`); it prints a warning and blocks nothing.
- **`python checks/run.py` still crashes** (`No module named 'checks'`); only `python -m checks.run` works.
- **#4 (end-to-end test) still missing.** Nothing in the suite caught the QA-loop false-failure above — the exact gap an e2e test through `_run_evidence_pipeline` would close. (Sandbox shows 4 failures, but those are only `yt_dlp` not installed here; they pass on a configured machine. 36 pass.)

### Minor

- The new `_call_minimax` only catches `HTTPError` in its retry loop, so a network/timeout error propagates raw instead of as a clean `RuntimeError`; and it kept only the `.chat` endpoint, dropping the `.io` backup that `_summarize_with_minimax` uses.

### Recommended next step

Two changes make the loudness story real and stop the loop thrashing: (1) skip loudness in `run_quality_gate` when there's no audio (one conditional — unblocks the entire evidence QA loop), and (2) wire `master_audio` at the export step so the final file is actually normalized to -16 LUFS.

### How this round was verified

- Ran `_build_opening_avoidance()` → returns a string (crash fixed).
- Ran `run_quality_gate("<clean script>")` with no audio → `passed = False`, blocked on `loudness: no audio file found` (confirms the QA-loop bug).
- Read the new `_call_minimax`, `extract_evidence`, `generate_outline` → system prompt sent, loud `RuntimeError` on failure.
- `grep` confirmed `master_audio`/`master(` is still never called in `video_downloader.py`; `python checks/run.py` still raises `ModuleNotFoundError`.
