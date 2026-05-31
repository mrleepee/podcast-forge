"""
check_pronunciation — Detect risky tokens and verify pronunciation coverage.

Risky tokens are acronyms, alphanumeric codes, and currency codes that
Kokoro might mispronounce. Every detected token must have a pronunciation
entry in the cache. The check passes when all risky tokens are covered.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# All-caps acronyms (2-6 letters) — main mispronunciation risk
_RE_ACRONYM = re.compile(r'\b([A-Z]{2,6})\b')

# Alphanumeric codes like x402, h264
_RE_CODE = re.compile(r'\b([a-zA-Z]\d{2,4})\b')

# HTTP status codes like "HTTP 402"
_RE_HTTP = re.compile(r'\b(HTTP\s*\d{3})\b', re.IGNORECASE)

# ISO currency codes
_RE_CURRENCY = re.compile(
    r'\b(USD|EUR|GBP|CHF|JPY|UGX|CZK|SEK|NOK|DKK|AUD|CAD|NZD|ZAR|INR)\b'
)

# Common English words that look like acronyms but aren't risky
FALSE_POSITIVES = frozenset({
    "AI", "AN", "THE", "AND", "OR", "NOT", "NO", "SO", "IF", "IS",
    "IT", "IN", "ON", "AT", "TO", "DO", "BE", "BY", "AS", "OF",
    "UP", "US", "HE", "WE", "ME", "MY", "GO", "UK", "UN", "EU",
    "AM", "PM",
})


@dataclass
class CheckResult:
    """Standard result from any quality check."""
    passed: bool
    reason: str = ""
    metrics: dict = field(default_factory=dict)

    def __bool__(self):
        return self.passed


def detect_risky_tokens(text: str) -> set[str]:
    """Find all pronunciation-risky tokens in a script.

    Detects: ALL-CAPS acronyms, alphanumeric codes (x402),
    HTTP status patterns, and ISO currency codes.
    """
    tokens = set()

    for m in _RE_ACRONYM.finditer(text):
        tok = m.group(1)
        if tok not in FALSE_POSITIVES:
            tokens.add(tok)

    for m in _RE_CODE.finditer(text):
        tokens.add(m.group(1).lower())

    for m in _RE_HTTP.finditer(text):
        tokens.add(m.group(1).replace(" ", "").upper())

    for m in _RE_CURRENCY.finditer(text):
        tokens.add(m.group(1))

    return tokens


def load_pronunciation_cache() -> set[str]:
    """Load known pronunciation entries (lowercase for matching)."""
    for name in ("pronunciation_cache.json", "pronunciation_golds.json"):
        path = Path(__file__).parent.parent / name
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return set(data.keys())
    return set()


def run(fixture: dict) -> CheckResult:
    """Run pronunciation coverage check against a fixture."""
    script_text = fixture.get("script_text", "")
    if not script_text:
        return CheckResult(passed=False, reason="empty script")

    risky = detect_risky_tokens(script_text)
    if not risky:
        return CheckResult(
            passed=True,
            reason="no risky tokens found",
            metrics={"risky_count": 0},
        )

    # Case-insensitive coverage check
    cache_lower = {k.lower() for k in load_pronunciation_cache()}
    uncovered = {t for t in risky if t.lower() not in cache_lower}

    metrics = {
        "risky_count": len(risky),
        "covered_count": len(risky) - len(uncovered),
        "uncovered_count": len(uncovered),
        "uncovered_tokens": sorted(uncovered),
    }

    if not uncovered:
        return CheckResult(
            passed=True,
            reason=f"{len(risky)} risky tokens, all covered",
            metrics=metrics,
        )

    return CheckResult(
        passed=False,
        reason=f"{len(uncovered)} uncovered: {', '.join(sorted(uncovered)[:5])}",
        metrics=metrics,
    )
