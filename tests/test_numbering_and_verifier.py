"""Phase 2 tests: episode-number registry (P1.4) and verifier error status (P1.2).

Each behaviour has a known-bad twin proving the assertion can fail.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def _mp3(audio_dir, slug):
    (audio_dir / f"{slug}.podcast.mp3").write_bytes(b"ID3fake")


def _report(audio_dir, slug, passed=True, failures=None):
    (audio_dir / f"{slug}.quality_report.json").write_text(
        json.dumps({"passed": passed, "blocking_failures": failures or []}),
        encoding="utf-8")


# ---------------------------------------------------------------------------
# P1.4 — episode numbering from the union of local dir + episodes.json
# ---------------------------------------------------------------------------

class TestNextEpisodeNumber:
    def test_union_of_local_and_registry(self, tmp_path):
        import video_downloader as v
        _mp3(tmp_path, "ep127-local")
        episodes = tmp_path / "episodes.json"
        episodes.write_text(json.dumps({"ep128-published": {"title": "P"}}), encoding="utf-8")
        # 128 is only in the registry, not the local dir → next must clear it.
        assert v._next_episode_number(tmp_path, episodes_json=episodes) == 129

    def test_local_only_when_registry_missing(self, tmp_path):
        import video_downloader as v
        _mp3(tmp_path, "ep127-local")
        assert v._next_episode_number(tmp_path, episodes_json=tmp_path / "none.json") == 128

    def test_registry_only_when_local_empty(self, tmp_path):
        import video_downloader as v
        episodes = tmp_path / "episodes.json"
        episodes.write_text(json.dumps({"ep200-x": {}}), encoding="utf-8")
        assert v._next_episode_number(tmp_path, episodes_json=episodes) == 201


# ---------------------------------------------------------------------------
# P1.4 — duplicate-number assertion in the publish gate
# ---------------------------------------------------------------------------

class TestDuplicateNumbers:
    def test_find_duplicate_numbers(self):
        from checks.publish_gate import find_duplicate_numbers
        dups = find_duplicate_numbers(["ep01-a", "ep01-b", "ep02-c", "ep03-d", "ep03-e"])
        assert set(dups.keys()) == {1, 3}
        assert dups[1] == ["ep01-a", "ep01-b"]

    def test_no_duplicates_when_unique(self):
        from checks.publish_gate import find_duplicate_numbers
        assert find_duplicate_numbers(["ep01-a", "ep02-b", "ep03-c"]) == {}

    def test_gate_blocks_duplicate_number(self, tmp_path):
        from checks.publish_gate import run_publish_gate
        _mp3(tmp_path, "ep05-first"); _report(tmp_path, "ep05-first", passed=True)
        _mp3(tmp_path, "ep05-second"); _report(tmp_path, "ep05-second", passed=True)
        result = run_publish_gate(tmp_path)
        assert 5 in result.duplicate_numbers
        # Both pass quality but collide on the number → both held back.
        assert set(result.blocked_slugs) == {"ep05-first", "ep05-second"}
        assert any("duplicate episode number ep5" in v.reason for v in result.needs_review)

    def test_override_admits_legacy_duplicate(self, tmp_path):
        from checks.publish_gate import run_publish_gate
        _mp3(tmp_path, "ep05-first"); _report(tmp_path, "ep05-first", passed=True)
        _mp3(tmp_path, "ep05-second"); _report(tmp_path, "ep05-second", passed=True)
        overrides = tmp_path / "publish_overrides.json"
        overrides.write_text(json.dumps({
            "ep05-first": "grandfathered", "ep05-second": "grandfathered"}), encoding="utf-8")
        result = run_publish_gate(tmp_path, overrides_path=overrides)
        assert result.blocked_slugs == []  # admitted despite the collision


# ---------------------------------------------------------------------------
# P1.2 — a verifier that returns no verdict must not pass at the publish gate
# ---------------------------------------------------------------------------

class TestVerificationErrorBlocksPublish:
    def test_error_verification_report_blocks(self, tmp_path):
        from checks.publish_gate import evaluate_episode
        _mp3(tmp_path, "ep10-x"); _report(tmp_path, "ep10-x", passed=True)
        (tmp_path / "ep10-x.podcast.verification_report.json").write_text(
            json.dumps({"passed": False, "status": "error",
                        "error": "verifier returned no JSON array"}), encoding="utf-8")
        v = evaluate_episode("ep10-x", tmp_path)
        assert not v.publishable
        assert "not performed" in v.reason

    def test_ok_verification_report_publishes(self, tmp_path):
        from checks.publish_gate import evaluate_episode
        _mp3(tmp_path, "ep11-x"); _report(tmp_path, "ep11-x", passed=True)
        (tmp_path / "ep11-x.podcast.verification_report.json").write_text(
            json.dumps({"passed": True, "status": "ok", "high_confidence": 0}),
            encoding="utf-8")
        assert evaluate_episode("ep11-x", tmp_path).publishable


class TestVerificationStageRecordsError:
    """_run_verification_stage writes a failing report when the verifier errors."""

    def test_prose_response_writes_error_report(self, monkeypatch, tmp_path):
        import video_downloader as v
        import pipeline_stages
        # Verifier returns prose (no JSON array) → verify_script reports error.
        monkeypatch.setattr(pipeline_stages, "call_verifier",
                            lambda s, u, **kw: "Everything looks fine to me.")
        script_path = tmp_path / "ep1.podcast.txt"
        script_path.write_text("script", encoding="utf-8")
        evidence = [{"claim": "c", "confidence": "high"}]

        result = v._run_verification_stage("script", evidence, script_path)
        assert result["status"] == "error"
        assert result["passed"] is False
        report = json.loads(
            (tmp_path / "ep1.podcast.verification_report.json").read_text(encoding="utf-8"))
        assert report["status"] == "error"

    def test_valid_response_writes_passing_report(self, monkeypatch, tmp_path):
        import video_downloader as v
        import pipeline_stages
        monkeypatch.setattr(pipeline_stages, "call_verifier",
                            lambda s, u, **kw: "[]")  # empty array = no claims flagged
        script_path = tmp_path / "ep2.podcast.txt"
        script_path.write_text("script", encoding="utf-8")
        result = v._run_verification_stage("script", [{"claim": "c"}], script_path)
        assert result["status"] == "ok"
        assert result["passed"] is True


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
