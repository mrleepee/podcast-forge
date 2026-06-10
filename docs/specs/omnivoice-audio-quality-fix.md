# OmniVoice Audio-Quality Fix — Seam Artifacts, Reference Clip, Pronunciation

Implementation hand-off for Claude Code. Fixes the recurring "round sound" artifact
between words/sentences in OmniVoice-rendered episodes, hardens the voice-clone reference
handling that causes it, and adds a normalization rule for adjacent model-name numbers
(e.g. "Gemma 4 12B").

**Initiative:** Podcast quality upgrade — TTS output quality
**Status:** mostly implemented — Phases 1 & 3 shipped (PR #11, commit e424c69:
per-chunk trim + de-click fades, adjacent-number/tmux fixups). Phase 2
(`_validate_ref_clip`) and Phase 4 (seam-QC harness `checks/seam_qc.py`) shipped
in the pipeline-integrity initiative (P2.2). **Outstanding asset task:** re-cut the
reference clip per Appendix D (see `voice_ref/README.md`); the hard-fail guard
(`OMNIVOICE_REF_STRICT`) defaults off until then.
**Owner:** Claude Code
**Primary files:** `video_downloader.py`, `tts_omnivoice.py`, `tts-normalization-prompt.md`, `voice_ref/`
**Engine context:** OmniVoice (`k2-fsa/OmniVoice`) diffusion TTS, voice-cloning enabled, Apple-Silicon MPS. Migrated from Kokoro on 2026-06-03 (see `.claude/diary/2026-06-03-075819.md`).

---

## 1. Objective

Make chunk seams inaudible. Episodes are synthesized as many short chunks that are
concatenated; a faint round vowel/breath ("round sound") is audible at the joins —
between sentences, sometimes mid-flow. Eliminate it without changing the engine or the
cloned voice, and prevent the underlying reference-clip defect from recurring.

Three independent fixes, in priority order:

1. **Seam fix (Phase 1):** trim per-chunk leading/trailing near-silence and apply short
   fades before concatenation. Engine-agnostic; the highest-leverage change.
2. **Reference-clip hardening (Phase 2):** validate the clone reference at load, warn
   loudly when it ends mid-speech (the documented echo cause), and clean its edges.
3. **Pronunciation (Phase 3):** stop two adjacent numbers in a model name from binding
   ("Gemma four twelve billion" → "Gemma four, twelve billion").

Phase 4 is an optional QC harness to verify the artifact is gone.

---

## 2. Background and root cause

How the OmniVoice path works today (`video_downloader.py`):

- `_chunk_text(text, max_chars=600)` (~line 1525) splits the script into sentence-grouped chunks of ≤600 chars.
- `_generate_omnivoice_audio(...)` (~line 1683) builds a segment list and calls `_omnivoice_render(...)`.
- `_omnivoice_render(...)` (~line 1590) writes a JSON job and invokes the worker `tts_omnivoice.py` under the OmniVoice venv. The worker calls `model.generate(...)` **once per segment**, conditioned on the clone reference (`ref_audio` + `ref_text`), and saves one WAV per segment.
- Back in `_omnivoice_render`, each segment WAV is read with `soundfile`, appended to `parts`, and a fixed `0.12s` `np.zeros` silence is inserted **between** segments (multi-segment only). `np.concatenate(parts)` → tmp WAV → `libmp3lame` encode → `checks/master_audio.py` LUFS master.

**Why chunks exist (not removable):** OmniVoice is a diffusion model whose duration
estimate degrades on long inputs, and a whole-episode pass is heavy on 16 GB unified
memory. `_chunk_text`'s own docstring states this. Chunking is required; it is not the root
cause and must stay.

**Root cause of the artifact:**

