"""
seam_qc — Phase 4 QC harness for OmniVoice seam artifacts (P2.2 / omnivoice spec R5).

Given an episode's per-segment WAVs (and, optionally, their transcripts), this:

  1. reports the peak energy inside each inter-segment gap — a clean render has
     near-silence there (< -60 dBFS); leakage shows up as a loud gap, and
  2. flags a token that recurs at the START of >= 30% of segments — the echo
     signature where a stray reference fragment ("fresh") bleeds into every chunk.

So "the artifact is gone" becomes a test result, not a listening impression.

This is a STANDALONE harness, used during verification of a render — NOT wired
into ``checks/run.py`` and NOT in the synthesis hot path. Transcription needs
whisperx, which lives only in the OmniVoice venv; it is injected via the
``transcriber`` callback (or pre-supplied transcripts) so the energy analysis and
the echo-signature logic stay unit-testable in the podcast-forge venv.

Usage (under the OmniVoice venv, with whisperx available):

    python -m checks.seam_qc /path/to/segment_wavs_dir
"""
from __future__ import annotations

import math
import string
from collections import Counter
from pathlib import Path

# A clean inter-segment gap should sit below this peak energy.
GAP_CLEAN_DBFS = -60.0
# A start token recurring in at least this fraction of segments is the echo signature.
ECHO_FRACTION = 0.30


def peak_dbfs(samples) -> float:
    """Peak amplitude of a sample array in dBFS (-inf for pure silence)."""
    import numpy as np
    if samples is None or len(samples) == 0:
        return -math.inf
    peak = float(np.max(np.abs(np.asarray(samples, dtype="float64"))))
    if peak <= 0.0:
        return -math.inf
    return 20.0 * math.log10(min(peak, 1.0))


def analyze_gap_energy(segment_arrays, sr: int, *, edge_ms: float = 40.0):
    """Measure the peak energy in the trailing edge of each segment (the seam).

    ``_omnivoice_render`` joins segments with inserted silence, so the gap itself
    is zeros — the artifact is residual energy at a segment's *trimmed* edge that,
    after the Phase 1 de-click fade, should be near-silent. We measure the last
    ``edge_ms`` of each segment: a clean seam sits below ``GAP_CLEAN_DBFS``, a
    click/leaked-token leaves audible energy. Returns per-segment peak dBFS, the
    worst seam, and whether the render is clean.
    """
    import numpy as np
    edge = max(1, int(edge_ms / 1000.0 * sr))
    per_seam = []
    for seg in segment_arrays:
        seg = np.asarray(seg, dtype="float64")
        window = seg[-edge:] if len(seg) >= edge else seg
        per_seam.append(peak_dbfs(window))
    worst = max(per_seam) if per_seam else -math.inf
    return {
        "seam_count": len(per_seam),
        "per_seam_dbfs": per_seam,
        "worst_gap_dbfs": worst,
        "clean": worst < GAP_CLEAN_DBFS,
        "threshold_dbfs": GAP_CLEAN_DBFS,
        "edge_ms": edge_ms,
    }


def _first_token(text: str) -> str | None:
    """Lowercased first word of a transcript, stripped of punctuation."""
    for word in text.strip().split():
        cleaned = word.strip(string.punctuation + "¿¡").lower()
        if cleaned:
            return cleaned
    return None


def detect_recurring_start_token(transcripts, *, threshold: float = ECHO_FRACTION):
    """Flag a token that starts >= ``threshold`` of segments (the echo signature)."""
    firsts = [t for t in (_first_token(x) for x in transcripts) if t]
    if not firsts:
        return {"token": None, "fraction": 0.0, "flagged": False, "segments": 0}
    token, count = Counter(firsts).most_common(1)[0]
    fraction = count / len(firsts)
    # Require the token to actually recur (count >= 2): a single occurrence is
    # never an echo, even when it's a large fraction of a short segment list.
    return {
        "token": token,
        "count": count,
        "fraction": fraction,
        "flagged": count >= 2 and fraction >= threshold,
        "segments": len(firsts),
        "threshold": threshold,
    }


def run_seam_qc(seg_wav_paths, transcripts=None, transcriber=None):
    """Run the full seam QC over a list of segment WAV paths.

    ``transcripts`` may be supplied directly; otherwise ``transcriber(path)`` is
    called per segment if provided. With neither, the echo-signature stage is
    skipped (energy analysis still runs). Returns a structured report dict.
    """
    import numpy as np
    import soundfile as sf

    arrays, sr = [], None
    for p in seg_wav_paths:
        wav, this_sr = sf.read(p)
        if wav.ndim > 1:
            wav = wav.mean(axis=1)
        arrays.append(np.asarray(wav, dtype="float64"))
        sr = this_sr

    energy = analyze_gap_energy(arrays, sr or 24000)

    if transcripts is None and transcriber is not None:
        transcripts = [transcriber(p) for p in seg_wav_paths]
    echo = (detect_recurring_start_token(transcripts)
            if transcripts is not None else
            {"token": None, "fraction": 0.0, "flagged": False, "skipped": True})

    return {
        "segments": len(seg_wav_paths),
        "energy": energy,
        "echo": echo,
        "clean": energy["clean"] and not echo.get("flagged", False),
    }


def _whisperx_transcriber():
    """Build a transcriber backed by whisperx (OmniVoice venv only), or None."""
    try:
        import whisperx  # noqa: F401
    except Exception:
        return None

    def _transcribe(path):
        import whisperx
        model = whisperx.load_model("base", device="cpu", compute_type="int8")
        audio = whisperx.load_audio(str(path))
        result = model.transcribe(audio)
        return " ".join(seg.get("text", "") for seg in result.get("segments", []))

    return _transcribe


def main(argv=None):
    import argparse
    import json as _json

    ap = argparse.ArgumentParser(description="OmniVoice seam-artifact QC harness")
    ap.add_argument("seg_dir", help="directory of segNNN.wav segment files")
    ap.add_argument("--glob", default="seg*.wav", help="segment filename glob")
    ap.add_argument("--no-transcribe", action="store_true",
                    help="skip whisperx transcription (energy-only)")
    args = ap.parse_args(argv)

    paths = sorted(Path(args.seg_dir).glob(args.glob))
    if not paths:
        print(f"No segments matching {args.glob} in {args.seg_dir}")
        return 1

    transcriber = None if args.no_transcribe else _whisperx_transcriber()
    if transcriber is None and not args.no_transcribe:
        print("  whisperx unavailable — running energy-only (no echo detection).")

    report = run_seam_qc(paths, transcriber=transcriber)
    print(_json.dumps(report, indent=2))
    return 0 if report["clean"] else 2


if __name__ == "__main__":
    import sys
    sys.exit(main())
