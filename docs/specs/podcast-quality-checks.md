# Podcast Quality Checks — Implementation Spec

Automated quality gates that run before any episode ships. Each check is
deterministic or LLM-judged, runs against a fixture set, and blocks publish on
failure. Background: `podcast-quality-recommendation-spec.md`; testable outcomes
from `podcast-quality-plan.md`.

**Initiative:** Podcast quality upgrade
**Status:** draft
**Branch:** `feature/podcast-quality-checks`

## Requirements

| # | User input / trigger | Current behaviour | Expected behaviour | Verified |
|---|---|---|---|---|
| R1 | A finished MP3 ready to publish | Episodes range from ~-22 to ~-27 LUFS (quiet, inconsistent). No loudness gate exists. | Two-pass EBU R128 normalisation to I=-16 LUFS, TP=-1.5 dBTP, LRA≤11. Publish blocked if integrated LUFS outside [-17, -15] or true peak > -1.0 dBFS. | Measured 2026-05-30: raw episodes sit ~-25 LUFS. One-pass loudnorm took ep102 from -23.9 → -16.1 LUFS. |
| R2 | A script containing `{x402, CBDC, Liberland, Georgia, SEPA}` before TTS synthesis | Pronunciation is handled ad-hoc by `pronunciation_db.py` golds. No coverage gate — risky tokens can slip through unhandled. | Before synthesis, detect all risky tokens (acronyms, proper nouns, currencies, jurisdictions, product names). Every detected token must have a pronunciation entry. Build blocked if coverage < 100%. | Observed: tmux pronounced inconsistently across episodes. Golds added manually after the fact. |
| R3 | A draft narration script | Scripts sometimes contain "experts say", "studies show" and lack specific numbers or named sources. | Filler denylist returns 0 hits. Script contains ≥6 specific numbers/dates and ≥2 named sources per 1000 words. LLM judge scores source_specificity ≥4/5 with no untraceable claims. | SOUL.md already forbids "experts say" but no automated check enforces it. |
| R4 | The first 30 seconds and final paragraph of a script | Openings are sometimes vague. Endings sometimes say "only time will tell." | First two sentences contain a number, a name, or a question. Ending denylist (see Phase 5) returns 0 hits. LLM judge confirms hook in first 30 s, single thesis, counterpoint present, ending lands implication. | SOUL.md already says "Never end with 'Only time will tell'" — not enforced programmatically. |
| R5 | A two-host dialogue script | Duo episodes sometimes have echo lines, two-word reactions, sentence fragments, or fake opposition. | Every turn ends with terminal punctuation and is ≥4 words. No adjacent turn shares >50% token overlap. LLM judge confirms no echo, no fragments, no fake opposition, all hooks resolved. | `two-host-dialogue-craft-prompt.md` lists these as "flat-TTS killers" but no automated check exists. |
| R6 | `produce_podcast()` finishes audio generation | Audio is published immediately after generation. No quality gate. | Publishing is blocked unless all checks (R1–R5) pass and metrics are written to `quality_report.json`. On failure, the failing check name and reason are reported. | No publish gate exists today. `_check_sponsored_content` warns but doesn't block. |
| R7 | Developer runs `python checks/run.py` | No check harness exists. Quality checks are manual. | All checks run against fixtures, print a pass/fail table, and exit 0 (all pass) or 1 (any fail). Good fixtures pass; known-bad fixtures fail. | `audition_voices.py --measure` is the loudness check in embryo. |

## Phases

### Phase 1 — Check harness and fixtures [not started]

**Status:** not started
**Fixes:** R7

#### Behaviour

- Given the `checks/` directory with `run.py` and `fixtures/`, when a developer runs `python checks/run.py`, then all registered checks execute against every fixture, a pass/fail table is printed to stdout, and the process exits 0 if all pass or 1 if any fail.
- Given a good fixture (real episode audio + script), when any check runs, then the result is PASS.
- Given a known-bad fixture (deliberately quiet audio, or a script with filler phrases), when the relevant check runs, then the result is FAIL.

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| `python checks/run.py` with good fixtures | Exit 0, all PASS | |
| `python checks/run.py` with one known-bad fixture | Exit 1, at least one FAIL | |
| New check registered in `checks/` | Automatically discovered and run | |

#### Not in scope

- No actual quality checks yet — just the harness structure.
- CI integration (future work).

### Phase 2 — Loudness normalisation [not started]

**Status:** not started
**Fixes:** R1

#### Behaviour