1. **Reference-clip echo.** The diary documents that OmniVoice, given a reference clip,
   "echoes reference fragments into every chunk" when the clip and its `ref_text` are
   misaligned (their first clip leaked the word "fresh" into all 24 chunks of ep106). The
   current clip `voice_ref/senora_freedom_en_ref.wav` has the same defect — verified:

   - Duration 6.90 s, 24 kHz mono.
   - **No trailing silence:** the last ~0.7 s is speech running straight to the file end
     (cut mid-flow). `ffmpeg silencedetect` shows the final `silence_end` at 6.18 s with
     speech to 6.90 s.
   - `ref_text` = "Drop the debugging so it knows what to preserve. Then there is clear,
     which wipes everything, but you write down what matters." The audio does not end
     cleanly on "matters", so audio↔text is misaligned — exactly the echo condition.

   Because every chunk is conditioned on this clip, the leaked fragment surfaces at each
   chunk's onset → a round sound at every seam.

2. **Raw concatenation.** `_omnivoice_render` appends each segment WAV untrimmed. Diffusion
   onsets/offsets and any echoed fragment are preserved and stack at the joins; the fixed
   0.12 s silence does not mask them.

Fixing (1) removes the source; fixing (2) removes the residue and any generic diffusion
onset. Do both.

---

## 3. Requirements

| # | Trigger | Current behaviour | Expected behaviour | Verify |
|---|---|---|---|---|
| R1 | A multi-chunk episode is rendered | Segment WAVs are concatenated untrimmed; onset/echo artifacts stack at seams | Each segment's leading/trailing near-silence is trimmed (bounded) and short fades applied before concat; seams contain only the intended 0.12 s silence | Phase 1 tests + listen |
| R2 | OmniVoice clone reference is loaded | No validation; a clip that ends mid-speech silently causes per-chunk echo | At first render the reference is validated; if it ends mid-speech or `ref_text` looks misaligned, a loud actionable warning is logged; edges are cleaned at load | Phase 2 tests |
| R3 | A script names a model as version + size (e.g. "Gemma 4 12B" → "Gemma four twelve billion") | Two number words sit adjacent and bind ("four-twelve") | Version and size are separated by a comma so the numbers do not bind | Phase 3 tests + listen |
| R4 | Affected already-published episodes (ep119, and any rendered before the fix) | Contain the artifact / the "Gemma" binding | Re-rendered with the fixes; mastered to −16 LUFS; feed regenerated | Re-render runbook |
| R5 | A render completes | No way to confirm seams are clean | Optional QC: transcribe each segment, flag a recurring leaked token at segment starts; report seam-gap energy | Phase 4 (optional) |

---

## 4. Phases

### Phase 1 — Per-chunk trim + click-free concatenation  *(primary fix, R1)*

**Target:** `video_downloader.py`, function `_omnivoice_render` (~line 1590), specifically
the concat loop (~lines 1648–1666).

**Add** a module-level helper `_trim_segment_audio(wav, sr, ...)` (reference implementation
in Appendix A) and a few tunable constants near the other `_OMNI_*` constants (~line 1480):

```python
_OMNI_TRIM_DB       = float(os.environ.get("OMNIVOICE_TRIM_DB", "-40"))   # silence threshold
_OMNI_TRIM_KEEP_MS  = int(os.environ.get("OMNIVOICE_TRIM_KEEP_MS", "30")) # margin kept each side
_OMNI_TRIM_MAX_MS   = int(os.environ.get("OMNIVOICE_TRIM_MAX_MS", "300")) # never trim more than this per side
_OMNI_FADE_MS       = int(os.environ.get("OMNIVOICE_FADE_MS", "8"))       # de-click fade in/out
```

**Behaviour:**

- Given a rendered segment WAV, when it is read in `_omnivoice_render`, then leading and trailing samples below `_OMNI_TRIM_DB` are removed, keeping `_OMNI_TRIM_KEEP_MS` of margin and trimming at most `_OMNI_TRIM_MAX_MS` per side (never eat real speech onsets).
- Given a trimmed segment, when it is appended, then an `_OMNI_FADE_MS` linear fade-in and fade-out is applied to prevent concatenation clicks.
- Given a segment that is entirely below threshold (pathological), when trimmed, then it is dropped (length 0) rather than contributing noise.
- Given the inter-segment gap, when concatenating, then the existing `0.12 s` silence is preserved (do not remove it; it provides natural sentence spacing).

**Edit sketch** (replace the per-segment append in the concat loop):

