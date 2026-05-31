"""
quality_gate — Run all quality checks and block publish on failure.

Writes quality_report.json with all check results.
Returns True only if all applicable checks pass.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from checks.check_loudness import run as check_loudness
from checks.check_pronunciation import run as check_pronunciation
from checks.check_substance import run as check_substance
from checks.check_structure import run as check_structure
from checks.check_dialogue import run as check_dialogue


@dataclass
class QualityReport:
    """Aggregated quality report for an episode."""
    passed: bool
    checks: dict = field(default_factory=dict)
    blocking_failures: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "publish_blocked": not self.passed,
            "checks": self.checks,
            "blocking_failures": self.blocking_failures,
        }


def run_quality_gate(
    script_text: str,
    audio_path: str | Path | None = None,
) -> QualityReport:
    """Run all quality checks. Returns a QualityReport.

    Checks that require unavailable data (e.g. no audio file) are
    reported as skipped, not as failures.
    """
    fixture = {
        "script_text": script_text,
        "audio_path": str(audio_path) if audio_path else None,
    }

    checks_to_run = [
        ("loudness", check_loudness),
        ("pronunciation", check_pronunciation),
        ("substance", check_substance),
        ("structure", check_structure),
        ("dialogue", check_dialogue),
    ]

    results = {}
    failures = []

    for name, check_fn in checks_to_run:
        result = check_fn(fixture)
        results[name] = {
            "passed": result.passed,
            "reason": result.reason,
            "metrics": result.metrics,
        }
        if not result.passed:
            failures.append(f"{name}: {result.reason}")

    report = QualityReport(
        passed=len(failures) == 0,
        checks=results,
        blocking_failures=failures,
    )

    return report


def write_quality_report(
    report: QualityReport,
    output_path: str | Path,
) -> Path:
    """Write the quality report to a JSON file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return path