- Given a finished MP3 file, when mastering runs, then the output file has integrated loudness in [-17.0, -15.0] LUFS and true peak ≤ -1.0 dBFS.
- Given a raw Kokoro MP3 at ~-25 LUFS, when mastering runs, then a single two-pass loudnorm filter produces the target level.
- Given an episode with mastered audio, when `produce_podcast()` finishes, then measured loudness values are written to `quality_report.json`.
- Given mastered audio outside tolerance, when publish is attempted, then publish is blocked and the failing metric is named.

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| Raw Kokoro MP3 at -25 LUFS | Mastered to -16 ±1 LUFS, TP ≤ -1.0 dBFS | |
| Episode already at -16 LUFS | No change (within tolerance) | |
| Known-bad fixture at -25 LUFS without mastering | Check fails: loudness out of range | |

#### Not in scope

- AAC/M4A output (MP3 only for now).
- Music beds or dynamic range compression beyond loudnorm.

### Phase 3 — Pronunciation manifest [not started]

**Status:** not started
**Fixes:** R2

#### Behaviour

- Given a narration script containing `{x402, HTTP 402, CBDC, Liberland, Georgia, SEPA}`, when pronunciation detection runs, then all six tokens are identified as risky.
- Given the detected risky tokens, when manifest coverage is checked, then every token has an entry in the pronunciation cache/golds.
- Given a risky token with no pronunciation entry, when the manifest is built, then the check fails with the uncovered token listed.
- Given a script with zero risky tokens, when pronunciation detection runs, then the check passes trivially.

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| Script with `{x402, CBDC, Liberland, Georgia, SEPA}` | All 5 detected and covered → PASS | |
| Same script, one gold removed | FAIL, names the uncovered token | |
| Plain English script with no jargon | PASS (nothing to cover) | |

#### Not in scope

- Audition clips for manual pronunciation review (future work).
- Automatic Wiktionary fallback during the check (already exists in `pronunciation_db.py`).

### Phase 4 — Substance over filler [not started]

**Status:** not started
**Fixes:** R3

#### Behaviour

- Given a script containing the phrase "experts say" or "studies show", when the filler denylist runs, then the check fails and lists the offending phrases.
- Given a script with ≥6 specific numbers/dates and ≥2 named sources per 1000 words and zero filler phrases, when the substance check runs, then the deterministic portion passes.
- Given a script that passes deterministic checks, when the LLM judge runs, then it returns `{ "untraceable_claims": [], "vague_phrases": [], "source_specificity_0to5": n, "pass": true }` where n ≥ 4.
- Given a script with "experts say" and no named sources, when the substance check runs, then the check fails regardless of LLM judge output.

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| Script with "experts say" | FAIL: filler phrase detected | |
| Script with 0 named sources | FAIL: insufficient source specificity | |
| Good script with numbers, sources, no filler | PASS (deterministic + LLM judge) | |

#### Not in scope

- Claim ledger extraction from source material (future work — the check validates the script, not the research process).
- Multi-source research pack enforcement.

### Phase 5 — Hooks early, lands the ending [not started]

**Status:** not started
**Fixes:** R4

#### Behaviour

- Given a script whose first two sentences contain neither a number, nor a name, nor a question, when the hook check runs, then the check fails.
- Given a script whose final paragraph contains any phrase from the ending denylist `{"only time will tell", "at the end of the day", "in conclusion", "in today's ... world"}`, when the ending check runs, then the check fails and lists the offending phrase.
- Given a script with a concrete hook and a strong ending, when the LLM judge runs, then it returns `{ "hook_in_first_30s": true, "single_thesis": true, "has_counterpoint": true, "ending_lands_implication": true, "persona_fit": true, "pass": true }`.

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| Script opening "Welcome to another episode" | FAIL: no number/name/question | |
| Script ending "Only time will tell." | FAIL: ending denylist hit | |
| Good script with number in first sentence, implication ending | PASS | |

#### Not in scope

- Outline-first workflow (enforced at production time, not as a check).

### Phase 6 — Two-host dialogue critic [not started]

**Status:** not started
**Fixes:** R5

#### Behaviour

- Given a duo script where a turn ends without terminal punctuation (`.`, `!`, `?`), when the fragment check runs, then the check fails and lists the fragment.
- Given a duo script where a turn is fewer than 4 words, when the fragment check runs, then the check fails and lists the short turn.
- Given a duo script where two adjacent turns share >50% token overlap (ignoring speaker labels), when the echo check runs, then the check fails and lists the echo pair.
- Given a duo script passing deterministic checks, when the LLM judge runs, then it returns `{ "echo_lines": [], "fragments": [], "fake_opposition": false, "hooks_unresolved": 0, "pass": true }`.
- Given a solo script, when the dialogue critic runs, then the check is skipped (PASS with note "solo episode").

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| Duo script with 2-word reaction "That's right." | FAIL: fragment | |
| Duo script with adjacent turns "It's a huge problem." / "It's a huge issue." | FAIL: echo >50% overlap | |
| Good duo script, complete turns, no echo | PASS | |
| Solo script | SKIP (not applicable) | |