```python
sr = status.get("sample_rate", 24000)
silence = np.zeros(int(silence_sec * sr))
parts = []
multi = len(job_segments) > 1
for seg in job_segments:
    wav, _ = sf.read(seg["out_wav"])
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    wav = _trim_segment_audio(
        wav, sr,
        thresh_db=_OMNI_TRIM_DB, keep_ms=_OMNI_TRIM_KEEP_MS,
        max_trim_ms=_OMNI_TRIM_MAX_MS, fade_ms=_OMNI_FADE_MS,
    )
    if wav.size == 0:
        continue
    parts.append(wav)
    if multi:
        parts.append(silence)
if parts and multi and len(parts) > 1:
    parts = parts[:-1]   # drop trailing silence after the last segment
full = np.concatenate(parts) if parts else np.zeros(0)
```

**Verification:**

| Input | Expected output |
|---|---|
| Unit: array `[0]*sr*0.4 + sine(0.5s) + [0]*sr*0.4` | Returned length ≈ 0.5 s + 2×keep, peaks unchanged, faded edges |
| Unit: all-zeros array | Returns length 0 |
| Unit: full-energy array (no silence) | Length unchanged (minus none), fades applied |
| Unit: leading silence 2 s | Trims at most `_OMNI_TRIM_MAX_MS`, not the full 2 s |
| Integration: 3 stub WAVs each padded with 0.3 s silence both ends | Concatenated length ≈ Σ(trimmed) + 2×0.12 s; RMS inside each 0.12 s gap < −60 dB |

**Not in scope:** crossfading across the silence (straight cut + fades is enough); resampling.

---

### Phase 2 — Reference-clip validation and clean edges  *(R2)*

**Target:** `video_downloader.py`, reference-clip constants block (~lines 1486–1500) plus a
new `_validate_ref_clip(...)` helper (Appendix B), invoked once before the first render.

**Behaviour:**

- Given `_OMNI_REF_AUDIO` is set, when the pipeline first renders, then `_validate_ref_clip` runs and prints warnings (does not abort).
- Given the reference ends with less than `150 ms` of trailing silence, then a loud warning is logged: `"ref clip ends mid-speech (Nms trailing) — RE-CUT; this causes per-chunk echo"`.
- Given `_OMNI_REF_TEXT` is empty/short, or the words-per-second implied by `ref_text` vs clip duration is outside ~1.5–5.0, then a warning recommends verifying the transcript matches the audio exactly.
- Given the reference passes validation, then a cleaned copy with trimmed silent edges is written next to it (`*_clean.wav`) and used as the effective `ref_audio` for the run. (Trimming the reference's own edges further reduces what can be echoed.)

**Wiring:** compute warnings once (guard with a module flag so it prints once per process),
e.g. at the top of `_omnivoice_render` before building the job. If a `*_clean.wav` is
produced, set `job["ref_audio"]` to it.

**Verification:**

| Input | Expected output |
|---|---|
| Current `voice_ref/senora_freedom_en_ref.wav` | Warning: "ends mid-speech (~0 ms trailing) — RE-CUT" |
| Synthetic clip: speech + 200 ms trailing silence + matching ref_text | No warnings; `*_clean.wav` written |
| Empty `ref_text` | Warning: "ref_text missing/short — required for clean cloning" |

**Not in scope:** automatically choosing a new reference moment — that needs a human listen
(see Appendix D runbook). This phase validates, warns, and cleans edges only.

---

### Phase 3 — Adjacent-number pronunciation normalization  *(R3)*

Two parts — a prompt rule (primary) and a deterministic safety net.

**3a. Normalization prompt rule.** Edit `tts-normalization-prompt.md`: add a rule that when a
product or model name contains a version number immediately followed by a size or parameter
count, the two are separated with a comma (or rephrased) so two numbers never sit adjacent.
Example: `Gemma 4 12B` → `Gemma four, twelve billion parameters`.

**3b. Deterministic safety net.** In `video_downloader.py`, extend `_omnivoice_fixups`
(~line 1554). Add a regex that inserts a comma between two consecutive spelled number-words
when the second begins a magnitude phrase (Appendix C). Conservative — must not fire on
"two hundred thousand" (where the middle token is a magnitude, not a unit/teens/tens word).

**Behaviour:**

- Given "Gemma four twelve billion parameters", when fixups run, then it becomes "Gemma four, twelve billion parameters".
- Given "two hundred thousand children", when fixups run, then it is unchanged.
- Given "twelve billion dollars", when fixups run, then it is unchanged (single number).

**Also:** fix the published `ep119` text (`…/audio/ep119-…podcast.txt`) line "Gemma four
twelve billion" → "Gemma four, twelve billion" in both occurrences, then re-render (Phase/
Appendix E).

