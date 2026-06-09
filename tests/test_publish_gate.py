"""Tests for the publish gate (P0.2) — nothing ships unless it earned it.

Each behaviour has a known-good and a known-bad twin so the test can fail.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def _write_episode(audio_dir, slug, *, report=None, verification=None, mp3=True):
    """Create an episode's files in a fake audio dir."""
    if mp3:
        (audio_dir / f"{slug}.podcast.mp3").write_bytes(b"ID3fake-audio")
    if report is not None:
        (audio_dir / f"{slug}.quality_report.json").write_text(
            json.dumps(report), encoding="utf-8")
    if verification is not None:
        (audio_dir / f"{slug}.podcast.verification_report.json").write_text(
            json.dumps(verification), encoding="utf-8")


class TestEvaluateEpisode:
    def test_missing_report_blocks(self, tmp_path):
        from checks.publish_gate import evaluate_episode
        _write_episode(tmp_path, "ep10-x")  # no report
        v = evaluate_episode("ep10-x", tmp_path)
        assert not v.publishable
        assert "no quality_report" in v.reason

    def test_failing_report_blocks_and_names_check(self, tmp_path):
        from checks.publish_gate import evaluate_episode
        _write_episode(tmp_path, "ep11-x",
                       report={"passed": False,
                               "blocking_failures": ["substance: only 0.0 numbers/1k"]})
        v = evaluate_episode("ep11-x", tmp_path)
        assert not v.publishable
        assert "substance" in v.reason  # names the failing check

    def test_passing_report_publishes(self, tmp_path):
        from checks.publish_gate import evaluate_episode
        _write_episode(tmp_path, "ep12-x", report={"passed": True, "blocking_failures": []})
        v = evaluate_episode("ep12-x", tmp_path)
        assert v.publishable
        assert not v.overridden

    def test_failing_verification_blocks_even_with_passing_quality(self, tmp_path):
        from checks.publish_gate import evaluate_episode
        _write_episode(tmp_path, "ep13-x",
                       report={"passed": True, "blocking_failures": []},
                       verification={"passed": False, "high_confidence": 4})
        v = evaluate_episode("ep13-x", tmp_path)
        assert not v.publishable
        assert "verification" in v.reason

    def test_passing_verification_still_publishes(self, tmp_path):
        from checks.publish_gate import evaluate_episode
        _write_episode(tmp_path, "ep14-x",
                       report={"passed": True, "blocking_failures": []},
                       verification={"passed": True, "high_confidence": 0})
        assert evaluate_episode("ep14-x", tmp_path).publishable

    def test_override_admits_failing_episode_with_logged_reason(self, tmp_path):
        from checks.publish_gate import evaluate_episode
        _write_episode(tmp_path, "ep15-x", report={"passed": False, "blocking_failures": ["x"]})
        v = evaluate_episode("ep15-x", tmp_path,
                             overrides={"ep15-x": "manual: host approved"})
        assert v.publishable
        assert v.overridden
        assert "manual: host approved" in v.reason


class TestRunPublishGate:
    def test_partitions_good_and_bad(self, tmp_path):
        from checks.publish_gate import run_publish_gate
        _write_episode(tmp_path, "ep01-good", report={"passed": True, "blocking_failures": []})
        _write_episode(tmp_path, "ep02-bad", report={"passed": False, "blocking_failures": ["loudness"]})
        _write_episode(tmp_path, "ep03-noreport")  # missing report

        result = run_publish_gate(tmp_path)
        assert "ep01-good" in result.publishable_slugs
        assert set(result.blocked_slugs) == {"ep02-bad", "ep03-noreport"}

    def test_override_file_admits_blocked_episode(self, tmp_path):
        from checks.publish_gate import run_publish_gate
        _write_episode(tmp_path, "ep02-bad", report={"passed": False, "blocking_failures": ["loudness"]})
        overrides = tmp_path / "publish_overrides.json"
        overrides.write_text(json.dumps({"ep02-bad": "grandfathered"}), encoding="utf-8")

        result = run_publish_gate(tmp_path, overrides_path=overrides)
        assert result.blocked_slugs == []
        assert "ep02-bad" in result.publishable_slugs

    def test_empty_dir_is_safe(self, tmp_path):
        from checks.publish_gate import run_publish_gate
        result = run_publish_gate(tmp_path)
        assert result.publishable == [] and result.needs_review == []


class TestRssExclude:
    """generate_rss --exclude keeps blocked episodes out of the feed."""

    def test_excluded_slug_omitted(self, tmp_path):
        import generate_rss
        _write_episode(tmp_path, "ep01-keep", mp3=True)
        _write_episode(tmp_path, "ep02-drop", mp3=True)

        kept = generate_rss.find_podcast_episodes(tmp_path, exclude={"ep02-drop"})
        names = {e["mp3_filename"] for e in kept}
        assert "ep01-keep.podcast.mp3" in names
        assert "ep02-drop.podcast.mp3" not in names

    def test_no_exclude_keeps_all(self, tmp_path):
        import generate_rss
        _write_episode(tmp_path, "ep01-keep", mp3=True)
        _write_episode(tmp_path, "ep02-drop", mp3=True)
        kept = generate_rss.find_podcast_episodes(tmp_path)
        assert len(kept) == 2


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
