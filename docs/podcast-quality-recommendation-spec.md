# Highest-Quality Podcast Production - Recommendation Spec

This spec recommends how to move `podcast-forge` from a useful automated video-to-podcast pipeline to a release-grade production pipeline optimized for editorial quality, factual reliability, voice consistency, and mastered audio. Status: draft.

**Initiative:** Podcast quality upgrade
**Status:** draft
**Primary recommendation:** Treat the current pipeline as a fast draft generator. For release-quality episodes, add evidence-first content production, scripted editorial QA, free/local TTS profiles, deterministic voice settings, segment-level retries, and objective loudness/mastering checks before publish.

## Recommendation Summary

- **Content:** Stop going directly from transcript summary to narration. Build every episode from a source pack, claim ledger, editorial outline, script draft, and critic pass.
- **Voice:** Keep `SOUL.md` as the show bible, but convert it into scored acceptance checks: named sources, specific numbers/dates, clear thesis, no unverified claims, and no cliché openings/closings.
- **TTS:** Do not use paid TTS. Keep Kokoro as the deterministic baseline, evaluate stronger free/local engines for final masters, and select the best local voice by blind A/B tests.
- **Audio:** Generate segment WAVs first, retry weak segments, then master once to podcast loudness targets. Do not publish raw concatenated TTS output.
- **Publishing:** Publish only when a quality report proves content checks, pronunciation checks, loudness checks, duration checks, and metadata checks passed.

## Requirements

| # | User input | Current behaviour | Expected behaviour | Verified |
|---|---|---|---|---|
| R1 | `python video_downloader.py URL --podcast` | Downloads captions or runs local Whisper `base`, then summarizes the transcript into bullet points. | The ingest step preserves transcript text, source URL, title, date, author/channel, and timecodes or paragraph anchors. | Code review: `video_downloader.py:1049`, `video_downloader.py:1058`, `video_downloader.py:1089`, `video_downloader.py:2232` |
| R2 | A YouTube interview with specific factual claims | The summarizer asks for concise key points and can discard evidence, qualifiers, and timestamps. | The first model output is an evidence map: claims, supporting quote/timecode, source reliability, and uncertainty. | Code review: `video_downloader.py:1100` |
| R3 | A research episode from the backlog, e.g. "The History of Taxation" | There is no first-class multi-source research workflow; the podcast path expects a video transcript or summary file. | Topic episodes require a source pack with at least three credible sources, dated citations, and a claim ledger before scripting. | Code review: `podcast-backlog.md:28`, `video_downloader.py:2232` |
| R4 | A short-form episode | Target length is calculated from source duration with a fixed 1:10 compression ratio, floor, and cap. | Target length is selected by episode type: brief reaction, explainer, research deep dive, interview digest, or language-learning episode. | Code review: `video_downloader.py:1164` |
| R5 | Solo episode script | The narration prompt produces conversational prose from the summary and appends `SOUL.md`. | The script must pass a rubric for hook, thesis, structure, evidence, persona fit, listener stakes, and legal/financial caveats. | Code review: `video_downloader.py:1177`, `SOUL.md:39`, `SOUL.md:55` |
| R6 | Two-host episode script | The dialogue prompt has strong craft guidance for flat-prosody TTS. | The dialogue must also pass an automated script critic that rejects fake banter, repeated lines, unresolved hooks, weak co-host roles, and unsupported claims. | Code review: `two-host-dialogue-craft-prompt.md:17`, `two-host-dialogue-craft-prompt.md:175` |
| R7 | Spanish/bilingual output | Spanish output is mixed with a language-learning EN/ES format and bypasses full TTS polishing. | Spanish podcast, bilingual learning episode, and English episode are explicit content products with separate rubrics and acceptance checks. | Code review: `video_downloader.py:1247`, `video_downloader.py:1381`, `video_downloader.py:2043` |
| R8 | English TTS | Kokoro generates the final MP3 with a random British voice. | Release TTS uses a locked free/local host voice, engine, model, speed, style settings, and reproducible version metadata. | Code review: `video_downloader.py:1461`, `video_downloader.py:1672` |
| R9 | Two-host TTS | Duo mode randomly chooses one female and one male Kokoro voice per run. | Host and co-host voices are stable across episodes unless an explicit voice change is approved. | Code review: `video_downloader.py:1511`, `video_downloader.py:1516` |
| R10 | Technical terms and acronyms | The repo has a strong normalization prompt and pronunciation cache, but pronunciation checks are not an explicit publish gate. | Every episode has a pronunciation manifest, audition clip, and retry loop for names, acronyms, brands, currencies, and jurisdictions. | Code review: `tts-normalization-prompt.md:17`, `pronunciation_db.py:140`, `pronunciation_db.py:242` |
| R11 | Audio generation | The system concatenates TTS chunks and encodes to MP3 with simple `ffmpeg` settings and optional tempo changes. | The system generates segment WAVs, inserts measured pauses, masters loudness/true peak, and exports a final RSS-safe audio file. | Code review: `video_downloader.py:1533`, `video_downloader.py:1716`, `tts_summary.py:150` |
| R12 | Publish workflow | The pipeline checks duplicate similarity and sponsored-content risk, then can publish. | Publish is blocked unless content QA, TTS QA, audio metrics, metadata, and episode archive artifacts all pass. | Code review: `video_downloader.py:1829`, `video_downloader.py:1898`, `video_downloader.py:1965` |

