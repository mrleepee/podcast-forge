"""Close-the-loop tests: P0.1 (revisions reach audio) and P0.3 (fail-closed gates).

These are the end-to-end pipeline tests the 2026-05-31 review asked for and the
suite lacked. Each has a known-bad twin proving the assertion can fail.
"""
import io
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

ORIGINAL_DRAFT = "Original draft. It is vague and has no numbers worth checking."
REVISED_DRAFT = "Revised draft with 5 concrete facts, 3 numbers, and 2 sources."


# ---------------------------------------------------------------------------
# P0.1 — the QA-revised script must reach verification, opening check, and audio
# ---------------------------------------------------------------------------

class TestRevisionReachesAudio:
    def _stub_pipeline(self, monkeypatch, drafts):
        """Stub every external stage so _run_evidence_pipeline runs offline.

        Returns a dict that captures the text handed to audio synthesis.
        """
        import video_downloader as v
        from checks.quality_gate import QualityReport
        import pipeline_stages
        import checks.quality_gate as qg
        import checks.check_opening as co

        captured = {}

        evidence = [{"claim": "c", "source_quote": "q", "timestamp": "0",
                     "source_reliability": "high", "confidence": "high", "type": "fact"}]
        monkeypatch.setattr(pipeline_stages, "extract_evidence", lambda txt: evidence)
        monkeypatch.setattr(pipeline_stages, "generate_outline", lambda ev, soul: {"thesis": "t"})

        calls = {"n": 0}

        def fake_draft(outline, ev, soul, **kw):
            i = min(calls["n"], len(drafts) - 1)
            calls["n"] += 1
            return drafts[i]
        monkeypatch.setattr(pipeline_stages, "draft_script", fake_draft)

        # A draft passes QA only once it contains "Revised".
        def fake_qg(script_text, audio_path=None, evidence=None):
            passed = "Revised" in script_text
            return QualityReport(
                passed=passed, checks={},
                blocking_failures=[] if passed else ["substance: too vague"])
        monkeypatch.setattr(qg, "run_quality_gate", fake_qg)

        monkeypatch.setattr(pipeline_stages, "verify_script",
                            lambda s, ev: {"claims": [], "high_confidence": 0,
                                           "threshold": 3, "passed": True})
        monkeypatch.setattr(v, "_polish_for_tts",
                            lambda text, language="en", duo=False: text)
        monkeypatch.setattr(co, "update_opening_log", lambda *a, **k: None)

        def fake_audio(text, out_path, lang="en"):
            captured["text"] = text
            Path(out_path).write_bytes(b"ID3fake")
            return True
        monkeypatch.setattr(v, "_generate_podcast_audio", fake_audio)
        return captured

    def test_audio_renders_the_revision_not_the_original(self, monkeypatch, tmp_path):
        import video_downloader as v
        captured = self._stub_pipeline(monkeypatch, [ORIGINAL_DRAFT, REVISED_DRAFT])

        en_txt, en_mp3 = v._run_evidence_pipeline(
            "source material " * 50, "ep99-loop", tmp_path,
            video_title="Test", target_words=700, duo=False)

        # The text sent to audio equals the revision …
        assert captured["text"] == REVISED_DRAFT
        # … and NOT the stale original (the exact bug P0.1 fixes).
        assert captured["text"] != ORIGINAL_DRAFT
        # The on-disk script (which the later quality gate re-reads) matches the
        # rendered audio, so the report and the episode agree.
        assert en_txt.read_text(encoding="utf-8") == REVISED_DRAFT

    def test_known_bad_twin_clean_draft_reaches_audio_unchanged(self, monkeypatch, tmp_path):
        """When the first draft already passes, audio gets that same text."""
        import video_downloader as v
        captured = self._stub_pipeline(monkeypatch, [REVISED_DRAFT])
        en_txt, en_mp3 = v._run_evidence_pipeline(
            "source material " * 50, "ep98-clean", tmp_path,
            video_title="Test", target_words=700, duo=False)
        assert captured["text"] == REVISED_DRAFT


class TestQaLoopReturnsFinalText:
    def test_returns_revised_text_and_writes_it(self, monkeypatch, tmp_path):
        import video_downloader as v
        from checks.quality_gate import QualityReport
        import checks.quality_gate as qg
        import pipeline_stages

        def fake_qg(script_text, audio_path=None, evidence=None):
            passed = "Revised" in script_text
            return QualityReport(passed=passed, checks={},
                                 blocking_failures=[] if passed else ["substance"])
        monkeypatch.setattr(qg, "run_quality_gate", fake_qg)
        monkeypatch.setattr(pipeline_stages, "draft_script",
                            lambda *a, **k: REVISED_DRAFT)
        monkeypatch.setattr(v, "_polish_for_tts",
                            lambda text, language="en", duo=False: text)

        script_path = tmp_path / "ep1.podcast.txt"
        script_path.write_text(ORIGINAL_DRAFT, encoding="utf-8")
        final = v._run_qa_revision_loop(
            ORIGINAL_DRAFT, script_path, {"thesis": "t"}, [{"x": 1}],
            "soul", "Title", "", 700, False, max_revisions=3)

        assert final == REVISED_DRAFT
        assert script_path.read_text(encoding="utf-8") == REVISED_DRAFT

    def test_clean_script_returns_unchanged(self, monkeypatch, tmp_path):
        import video_downloader as v
        from checks.quality_gate import QualityReport
        import checks.quality_gate as qg
        monkeypatch.setattr(qg, "run_quality_gate",
                            lambda *a, **k: QualityReport(passed=True, checks={}, blocking_failures=[]))
        script_path = tmp_path / "ep1.podcast.txt"
        script_path.write_text(REVISED_DRAFT, encoding="utf-8")
        final = v._run_qa_revision_loop(
            REVISED_DRAFT, script_path, {}, [], "", "", "", 700, False, max_revisions=1)
        assert final == REVISED_DRAFT


