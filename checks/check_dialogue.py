"""
check_dialogue — Two-host dialogue quality check.

Applies only to duo scripts (detected by speaker labels like "Host:" or
"Co-host:"). Solo scripts are skipped with PASS.

Deterministic checks:
  - Every turn ends with terminal punctuation (. ! ?)
  - Every turn is at least 4 words
  - No adjacent turns share >50% token overlap (echo detector)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Detect duo scripts by looking for speaker labels
_RE_SPEAKER = re.compile(r'^(?:Host|Co-host|Speaker\s*\d?|A|B)\s*:', re.MULTILINE)

_RE_TURN = re.compile(
    r'^(?:Host|Co-host|Speaker\s*\d?|A|B)\s*:\s*(.+)$',
    re.MULTILINE,
)

TERMINAL_PUNCT = {'.', '!', '?'}
MIN_TURN_WORDS = 4
ECHO_THRESHOLD = 0.5


@dataclass
class CheckResult:
    passed: bool
    reason: str = ""
    metrics: dict = field(default_factory=dict)

    def __bool__(self):
        return self.passed


def _is_duo_script(text: str) -> bool:
    """Return True if the script contains speaker labels."""
    return bool(_RE_SPEAKER.search(text))


def _extract_turns(text: str) -> list[str]:
    """Extract all dialogue turns (text after speaker labels)."""
    return [m.group(1).strip() for m in _RE_TURN.finditer(text)]


def _token_overlap(a: str, b: str) -> float:
    """Jaccard-like token overlap between two strings."""
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def run(fixture: dict) -> CheckResult:
    """Run dialogue quality check. Skips solo scripts."""
    text = fixture.get("script_text", "")
    if not text:
        return CheckResult(passed=False, reason="empty script")

    # Solo scripts — not applicable
    if not _is_duo_script(text):
        return CheckResult(
            passed=True,
            reason="solo episode (not applicable)",
            metrics={"duo": False},
        )

    turns = _extract_turns(text)
    if len(turns) < 2:
        return CheckResult(
            passed=True,
            reason="too few turns to check",
            metrics={"duo": True, "turns": len(turns)},
        )

    fragments = []
    echo_pairs = []

    for i, turn in enumerate(turns):
        # Fragment check: must end with terminal punctuation
        if turn[-1] not in TERMINAL_PUNCT:
            fragments.append((i + 1, turn[:60]))

        # Short turn check: minimum word count
        if len(turn.split()) < MIN_TURN_WORDS:
            fragments.append((i + 1, f"too short ({len(turn.split())} words): {turn[:60]}"))

    # Echo detection: adjacent turns
    for i in range(len(turns) - 1):
        overlap = _token_overlap(turns[i], turns[i + 1])
        if overlap > ECHO_THRESHOLD:
            echo_pairs.append((i + 1, i + 2, round(overlap, 2)))

    metrics = {
        "duo": True,
        "turns": len(turns),
        "fragments": len(fragments),
        "echo_pairs": len(echo_pairs),
    }

    if fragments:
        details = "; ".join(f"turn {n}: {t}" for n, t in fragments[:3])
        return CheckResult(
            passed=False,
            reason=f"{len(fragments)} fragment(s): {details}",
            metrics=metrics,
        )

    if echo_pairs:
        details = "; ".join(f"turns {a}-{b} ({o:.0%})" for a, b, o in echo_pairs[:3])
        return CheckResult(
            passed=False,
            reason=f"{len(echo_pairs)} echo pair(s): {details}",
            metrics=metrics,
        )

    return CheckResult(
        passed=True,
        reason=f"{len(turns)} turns, no fragments, no echoes",
        metrics=metrics,
    )