**Verification:**

| Input | Output |
|---|---|
| "Gemma four twelve billion" | "Gemma four, twelve billion" |
| "GPT four one hundred" | "GPT four, one hundred" |
| "two hundred thousand" | "two hundred thousand" (unchanged) |
| "in twenty twenty-six" (year) | unchanged |

> Watch the year edge case: "twenty twenty-six" must not get a comma. The regex only fires
> when the second number is followed by a magnitude word (billion/million/thousand/
> trillion), which years are not — so years are safe. Add the year case to the tests.

---

### Phase 4 — Seam-artifact QC harness  *(optional, R5)*

A standalone script (runs under the OmniVoice venv, which already bundles `whisperx`) that,
given an episode's segment WAVs, transcribes each and flags a token that recurs at the start
of ≥ 30% of segments (the echo signature), and reports peak energy inside each inter-segment
gap. Use during verification of a render, not in the hot path.

**Verification:** on a known-bad render (current ref clip) it flags the leaked token; on a
fixed render it reports none and gap energy < −60 dB.

**Not in scope:** wiring this into `checks/run.py` (it needs the OmniVoice venv + whisperx,
which the podcast-forge venv does not have).

---

## 5. Constraints

- **Keep chunking.** It is required by OmniVoice (duration estimate + memory). Do not remove `_chunk_text`.
- **Keep the cloned voice and the engine default.** Do not switch back to Kokoro or to instruct mode. `TTS_ENGINE=kokoro` and `OMNIVOICE_REF_AUDIO=""` remain the documented escape hatches.
- **All new behaviour is configurable** via the `_OMNI_*` env constants, with the defaults above.
- **No new external dependencies** in the podcast-forge venv (NumPy/soundfile already present). Phase 4's whisperx runs only in the OmniVoice venv.
- **Master step unchanged.** `checks/master_audio.py` still runs after encode; trimming changes content, not loudness targets.
- **Idempotent re-render.** Re-rendering an episode must overwrite cleanly and re-master to −16 LUFS.

## 6. Not in scope

- Editorial rewrite of ep119's content (the "weak episode" / Gemma angle) — that is separate content work, not this code change.
- Changing chunk size as the primary fix (it is a secondary tuning lever; see below).
- The evidence-first / verification pipeline work (separate spec).

## 7. Definition of Done

1. `_trim_segment_audio` implemented with unit tests (Appendix F) passing.
2. `_omnivoice_render` trims + fades each segment; integration test confirms gap energy < −60 dB and correct total length.
3. `_validate_ref_clip` implemented; running the pipeline with the current reference prints the "ends mid-speech — RE-CUT" warning; with a clean clip it is silent.
4. Normalization prompt rule added; `_omnivoice_fixups` safety net implemented with tests (including the year and "two hundred thousand" negatives).
5. A clean reference clip produced per Appendix D (human listen), with matching `ref_text`; validation passes.
6. ep119 (and any episodes rendered before the fix) re-rendered per Appendix E; a listen confirms the round sounds are gone and "Gemma four, twelve billion" reads correctly; LUFS summary verified before publish.
7. Stale comments at `video_downloader.py` ~1476–1480 corrected (cloning IS wired; speed default is 0.9).

---

## Appendix A — `_trim_segment_audio` reference implementation