## Recommended Target Pipeline

1. **Ingest:** Capture source media, transcript, title, author/channel, source date, URL, language, and time-aligned transcript anchors.
2. **Evidence map:** Extract claims, quotes, numbers, dates, named entities, and uncertainty from the source material.
3. **Research pack:** For research episodes, gather additional sources before any script writing.
4. **Angle selection:** Produce three possible episode theses, then select one based on novelty, listener stakes, and fit with `SOUL.md`.
5. **Outline:** Generate a story arc: hook, stakes, evidence beats, counterpoint, implication, close.
6. **Script:** Write either solo narration or two-host dialogue against the outline, not directly against the raw summary.
7. **Content QA:** Run a critic pass and revise until all required checks pass.
8. **TTS normalization:** Normalize only the approved script, preserving speaker labels and meaning.
9. **Pronunciation prep:** Build a pronunciation manifest and generate a short audition clip before full synthesis.
10. **Segment synthesis:** Generate each paragraph or turn as its own WAV with stable voice settings.
11. **Audio QA:** Detect clipping, silence, duration mismatch, failed words, loudness, and true peak.
12. **Master/export:** Produce final AAC or MP3 plus a quality report, transcript, show notes, and RSS metadata.

## Phases

### Phase 1 - Evidence-First Ingest

**Status:** not started
**Ticket:** none
**Fixes:** R1, R2, R3

#### Behaviour

- Given a URL episode, when the source is ingested, then the system stores source URL, title, author/channel, source date when available, transcript language, transcript provenance, and transcript anchors.
- Given a transcript line with a timestamp, when evidence is extracted, then the claim ledger links the claim back to the nearest timestamp or paragraph anchor.
- Given a topic-only episode, when production starts, then the system refuses to script until a source pack exists.
- Given a source pack, when it contains fewer than three credible sources for a research episode, then the system marks the episode as `research_incomplete`.

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| One YouTube URL with captions | Source record, transcript text, transcript provenance, time anchors | |
| One research topic with no URLs | `research_incomplete` and no script | |
| One article, one video, one report | Source pack with dated citations and extractable claim ledger | |

#### Not in scope

- Legal clearance for reusing source material.
- Fully automated source credibility scoring.

### Phase 2 - Editorial Script Engine

**Status:** not started
**Ticket:** none
**Fixes:** R4, R5, R6, R7

#### Behaviour

- Given an evidence map, when the system drafts an episode, then it first creates a thesis and outline before writing prose.
- Given a solo episode, when the first script draft is generated, then it opens with a concrete hook and states the central tension within the first thirty seconds.
- Given a two-host episode, when the first script draft is generated, then each host has a stable role and every turn is a complete sentence.
- Given a research episode, when the script makes a factual claim, then the claim is either traceable to the claim ledger or explicitly framed as interpretation.
- Given a legal, tax, investment, residency, or medical topic, when the script reaches an advice-like section, then it includes a clear non-personalized analysis boundary without weakening the thesis.

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| "The History of Taxation" source pack | Outline with hook, thesis, counterpoint, implication, and close | |
| Two-host AI payments episode | Dialogue with no echo lines, no fragments, no fake opposition, and one resolved hook | |
| Residency/tax episode | Specific numbers and named sources, plus non-personalized advice boundary | |

#### Not in scope

- Replacing the show persona.
- Long-form interview editing.

### Phase 3 - Content QA Gates

