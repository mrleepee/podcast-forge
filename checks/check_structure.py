"""
check_structure — Verify the script hooks early and lands the ending.

Deterministic checks:
  - First two sentences contain a number, a name, or a question
  - Ending denylist returns 0 hits

SOUL.md already forbids "Only time will tell" — this enforces it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

ENDING_DENYLIST = [
    "only time will tell",
    "at the end of the day",
    "in conclusion",
    "in today's world",
    "in today's ... world",
    "thanks for listening",
    "that's all for today",
    "until next time",
    "stay tuned",
]

# Match a number, a proper name (capitalised word ≥3 chars), or a question mark
_RE_HOOK = re.compile(r'(\d+|[A-Z][a-z]{2,}|\?)')


@dataclass
class CheckResult:
    passed: bool
    reason: str = ""
    metrics: dict = field(default_factory=dict)

    def __bool__(self):
        return self.passed


def _first_sentences(text: str, count: int = 2) -> str:
    """Extract the first N sentences from text."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return " ".join(sentences[:count])


def _last_paragraph(text: str) -> str:
    """Extract the last paragraph from text."""
    paragraphs = [p.strip() for p in text.strip().split("\n\n") if p.strip()]
    return paragraphs[-1] if paragraphs else ""


def run(fixture: dict) -> CheckResult:
    """Run structure check: hook in first sentences, strong ending."""
    text = fixture.get("script_text", "")
    if not text:
        return CheckResult(passed=False, reason="empty script")

    metrics = {}

    # Check 1: hook — first two sentences must have number, name, or question
    opening = _first_sentences(text, 2)
    has_hook = bool(_RE_HOOK.search(opening))
    metrics["has_hook"] = has_hook
    metrics["opening"] = opening[:100]

    # Check 2: ending — no denylist phrases in last paragraph
    ending = _last_paragraph(text)
    lower_ending = ending.lower()
    denied = [p for p in ENDING_DENYLIST if p in lower_ending]
    metrics["ending_clean"] = len(denied) == 0
    metrics["ending_denied_phrases"] = denied

    if not has_hook and denied:
        return CheckResult(
            passed=False,
            reason=f"no hook in opening; ending has: {', '.join(denied)}",
            metrics=metrics,
        )
    if not has_hook:
        return CheckResult(
            passed=False,
            reason="no number, name, or question in first two sentences",
            metrics=metrics,
        )
    if denied:
        return CheckResult(
            passed=False,
            reason=f"ending denylist hit: {', '.join(denied)}",
            metrics=metrics,
        )

    return CheckResult(
        passed=True,
        reason="hook present, ending clean",
        metrics=metrics,
    )
