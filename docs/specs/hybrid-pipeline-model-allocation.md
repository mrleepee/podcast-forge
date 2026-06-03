# Hybrid Pipeline — Full Context and Verification

Improves the evidence-first pipeline by removing the hard truncation bottleneck (use the
model's full context instead of chunking) and adding an independent verification stage to
catch factual drift before audio.

**Initiative:** Podcast quality upgrade — pipeline optimisation
**Status:** draft (revised 2026-06-03 after review)
**Related spec:** `evidence-first-pipeline.md` (this builds on it)

## Revision note (2026-06-03)

This spec was cut down after review. Removed as erroneous or unnecessary:

- **Chunking + merge/dedup (former Phases 6–8 and Appendix B1).** GLM-5.1 and
  MiniMax-M2.7 both carry ~200K-token context. A 60-minute transcript is ~15k words
  (~20k tokens) and fits whole in a single call — roughly ten times over. Chunking to
  30k chars was unnecessary at episode scale, and the B1 algorithm was non-terminating:
  run directly, it emitted a duplicate tail chunk and then infinite-looped, so its own
  "2 chunks / 4 chunks" verification examples were wrong. The truncation bug is real, but
  the fix is to use the full context, not to chunk and merge.
- **Mandated GLM-for-structural-stages and the cost claim (former R9/R11, Phases 9/10/12).**
  GLM-5.1 and MiniMax-M2 are both coding/agentic models; there is no published basis that
  one is better at extraction and the other at prose. MiniMax-M2 is also the *cheaper*
  model, so routing most calls to GLM was a cost increase, not a saving. R11's "current
  behaviour = all GLM-5.1" was also factually wrong — the current pipeline is all MiniMax.
  Generation stays on MiniMax; the only model change kept is an *independent* verification
  pass (a different model checking the drafter's output catches errors the drafter is blind
  to — a principled reason, distinct from the unproven "better at facts" claim).

Kept: full-context extraction (R7) and the verification stage (R10), the strongest idea in
the original.

## Requirements

| # | Trigger | Current behaviour | Expected behaviour | Verified |
|---|---|---|---|---|
| R7 | A 60-minute interview transcript (~15k words / ~20k tokens) | `extract_evidence()` truncates input at 8,000 characters (~1,300 words) before sending to the LLM, discarding ~90% of a long transcript. | The full transcript is sent in a single call within the model's ~200K-token context, with a safety cap (~150k chars). No chunking — ~20k tokens fits ~10× in context. | `pipeline_stages.py` line 110: `text[:8000]` |
| R10 | A produced script contains an invented fact not in the evidence | No verification stage exists. If the LLM hallucinates during drafting, the error propagates to audio. | After drafting, an independent verification model compares the script against the evidence map and returns each untraceable claim (number, quote, name, date) with a confidence. Scripts with more than 3 high-confidence untraceable claims fail content QA. | No verification stage exists today. |

Removed in review: **R8** (chunk merge — chunking removed), **R9** (mandated GLM structural
allocation — unproven), **R11** (cost optimisation — inverted, and its "current behaviour"
was wrong).

## Phases

Phases are renumbered (the old 6–12 are gone or merged). Build order is sequential:
infrastructure first, then the stages that use it.

### Phase 6 — Full-context evidence extraction

**Status:** not started
**Fixes:** R7

#### Behaviour

- Given a transcript up to the safety cap (~150k chars), when extraction runs, then the entire transcript is sent in one call — not `text[:8000]` — within the model's ~200K-token context.
- Given a transcript longer than the cap, when extraction runs, then it is truncated at the cap and a warning is logged naming how many characters were dropped.
- Given evidence entries, when they are produced, then timestamps keep the existing `para:N` / `MM:SS` scheme (no change to an absolute-character-offset format).

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| 15k-word transcript | Single extraction call, full text sent, no truncation warning | |
| 200k-char transcript | Extraction runs on first ~150k chars, warning logs dropped length | |
| Existing fixture `checks/fixtures/good/liberland-meritocracy.txt` | Same evidence as before (well under the cap) | |

#### Not in scope

- Chunking, multi-chunk merge, and split-claim reconstruction. Unnecessary at episode scale; revisit only if sources exceed ~150k chars (~10 hours of audio).

---

### Phase 7 — Independent verification client (infrastructure)

**Status:** not started
**Fixes:** R10 (prerequisite)

#### Behaviour

- Given the pipeline needs a verifier, when it initialises, then a second model client is available (GLM-5.1 via the Z.ai API by default; configurable). Generation stages — extraction, outline, draft — remain on MiniMax-M2.7.
- Given the verification API key is missing, when the pipeline starts, then verification is skipped with a logged warning — it does not hard-fail the run on a second external dependency.
- Given a verification API call fails (timeout, auth, rate limit), when the error occurs, then it retries once, then skips verification for that episode with a warning naming the stage and service.

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| `ZAI_API_KEY` set | Verifier client initialises; generation still uses MiniMax | |
| `ZAI_API_KEY` unset | Verification skipped, warning logged, episode still produced | |
| Verifier API returns 500 twice | Retry once, then skip with a clear warning | |

#### Appendix reference

See Appendix B2 for the verification client implementation and API configuration.

---

### Phase 8 — Script verification against evidence

**Status:** not started
**Fixes:** R10

#### Behaviour

- Given a script draft and the evidence map, when verification runs, then the verifier returns a JSON array of untraceable claims, each with `claim`, `confidence` (high/medium), and `type` (number/date/quote/name/unattributed_expert).
- Given a script containing "In 2024, 90 countries piloted CBDCs" and an evidence entry "90 countries piloting CBDCs" (no year), when verification runs, then it flags `"2024"` with `confidence: high`.
- Given a verification report with more than 3 high-confidence untraceable claims, when content QA runs, then the script fails QA with `"verification_failed": "N untraceable claims"`. The threshold is a configurable constant.
- Given the existing deterministic substance check already flags vague attribution ("experts say"), when verification runs, then it integrates with that check rather than duplicating the denylist.

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| Script: "By 2025, 100 countries…"; Evidence: "100 countries…" (no year) | Report: untraceable claim "2025", confidence high | |
| Script: "Experts agree…"; Evidence: 3 named sources | Report: untraceable claim "Experts", confidence medium | |
| Script with 4 high-confidence untraceable claims | Content QA fails: "verification_failed" | |

#### Not in scope

- Automatic script revision from the report. The report is emitted; revision uses the existing Phase 5 revision loop (which must be fixed first — see Dependencies).

#### Appendix reference

See Appendix B1 for the verification prompt schema.

---

## Constraints

- **Use full model context.** Send the whole transcript (cap ~150k chars). No chunking until sources exceed the cap (~10 hours of audio), which the show does not produce.
- **Generation stays on MiniMax-M2.7.** Extraction, outline, and drafting use the already-wired MiniMax API — one generation dependency, no proven reason to split.
- **Verification SHOULD use a different model than the drafter.** An independent checker decorrelates errors. GLM-5.1 via Z.ai is the default; MiniMax-only is an acceptable fallback. This allocation is a hypothesis to validate by blind A/B on real scripts, not a proven win.
- **Verification is best-effort, not a hard dependency.** If the verification API is unavailable, skip with a warning; do not block an episode on a second external service.
- **Backward compatible.** The existing pipeline (full MiniMax, no verification) remains the default until verification is validated.
- **API keys.** `MINIMAX_API_KEY` is required; `ZAI_API_KEY` is optional (enables verification).

## Dependencies

This builds on the evidence-first pipeline, which per the 2026-05-31 review still has open
issues that must be fixed before verification can gate publishing reliably:

- The content-QA revision loop fails on a spurious loudness check when no audio is present (`run_quality_gate` does not skip audio-less checks). Verification gates publishing through that same loop.
- Loudness mastering (`master_audio`) is not yet wired into the export path.

Land those first; otherwise the verification gate inherits a broken loop.

## Not In Scope

- **Chunking / multi-chunk merge / split reconstruction.** Unnecessary at episode scale.
- **Mandated model allocation across structural stages.** Unproven; would require A/B benchmarking before adoption.
- **Multi-source evidence fusion.** Single-source only.
- **Semantic claim deduplication.**
- **Automatic revision on verification failure.** Report only; revision via the existing Phase 5 loop.

## Appendix

### B1. Verification prompt schema

```
You are a skeptical fact-checker. Compare the podcast script against the evidence map.
For each factual claim in the script (numbers, dates, quotes, names), check if the
evidence map supports it. Return ONLY a JSON array with entries:
- claim: the specific text from the script
- confidence: "high" if clearly missing, "medium" if ambiguous
- type: one of "number", "date", "quote", "name", "unattributed_expert"
- reason: brief justification
```

Example output:

```json
[
  { "claim": "2024", "confidence": "high", "type": "date",
    "reason": "Evidence mentions '90 countries' but no year" },
  { "claim": "experts say", "confidence": "medium", "type": "unattributed_expert",
    "reason": "Evidence names 3 sources; script uses vague attribution" }
]
```

---

### B2. Verification client (Z.ai / GLM-5.1)

GLM-5.1 (released April 2026, ~200K-token context, OpenAI-compatible Z.ai endpoint) is the
default verifier. Generation stays on MiniMax-M2.7; this client is used only for the
verification pass.

```python
import json
import os
import urllib.error
import urllib.request

_ZAI_API_KEY = os.environ.get("ZAI_API_KEY")
_ZAI_API_URL = "https://api.z.ai/api/paas/v4/chat/completions"


def call_verifier(system_prompt: str | None, user_prompt: str,
                  temperature: float = 0.2, timeout: int = 180) -> str:
    """Call the verification model (GLM-5.1) with optional system + user prompt."""
    if not _ZAI_API_KEY:
        raise RuntimeError("ZAI_API_KEY not set — verification skipped")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    payload = json.dumps({
        "model": "glm-5.1",
        "messages": messages,
        "temperature": temperature,
    }).encode("utf-8")

    req = urllib.request.Request(
        _ZAI_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_ZAI_API_KEY}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        choices = body.get("choices") or []
        if choices:
            return choices[0].get("message", {}).get("content", "").strip()
        raise RuntimeError(f"Unexpected verifier response: {body}")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Verifier API error {e.code}: {err_body}")
```

**Retry / failure:** retry once on transient errors; after the second failure, skip
verification for that episode with a warning (do not block the run).

---

### B3. Why an independent verifier (not a model "better at facts")

The verifier is deliberately a *different* model than the drafter. A model is poor at
catching its own fabrications — it tends to rate its own output as supported. Running the
check on a second model (GLM-5.1, while drafting stays on MiniMax-M2.7) decorrelates those
errors, so a fact the drafter invented is more likely to be caught. This is the only
defensible reason to introduce a second model; it does not rest on any claim that GLM-5.1 is
inherently better at extraction or facts. If a second API is undesirable, running the
verification on MiniMax with a fresh context is an acceptable, weaker fallback.

---

### B4. Current vs revised pipeline flow

**Current (all MiniMax, truncated):**
```
Transcript → text[:8000] → MiniMax extract_evidence → MiniMax outline
           → MiniMax draft_script → TTS
```

**Revised (full context + verification):**
```
Transcript → (full text, ~200K context) → MiniMax extract_evidence → MiniMax outline
           → MiniMax draft_script → independent verify (GLM-5.1) → TTS
```

**Key differences:**
1. Full context replaces the 8k-char truncation (no chunking needed).
2. Generation stays on MiniMax (one API, already wired).
3. An independent model verifies the draft against the evidence before TTS.
