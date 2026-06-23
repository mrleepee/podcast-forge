"""
master_audio.py — Two-pass EBU R128 loudness normalisation for podcast audio.

Takes a raw TTS MP3 (~-25 LUFS) and masters it to broadcast-standard
loudness: I=-16 LUFS, TP=-1.5 dBTP, LRA≤11.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

TARGET_I = -16.0
TARGET_TP = -1.5
TARGET_LRA = 11.0


def master(input_path: str | Path, output_path: str | Path | None = None) -> dict:
    """Two-pass loudnorm mastering. Returns measured metrics dict.

    Pass 1: Measure current levels.
    Pass 2: Apply normalisation with measured offsets.
    When output_path is None, writes to a temp file then replaces the original.
    """
    input_path = Path(input_path)
    in_place = output_path is None
    if in_place:
        # FFmpeg cannot write to the same file it reads — use temp file
        tmp = Path(tempfile.gettempdir()) / f"_master_{input_path.name}"
        output_path = tmp
    output_path = Path(output_path)

    # Pass 1: measure
    r1 = subprocess.run(
        ["ffmpeg", "-i", str(input_path),
         "-af", "loudnorm=I={}:TP={}:LRA={}:print_format=json".format(
             TARGET_I, TARGET_TP, TARGET_LRA),
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    match = re.search(r'\{[^{}]*"input_i"[^{}]*\}', r1.stderr, re.DOTALL)
    if not match:
        raise RuntimeError(f"Could not measure {input_path} (ffmpeg loudnorm failed)")

    stats = json.loads(match.group(0))

    # If already in tolerance, skip
    input_i = float(stats.get("input_i", 0))
    input_tp = float(stats.get("input_tp", 0))
    if -17.0 <= input_i <= -15.0 and input_tp <= -1.0:
        if in_place:
            pass  # original is already good
        elif input_path != output_path:
            subprocess.run(["cp", str(input_path), str(output_path)], check=True)
        return {
            "integrated_lufs": round(input_i, 1),
            "true_peak_dbfs": round(input_tp, 1),
            "passes_target": True,
            "passes_true_peak": True,
            "normalised": False,
        }

    # Pass 2: normalise using measured values
    filter_str = (
        f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}"
        f":measured_I={stats.get('input_i', input_i)}"
        f":measured_TP={stats.get('input_tp', input_tp)}"
        f":measured_LRA={stats.get('input_lra', '0.0')}"
        f":measured_thresh={stats.get('input_thresh', '-70.0')}"
        f":offset={stats.get('target_offset', '0.0')}"
        f":linear=true:print_format=json"
    )

    r2 = subprocess.run(
        ["ffmpeg", "-y", "-i", str(input_path),
         "-af", filter_str,
         "-codec:a", "libmp3lame", "-qscale:a", "2",
         str(output_path)],
        capture_output=True, text=True,
    )
    if r2.returncode != 0:
        raise RuntimeError(f"ffmpeg mastering failed: {r2.stderr[-500:]}")

    # Replace original with mastered version
    if in_place:
        subprocess.run(["mv", str(output_path), str(input_path)], check=True)
        output_path = input_path

    # Verify the output
    verify = subprocess.run(
        ["ffmpeg", "-i", str(output_path),
         "-af", "loudnorm=print_format=json",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    v_match = re.search(r'\{[^{}]*"input_i"[^{}]*\}', verify.stderr, re.DOTALL)
    if v_match:
        v_stats = json.loads(v_match.group(0))
        final_i = float(v_stats.get("input_i", 0))
        final_tp = float(v_stats.get("input_tp", 0))
    else:
        final_i = input_i
        final_tp = input_tp

    return {
        "integrated_lufs": round(final_i, 1),
        "true_peak_dbfs": round(final_tp, 1),
        "passes_target": -17.0 <= final_i <= -15.0,
        "passes_true_peak": final_tp <= -1.0,
        "normalised": True,
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Master podcast audio to -16 LUFS")
    ap.add_argument("input", help="input MP3 file")
    ap.add_argument("-o", "--output", help="output MP3 file (default: overwrite)")
    args = ap.parse_args()
    result = master(args.input, args.output)
    for k, v in result.items():
        print(f"  {k}: {v}")
    if result["passes_target"] and result["passes_true_peak"]:
        print("  ✓ Within broadcast targets")
    else:
        print("  ✗ Outside broadcast targets")
