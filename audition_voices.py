#!/usr/bin/env python3
"""
audition_voices.py — Hear the same Señor Freedom line in each candidate Kokoro
voice, and measure the real loudness of each clip.

Why this exists
---------------
1. "Which single voice should the show use?" is hard to answer in the abstract.
   Run this, listen to the labelled clips, pick the one that fits the persona.
2. "Is there actually a loudness problem, or does Kokoro sound fine?" — this
   prints the *measured* integrated loudness (LUFS) and true peak (dBFS) of each
   clip, so you can compare against the podcast target (~ -16 LUFS, true peak
   <= -1 dBFS) with real numbers instead of guessing.

Usage
-----
    python audition_voices.py                 # all 8 British voices (pick by ear)
    python audition_voices.py --voices bm_fable,bf_emma   # just a shortlist
    python audition_voices.py --measure path/to/an_existing_episode.mp3

Run it inside the project's virtualenv (the same one the pipeline uses), so the
`kokoro` package and pronunciation data are available.

Output: auditions/audition_<voice>.mp3  + a summary table printed to the console.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SAMPLE_RATE = 24000

# A real Señor Freedom audition line: a hook, a hard number, a named place, a
# date, and risky tokens (CBDC, Liberland, x402) so you can judge prosody AND
# pronunciation at the same time.
AUDITION_TEXT = (
    "Here's the catch they won't print on the brochure. "
    "By 2024, central banks in more than ninety countries were piloting a CBDC — "
    "a currency that watches you spend it. "
    "Liberland's answer was the opposite: settle in seconds over a protocol called x402, "
    "no permission required. "
    "Follow the money, and the story tells itself."
)

MALE_BRITISH = ["bm_daniel", "bm_fable", "bm_george", "bm_lewis"]
FEMALE_BRITISH = ["bf_alice", "bf_emma", "bf_isabella", "bf_lily"]

TARGET_NOTE = "target: ~ -16 LUFS, true peak <= -1 dBFS"


def measure_loudness(path):
    """Return (integrated_LUFS, true_peak_dBFS) via ffmpeg's EBU R128 loudnorm."""
    r = subprocess.run(
        ["ffmpeg", "-i", str(path), "-af", "loudnorm=print_format=json",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.DOTALL)
    if not m:
        return None, None
    d = json.loads(m.group(0))
    try:
        return float(d["input_i"]), float(d["input_tp"])
    except (KeyError, ValueError):
        return None, None


def synth(pipeline, text, voice, out_wav):
    import numpy as np
    import soundfile as sf
    parts = [audio for _gs, _ps, audio in pipeline(text, voice=voice)]
    if not parts:
        return False
    sf.write(str(out_wav), np.concatenate(parts), SAMPLE_RATE)
    return True


def to_mp3(wav_path, mp3_path):
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav_path), "-codec:a", "libmp3lame",
         "-qscale:a", "2", str(mp3_path)],
        capture_output=True, text=True,
    )


def print_table(rows):
    print(f"\n=== Audition results ({TARGET_NOTE}) ===")
    print(f"{'voice':<12}{'loudness (LUFS)':>18}{'true peak (dBFS)':>20}")
    for voice, lufs, tp in rows:
        ls = f"{lufs:.1f}" if lufs is not None else "n/a"
        ts = f"{tp:.1f}" if tp is not None else "n/a"
        print(f"{voice:<12}{ls:>18}{ts:>20}")


def main():
    ap = argparse.ArgumentParser(description="Audition Kokoro voices and measure loudness.")
    ap.add_argument("--voices", help="comma-separated voice ids (default: all 8 British voices)")
    ap.add_argument("--text", help="override the audition line")
    ap.add_argument("--measure", metavar="FILE",
                    help="just measure loudness of an existing audio file and exit")
    args = ap.parse_args()

    # Measurement-only mode: answer "is the volume off?" on a real episode,
    # no Kokoro needed.
    if args.measure:
        lufs, tp = measure_loudness(args.measure)
        if lufs is None:
            sys.exit(f"Could not measure {args.measure} (is ffmpeg installed?)")
        print(f"{args.measure}")
        print(f"  integrated loudness: {lufs:.1f} LUFS   true peak: {tp:.1f} dBFS")
        print(f"  ({TARGET_NOTE})")
        gap = -16.0 - lufs
        if abs(gap) <= 1.0 and tp <= -1.0:
            print("  -> already in range; mastering work is optional.")
        elif tp > -1.0:
            print("  -> true peak is hot; risks clipping on platform normalization.")
        else:
            print(f"  -> about {gap:+.1f} dB from target; a one-pass normalize would fix it.")
        return

    if args.voices:
        voices = [v.strip() for v in args.voices.split(",") if v.strip()]
    else:
        voices = MALE_BRITISH + FEMALE_BRITISH
    text = args.text or AUDITION_TEXT

    try:
        from kokoro import KPipeline
    except ImportError:
        sys.exit("kokoro not installed — run this inside the project venv the pipeline uses.")

    pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")

    # Match the real pipeline: load pronunciation golds so jargon is said correctly.
    try:
        from pronunciation_db import enrich_pronunciation_cache, load_golds_into_pipeline
        enrich_pronunciation_cache(text)
        loaded = load_golds_into_pipeline(pipeline)
        if loaded:
            print(f"Loaded {loaded} pronunciation golds.")
    except Exception as e:  # best effort; auditioning still works without it
        print(f"(pronunciation golds not loaded: {e})")

    out_dir = Path("auditions")
    out_dir.mkdir(exist_ok=True)

    rows = []
    for voice in voices:
        wav = out_dir / f"audition_{voice}.wav"
        mp3 = out_dir / f"audition_{voice}.mp3"
        print(f"Synthesizing {voice} ...")
        if not synth(pipeline, text, voice, wav):
            print(f"  no audio produced for {voice}")
            continue
        to_mp3(wav, mp3)
        lufs, tp = measure_loudness(mp3)
        wav.unlink(missing_ok=True)
        rows.append((voice, lufs, tp))

    print_table(rows)
    print(f"\nClips saved in: {out_dir.resolve()}")
    print("Listen and pick the voice that best fits the show's skeptical, direct tone —")
    print("any gender works; the name (Señor / Señora Freedom) can follow the voice.")
    print("Then lock it as the show voice. The LUFS column shows whether loudness is")
    print("even an issue worth addressing.")


if __name__ == "__main__":
    main()
