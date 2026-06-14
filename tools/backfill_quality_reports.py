#!/usr/bin/env python3
"""
tools/backfill_quality_reports.py — Regenerate quality reports for legacy episodes.

The publish gate (``checks/publish_gate.py``) blocks any episode whose
``<slug>.quality_report.json`` is missing or reports ``passed: false``.
Episodes produced before the gate existed — or whose gate run stalled mid-pipeline
— lack a report, so the gate holds them out of the feed even though their audio
and script are fine.

This tool regenerates a report from the on-disk ``<slug>.podcast.txt`` (and the
``<slug>.podcast.mp3`` when present) WITHOUT re-running TTS. Every check except
loudness is a deterministic check on the script text, and loudness is a single
ffmpeg pass over the existing MP3. That makes legacy backfill cheap and safe:
the report is derived from artifacts that already exist on disk.

Usage::

    # backfill specific episodes (always (re)writes their reports)
    python tools/backfill_quality_reports.py ep131-anthropic-self-service-data-analytics

    # backfill every MP3 that is missing a report
    python tools/backfill_quality_reports.py --all

    # also re-run episodes that already have a report (e.g. after a lexicon fix)
    python tools/backfill_quality_reports.py --all --force

    # preview outcomes without writing anything
    python tools/backfill_quality_reports.py --all --dry-run

    --audio-dir overrides the default freeist-podcast/audio location.

Exit code: 0 if every processed report passes the gate; 1 if any report fails
or any slug could not be processed; 2 if the audio directory is missing.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the repo importable when run as a script (``python tools/...``).
REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from checks.quality_gate import run_quality_gate, write_quality_report  # noqa: E402

MP3_SUFFIX = ".podcast.mp3"
TXT_SUFFIX = ".podcast.txt"
REPORT_SUFFIX = ".quality_report.json"

# Episodes live in the sibling freeist-podcast repo by default.
DEFAULT_AUDIO_DIR = REPO.parent / "freeist-podcast" / "audio"


def find_mp3_slugs(audio_dir: Path) -> list[str]:
    """Every slug with a ``<slug>.podcast.mp3`` in ``audio_dir``, sorted."""
    return sorted(p.name[: -len(MP3_SUFFIX)] for p in audio_dir.glob(f"*{MP3_SUFFIX}"))


def has_report(audio_dir: Path, slug: str) -> bool:
    return (audio_dir / f"{slug}{REPORT_SUFFIX}").exists()


def select_slugs(audio_dir: Path, slugs, all_missing: bool, force: bool) -> list[str]:
    """Resolve the slug set to process.

    Explicit slugs are always processed as given. ``--all`` selects every MP3
    slug missing a report, unless ``--force`` broadens it to every MP3 slug.
    """
    if slugs:
        return list(slugs)
    if not all_missing:
        return []
    if force:
        return find_mp3_slugs(audio_dir)
    return [s for s in find_mp3_slugs(audio_dir) if not has_report(audio_dir, s)]


def backfill_slug(slug: str, audio_dir: Path, dry_run: bool = False,
                  gate_runner=run_quality_gate) -> dict:
    """Regenerate one episode's quality report.

    Returns a result dict::

        {slug, status, passed, report_path, failures, error}

    where ``status`` is one of ``passed`` / ``failed`` / ``error``. The report
    is written even on failure — a ``passed: false`` report documents *why* an
    episode is held and lets the publish gate block it precisely.
    """
    script_path = audio_dir / f"{slug}{TXT_SUFFIX}"
    report_path = audio_dir / f"{slug}{REPORT_SUFFIX}"
    result = {
        "slug": slug, "status": None, "passed": False,
        "report_path": str(report_path), "failures": [], "error": None,
    }

    if not script_path.exists():
        result["status"] = "error"
        result["error"] = f"missing script: {script_path.name}"
        return result

    script_text = script_path.read_text(encoding="utf-8")

    # Only run loudness when the audio actually exists; otherwise run_quality_gate
    # would record a hard loudness failure instead of skipping the check.
    mp3_path = audio_dir / f"{slug}{MP3_SUFFIX}"
    audio_path = str(mp3_path) if mp3_path.exists() else None

    report = gate_runner(script_text, audio_path=audio_path)
    result["passed"] = report.passed
    result["failures"] = list(report.blocking_failures)
    result["status"] = "passed" if report.passed else "failed"

    if not dry_run:
        write_quality_report(report, report_path)

    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Regenerate quality reports for legacy episodes without re-running TTS.",
    )
    ap.add_argument("slugs", nargs="*", help="episode slugs to backfill")
    ap.add_argument("--all", action="store_true",
                    help="select every MP3 missing a report (use --force to include all)")
    ap.add_argument("--force", action="store_true",
                    help="with --all, also re-run episodes that already have a report")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute reports but do not write them")
    ap.add_argument("--audio-dir", type=Path, default=None,
                    help=f"audio directory (default: {DEFAULT_AUDIO_DIR})")
    args = ap.parse_args(argv)

    audio_dir = args.audio_dir or DEFAULT_AUDIO_DIR
    if not audio_dir.exists():
        print(f"error: audio dir not found: {audio_dir}", file=sys.stderr)
        return 2

    if not args.slugs and not args.all:
        ap.error("provide episode slugs or use --all")

    selected = select_slugs(audio_dir, args.slugs, args.all, args.force)
    if not selected:
        print("nothing to backfill")
        return 0

    prefix = "dry-run: " if args.dry_run else ""
    print(f"{prefix}backfilling {len(selected)} episode(s) in {audio_dir}\n")

    results = [backfill_slug(s, audio_dir, dry_run=args.dry_run) for s in selected]

    passed = [r for r in results if r["status"] == "passed"]
    failed = [r for r in results if r["status"] == "failed"]
    errors = [r for r in results if r["status"] == "error"]

    for r in results:
        if r["status"] == "passed":
            print(f"  {r['slug']}: PASSED")
        elif r["status"] == "failed":
            print(f"  {r['slug']}: FAILED ({'; '.join(r['failures'])})")
        else:
            print(f"  {r['slug']}: ERROR ({r['error']})", file=sys.stderr)

    print(f"\n{len(passed)} passed, {len(failed)} failed, {len(errors)} error(s)")
    return 0 if not (failed or errors) else 1


if __name__ == "__main__":
    sys.exit(main())
