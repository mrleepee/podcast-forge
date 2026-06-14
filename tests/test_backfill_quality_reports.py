"""Tests for tools/backfill_quality_reports.py — legacy report regeneration.

Unit tests stub the gate so slug-discovery, IO, dry-run and exit-code logic are
checked independently of the checks themselves; one end-to-end test runs the
real ``run_quality_gate`` against a passing script to prove the wiring writes a
valid green report.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from checks.quality_gate import QualityReport  # noqa: E402
import backfill_quality_reports as bf  # noqa: E402


def _write_script(audio_dir, slug, text="hello"):
    (audio_dir / f"{slug}.podcast.txt").write_text(text, encoding="utf-8")


def _fake_gate(passed=True, failures=None):
    """A gate_runner stub returning a canned QualityReport, recording its call."""
    def runner(script_text, audio_path=None):
        runner.calls.append({"script_text": script_text, "audio_path": audio_path})
        return QualityReport(passed=passed,
                             checks={"stub": {"passed": passed}},
                             blocking_failures=failures or [])
    runner.calls = []
    return runner


class TestBackfillSlug:
    def test_writes_passing_report(self, tmp_path):
        _write_script(tmp_path, "ep1", "script body")
        r = bf.backfill_slug("ep1", tmp_path, gate_runner=_fake_gate(passed=True))
        assert r["status"] == "passed" and r["passed"] is True
        written = json.loads((tmp_path / "ep1.quality_report.json").read_text())
        assert written["passed"] is True

    def test_failed_report_still_written_with_failures(self, tmp_path):
        _write_script(tmp_path, "ep1")
        gate = _fake_gate(passed=False, failures=["loudness: LUFS=-20.0"])
        r = bf.backfill_slug("ep1", tmp_path, gate_runner=gate)
        assert r["status"] == "failed"
        assert r["failures"] == ["loudness: LUFS=-20.0"]
        written = json.loads((tmp_path / "ep1.quality_report.json").read_text())
        assert written["passed"] is False
        assert written["blocking_failures"] == ["loudness: LUFS=-20.0"]

    def test_missing_script_is_error_and_writes_nothing(self, tmp_path):
        r = bf.backfill_slug("ghost", tmp_path, gate_runner=_fake_gate())
        assert r["status"] == "error"
        assert "missing script" in r["error"]
        assert not (tmp_path / "ghost.quality_report.json").exists()

    def test_dry_run_writes_nothing(self, tmp_path):
        _write_script(tmp_path, "ep1")
        r = bf.backfill_slug("ep1", tmp_path, dry_run=True, gate_runner=_fake_gate(True))
        assert r["status"] == "passed"
        assert not (tmp_path / "ep1.quality_report.json").exists()

    def test_audio_path_passed_only_when_mp3_exists(self, tmp_path):
        _write_script(tmp_path, "withmp3", "s")
        _write_script(tmp_path, "nomp3", "s")
        (tmp_path / "withmp3.podcast.mp3").write_bytes(b"")
        g1 = _fake_gate()
        bf.backfill_slug("withmp3", tmp_path, gate_runner=g1)
        g2 = _fake_gate()
        bf.backfill_slug("nomp3", tmp_path, gate_runner=g2)
        assert g1.calls[0]["audio_path"] is not None
        assert g2.calls[0]["audio_path"] is None


class TestSelectSlugs:
    def _seed(self, tmp_path):
        for s in ("ep1", "ep2", "ep3"):
            (tmp_path / f"{s}.podcast.mp3").write_bytes(b"")
        (tmp_path / "ep1.quality_report.json").write_text("{}")  # already reported

    def test_all_picks_only_missing(self, tmp_path):
        self._seed(tmp_path)
        assert bf.select_slugs(tmp_path, [], all_missing=True, force=False) == ["ep2", "ep3"]

    def test_all_force_picks_every_mp3(self, tmp_path):
        self._seed(tmp_path)
        assert bf.select_slugs(tmp_path, [], all_missing=True, force=True) == ["ep1", "ep2", "ep3"]

    def test_explicit_slugs_returned_verbatim(self, tmp_path):
        self._seed(tmp_path)
        assert bf.select_slugs(tmp_path, ["ep2", "ghost"], all_missing=False, force=False) == ["ep2", "ghost"]


# A script that clears every deterministic check: ≥6 numbers/1k words, a hook
# (a number) in the first sentence, no filler phrases, no denylisted ending,
# no speaker labels (solo), and no risky tokens. No MP3 → loudness is skipped.
PASSING_SCRIPT = (
    "In 2026, the team shipped version 4.2 of the platform. Over 90 percent of "
    "the 1500 active users adopted it within 30 days. The release closed 47 "
    "tickets and cut median latency from 220 milliseconds to 95 milliseconds. "
    "A reviewer at the journal noted that the redesign addressed three "
    "long-standing issues. The roadmap lists five more milestones for the year. "
    "Engineers credited the rapid turnaround to a tighter review loop and a "
    "smaller, focused team. The project began in March with a staff of 8 and "
    "grew to 12 by June. Documentation covered 23 modules, and the changelog "
    "tallied 64 entries. Adoption outpaced the 2024 launch by a wide margin."
)


class TestEndToEndWithRealGate:
    def test_passing_script_writes_green_report(self, tmp_path):
        _write_script(tmp_path, "ep99", PASSING_SCRIPT)  # no mp3 -> loudness skipped
        r = bf.backfill_slug("ep99", tmp_path)  # real run_quality_gate
        assert r["status"] == "passed", r
        written = json.loads((tmp_path / "ep99.quality_report.json").read_text())
        assert written["passed"] is True
        # every deterministic check ran and is represented in the report
        assert {"pronunciation", "substance", "structure", "dialogue"} <= set(written["checks"])


class TestMain:
    def test_exit_zero_when_all_pass(self, tmp_path, monkeypatch):
        _write_script(tmp_path, "ep1", PASSING_SCRIPT)
        monkeypatch.setattr(bf, "DEFAULT_AUDIO_DIR", tmp_path)
        assert bf.main(["ep1"]) == 0

    def test_exit_nonzero_on_failure(self, tmp_path, monkeypatch):
        # Empty script fails substance ("empty script") and structure.
        _write_script(tmp_path, "ep1", "")
        monkeypatch.setattr(bf, "DEFAULT_AUDIO_DIR", tmp_path)
        assert bf.main(["ep1"]) == 1

    def test_missing_audio_dir_returns_two(self, tmp_path):
        assert bf.main(["ep1", "--audio-dir", str(tmp_path / "nope")]) == 2


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