```python
import numpy as np

def _trim_segment_audio(wav, sr, *, thresh_db=-40.0, keep_ms=30,
                        max_trim_ms=300, fade_ms=8):
    """Trim leading/trailing near-silence (bounded) and apply de-click fades.

    wav: 1-D float array in [-1, 1]. Returns a (possibly shorter) 1-D array.
    Never trims more than max_trim_ms per side, so real soft onsets survive.
    """
    if wav.size == 0:
        return wav
    amp = np.abs(wav)
    thresh = 10.0 ** (thresh_db / 20.0)          # dBFS -> linear
    above = np.flatnonzero(amp > thresh)
    if above.size == 0:
        return wav[:0]                            # all silence -> drop

    keep = int(keep_ms * sr / 1000)
    max_trim = int(max_trim_ms * sr / 1000)

    lead_sil = int(above[0])
    trail_sil = int(wav.size - (above[-1] + 1))
    trim_lead = min(max(0, lead_sil - keep), max_trim)
    trim_trail = min(max(0, trail_sil - keep), max_trim)

    seg = wav[trim_lead: wav.size - trim_trail].copy()

    f = int(fade_ms * sr / 1000)
    if f > 0 and seg.size > 2 * f:
        ramp = np.linspace(0.0, 1.0, f, dtype=seg.dtype)
        seg[:f] *= ramp
        seg[-f:] *= ramp[::-1]
    return seg
```

## Appendix B — `_validate_ref_clip` reference implementation

```python
def _validate_ref_clip(path, ref_text, *, sr_expected=24000, min_trailing_ms=150):
    """Return a list of human-readable warnings ([] == clean)."""
    import numpy as np, soundfile as sf
    warns = []
    try:
        wav, sr = sf.read(path)
    except Exception as e:
        return [f"could not read ref clip {path}: {e}"]
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    if sr != sr_expected:
        warns.append(f"ref sample rate {sr} != expected {sr_expected}")
    amp = np.abs(wav); thr = 10.0 ** (-40.0 / 20.0)
    above = np.flatnonzero(amp > thr)
    if above.size == 0:
        return warns + ["ref clip is silent"]
    trailing_ms = (wav.size - (above[-1] + 1)) / sr * 1000.0
    if trailing_ms < min_trailing_ms:
        warns.append(
            f"ref clip ends mid-speech ({trailing_ms:.0f}ms trailing silence; "
            f"need >= {min_trailing_ms}ms) -- RE-CUT the clip; this causes per-chunk echo")
    if not ref_text or len(ref_text.split()) < 3:
        warns.append("ref_text missing/too short -- required for clean cloning")
    else:
        dur = wav.size / sr
        wps = len(ref_text.split()) / dur if dur > 0 else 0.0
        if not (1.5 <= wps <= 5.0):
            warns.append(
                f"ref_text/clip length mismatch ({wps:.1f} words/sec) -- "
                f"verify the transcript matches the audio exactly")
    return warns
```

Call once (guarded by a module-level `_REF_VALIDATED` flag) at the top of `_omnivoice_render`
when `_OMNI_REF_AUDIO` is set; `print("  [ref] " + w)` each warning.

## Appendix C — pronunciation fixup

```python
_NUM_WORD = (r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
             r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
             r"thirty|forty|fifty|sixty|seventy|eighty|ninety|\d+)"
             r"(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?")
_MAGNITUDE = r"(?:billion|million|thousand|trillion)"

_RE_ADJ_NUM = re.compile(
    rf"\b({_NUM_WORD})\s+({_NUM_WORD}\s+{_MAGNITUDE})\b", re.IGNORECASE)

_OMNI_TEXT_FIXUPS = [
    ("tmux", "tee-mux"),
]

def _omnivoice_fixups(text):
    for needle, repl in _OMNI_TEXT_FIXUPS:
        text = re.sub(rf"\b{re.escape(needle)}\b", repl, text)
    # Separate a version number from an immediately-following size, so two
    # numbers don't bind ("Gemma four twelve billion" -> "Gemma four, twelve billion").
    text = _RE_ADJ_NUM.sub(r"\1, \2", text)
    return text
```

Negative cases the tests must cover: "two hundred thousand" (middle token is a magnitude, so
the first group is "two" and the second would need to be "hundred … magnitude" — does not
match), "twenty twenty-six" (no magnitude follows), "twelve billion" alone (only one number).

## Appendix D — Reference-clip re-cut runbook (human step)