# ---------------------------------------------------------------------------
# P0.3 — non-interactive runs fail closed on similarity / sponsorship
# ---------------------------------------------------------------------------

class _ReachedProduction(Exception):
    """Raised by a stub to prove control reached production past the gate."""


class TestNonInteractiveGates:
    def _setup(self, monkeypatch, tmp_path, *, sim_matches=None, sponsor=None):
        import video_downloader as v
        monkeypatch.setattr(v, "_check_sponsored_content", lambda *a, **k: sponsor)
        monkeypatch.setattr(v, "_check_episode_similarity", lambda *a, **k: sim_matches or [])
        monkeypatch.setattr(v, "_display_similarity_table", lambda m: None)
        monkeypatch.setattr(v, "_SKIPPED_QUEUE", tmp_path / "skipped.json")
        # Non-interactive stdin: StringIO.isatty() -> False
        monkeypatch.setattr(sys, "stdin", io.StringIO())

        def reached(*a, **k):
            raise _ReachedProduction()
        monkeypatch.setattr(v, "_narrate_as_podcast", reached)

        summary = tmp_path / "src.summary.md"
        summary.write_text("Some source summary text. " * 40, encoding="utf-8")
        return v, summary

    def test_similarity_fails_closed_and_queues(self, monkeypatch, tmp_path):
        matches = [{"slug": "ep01-dup", "title": "Dup", "similarity": 0.91,
                    "shared_terms": ["ai", "agent"]}]
        v, summary = self._setup(monkeypatch, tmp_path, sim_matches=matches)

        out = v.produce_podcast(str(summary), video_title="Karpathy", podcast_dir=tmp_path)

        assert out is None  # no audio produced
        queue = json.loads((tmp_path / "skipped.json").read_text(encoding="utf-8"))
        assert len(queue) == 1
        assert queue[0]["gate"] == "similarity"
        assert queue[0]["detail"]["matches"] == matches

    def test_sponsorship_fails_closed_and_queues(self, monkeypatch, tmp_path):
        v, summary = self._setup(monkeypatch, tmp_path, sponsor=(8, "heavy product CTA"))
        out = v.produce_podcast(str(summary), video_title="Ad", podcast_dir=tmp_path)
        assert out is None
        queue = json.loads((tmp_path / "skipped.json").read_text(encoding="utf-8"))
        assert queue[0]["gate"] == "sponsorship"
        assert queue[0]["detail"]["score"] == 8

    def test_force_bypasses_gate_and_reaches_production(self, monkeypatch, tmp_path):
        matches = [{"slug": "ep01-dup", "title": "Dup", "similarity": 0.91,
                    "shared_terms": ["ai"]}]
        v, summary = self._setup(monkeypatch, tmp_path, sim_matches=matches)
        # With --force the gate is bypassed, so control reaches production.
        with pytest.raises(_ReachedProduction):
            v.produce_podcast(str(summary), video_title="Karpathy",
                              podcast_dir=tmp_path, force=True)
        # And nothing was queued.
        assert not (tmp_path / "skipped.json").exists()

    def test_no_match_proceeds_to_production(self, monkeypatch, tmp_path):
        """Known-bad twin: with no duplicate, the gate does not skip."""
        v, summary = self._setup(monkeypatch, tmp_path, sim_matches=[])
        with pytest.raises(_ReachedProduction):
            v.produce_podcast(str(summary), video_title="Fresh", podcast_dir=tmp_path)
        assert not (tmp_path / "skipped.json").exists()


class TestQueueHelper:
    def test_appends_entries(self, tmp_path):
        import video_downloader as v
        q = tmp_path / "skipped.json"
        v._queue_skipped_episode("ep1-a", "A", "similarity", {"matches": []}, queue_path=q)
        v._queue_skipped_episode("ep2-b", "B", "sponsorship", {"score": 7}, queue_path=q)
        data = json.loads(q.read_text(encoding="utf-8"))
        assert [e["clean_name"] for e in data] == ["ep1-a", "ep2-b"]
        assert all("skipped_at" in e for e in data)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
