"""
check_opening — Verify podcast opening sentence is fresh, not a repeated formula.

Tracks first sentences across episodes. Flags new openings that are too
similar to existing ones (same opening word + high token overlap).

Similarity check:
  1. First-word match: if the new opening starts with the same word as
     N recent episodes, flag it (e.g., "Imagine..." used 4 times).
  2. Jaccard overlap: after stripping common English stopwords, compute
     token overlap with every recent opening. Flag if similarity > 0.5.

The check passes when the opening is sufficiently different from recent
episodes. It warns (but does not fail) on moderate similarity.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# Stopwords to strip before computing Jaccard similarity
STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "it", "its",
    "you", "your", "he", "she", "they", "we", "i", "me", "my", "that",
    "this", "these", "those", "what", "which", "who", "whom", "how",
    "when", "where", "why", "not", "no", "nor", "if", "then", "so",
    "just", "than", "too", "very", "also", "about", "up", "out", "over",
    "into", "some", "such", "each", "every", "own", "other", "more", "most",
})

# How many recent openings to compare against
RECENT_WINDOW = 10

# Thresholds
FIRST_WORD_MAX_REPEATS = 2  # flag if same first word used N+ times in window
JACCARD_WARN = 0.4          # warn on overlap above this
JACCARD_FAIL = 0.6          # fail on overlap above this


@dataclass
class CheckResult:
    """Standard result from any quality check."""
    passed: bool
    reason: str = ""
    metrics: dict = field(default_factory=dict)

    def __bool__(self):
        return self.passed


def _extract_first_sentence(text: str) -> str:
    """Extract the first sentence from script text."""
    text = text.strip()
    if not text:
        return ""
    m = re.match(r'([^.!?]*[.!?])', text)
    return m.group(1).strip()[:300] if m else text[:300]


def _tokenize(sentence: str) -> set[str]:
    """Lowercase, strip stopwords, return meaningful token set."""
    words = re.findall(r"[a-z]+", sentence.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two token sets."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _load_opening_log(log_path: Path) -> dict[str, str]:
    """Load the opening log (episode slug → first sentence)."""
    if not log_path.exists():
        return {}
    data = json.loads(log_path.read_text(encoding="utf-8"))
    # Support both {slug: sentence} and {slug: {sentence: ...}} formats
    out = {}
    for k, v in data.items():
        out[k] = v["sentence"] if isinstance(v, dict) else v
    return out


def _get_recent_openings(log: dict[str, str], n: int = RECENT_WINDOW) -> list[str]:
    """Get the N most recent opening sentences from the log."""
    # Sort by key (ep numbers sort correctly with leading zeros)
    keys = sorted(log.keys(), reverse=True)
    return [log[k] for k in keys[:n] if log[k]]


def detect_first_word_repeats(new_opening: str, recent: list[str]) -> list[str]:
    """Check if the opening word is overused in recent episodes.

    Returns list of episodes that share the same first word.
    """
    first_word = re.match(r"[a-zA-Z]+", new_opening)
    if not first_word:
        return []
    word = first_word.group(0).lower()

    matches = []
    for opening in recent:
        ow = re.match(r"[a-zA-Z]+", opening)
        if ow and ow.group(0).lower() == word:
            matches.append(opening[:60])

    return matches


def compute_max_similarity(new_tokens: set[str],
                           recent: list[str]) -> tuple[float, str]:
    """Compute max Jaccard similarity against recent openings.

    Returns (max_similarity, most_similar_opening).
    """
    max_sim = 0.0
    best_match = ""
    for opening in recent:
        tokens = _tokenize(opening)
        sim = _jaccard(new_tokens, tokens)
        if sim > max_sim:
            max_sim = sim
            best_match = opening[:80]
    return max_sim, best_match


def run(fixture: dict, log_path: str | Path | None = None) -> CheckResult:
    """Run opening sentence uniqueness check.

    Args:
        fixture: dict with "script_text" and optional "episode_name"
        log_path: path to opening_log.json (default: checks/opening_log.json)
    """
    if log_path is None:
        log_path = Path(__file__).parent / "opening_log.json"
    else:
        log_path = Path(log_path)

    text = fixture.get("script_text", "")
    if not text:
        return CheckResult(passed=False, reason="empty script")

    opening = _extract_first_sentence(text)
    if not opening:
        return CheckResult(passed=False, reason="could not extract first sentence")

    new_tokens = _tokenize(opening)
    log = _load_opening_log(log_path)
    recent = _get_recent_openings(log)

    if not recent:
        return CheckResult(passed=True, reason="no previous openings to compare",
                          metrics={"opening": opening[:100], "previous_count": 0})

    issues = []

    # Check 1: first-word repetition
    first_word_matches = detect_first_word_repeats(opening, recent)
    if len(first_word_matches) >= FIRST_WORD_MAX_REPEATS:
        issues.append(
            f"opening word used {len(first_word_matches)} times in last "
            f"{len(recent)} episodes"
        )

    # Check 2: Jaccard similarity
    max_sim, best_match = compute_max_similarity(new_tokens, recent)
    if max_sim >= JACCARD_FAIL:
        issues.append(
            f"opening too similar to previous (similarity {max_sim:.0%}): "
            f"\"{best_match}\""
        )
    elif max_sim >= JACCARD_WARN:
        issues.append(
            f"opening moderately similar (similarity {max_sim:.0%}): "
            f"\"{best_match}\""
        )

    passed = len([i for i in issues if "too similar" in i or "opening word" in i]) == 0
    reason = "; ".join(issues) if issues else "opening is fresh"

    metrics = {
        "opening": opening[:100],
        "previous_count": len(recent),
        "max_similarity": round(max_sim, 2),
        "first_word_matches": len(first_word_matches),
    }

    return CheckResult(passed=passed, reason=reason, metrics=metrics)


def update_opening_log(log_path: str | Path, episode_slug: str,
                       first_sentence: str) -> None:
    """Add a new opening to the log after episode production."""
    log_path = Path(log_path)
    log = _load_opening_log(log_path)
    log[episode_slug] = first_sentence
    log_path.write_text(
        json.dumps(log, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