#### Not in scope

- Voice consistency checks across episodes.
- Speaker role validation.

### Phase 7 — Publish gate [not started]

**Status:** not started
**Fixes:** R6

#### Behaviour

- Given all checks passing (R1–R5 applicable to the episode type), when publish is attempted, then `quality_report.json` is written with all check results and publish proceeds.
- Given any check failing, when publish is attempted, then publish is blocked, the failing check name and reason are printed, and `quality_report.json` is written with `publish_blocked: true`.
- Given a known-bad fixture (quiet audio or vague script), when `produce_podcast()` reaches the publish step, then it refuses and names the failing check.
- Given a known-good fixture, when `produce_podcast()` reaches the publish step, then it proceeds normally.

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| Episode with all checks PASS | Publish proceeds, quality_report.json written | |
| Episode with loudness FAIL | Publish blocked, reason: "loudness out of range" | |
| Episode with filler FAIL | Publish blocked, reason: "filler phrases detected" | |

#### Not in scope

- Human override for blocked episodes (future work — add `--force-publish` flag).
- Notification/webhook on blocked publish.

## Constraints

- **One branch per phase.** Each phase is implemented, reviewed, and merged independently.
- **~150–200 lines of production code per phase.** Keep phases reviewable in one sitting.
- **Deterministic first.** Where a deterministic check exists, it runs before any LLM judge call.
- **LLM judge contract.** One judge call per content check, temperature 0, strict JSON output. Parse error = failure. Prompt is fixed per item — only the rubric block changes.
- **No paid TTS.** Quality checks must not introduce recurring costs beyond existing MiniMax usage.
- **Kokoro stays.** Do not change the TTS engine.
- **Backward compatible.** Existing episodes that have already been published are not re-processed. Checks apply to new episodes only.

## Not In Scope

- **Consistent host voice (Item parked):** Voice not yet chosen. `audition_voices.py` exists for picking. When resumed: test that the same script synthesized twice records an identical configured voice id.
- **Claim ledger from source material:** The substance check validates the script; extracting claims from the source is a separate production workflow change.
- **Multi-source research packs:** Enforcing minimum source counts before scripting starts is a production workflow change, not a check.
- **CI integration:** `checks/run.py` is designed for local use. CI can call it later.
- **AAC/M4A output format:** MP3 only for now.
- **Segment-level synthesis and retry:** Single-pass synthesis continues. Segment retry is future work.

## Appendix

### A1. Existing infrastructure

- `audition_voices.py` contains `measure_loudness()` using ffmpeg EBU R128 loudnorm — the seed for Phase 2.
- `pronunciation_db.py` has `load_golds_into_pipeline()`, `enrich_pronunciation_cache()`, and Wiktionary IPA lookup — the seed for Phase 3.
- `_check_sponsored_content()` at line 1898 shows the pattern for MiniMax-based checks — the seed for LLM judging.
- `SOUL.md` defines the show persona, sourcing rules, and banned phrases — the source of truth for content checks.
- `two-host-dialogue-craft-prompt.md` defines craft rules for duo episodes — the source of truth for Phase 6.

### A2. Audio targets

- Primary target: -16 LUFS ±1 dB (integrated loudness).
- True peak: ≤ -1.0 dBFS.
- Loudness range: LRA ≤ 11.
- Measured baseline (2026-05-30): raw Kokoro output sits at ~-25 LUFS.
- One-pass loudnorm fix confirmed on ep102: -23.9 → -16.1 LUFS.

### A3. LLM judge contract

Shared across Phases 4, 5, and 6. One call per content check:

```
SYSTEM: You are a strict podcast QA judge. You receive a SCRIPT and the show
bible SOUL.md. Apply the RUBRIC exactly. Return ONLY the JSON object named in the
rubric — no prose, no markdown fences. If unsure, fail the check.

USER:
SOUL.md:
<<<{soul}>>>
SCRIPT:
<<<{script}>>>
RUBRIC:
<<<{the JSON shape + pass condition for the item}>>>
```

The implementing code parses the JSON. A check passes only when `pass == true`.
Parse error counts as failure.

### A4. Build order

`Phase 1 (harness) → Phase 2 (loudness) → Phase 3 (pronunciation) → Phase 4 (substance) + Phase 5 (hooks) → Phase 6 (dialogue) → Phase 7 (publish gate)`

Phases 4 and 5 can proceed in parallel since they are independent. Phase 6 is
independent of 4/5 but comes later because it only applies to duo episodes.
Phase 7 ties everything together and must be last.
