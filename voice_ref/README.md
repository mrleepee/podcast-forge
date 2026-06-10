# Voice reference clip — Señora Freedom

OmniVoice clones the timbre in `senora_freedom_en_ref.wav` for every episode
(both languages). The `.wav` files are gitignored; only `senora_freedom_en_ref.txt`
(the transcript OmniVoice uses for alignment) is tracked.

## ⚠️ The current clip is defective — re-cut needed (asset task, P2.2)

Measured 2026-06-09 and still true: `senora_freedom_en_ref.wav` **ends
mid-speech** (≈6.90 s, **0 ms trailing silence**). Cloning every chunk against a
clip that ends mid-word is the documented root cause of the per-chunk echo
artifact (a stray reference fragment bleeding into each segment). The auto-trim
in `_validate_ref_clip` can only remove silence, and there is none to remove.

`_validate_ref_clip` prints a loud `RE-CUT the clip` warning on every render, and
the hard-fail guard (`OMNIVOICE_REF_STRICT`) can stop the run entirely — but it is
**disabled by default** precisely because this clip has not been re-cut yet.
Turning it on before the re-cut would halt all production.

## How to re-cut (per the omnivoice spec, Appendix D)

1. Choose a passage where Señora Freedom **finishes a sentence**, then stays
   silent for ≥ 150 ms.
2. Export: **24 kHz, mono, WAV**, ending on that completed sentence with the
   trailing silence intact. ~6–10 s is plenty.
3. Overwrite `senora_freedom_en_ref.wav`.
4. Update `senora_freedom_en_ref.txt` so the transcript **matches the audio
   exactly** (word for word).
5. Verify:
   ```bash
   .venv/bin/python -c "import video_downloader as v; \
     print(v._validate_ref_clip(v._OMNI_REF_AUDIO, v._OMNI_REF_TEXT))"
   ```
   A clean clip returns `([], <clean_path or None>)` — no warnings.
6. **Enable the hard-fail** so future defective clips can't ship: set
   `OMNIVOICE_REF_STRICT=1` (or flip the default in `video_downloader.py`).

## Verifying a render is artifact-free (Phase 4 QC)

`checks/seam_qc.py` is a standalone harness (run under the OmniVoice venv, which
has `whisperx`):

```bash
python -m checks.seam_qc /path/to/segment_wavs_dir
```

It reports the peak energy at each segment seam (clean < −60 dBFS) and flags any
token that recurs at the start of ≥ 30 % of segments (the echo signature). Exit
code 0 = clean, 2 = artifact detected.
