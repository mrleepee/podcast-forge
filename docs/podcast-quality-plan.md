# Podcast Quality Plan — Testable Outcomes

The lean, outcome-first version of the quality work. Each item is a listener-facing
outcome, the change that delivers it, and a **test an implementing LLM can run** to
confirm it is done. Consistent host voice is parked at the owner's request.

Ordered by payoff for effort. The detailed background lives in
`podcast-quality-recommendation-spec.md`.

## How to read this

- **Test = Definition of Done.** An item is complete only when its test passes on the regression set.
- **Deterministic checks** are scripts that exit `0` (pass) / `1` (fail).
- **LLM-judge checks** return strict JSON with a `pass` boolean (temperature 0). The implementing LLM runs the judge and treats `pass: false` as a failing test. Shared judge contract is in the appendix.
- **Regression set:** a fixed `checks/fixtures/` folder of representative inputs — ~5 scripts and ~5 episode audio files spanning EN/ES and solo/duo. Every test runs against it, plus one known-bad fixture per item to prove the test actually fails.

## Item 0 — Check harness (prerequisite)

- **Outcome:** every change below is verifiable automatically and re-runnable on demand.
- **Change:** add `checks/run.py` that runs all checks against the fixtures and prints a pass/fail table; add the fixtures by copying existing scripts/episodes.
- **Test:** `python checks/run.py` exits `0` on good fixtures and `1` on the known-bad ones. Seed already exists — `audition_voices.py --measure <file>` is the loudness check in embryo.

## Item 1 — Consistent, professional volume  *(quick win, already validated)*

- **Outcome:** every episode plays at the same broadcast-standard level — no quiet episodes, no clipping.
- **Change:** at export, run two-pass EBU R128 loudness normalization to `I=-16 LUFS, TP=-1.5 dBTP, LRA=11`, then encode. Write the measured values to `quality_report.json` and block publish if out of tolerance.
- **Test (deterministic):**

  ```
  measure(final.mp3):  integrated_LUFS in [-17.0, -15.0]   AND   true_peak <= -1.0 dBFS
  ```

  Baseline measured today: episodes sit at ~-25 LUFS → **fail**. Proven fix: the ep102 demo went -23.9 → -16.1 LUFS in a single pass. Regression: all sample episodes pass after mastering; the known-bad (raw -25 LUFS file) fails.

## Item 2 — Names and jargon pronounced correctly

- **Outcome:** the host doesn't fumble terms like x402, CBDC, Liberland, Georgia, or SEPA.
- **Change:** before TTS, detect risky tokens (acronyms, proper nouns, currencies, jurisdictions, product names) and build a pronunciation manifest with an expected spoken form for each. Fail if any risky token is uncovered.
- **Test (deterministic):**

  ```
  detect_risky_tokens(script)  is a subset of  manifest.keys()      # 100% coverage -> exit 0
  ```

  Known-good fixture: a script containing `{x402, HTTP 402, CBDC, Liberland, Georgia, SEPA}` with all six in the manifest passes. Drop one entry → exit `1`.

## Item 3 — Substance over filler

- **Outcome:** episodes carry specific, checkable facts and named sources instead of "experts say."
- **Change:** extract a claim ledger (claim, source, quote/locator, confidence) from the source material; write the script from the ledger, not from a loose summary; persist the ledger as an artifact.
- **Test (deterministic proxies + LLM-judge):**
  - Deterministic: denylist grep returns **0** hits for `{"experts say", "studies show", "many believe", "it's well known"}`; at least 6 specific numbers/dates and 2 named sources per 1000 words (regex count).
  - LLM-judge JSON: `{ "untraceable_claims": [...], "vague_phrases": [...], "source_specificity_0to5": n, "pass": (untraceable_claims == [] and source_specificity_0to5 >= 4) }`.

## Item 4 — Hooks early, lands the ending

- **Outcome:** grabs attention in the first ~30 seconds and ends on an implication, not "only time will tell."
- **Change:** generate a thesis + outline (hook → stakes → evidence → counterpoint → implication → close) before writing prose; QA-revise the draft until it passes.
- **Test (deterministic + LLM-judge):**
  - Deterministic: ending denylist returns **0** hits for `{"only time will tell", "at the end of the day", "in conclusion", "in today's ... world"}`; the first two sentences contain a number, a name, or a question.
  - LLM-judge JSON: `{ "hook_in_first_30s": bool, "single_thesis": bool, "has_counterpoint": bool, "ending_lands_implication": bool, "persona_fit": bool, "pass": all_true }`.

## Item 5 — Two-host episodes don't sound fake

- **Outcome:** no parroting, no sentence fragments, a real exchange between the hosts.
- **Change:** add an automated dialogue critic; revise until it passes.
- **Test (deterministic + LLM-judge):**
  - Deterministic: every turn ends with terminal punctuation and is at least 4 words; no adjacent turn shares more than 50% token overlap with the previous one (echo detector).
  - LLM-judge JSON: `{ "echo_lines": [...], "fragments": [...], "fake_opposition": bool, "hooks_unresolved": int, "pass": (echo_lines == [] and fragments == [] and not fake_opposition and hooks_unresolved == 0) }`.

## Publish gate (ties it together)

- **Outcome:** nothing ships unless it earned it.
- **Change:** publishing is blocked unless Items 1–5 tests pass and their metrics are written to `quality_report.json`.
- **Test:** on a known-bad fixture (quiet audio or a vague script) `publish()` refuses and names the failing check; on a known-good fixture it proceeds.

## Parked — consistent host voice

On hold at the owner's request (voice not yet chosen; use `audition_voices.py` to pick). When resumed, the test is: the same script synthesized twice records an identical configured voice id in `quality_report.json`, with no random voice selection left in the code path.

## Build order

`0 → 1 → 2 → (3, 4) → 5 → publish gate.` Items 1 and 2 are quick and almost entirely deterministic. Items 3–5 lean on the LLM judge, so they come after the harness can run it.

## Appendix — shared LLM-judge contract

One judge call per content item. Run at temperature 0. The prompt is fixed; only the rubric block changes per item.

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

The implementing LLM parses the JSON, and a check passes only when `pass == true`.
Any parse error counts as a failure.