**Status:** not started
**Ticket:** none
**Fixes:** R2, R5, R6, R12

#### Behaviour

- Given a script draft, when content QA runs, then it scores hook strength, evidence density, claim traceability, persona fit, source specificity, narrative structure, repetition, caveats, and ending quality.
- Given any unverified factual claim, when content QA runs, then publish status remains blocked until the claim is sourced, softened, or removed.
- Given an episode with promotional language, when the sponsored-content check scores high, then non-interactive runs block instead of proceeding by default.
- Given a script that passes content QA, when a revision is made afterward, then the script returns to `needs_qa`.

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| Script with "experts say" and no source | Fails source specificity | |
| Script with sponsored product demo tone | Blocks publish until explicitly approved | |
| Approved script changed after QA | Reverts to `needs_qa` | |

#### Not in scope

- Human editorial judgment replacement.
- Automated truth guarantee.

### Phase 4 - Free Local TTS Profiles

**Status:** not started
**Ticket:** none
**Fixes:** R8, R9, R10

#### Behaviour

- Given a production episode, when final TTS is requested, then the system selects a configured free/local TTS profile rather than a random voice.
- Given a draft episode, when fast preview TTS is requested, then local Kokoro remains available.
- Given a release episode, when local TTS is configured, then the output records engine, model path/version, voice, speed, style prompt/settings, sample rate, device, and generation timestamp.
- Given a two-host episode, when TTS runs, then each character uses the same configured voice across all segments and future episodes unless deliberately changed.
- Given the configured local engine is unavailable or too slow, when fallback TTS runs, then the episode is marked `fallback_voice` and must be reviewed before publish.

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| Same solo script generated twice | Same configured host voice and comparable pacing | |
| Duo script generated twice | Same host/co-host voice pair | |
| Missing local model files | Fallback audio generated but publish blocked for review | |

#### Not in scope

- Paid TTS APIs.
- Real-time interactive voice chat.

### Phase 5 - Pronunciation and Segment Synthesis

**Status:** not started
**Ticket:** none
**Fixes:** R10, R11

#### Behaviour

- Given an approved script, when TTS normalization runs, then it preserves meaning and speaker labels while converting written forms into spoken forms.
- Given names, acronyms, currency amounts, dates, file paths, jurisdictions, and product names, when the pronunciation manifest is built, then each risky token has an expected spoken form.
- Given a pronunciation manifest, when an audition clip is generated, then the operator can approve or override pronunciations before full synthesis.
- Given a long script, when audio is synthesized, then each paragraph or dialogue turn is generated as a separate segment with stable segment IDs.
- Given a bad segment, when the operator requests a retry, then only that segment is regenerated and the rest of the episode remains unchanged.

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| Script mentioning `x402`, `HTTP 402`, `Georgia`, `Liberland`, and `CBDC` | Pronunciation manifest with expected spoken forms | |
| One failed paragraph | Single segment retry without regenerating full episode | |
| Speaker-labeled dialogue | Preserved speaker labels through normalization and synthesis | |

#### Not in scope

- Perfect automatic pronunciation of all proper nouns.
- Voice cloning without explicit approval.

### Phase 6 - Mastering and Audio QA

**Status:** not started
**Ticket:** none
**Fixes:** R11, R12

#### Behaviour

- Given synthesized segment WAVs, when the episode is assembled, then the system inserts consistent pauses and exports a pre-master WAV.
- Given the pre-master WAV, when audio QA runs, then it reports integrated loudness, true peak, duration, silence anomalies, clipping, sample rate, channel count, and codec.
- Given a release master, when metrics are outside target, then publish is blocked.
- Given a final file, when export completes, then the RSS asset and archive asset are both generated from the same approved master.

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| Master above target peak | Publish blocked with true-peak failure | |
| Master with long accidental silence | Publish blocked with silence anomaly | |
| Approved master | RSS audio, archive WAV, metrics JSON, and transcript emitted | |

#### Not in scope

- Music bed composition.
- Human-style acting direction for non-expressive local models.

### Phase 7 - Release Package and Regression Evals

**Status:** not started
**Ticket:** none
**Fixes:** R12

#### Behaviour

