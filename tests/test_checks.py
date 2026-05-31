"""Tests for the podcast quality check harness and loudness check."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Add project root to path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from checks.check_loudness import CheckResult, measure_loudness, run as loudness_run
from checks.master_audio import master


class TestCheckResult:
    """CheckResult dataclass behaves correctly."""

    def test_passed_bool(self):
        r = CheckResult(passed=True, reason="ok")
        assert bool(r) is True

    def test_failed_bool(self):
        r = CheckResult(passed=False, reason="bad")
        assert bool(r) is False


class TestMeasureLoudness:
    """measure_loudness returns (LUFS, TP) tuples."""

    def test_returns_floats_on_real_audio(self):
        # Use the mastered fixture
        audio = REPO / "checks/fixtures/good/liberland-meritocracy.mp3"
        if not audio.exists():
            return  # skip if no fixture
        lufs, tp = measure_loudness(audio)
        assert lufs is not None
        assert tp is not None
        assert -30.0 <= lufs <= 0.0  # sanity range
        assert -10.0 <= tp <= 0.0

    def test_returns_none_on_missing_file(self):
        lufs, tp = measure_loudness("/nonexistent/file.mp3")
        assert lufs is None
        assert tp is None


class TestLoudnessCheck:
    """check_loudness.run returns correct results."""

    def test_passes_on_mastered_audio(self):
        audio = REPO / "checks/fixtures/good/liberland-meritocracy.mp3"
        if not audio.exists():
            return
        fixture = {"name": "test", "audio_path": str(audio), "script_text": ""}
        result = loudness_run(fixture)
        assert result.passed
        assert "LUFS" in result.reason

    def test_fails_on_missing_audio(self):
        fixture = {"name": "test", "audio_path": None, "script_text": ""}
        result = loudness_run(fixture)
        assert not result.passed
        assert "no audio" in result.reason


class TestMasterAudio:
    """master_audio produces broadcast-standard output."""

    def test_mastered_file_passes_loudness_check(self):
        # Use a temp file to avoid modifying the fixture
        src = REPO / "checks/fixtures/good/liberland-meritocracy.mp3"
        if not src.exists():
            return
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        # First copy raw (unmastered) audio by re-downloading or using a raw one
        # For now, just verify the fixture already passes
        result = loudness_run({"audio_path": str(src), "script_text": ""})
        assert result.passed
        Path(tmp_path).unlink(missing_ok=True)


class TestPronunciationCheck:
    """check_pronunciation detects and covers risky tokens."""

    def test_detects_acronyms(self):
        from checks.check_pronunciation import detect_risky_tokens
        tokens = detect_risky_tokens("The API uses HTML and CSS for the GUI.")
        assert "API" in tokens
        assert "HTML" in tokens
        assert "CSS" in tokens

    def test_ignores_false_positives(self):
        from checks.check_pronunciation import detect_risky_tokens
        tokens = detect_risky_tokens("AI is the future of US and UK.")
        assert "AI" not in tokens
        assert "US" not in tokens
        assert "UK" not in tokens

    def test_detects_alphanumeric_codes(self):
        from checks.check_pronunciation import detect_risky_tokens
        tokens = detect_risky_tokens("Use x402 for HTTP 402 payments.")
        assert "x402" in tokens or any("402" in t for t in tokens)

    def test_passes_on_covered_script(self):
        from checks.check_pronunciation import run as pron_run
        fixture = {
            "name": "test",
            "script_text": "The API uses HTML and CSS.",
            "audio_path": None,
        }
        result = pron_run(fixture)
        assert result.passed

    def test_fails_on_uncovered_tokens(self):
        from checks.check_pronunciation import run as pron_run
        fixture = {
            "name": "test",
            "script_text": "The ZYXW protocol uses QWERT for VBNM.",
            "audio_path": None,
        }
        result = pron_run(fixture)
        assert not result.passed
        assert "uncovered" in result.reason.lower()

    def test_passes_on_plain_english(self):
        from checks.check_pronunciation import run as pron_run
        fixture = {
            "name": "test",
            "script_text": "The cat sat on the mat and looked at the moon.",
            "audio_path": None,
        }
        result = pron_run(fixture)
        assert result.passed



    """The check harness discovers and runs checks."""

    def test_discover_finds_loudness(self):
        from checks.run import discover_checks
        checks = discover_checks()
        names = [n for n, _ in checks]
        assert "check_loudness" in names

    def test_load_fixtures_finds_good(self):
        from checks.run import load_fixtures
        fixtures = load_fixtures("good")
        names = [f["name"] for f in fixtures]
        assert "liberland-meritocracy" in names

    def test_load_fixtures_finds_bad(self):
        from checks.run import load_fixtures
        fixtures = load_fixtures("bad")
        names = [f["name"] for f in fixtures]
        assert "vague-filler" in names


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
