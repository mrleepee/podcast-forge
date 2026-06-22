"""Phase 7 tests: opening-check revision trigger (P4.2), feed verification (P4.3),
and LUFS persistence (P4.4). Each has a known-bad twin."""
import base64
import json
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def _completed(returncode=0, stdout="", stderr=""):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# P4.2 — a stale opening triggers a QA revision (not just a printed shrug)
# ---------------------------------------------------------------------------

class TestOpeningTriggersRevision:
    def _patch_qa_pass(self, monkeypatch):
        from checks.quality_gate import QualityReport
        import checks.quality_gate as qg
        monkeypatch.setattr(qg, "run_quality_gate",
                            lambda *a, **k: QualityReport(passed=True, checks={}, blocking_failures=[]))

    def test_stale_opening_forces_redraft(self, monkeypatch, tmp_path):
        import video_downloader as v
        import pipeline_stages
        self._patch_qa_pass(monkeypatch)
        # QA passes, but the opening is stale until the script is re-drafted.
        monkeypatch.setattr(v, "_check_opening_freshness",
                            lambda text: None if "Revised" in text else "too similar to recent")
        monkeypatch.setattr(pipeline_stages, "draft_script",
                            lambda *a, **k: "Revised fresh hook here")
        monkeypatch.setattr(v, "_polish_for_tts", lambda t, language="en", duo=False: t)
        # Neutralize the post-draft humanize step (LLM transform) so the test
        # asserts on the re-drafted text, not a humanizer rewrite.
        monkeypatch.setattr(v, "humanize_script", lambda t, *, language="en": t)

        script_path = tmp_path / "ep.podcast.txt"
        script_path.write_text("Original stale opening", encoding="utf-8")
        final = v._run_qa_revision_loop("Original stale opening", script_path, {}, [],
                                        "", "", "", 700, False, max_revisions=3)
        assert "Revised" in final  # the stale opening was revised away

    def test_fresh_opening_no_revision(self, monkeypatch, tmp_path):
        """Known-bad twin: QA passes and the opening is already fresh → no revision."""
        import video_downloader as v
        import pipeline_stages
        self._patch_qa_pass(monkeypatch)
        monkeypatch.setattr(v, "_check_opening_freshness", lambda text: None)

        def _should_not_draft(*a, **k):
            raise AssertionError("draft_script should not be called for a fresh opening")
        monkeypatch.setattr(pipeline_stages, "draft_script", _should_not_draft)

        script_path = tmp_path / "ep.podcast.txt"
        script_path.write_text("A fresh, original opening", encoding="utf-8")
        final = v._run_qa_revision_loop("A fresh, original opening", script_path, {}, [],
                                        "", "", "", 700, False, max_revisions=3)
        assert final == "A fresh, original opening"

    def test_freshness_helper_is_best_effort(self, monkeypatch):
        import video_downloader as v
        # When the opening check blows up, the helper returns None (never raises).
        import checks.check_opening as co
        monkeypatch.setattr(co, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        assert v._check_opening_freshness("anything") is None


# ---------------------------------------------------------------------------
# P4.3 — verify the feed actually landed after the API-fallback publish
# ---------------------------------------------------------------------------

class TestVerifyFeedLanded:
    def _patch_remote(self, monkeypatch, content_bytes=None, returncode=0):
        import video_downloader as v
        stdout = base64.b64encode(content_bytes).decode() if content_bytes is not None else ""
        monkeypatch.setattr(v.subprocess, "run",
                            lambda *a, **k: _completed(returncode=returncode, stdout=stdout))

    def test_match_returns_true(self, monkeypatch, tmp_path):
        import video_downloader as v
        feed = tmp_path / "feed.xml"
        feed.write_bytes(b"<rss>same</rss>")
        self._patch_remote(monkeypatch, content_bytes=b"<rss>same</rss>")
        assert v._verify_feed_landed(local_feed=feed) is True

    def test_mismatch_returns_false(self, monkeypatch, tmp_path):
        import video_downloader as v
        feed = tmp_path / "feed.xml"
        feed.write_bytes(b"<rss>local</rss>")
        self._patch_remote(monkeypatch, content_bytes=b"<rss>REMOTE-DIFFERENT</rss>")
        assert v._verify_feed_landed(local_feed=feed) is False

    def test_api_error_returns_false(self, monkeypatch, tmp_path):
        import video_downloader as v
        feed = tmp_path / "feed.xml"
        feed.write_bytes(b"<rss>x</rss>")
        self._patch_remote(monkeypatch, returncode=1)
        assert v._verify_feed_landed(local_feed=feed) is False

    def test_missing_local_returns_false(self, monkeypatch, tmp_path):
        import video_downloader as v
        assert v._verify_feed_landed(local_feed=tmp_path / "nope.xml") is False


# ---------------------------------------------------------------------------
# P4.4 — persist the measured LUFS into episodes.json
# ---------------------------------------------------------------------------

class TestRecordLufs:
    def test_writes_lufs_preserving_other_fields(self, tmp_path):
        import video_downloader as v
        ep = tmp_path / "episodes.json"
        ep.write_text(json.dumps({"ep5-x": {"title": "X", "description": "d"}}), encoding="utf-8")
        v._record_episode_lufs("ep5-x", -16.047, episodes_json=ep)
        data = json.loads(ep.read_text(encoding="utf-8"))
        assert data["ep5-x"]["lufs"] == -16.0
        assert data["ep5-x"]["title"] == "X"  # untouched

    def test_none_is_noop(self, tmp_path):
        import video_downloader as v
        ep = tmp_path / "episodes.json"
        ep.write_text(json.dumps({"ep5-x": {"title": "X"}}), encoding="utf-8")
        v._record_episode_lufs("ep5-x", None, episodes_json=ep)
        assert "lufs" not in json.loads(ep.read_text(encoding="utf-8"))["ep5-x"]

    def test_creates_entry_when_absent(self, tmp_path):
        import video_downloader as v
        ep = tmp_path / "episodes.json"
        ep.write_text(json.dumps({}), encoding="utf-8")
        v._record_episode_lufs("ep9-new", -15.9, episodes_json=ep)
        assert json.loads(ep.read_text(encoding="utf-8"))["ep9-new"]["lufs"] == -15.9


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