- Given a passed episode, when publishing runs, then the system writes an episode package containing source pack, claim ledger, approved script, normalized TTS script, pronunciation manifest, audio metrics, show notes, and RSS metadata.
- Given a new model, voice, prompt, or mastering change, when regression evals run, then the system compares outputs against a fixed set of representative episodes.
- Given regression output, when quality falls below baseline, then the changed model, voice, prompt, or mastering profile is blocked from becoming the default.

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| Episode ready to publish | Complete release package and feed-safe audio | |
| TTS engine change | Blind-listening eval and metrics comparison | |
| Prompt change | Script rubric comparison against prior baseline | |

#### Not in scope

- Public analytics dashboard.
- Automatic ad insertion.

## Quality Bar

### Content Acceptance Criteria

- The first thirty seconds name the topic and create a concrete reason to continue listening.
- Every episode has one central thesis, not a list of disconnected points.
- Every important number, date, quote, law, protocol, price, or named source is traceable.
- Analysis and fact are distinguishable in the script.
- The episode includes at least one counterpoint or limiting caveat.
- The close lands the implication for the listener, not a generic recap.
- The script obeys `SOUL.md`: specific numbers, named sources, direct claims, no shilling, no unverified claims, no personal legal/financial advice.
- Two-host scripts obey flat-prosody constraints: complete turns, no echo lines, no fake laughter, no delivery-dependent jokes, no clipped reaction fragments.

### TTS Acceptance Criteria

- Final voice selection is deterministic and documented.
- No random host voice appears in production output.
- Pronunciation manifest covers all high-risk tokens before full synthesis.
- Segment-level generation makes local fixes possible without regenerating the whole episode.
- Final audio passes objective loudness, true peak, silence, clipping, duration, and codec checks.
- Release artifacts include the exact text that was synthesized.
- Fallback/local preview output is reviewable but not automatically publishable as final output.

### Recommended Audio Targets

- **Primary RSS target:** Apple Podcasts-compatible loudness around `-16 dB LKFS`, with tolerance of `+/- 1 dB`, and true peak not exceeding `-1 dB FS`.
- **Export format:** Keep an archive WAV. Publish AAC where platform compatibility allows; keep MP3 available for broad RSS compatibility.
- **Codec sanity:** Avoid repeated lossy transcodes. Generate lossless segment WAVs, assemble/master once, then encode the final publish file.
- **Tempo:** Prefer engine-native speed/style controls. Avoid global `atempo` as a default because it can introduce artifacts and changes every word equally, including places where the script needs weight.

## Free Local TTS Guidance

Use an engine interface, not engine-specific code paths. The correct default should be decided by blind A/B tests using actual Señor Freedom scripts. Paid text-to-speech APIs are out of scope.

### Recommended Engine Roles

- **Kokoro:** Keep as the default baseline because it is already integrated, local, fast, and permissively licensed. Improve it with deterministic voices, better segmentation, pronunciation gates, and mastering.
- **VibeVoice:** Evaluate as the first higher-quality local candidate. The repo already has an experimental script, and Microsoft’s model card describes the realtime 0.5B variant as open-source, MIT-licensed, streaming-capable, and robust for long-form English speech.
- **F5-TTS:** Evaluate as a second local candidate if voice consistency or reference-voice workflows become important. Its official repository describes it as flow-matching TTS with official code and local/Docker usage.
- **System TTS / Piper-class fallback:** Keep only as emergency fallback or accessibility preview. Do not use for final masters unless it wins blind tests.
- **Paid APIs:** OpenAI TTS, ElevenLabs, Cartesia, and similar services are excluded unless the no-paid-TTS constraint changes later.

### Local Engine Selection Rubric

| Criterion | Weight | Pass condition |
|---|---:|---|
| Naturalness | 25% | Listener does not hear "AI narrator" artifacts in normal playback |
| Authority/brand fit | 20% | Voice supports skeptical, direct Señor Freedom persona without sounding theatrical |
| Prosody control | 15% | Hooks, numbers, contrasts, and implications are emphasized naturally |
| Pronunciation reliability | 15% | Names, acronyms, finance terms, and jurisdictions need few manual fixes |
| Segment consistency | 10% | Adjacent regenerated segments match timbre, pace, and energy |
| Runtime practicality | 10% | Practical on local hardware for normal backlog throughput |
| License/control constraints | 5% | Acceptable local use, redistribution, and attribution posture |

## Constraints

