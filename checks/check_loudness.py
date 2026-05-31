"""
check_loudness — Verify episode audio meets broadcast loudness targets.

Targets:
  Integrated loudness: -16 LUFS ±1 dB (range: [-17.0, -15.0])
  True peak: ≤ -1.0 dBFS
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

TARGET_LUFS = -16.0
LUFS_TOLERANCE = 1.0
LUFS_MIN = TARGET_LUFS - LUFS_TOLERANCE  # -17.0
LUFS_MAX = TARGET_LUFS + LUFS_TOLERANCE  # -15.0
TRUE_PEAK_MAX = -1.0  # dBFS


@dataclass
class CheckResult:
    """Standard result from any quality check."""
    passed: bool
    reason: str = ""
    metrics: dict = field(default_factory=dict)

    def __bool__(self):
        return self.passed


def measure_loudness(path: str | Path) -> tuple[float | None, float | None]:
    """Return (integrated_LUFS, true_peak_dBFS) via ffmpeg EBU R128 loudnorm."""
    result = subprocess.run(
        ["ffmpeg", "-i", str(path), "-af",
         "loudnorm=print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    match = re.search(r'\{[^{}]*"input_i"[^{}]*\}', result.stderr, re.DOTALL)
    if not match:
        return None, None
    data = json.loads(match.group(0))
    try:
        return float(data["input_i"]), float(data["input_tp"])
    except (KeyError, ValueError):
        return None, None


def run(fixture: dict) -> CheckResult:
    """Run loudness check against a fixture.

    Expects fixture to have an 'audio_path' key pointing to an MP3/WAV file.
    """
    audio_path = fixture.get("audio_path")
    if not audio_path or not Path(audio_path).exists():
        return CheckResult(
            passed=False,
            reason="no audio file found",
            metrics={"error": "missing_audio"},
        )

    lufs, tp = measure_loudness(audio_path)
    if lufs is None:
        return CheckResult(
            passed=False,
            reason="could not measure loudness (ffmpeg missing or corrupt file)",
            metrics={"error": "measurement_failed"},
        )

    metrics = {"integrated_lufs": round(lufs, 1), "true_peak_dbfs": round(tp, 1)}

    lufs_ok = LUFS_MIN <= lufs <= LUFS_MAX
    tp_ok = tp <= TRUE_PEAK_MAX

    if lufs_ok and tp_ok:
        return CheckResult(
            passed=True,
            reason=f"LUFS={lufs:.1f} TP={tp:.1f}",
            metrics=metrics,
        )

    reasons = []
    if not lufs_ok:
        reasons.append(f"LUFS={lufs:.1f} (target {LUFS_MIN:.1f} to {LUFS_MAX:.1f})")
    if not tp_ok:
        reasons.append(f"TP={tp:.1f} (max {TRUE_PEAK_MAX:.1f})")
    return CheckResult(
        passed=False,
        reason="; ".join(reasons),
        metrics=metrics,
    )
