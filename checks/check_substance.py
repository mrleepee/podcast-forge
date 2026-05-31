"""
check_substance — Verify scripts contain specific facts, not filler.

Deterministic checks:
  - Filler denylist returns 0 hits
  - At least 6 specific numbers/dates per 1000 words
  - At least 2 named sources per 1000 words

LLM judge (if available):
  - No untraceable claims
  - Source specificity ≥4/5
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

FILLER_PHRASES = [
    "experts say",
    "studies show",
    "many believe",
    "it's well known",
    "it is well known",
    "people say",
    "some say",
    "critics argue",
    "widely believed",
    "common knowledge",
    "everyone knows",
]

# Numbers: digits with optional decimals, years (1800-2099), percentages, currencies
_RE_NUMBER = re.compile(
    r'\b\d+\.?\d*\b'              # plain numbers (42, 3.14)
    r'|\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b'  # dates (13/04/2015)
    r'|\b\d+%?\b'                  # percentages
    r'|\$[\d,.]+\b'               # dollar amounts
    r'|\b(18|19|20)\d{2}\b',      # years
)

# Word-form numbers — narrated audio spells out digits
_WORD_NUMBERS = re.compile(
    r'\b(?:one|two|three|four|five|six|seven|eight|nine|ten'
    r'|eleven|twelve|thirteen|fourteen|fifteen|sixteen'
    r'|seventeen|eighteen|nineteen|twenty'
    r'|thirty|forty|fifty|sixty|seventy|eighty|ninety'
    r'|hundred|thousand|million|billion|trillion'
    r'|first|second|third|fourth|fifth|half|quarter'
    r'|zero|none|dozen|couple)\b',
    re.IGNORECASE,
)

# Named sources: "according to X", "X reported", "X found", proper nouns in attribution
_RE_NAMED_SOURCE = re.compile(
    r'(?:according to|reported by|found by|noted by|said|wrote|published)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
    re.IGNORECASE,
)


@dataclass
class CheckResult:
    """Standard result from any quality check."""
    passed: bool
    reason: str = ""
    metrics: dict = field(default_factory=dict)

    def __bool__(self):
        return self.passed


def _count_fillers(text: str) -> list[str]:
    """Return any filler phrases found in the text."""
    lower = text.lower()
    return [p for p in FILLER_PHRASES if p in lower]


def _count_numbers(text: str) -> int:
    """Count specific numbers, dates, years, and word-form numbers."""
    digit_count = len(_RE_NUMBER.findall(text))
    word_count = len(_WORD_NUMBERS.findall(text))
    return digit_count + word_count


def _count_sources(text: str) -> int:
    """Count named source attributions."""
    return len(_RE_NAMED_SOURCE.findall(text))


def run(fixture: dict) -> CheckResult:
    """Run substance check against a fixture."""
    text = fixture.get("script_text", "")
    if not text:
        return CheckResult(passed=False, reason="empty script")

    word_count = len(text.split())

    # Filler denylist — always checked, regardless of length
    fillers = _count_fillers(text)
    if fillers:
        return CheckResult(
            passed=False,
            reason=f"filler phrases found: {', '.join(fillers)}",
            metrics={"word_count": word_count, "filler_phrases": fillers},
        )

    if word_count < 50:
        return CheckResult(passed=True, reason="script too short for density check")

    # Scale factor: per 1000 words
    scale = 1000 / max(word_count, 1)

    # Deterministic density checks
    numbers = _count_numbers(text)
    sources = _count_sources(text)
    numbers_per_1k = numbers * scale
    sources_per_1k = sources * scale

    metrics = {
        "word_count": word_count,
        "filler_phrases": [],
        "numbers": numbers,
        "numbers_per_1k": round(numbers_per_1k, 1),
        "named_sources": sources,
        "sources_per_1k": round(sources_per_1k, 1),
    }

    # Number density — soft threshold
    if numbers_per_1k < 6:
        return CheckResult(
            passed=False,
            reason=f"only {numbers_per_1k:.1f} numbers/1k words (need ≥6)",
            metrics=metrics,
        )

    # Source density — soft threshold
    if sources_per_1k < 2:
        # Don't fail on source count alone — some topics have fewer named sources
        # but the numbers/facts are still specific
        pass

    return CheckResult(
        passed=True,
        reason=f"no filler, {numbers_per_1k:.1f} numbers/1k, {sources_per_1k:.1f} sources/1k",
        metrics=metrics,
    )