The reference defines the cloned voice for every episode, so cut it carefully:

1. Pick a 5–10 s span of the locked Señora voice that is a **complete sentence**, with a
   natural pause (silence) before and after. Avoid spans cut mid-word or mid-phrase.
2. Export 24 kHz mono WAV. Ensure ≥ 150 ms of silence at the **end** (and a little at the
   start). `ffmpeg -af silencedetect=noise=-40dB:d=0.1` should show trailing silence.
3. Write the **exact** transcript to the sibling `.txt` (`voice_ref/<name>.txt`), matching
   the words spoken in the clip — no missing or extra words at the boundaries.
4. Point `OMNIVOICE_REF_AUDIO` (or `_OMNI_REF_DEFAULT`) at the new clip. Run the pipeline;
   `_validate_ref_clip` must print no warnings.
5. Render one multi-chunk test episode and listen at the seams (and run Phase 4 QC).

## Appendix E — Re-render affected episodes

- Driver: `rerender_omnivoice.py` (overwrites already-published mp3s, re-masters to −16 LUFS).
- Run it as a **background Bash job** (PID-waiter), not a subagent — the 2026-06-03 diary
  notes a monitoring subagent relaunched killed renders and corrupted audio. `pkill` by name
  if needed; a detached render survives its launcher.
- Throughput: ~14 min/episode for EN+ES on MPS. Sequential only (one model load; parallel
  MPS jobs OOM on 16 GB).
- After re-render: regenerate the feed (`generate_rss.py` invocation referenced in
  `video_downloader.py` ~L2411), verify the LUFS summary, then commit+push the publish repo
  (`~/Dev/freeist-podcast`).
- Episodes to re-render: ep119 (Gemma), plus any episode rendered before this fix lands that
  still exhibits the seam artifact.

## Appendix F — Test plan

Add `tests/test_omnivoice_audio.py` (podcast-forge venv; NumPy + soundfile only — does **not**
import `video_downloader` top-level if that pulls heavy deps; import the helpers directly or
guard with the existing pattern):

- `test_trim_removes_padding`: 0.4 s silence + 0.5 s tone + 0.4 s silence → length ≈ 0.5 s + 2×keep; interior peak preserved.
- `test_trim_all_silence_drops`: zeros → size 0.
- `test_trim_caps_at_max`: 2 s leading silence → trims ≤ `max_trim_ms`.
- `test_trim_applies_fades`: first/last `fade_ms` samples are monotonic ramps; no full-scale discontinuity.
- `test_render_gap_energy` (integration, stubbed worker output): 3 padded stub WAVs → concatenated; RMS within each 0.12 s gap < −60 dB; total length within tolerance.
- `test_ref_validation_flags_bad_clip`: synthetic clip ending mid-speech → warning present; clip with trailing silence → none.
- `test_fixup_separates_version_size`: "Gemma four twelve billion" → comma inserted.
- `test_fixup_negatives`: "two hundred thousand", "twenty twenty-six", "twelve billion" → unchanged.

Manual listen checklist (after a real render):

- [ ] No round vowel/breath at sentence joins.
- [ ] No recurring leaked word at chunk starts (cross-check Phase 4 QC).
- [ ] "Gemma four, twelve billion" reads as two distinct numbers.
- [ ] Pacing/voice unchanged vs. the locked timbre; LUFS ≈ −16.

## Appendix G — Config / env summary

| Env var | Default | Meaning |
|---|---|---|
| `OMNIVOICE_TRIM_DB` | `-40` | silence threshold for per-chunk trim |
| `OMNIVOICE_TRIM_KEEP_MS` | `30` | margin kept each side after trim |
| `OMNIVOICE_TRIM_MAX_MS` | `300` | max trim per side (protects soft onsets) |
| `OMNIVOICE_FADE_MS` | `8` | de-click fade in/out per segment |
| `OMNIVOICE_REF_AUDIO` | `voice_ref/senora_freedom_en_ref.wav` | clone reference (`""` → instruct mode) |
| `OMNIVOICE_SPEED` | `0.9` | speech pace |
| `TTS_ENGINE` | `omnivoice` | `kokoro` selects the legacy path |
