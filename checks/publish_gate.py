"""
publish_gate — Decide which episodes are allowed into the published feed.

This enforces, at publish time, the contract from ``docs/podcast-quality-plan.md``:

    "publishing is blocked unless Items 1-5 tests pass."

An episode is publishable only when, in the audio directory, it has:

  * a ``<slug>.quality_report.json`` with ``passed: true``, and
  * (if present) a ``<slug>.podcast.verification_report.json`` whose ``passed``
    is not ``false``.

An episode that is missing its quality report, has ``passed: false``, or whose
verification report failed is sent to the ``needs_review`` list and excluded
from the feed — unless it is explicitly allowlisted in ``publish_overrides.json``
(a ``{slug: reason}`` map), in which case it is published and the reason logged.

The module is pure and offline: it only reads JSON files from a directory, so it
is cheap to unit-test with fixtures. ``video_downloader.publish_feed`` calls
``run_publish_gate`` and passes the blocked slugs to ``generate_rss --exclude``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_SUFFIX = ".podcast.mp3"


@dataclass
class EpisodeVerdict:
    """Whether a single episode may be published, and why."""
    slug: str
    publishable: bool
    reason: str
    overridden: bool = False

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "publishable": self.publishable,
            "reason": self.reason,
            "overridden": self.overridden,
        }


@dataclass
class PublishGateResult:
    """Aggregate verdict over an audio directory."""
    publishable: list = field(default_factory=list)   # list[EpisodeVerdict]
    needs_review: list = field(default_factory=list)   # list[EpisodeVerdict]

    @property
    def publishable_slugs(self) -> list:
        return [v.slug for v in self.publishable]

    @property
    def blocked_slugs(self) -> list:
        return [v.slug for v in self.needs_review]

    def to_dict(self) -> dict:
        return {
            "publishable": [v.to_dict() for v in self.publishable],
            "needs_review": [v.to_dict() for v in self.needs_review],
        }


def _load_json(path: Path):
    """Load JSON, returning None on any read/parse error (treated as 'absent')."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def evaluate_episode(slug: str, audio_dir, overrides: dict | None = None) -> EpisodeVerdict:
    """Return the publish verdict for a single episode slug."""
    overrides = overrides or {}
    audio_dir = Path(audio_dir)

    if slug in overrides:
        reason = str(overrides[slug]) or "allowlisted"
        return EpisodeVerdict(slug, True, f"override: {reason}", overridden=True)

    report = _load_json(audio_dir / f"{slug}.quality_report.json")
    if report is None:
        return EpisodeVerdict(slug, False, "no quality_report.json")
    if not report.get("passed", False):
        failures = report.get("blocking_failures") or []
        detail = "; ".join(str(f) for f in failures[:3]) if failures else "passed=false"
        return EpisodeVerdict(slug, False, f"quality gate failed: {detail}")

    # Verification is best-effort: block only when a report exists and explicitly
    # failed. A missing verification report does not block here (see P1.2 for the
    # tighter "verification not performed" treatment in a later phase).
    verification = _load_json(audio_dir / f"{slug}.podcast.verification_report.json")
    if verification is not None and verification.get("passed") is False:
        high = verification.get("high_confidence")
        detail = f"{high} untraceable claims" if high is not None else "verification failed"
        return EpisodeVerdict(slug, False, f"verification failed: {detail}")

    return EpisodeVerdict(slug, True, "quality gate passed")


def load_overrides(overrides_path) -> dict:
    """Load the publish_overrides.json allowlist as a {slug: reason} dict."""
    if not overrides_path:
        return {}
    data = _load_json(overrides_path)
    return data if isinstance(data, dict) else {}


def run_publish_gate(audio_dir, overrides_path=None, suffix: str = DEFAULT_SUFFIX) -> PublishGateResult:
    """Evaluate every ``*<suffix>`` episode in ``audio_dir``.

    Returns a :class:`PublishGateResult` partitioning episodes into publishable
    and needs_review. Overrides are read from ``overrides_path`` if given.
    """
    audio_dir = Path(audio_dir)
    overrides = load_overrides(overrides_path)

    result = PublishGateResult()
    if not audio_dir.exists():
        return result

    for mp3 in sorted(audio_dir.glob(f"*{suffix}")):
        slug = mp3.name[: -len(suffix)]
        verdict = evaluate_episode(slug, audio_dir, overrides)
        if verdict.publishable:
            result.publishable.append(verdict)
        else:
            result.needs_review.append(verdict)
    return result
