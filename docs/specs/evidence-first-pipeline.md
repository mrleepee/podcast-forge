# Evidence-First Pipeline — Implementation Spec

Replaces the current summary-first pipeline (transcript → bullet summary → narration)
with a multi-stage evidence-first pipeline where each stage has a focused agent,
produces a checkable artifact, and the script is written from evidence — not from
a compressed summary.

**Initiative:** Podcast quality upgrade — pipeline refactor
**Status:** review fixes applied — critical findings #1 #2 #3 #5 resolved, pending end-to-end validation
**Branch:** `feature/evidence-first-pipeline`

## Requirements

| # | User input / trigger | Current behaviour | Expected behaviour | Verified |
|---|---|---|---|---|
| R1 | A YouTube URL with a 25-minute interview | The summary step asks for "concise bullet points" — claims, quotes, timestamps, and qualifiers are discarded before the narration is written. | The transcript is first converted to an evidence map: a JSON array where each entry has `claim`, `source_quote`, `timestamp` (offset or paragraph anchor), `source_reliability` (primary/secondary/hearsay), `confidence` (high/medium/low), and `type` (fact/opinion/prediction/statistic). The script is written from this evidence map, not from a loose summary. | Observed 2026-05-31: summaries discard specific numbers and named sources that the transcript contains. |
| R3 | The narration prompt receives a flat summary and generates prose in one shot | The outline and thesis are implicit — no artefact exists to inspect. | Before prose, the pipeline generates a thesis and outline (hook → stakes → evidence beats → counterpoint → implication → close). The outline persists. The script is written against the outline, not directly against the raw evidence. | SOUL.md defines "one central thesis" but no step enforces it. |
| R4 | A narration script that fails content QA | There is no revision loop — the audio is generated as-is. | After content QA fails, the pipeline revises only the script, re-runs QA, and loops until pass or max 3 revisions. Earlier stages are not re-run. | Quality checks exist (PR #3) but no revision loop. |
| R5 | An episode produced on the new pipeline vs the old pipeline | No way to compare pipeline output or roll back. | The new pipeline coexists with the old. The new path is selected via parameter. The old path remains the default. The new path becomes default after 5 consecutive episodes pass all quality checks. | Safe rollout needed — can't break existing production. |
| R6 | A developer inspects an episode's production artifacts | Only the summary, narration text, and audio are saved. | Each stage's output is written as a human-readable artifact: evidence map JSON, outline markdown, script text, and quality report JSON. | Current pipeline saves only summary + narration text + audio. |

## Phases

### Phase 1 — Pipeline scaffolding and flag [done]

**Status:** done
**Fixes:** R5 (partial), R6 (partial)

#### Behaviour

- Given a request to produce a podcast with the evidence-first flag set, when the pipeline starts, then the new multi-stage path is selected. When the flag is not set, the existing summary-first path runs unchanged.
- Given the evidence-first path, when any stage completes, then its output artifact is written to the episode directory before the next stage begins.
- Given a stage failure on the evidence-first path, when the error is reported, then the error message names the failed stage and the path to the last successfully written artifact.

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| Evidence-first flag + valid source | New pipeline runs, artifact files appear in episode directory | |
| No flag (default) | Old pipeline runs, no new artifacts | |
| Evidence-first flag + stage 2 failure | Error: "outline generation failed", evidence_map.json exists on disk | |

#### Not in scope

- Removing the old pipeline.
- CLI `--evidence-first` flag (wired through the `produce_podcast` parameter for now).

### Phase 2 — Evidence extraction agent [done]

**Status:** done
**Fixes:** R1

#### Behaviour

- Given a transcript of at least 100 words containing specific claims, numbers, named sources, and quotes, when evidence extraction runs, then the output is a JSON array where each entry contains: `claim` (string), `source_quote` (the original text), `timestamp` (paragraph index or time offset from the source), `source_reliability` (one of: primary, secondary, hearsay), `confidence` (one of: high, medium, low), and `type` (one of: fact, opinion, prediction, statistic).
- Given a transcript containing the sentence "By 2024, ninety countries were piloting CBDCs — a currency that watches you spend it", when evidence extraction runs, then at least one entry has `claim` containing "90 countries piloting CBDCs" and `source_quote` preserving the original sentence.
- Given a transcript with at least 3 named entities and 5 specific numbers, when evidence extraction runs, then all named entities and numbers appear in at least one evidence entry's `claim` or `source_quote`.
- Given source material that is empty or fewer than 100 words, when evidence extraction runs, then the pipeline stops with a clear message: "not enough source material to extract evidence (received N words, need ≥100)".

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| Fixture: `checks/fixtures/good/liberland-meritocracy.txt` (~200 words) | JSON array with ≥5 entries, each with all 6 required fields | |
| Fixture: `checks/fixtures/bad/short-source.txt` (50 words) | Pipeline stops: "not enough source material (received 50 words, need ≥100)" | |
| Fixture: transcript containing "2024", "Liberland", "Jedlicka", "13 April", "7 square kilometres" | All 5 values appear across entries | |

#### Not in scope

- Evidence verification (checking if claims are actually true).
- Multi-source evidence fusion (combining evidence from multiple transcripts).

### Phase 3 — Thesis and outline agent [done]

**Status:** done
**Fixes:** R3

#### Behaviour

- Given an evidence map with at least 5 entries and the SOUL.md show bible, when outline generation runs, then the output contains: `thesis` (one sentence), `hook` (the opening strategy), `stakes` (why the listener should care), `evidence_beats` (array referencing specific evidence entries), `counterpoint` (the opposing view), `implication` (what it means), and `close` (the ending strategy).
- Given an evidence map with 2–4 entries, when outline generation runs, then the output still contains all 7 required fields but includes a `warnings` array with the entry `"thin evidence: only N claims available"`.
- Given the SOUL.md persona, when the outline includes a claim contradicting the persona, then the output's `warnings` array includes `"persona_tension: <description>"`.

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| Fixture: evidence map with 15 entries from liberland transcript | Outline JSON with all 7 fields, no warnings | |
| Fixture: evidence map with 2 entries | Outline JSON with all 7 fields, warnings includes "thin evidence" | |

#### Not in scope

- Multiple outline candidates (the quality spec recommends 3; this generates 1).
- Automated angle selection between multiple outlines.

### Phase 4 — Script drafting from outline + evidence [done]

**Status:** done
**Fixes:** R1, R3

#### Behaviour

- Given an outline and evidence map, when script drafting runs, then the output is a narration script in the show's established style: British English, conversational, plain text paragraphs, no markdown, no bullet points, direct entry into the topic.
- Given a script draft containing a specific number (e.g., "2024") that does not appear in any evidence entry's `claim` or `source_quote`, when traceability checking runs, then a warning is emitted: "untraceable number: 2024".
- Given a duo episode, when script drafting runs, then the output uses two-speaker dialogue with Host and Co-host labels, complete sentences, and no fragments or echo lines.

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| Outline + 15 evidence entries | Script with ≥6 specific numbers, ≥2 named sources, zero filler phrases (per substance check denylist) | |
| Outline + 2 evidence entries (thin) | Script that acknowledges uncertainty, zero numbers not in the evidence | |
| Duo outline + evidence | Dialogue text passing the dialogue check (terminal punctuation, ≥4 words per turn, <50% token overlap) | |

#### Not in scope

- Replacing the existing narration prompt (it is adapted, not replaced).

### Phase 5 — Revision loop with content QA [done]

**Status:** done
**Fixes:** R4

#### Behaviour

- Given a script draft that fails the substance check (filler phrases detected), when the revision loop runs, then the script is revised with the QA feedback appended as additional instructions, the evidence map and outline are not re-generated, and QA is re-run on the revised script.
- Given a script that fails QA on 3 consecutive revision attempts, when the loop exhausts, then the pipeline proceeds with the best draft and flags it in the quality report as `qa_exhausted: true`.
- Given a script that passes content QA on the first attempt, when the revision loop checks, then no revision occurs and the pipeline proceeds to TTS.

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| Fixture: script containing "experts say" | After 1 revision, filler removed, substance check passes | |
| Fixture: script where every revision reintroduces a filler phrase | After 3 revisions, `qa_exhausted: true` in quality report | |
| Fixture: clean script with numbers and named sources | Zero revisions, quality report shows all checks passed | |

#### Not in scope

- Re-running evidence extraction or outline on QA failure.
- Human-in-the-loop revision approval.

## Constraints

- **Coexist with old pipeline.** The flag selects the path. Default is unchanged.
- **~150-200 lines per phase.** Each phase is independently reviewable.
- **One branch per phase.** Each phase merges independently.
- **MiniMax for all LLM stages.** No new API dependencies.
- **No paid APIs.** Same constraint as the rest of the project.
- **Kokoro stays.** TTS engine is not changing.
- **Quality checks apply to both pipelines.** The checks from PR #3 run after script generation regardless of pipeline path.
- **Each stage persists its artifact.** The stage that produces an artifact writes it to disk. No retroactive persistence.

## Not In Scope

- **Source pack enforcement for topic episodes:** Requiring minimum source counts before extraction begins is a production workflow change (the producing agent or `/podcast` skill), not a pipeline change. Topic episodes receive whatever summary or research the agent provides; the evidence extraction stage handles it.
- **Multiple outline candidates:** The quality spec recommends generating 3 outlines and selecting the best. This generates 1. Multi-outline selection can be added later.
- **LLM judge integration:** The checks from PR #3 are deterministic. The LLM judge contract is not wired in this refactor.
- **Claim verification:** Checking if claims are factually true is out of scope — the pipeline preserves evidence traceability, not truth.
- **Human-in-the-loop approval between stages:** Each stage runs automatically. A human can inspect artifacts after production.
- **Default switch after 5 episodes:** The rollout condition (5 consecutive passing episodes) is a manual operational decision, not an automated counter. The default changes when the operator changes it.

## Appendix

### A1. Current pipeline flow (being replaced)

```
Transcript → _summarize_with_minimax("concise bullet points") → summary.md
         → _narrate_as_podcast(summary_text) → narration.txt
         → _polish_for_tts(narration) → polished.txt
         → Kokoro TTS → MP3
```

Evidence loss happens at the summary step. The summarisation prompt asks for "concise
key points" which discards quotes, timestamps, qualifiers, and source reliability.

### A2. New pipeline flow

```
Source material → extract evidence → evidence_map.json
               → generate outline → outline.md
               → draft script → script.txt
               → content QA → if fail, revise script (loop max 3)
               → TTS polish → pronunciation + audio synthesis
               → quality gate (loudness, mastering) → publish gate
```

### A3. Stage prompts

Each stage has a focused system prompt:

- **Stage 2 (Extraction):** "You are a forensic evidence analyst. Extract every factual claim, statistic, named source, and specific number from the transcript. For each claim, preserve the original quote, note the paragraph or timestamp, and classify source reliability and confidence."
- **Stage 3 (Outline):** "You are a podcast editor. Given these claims and the show bible SOUL.md, choose the strongest angle for a 5-minute episode. Structure: thesis → hook → stakes → evidence beats → counterpoint → implication → close."
- **Stage 4 (Script):** Adapted from the existing narration prompt. Input is outline + evidence map instead of flat summary. Additional instruction: "Every factual claim must be traceable to the evidence. Do not introduce facts not in the evidence map."

### A4. Build order

`Phase 1 (scaffolding) → Phase 2 (evidence) → Phase 3 (outline) → Phase 4 (script) → Phase 5 (revision loop).`

Phase 1 establishes the flag and artifact contract first so every subsequent phase
persists its own output as it goes, rather than retroactively saving artifacts at the end.

### A5. Codex review findings (incorporated)

Seven findings from Codex review (2026-05-31), all addressed:

1. **R2 orphaned** → Moved R2 to Not In Scope with clear justification (workflow change, not pipeline change)
2. **Evidence schema mismatch** → Phase 2 now includes all 6 fields: `claim`, `source_quote`, `timestamp`, `source_reliability`, `confidence`, `type`
3. **Artifact naming inconsistency** → Collapsed to single `evidence_map.json`; removed `claim_ledger.json` ambiguity
4. **Verification rows not runnable** → Added fixture references (`checks/fixtures/...`) and concrete rules
5. **Implementation details in phases** → Removed function names, parameters, and internal flags from behaviour sections
6. **Phase 5 overloaded** → Split: Phase 1 now handles scaffolding + artifact contract; each subsequent phase persists its own output
7. **Empty-source conflict** → Unified: under 100 words → "not enough source material" (stops pipeline)