- Use one implementation branch per phase.
- Keep each phase independently shippable and publish-safe.
- No recurring per-character, per-minute, or subscription TTS spend.
- Do not remove Kokoro; keep it as the baseline until a local/free engine beats it in blind tests.
- Do not publish a changed engine, voice, model, prompt, or mastering profile without regression samples.
- Preserve existing RSS generation and publishing behaviour until the release package can replace it safely.
- Tests should start with pure functions and artifact validation before slow local TTS calls.

## Not In Scope

- **Copyright/legal clearance:** Deferred because source reuse policy depends on business/legal decisions.
- **Paid ad insertion:** Deferred because the show identity currently rejects shilling and sponsored content.
- **Full studio post-production:** Deferred because the immediate bottleneck is deterministic QA and TTS quality, not music beds or live mixing.
- **Automatic truth guarantee:** Deferred because factual review still needs human editorial accountability.
- **Paid TTS APIs:** Deferred because the operating constraint is no recurring TTS spend.
- **Voice cloning:** Deferred unless explicit consent, licensing, and retention rules are defined.

## Appendix: Codebase Review Notes

### A1. Current Strengths

- The repo already has a single command path from download to summary to podcast output.
- `SOUL.md` is unusually useful as a show bible: it defines worldview, boundaries, voice, sourcing expectations, and pet peeves.
- `two-host-dialogue-craft-prompt.md` correctly recognizes that Kokoro-style local TTS needs complete sentences and cannot carry deadpan delivery.
- `tts-normalization-prompt.md` is a strong foundation for spoken-form normalization.
- `pronunciation_db.py` has the right idea: manual seeds, Wiktionary IPA lookup, and injection into Kokoro lexicon golds.
- Duplicate-topic and sponsored-content checks already exist, so the codebase has a natural place to add stronger publish gates.

### A2. Current Quality Risks

- The summary prompt asks for concise bullets, which is useful for speed but weak for evidence preservation.
- The script prompt consumes a summary, not a claim ledger, so script quality depends on what the summary retained.
- The source transcript is not saved as part of a durable episode package.
- The production path does not require source citations even though `SOUL.md` says source material should be cited by name and date.
- The current code can proceed in non-interactive mode after sponsored-content and duplicate warnings.
- Voice selection is random for both solo and duo output, which weakens brand consistency and makes revisions harder.
- Final audio is encoded directly after simple concatenation and tempo adjustment; there is no loudness or true-peak gate.
- Existing text and audio files cause the pipeline to skip generation, but there is no artifact versioning that proves which prompt/model produced them.
- Bilingual output has a distinct educational format but is mixed into the normal podcast production path.

### A3. Recommended Artifact Model

Each episode should have a folder or manifest with:

- `source_pack.json`: URLs, titles, authors/channels, dates, source type, transcript provenance.
- `transcript.txt`: raw or cleaned transcript with anchors.
- `claim_ledger.json`: claim, source, quote/timecode, confidence, status.
- `outline.md`: selected thesis and episode arc.
- `script.approved.txt`: final editorial script.
- `tts.normalized.txt`: exact text sent to TTS.
- `pronunciation.json`: risky terms, expected spoken forms, overrides, audition status.
- `segments/`: per-paragraph or per-turn WAVs.
- `master.wav`: archive master.
- `episode.mp3` or `episode.m4a`: RSS asset.
- `quality_report.json`: content QA, TTS settings, audio metrics, publish status.

### A4. Immediate Implementation Order

1. Add deterministic voice profiles and remove random production voices.
2. Add audio metrics with `ffmpeg`/`ffprobe` loudness checks and block publish on failure.
3. Save transcript, summary, approved script, normalized script, and TTS settings in an episode package.
4. Add a content QA rubric pass before TTS generation.
5. Add a pronunciation manifest and audition clip step.
6. Refactor TTS into local engine profiles: Kokoro baseline, VibeVoice candidate, F5-TTS candidate, emergency fallback.
7. Add segment-level synthesis and retry.
8. Add multi-source research packs for backlog/topic episodes.

### A5. External References Checked

- Kokoro model page: `https://huggingface.co/hexgrad/Kokoro-82M`
- Microsoft VibeVoice repository/model docs: `https://github.com/microsoft/VibeVoice`, `https://huggingface.co/microsoft/VibeVoice-Realtime-0.5B`
- F5-TTS official repository: `https://github.com/SWivid/F5-TTS`
- Apple Podcasts audio requirements: `https://podcasters.apple.com/support/893-audio-requirements`
- Spotify loudness normalization reference: `https://support.spotify.com/artists/article/loudness-normalization/`
