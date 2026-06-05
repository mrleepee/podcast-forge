"""Tests for the opening sentence uniqueness check."""
import json
import tempfile
from pathlib import Path

import sys
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from checks.check_opening import (
    _extract_first_sentence,
    _tokenize,
    _jaccard,
    detect_first_word_repeats,
    compute_max_similarity,
    run,
    update_opening_log,
)


class TestExtractFirstSentence:
    """First sentence extraction from script text."""

    def test_extracts_until_first_period(self):
        text = "The quick brown fox jumps. Then it stops. The end."
        assert _extract_first_sentence(text) == "The quick brown fox jumps."

    def test_extracts_until_question_mark(self):
        text = "What if money grew on trees? Nobody knows."
        assert _extract_first_sentence(text) == "What if money grew on trees?"

    def test_extracts_until_exclamation(self):
        text = "Freedom! That is the word."
        assert _extract_first_sentence(text) == "Freedom!"

    def test_handles_empty(self):
        assert _extract_first_sentence("") == ""

    def test_handles_whitespace(self):
        assert _extract_first_sentence("   Hello. World.  ") == "Hello."

    def test_no_terminal_punctuation(self):
        text = "Just a fragment of text without ending"
        assert _extract_first_sentence(text) == "Just a fragment of text without ending"


class TestTokenize:
    """Stopword-stripped tokenization for similarity comparison."""

    def test_strips_stopwords(self):
        tokens = _tokenize("The quick brown fox jumps over the lazy dog")
        assert "the" not in tokens
        assert "over" not in tokens
        assert "quick" in tokens
        assert "brown" in tokens

    def test_lowercase(self):
        tokens = _tokenize("Liberland CBDC Protocol")
        assert "liberland" in tokens
        assert "cbdc" in tokens

    def test_strips_short_words(self):
        tokens = _tokenize("A big AI tool is it on at to")
        assert "a" not in tokens
        assert "is" not in tokens
        # AI is 2 chars, kept (len > 2 is the filter, but "ai" is 2)
        # Actually len > 2 means 3+, so "ai" is stripped
        assert "ai" not in tokens

    def test_empty_string(self):
        assert _tokenize("") == set()


class TestJaccard:
    """Jaccard similarity computation."""

    def test_identical_sets(self):
        assert _jaccard({"a", "b", "c"}, {"a", "b", "c"}) == 1.0

    def test_disjoint_sets(self):
        assert _jaccard({"a", "b"}, {"c", "d"}) == 0.0

    def test_partial_overlap(self):
        sim = _jaccard({"a", "b", "c"}, {"b", "c", "d"})
        assert 0.0 < sim < 1.0
        assert abs(sim - 0.5) < 0.01  # 2 shared / 4 total

    def test_empty_both(self):
        assert _jaccard(set(), set()) == 1.0

    def test_one_empty(self):
        assert _jaccard({"a"}, set()) == 0.0


class TestFirstWordRepeats:
    """Detection of repeated opening words."""

    def test_detects_imagine_repeats(self):
        matches = detect_first_word_repeats(
            "Imagine a world where agents never die.",
            [
                "Imagine waking up to find your agent still running.",
                "Imagine you spent hours building something great.",
                "The quick brown fox.",
                "Imagine this scenario.",
            ],
        )
        assert len(matches) == 3

    def test_no_repeats(self):
        matches = detect_first_word_repeats(
            "In 2024, everything changed.",
            ["Imagine something.", "What if things were different.", "By then it was too late."],
        )
        assert len(matches) == 0

    def test_case_insensitive(self):
        matches = detect_first_word_repeats(
            "what if money was free?",
            ["What if the world ended?"],
        )
        assert len(matches) == 1


class TestOpeningCheck:
    """Full opening check against log."""

    def _make_log(self, entries: dict[str, str]) -> str:
        """Create a temp log file and return its path."""
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
        json.dump(entries, tmp)
        tmp.close()
        return tmp.name

    def test_fails_on_repeated_imagine(self):
        log = self._make_log({
            "ep1": "Imagine waking up every morning.",
            "ep2": "Imagine you spent hours building.",
            "ep3": "Imagine this scenario plays out.",
        })
        try:
            result = run({"script_text": "Imagine a new world of agents."}, log)
            assert not result.passed
            assert "opening word" in result.reason
        finally:
            Path(log).unlink()

    def test_passes_on_fresh_opening(self):
        log = self._make_log({
            "ep1": "Imagine waking up every morning.",
            "ep2": "What if the world ended?",
        })
        try:
            result = run({"script_text": "Eight hundred thousand people applied for citizenship."}, log)
            assert result.passed
        finally:
            Path(log).unlink()

    def test_passes_with_empty_log(self):
        log = self._make_log({})
        try:
            result = run({"script_text": "Something brand new and fresh."}, log)
            assert result.passed
        finally:
            Path(log).unlink()

    def test_update_log_preserves_entries(self):
        log = self._make_log({"ep1": "First opening."})
        try:
            update_opening_log(log, "ep2", "Second opening.")
            data = json.loads(Path(log).read_text())
            assert "ep1" in data
            assert data["ep2"] == "Second opening."
        finally:
            Path(log).unlink()

    def test_fails_on_high_similarity(self):
        log = self._make_log({
            "ep1": "Imagine waking up every morning with a colleague who reads your email.",
            "ep2": "Imagine waking up every morning with a system that scans your messages.",
            "ep3": "Imagine waking up every morning with a tool that digests your calendar.",
        })
        try:
            # Very similar structure and content words — high Jaccard + first word repeat
            result = run({"script_text": "Imagine waking up every morning with a bot that reads your email."}, log)
            assert not result.passed  # fails on first-word repeat (4 "Imagine" in window)
            assert "similar" in result.reason.lower()
        finally:
            Path(log).unlink()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
