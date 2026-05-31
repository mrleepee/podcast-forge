#!/usr/bin/env python3
"""
checks/run.py — Run all podcast quality checks against fixtures.

Usage:
    python checks/run.py              # run all checks
    python checks/run.py --check loudness   # run one check
    python checks/run.py --fix            # also run known-bad fixtures (expect failures)

Exit 0 if all applicable checks pass, 1 if any fail.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CHECKS_DIR = Path(__file__).parent


def discover_checks() -> list:
    """Find all check_* modules in the checks directory."""
    checks = []
    for p in sorted(CHECKS_DIR.glob("check_*.py")):
        name = p.stem  # e.g. check_loudness
        mod = importlib.import_module(f"checks.{name}")
        if hasattr(mod, "run"):
            checks.append((name, mod))
    return checks


def load_fixtures(subdir: str) -> list[dict]:
    """Load fixture scripts and audio files from a subdirectory."""
    fixtures = []
    base = FIXTURES_DIR / subdir
    if not base.exists():
        return fixtures
    for script in sorted(base.glob("*.txt")):
        entry = {
            "name": script.stem,
            "script_path": script,
            "script_text": script.read_text(encoding="utf-8"),
            "audio_path": None,
        }
        # Look for matching audio file
        for ext in (".mp3", ".wav"):
            audio = script.with_suffix(ext)
            if audio.exists():
                entry["audio_path"] = audio
                break
        fixtures.append(entry)
    return fixtures


def run_all(check_name: str | None = None, include_bad: bool = False) -> bool:
    """Run checks against good fixtures (and optionally bad). Returns True if all pass."""
    checks = discover_checks()
    if check_name:
        checks = [(n, m) for n, m in checks if n == f"check_{check_name}"]
        if not checks:
            print(f"Unknown check: {check_name}")
            print(f"Available: {', '.join(n for n, _ in discover_checks())}")
            return False

    good = load_fixtures("good")
    bad = load_fixtures("bad") if include_bad else []

    all_pass = True
    rows = []

    for check_name, mod in checks:
        for fx in good:
            result = mod.run(fx)
            status = "PASS" if result.passed else "FAIL"
            if not result.passed:
                all_pass = False
            rows.append((fx["name"], check_name, status, result.reason))

        for fx in bad:
            result = mod.run(fx)
            status = "XPASS" if result.passed else "XFAIL"
            if result.passed:
                # Known-bad fixture unexpectedly passed — the check is broken
                all_pass = False
                status = "XPASS (check broken!)"
            rows.append((fx["name"], check_name, status, result.reason))

    # Print results table
    name_w = max(len(r[0]) for r in rows) if rows else 10
    check_w = max(len(r[1]) for r in rows) if rows else 10
    print(f"\n{'fixture':<{name_w}}  {'check':<{check_w}}  {'status':<8}  reason")
    print("-" * (name_w + check_w + 30))
    for name, chk, status, reason in rows:
        print(f"{name:<{name_w}}  {chk:<{check_w}}  {status:<8}  {reason}")

    print(f"\n{'Total':<{name_w}}  {'':<{check_w}}  {'PASS' if all_pass else 'FAIL'}")
    return all_pass


class CheckResult:
    """Standard result from any quality check — shared across all check modules."""

    def __init__(self, passed: bool, reason: str = "", metrics: dict | None = None):
        self.passed = passed
        self.reason = reason
        self.metrics = metrics or {}

    def __bool__(self):
        return self.passed


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Run podcast quality checks")
    ap.add_argument("--check", help="run a single check by name (e.g. loudness)")
    ap.add_argument("--fix", action="store_true", help="also run known-bad fixtures")
    args = ap.parse_args()

    ok = run_all(check_name=args.check, include_bad=args.fix)
    sys.exit(0 if ok else 1)
