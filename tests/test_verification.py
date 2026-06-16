"""Tests for the hybrid pipeline: full-context extraction + independent verification.

Covers:
  - Phase 6: full-context evidence extraction (150k cap, no 8k truncation)
  - Phase 7: verifier client + key resolution (env → settings-GLM.json)
  - Phase 8: script verification, content-QA gating, graceful skip
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


# ---------------------------------------------------------------------------
# Phase 6 — Full-context evidence extraction
# ---------------------------------------------------------------------------

class TestFullContextExtraction:
    """extract_evidence sends the full transcript, capping only at ~150k chars."""

    def test_full_transcript_sent_no_truncation_warning(self, monkeypatch, capsys):
        import pipeline_stages

        captured = {}

        def fake_call(system_prompt, user_prompt, temperature=0.3):
            captured["user_prompt"] = user_prompt
            return '[{"claim": "x", "source_quote": "x", "timestamp": "para:0", ' \
                   '"source_reliability": "secondary", "confidence": "high", "type": "fact"}]'

        monkeypatch.setattr(pipeline_stages, "_call_llm", fake_call)

        # ~15k words, well under the cap and far over the old 8k-char limit.
        transcript = ("Liberland declared independence in 2015. " * 2000)
        assert len(transcript) > 8000  # would have been truncated before
        pipeline_stages.extract_evidence(transcript)

        # The entire transcript reached the model — not text[:8000].
        assert transcript in captured["user_prompt"]
        out = capsys.readouterr().out
        assert "truncated" not in out

    def test_oversize_transcript_truncated_at_cap_with_warning(self, monkeypatch, capsys):
        import pipeline_stages

        captured = {}

        def fake_call(system_prompt, user_prompt, temperature=0.3):
            captured["user_prompt"] = user_prompt
            return '[{"claim": "x", "source_quote": "x", "timestamp": "para:0", ' \
                   '"source_reliability": "secondary", "confidence": "high", "type": "fact"}]'

        monkeypatch.setattr(pipeline_stages, "_call_llm", fake_call)

        transcript = "word " * 40000  # 200k chars
        assert len(transcript) > 150_000
        pipeline_stages.extract_evidence(transcript)

        # Only the first ~150k chars of the source were sent.
        cap = 150_000
        assert captured["user_prompt"].count("word") == cap // len("word ")
        out = capsys.readouterr().out
        assert "truncated" in out
        assert "150,000" in out
        assert "50,000 chars dropped" in out


# ---------------------------------------------------------------------------
# Phase 7 — Verifier client + key resolution
# ---------------------------------------------------------------------------

class TestKeyResolution:
    """The Z.ai/GLM key resolves from env first, then settings-GLM.json."""

    def test_env_var_takes_precedence(self, monkeypatch):
        import pipeline_stages
        monkeypatch.setenv("ZAI_API_KEY", "env-key-123")
        assert pipeline_stages._resolve_zai_key() == "env-key-123"

    def test_falls_back_to_settings_file(self, monkeypatch, tmp_path):
        import pipeline_stages
        monkeypatch.delenv("ZAI_API_KEY", raising=False)
        settings = tmp_path / "settings-GLM.json"
        settings.write_text(json.dumps({"env": {"ANTHROPIC_AUTH_TOKEN": "file-token-xyz"}}))
        monkeypatch.setattr(pipeline_stages, "_GLM_SETTINGS_PATH", settings)
        assert pipeline_stages._resolve_zai_key() == "file-token-xyz"

    def test_returns_none_when_unavailable(self, monkeypatch, tmp_path):
        import pipeline_stages
        monkeypatch.delenv("ZAI_API_KEY", raising=False)
        monkeypatch.setattr(pipeline_stages, "_GLM_SETTINGS_PATH", tmp_path / "missing.json")
        assert pipeline_stages._resolve_zai_key() is None

    def test_env_whitespace_is_stripped(self, monkeypatch):
        import pipeline_stages
        monkeypatch.setenv("ZAI_API_KEY", "  spaced-key  ")
        assert pipeline_stages._resolve_zai_key() == "spaced-key"


class TestCallVerifier:
    """call_verifier hard-requires a resolvable key."""

    def test_raises_without_key(self, monkeypatch):
        import pipeline_stages
        monkeypatch.setattr(pipeline_stages, "_resolve_zai_key", lambda: None)
        with pytest.raises(RuntimeError, match="verification unavailable"):
            pipeline_stages.call_verifier("sys", "user")

    def test_verification_available_reflects_key(self, monkeypatch, tmp_path):
        import pipeline_stages
        monkeypatch.delenv("ZAI_API_KEY", raising=False)
        monkeypatch.setattr(pipeline_stages, "_GLM_SETTINGS_PATH", tmp_path / "missing.json")
        assert pipeline_stages.verification_available() is False
        monkeypatch.setenv("ZAI_API_KEY", "k")
        assert pipeline_stages.verification_available() is True


# ---------------------------------------------------------------------------
# Phase 8 — Script verification against evidence
# ---------------------------------------------------------------------------

_EVIDENCE = [{"claim": "100 countries piloting CBDCs", "source_quote": "100 countries",
              "timestamp": "para:0", "source_reliability": "primary",
              "confidence": "high", "type": "statistic"}]


class TestVerifyScript:
    """verify_script parses the verifier report and applies the threshold."""

    def _patch(self, monkeypatch, response):
        import pipeline_stages
        monkeypatch.setattr(pipeline_stages, "call_verifier",
                            lambda sys_p, user_p, **kw: response)

    def test_passes_within_threshold(self, monkeypatch):
        import pipeline_stages
        self._patch(monkeypatch, json.dumps([
            {"claim": "2025", "confidence": "high", "type": "date", "reason": "no year"},
        ]))
        result = pipeline_stages.verify_script("By 2025, 100 countries…", _EVIDENCE)
        assert result["high_confidence"] == 1
        assert result["passed"] is True
        assert result["claims"][0]["claim"] == "2025"

    def test_fails_over_threshold(self, monkeypatch):
        claims = [{"claim": f"c{i}", "confidence": "high", "type": "number",
                   "reason": "missing"} for i in range(4)]
        self._patch(monkeypatch, json.dumps(claims))
        import pipeline_stages
        result = pipeline_stages.verify_script("script", _EVIDENCE)
        assert result["high_confidence"] == 4
        assert result["passed"] is False

    def test_medium_claims_do_not_count_toward_threshold(self, monkeypatch):
        claims = [{"claim": f"c{i}", "confidence": "medium", "type": "name",
                   "reason": "ambiguous"} for i in range(10)]
        self._patch(monkeypatch, json.dumps(claims))
        import pipeline_stages
        result = pipeline_stages.verify_script("script", _EVIDENCE)
        assert result["high_confidence"] == 0
        assert result["passed"] is True

    def test_extracts_json_from_surrounding_prose(self, monkeypatch):
        self._patch(monkeypatch,
                    'Here is the report:\n[{"claim": "x", "confidence": "high", '
                    '"type": "quote", "reason": "absent"}]\nDone.')
        import pipeline_stages
        result = pipeline_stages.verify_script("script", _EVIDENCE)
        assert result["high_confidence"] == 1

    def test_no_array_is_error_not_pass(self, monkeypatch):
        # P1.2: prose with no JSON array means the verifier did not return a
        # verdict — that is an error, NOT a clean bill of health.
        self._patch(monkeypatch, "All claims are supported by the evidence.")
        import pipeline_stages
        result = pipeline_stages.verify_script("script", _EVIDENCE)
        assert result["claims"] == []
        assert result["status"] == "error"
        assert result["passed"] is False

    def test_valid_array_reports_ok_status(self, monkeypatch):
        self._patch(monkeypatch, json.dumps([
            {"claim": "x", "confidence": "high", "type": "quote", "reason": "absent"},
        ]))
        import pipeline_stages
        result = pipeline_stages.verify_script("script", _EVIDENCE)
        assert result["status"] == "ok"

    def test_unparseable_array_raises(self, monkeypatch):
        # Has brackets (so the array regex matches) but invalid JSON inside.
        self._patch(monkeypatch, "[{'claim': 'x', confidence: high,}]")
        import pipeline_stages
        with pytest.raises(ValueError, match="unparseable"):
            pipeline_stages.verify_script("script", _EVIDENCE)


class TestCheckVerification:
    """check_verification adapts verify_script to the quality-check interface."""

    def test_empty_script_fails(self):
        from checks.check_verification import run
        result = run({"script_text": "", "evidence": _EVIDENCE})
        assert not result.passed
        assert "empty" in result.reason

    def test_no_evidence_skips(self):
        from checks.check_verification import run
        result = run({"script_text": "Some script", "evidence": None})
        assert result.passed
        assert "skipped" in result.reason

    def test_skips_when_verifier_unavailable(self, monkeypatch):
        import pipeline_stages
        monkeypatch.setattr(pipeline_stages, "_resolve_zai_key", lambda: None)
        from checks.check_verification import run
        result = run({"script_text": "Some script", "evidence": _EVIDENCE})
        assert result.passed
        assert "skipped" in result.reason

    def test_fails_over_threshold(self, monkeypatch):
        import pipeline_stages
        claims = [{"claim": f"c{i}", "confidence": "high", "type": "number",
                   "reason": "missing"} for i in range(4)]
        monkeypatch.setattr(pipeline_stages, "call_verifier",
                            lambda s, u, **kw: json.dumps(claims))
        from checks.check_verification import run
        result = run({"script_text": "script", "evidence": _EVIDENCE})
        assert not result.passed
        assert result.reason == "verification_failed: 4 untraceable claims"
        assert result.metrics["high_confidence"] == 4

    def test_passes_within_threshold(self, monkeypatch):
        import pipeline_stages
        monkeypatch.setattr(pipeline_stages, "call_verifier",
                            lambda s, u, **kw: json.dumps([
                                {"claim": "2025", "confidence": "high",
                                 "type": "date", "reason": "no year"}]))
        from checks.check_verification import run
        result = run({"script_text": "script", "evidence": _EVIDENCE})
        assert result.passed
        assert "within threshold" in result.reason


class TestQualityGateIntegration:
    """run_quality_gate only verifies when evidence is supplied, and gates on it."""

    _CLEAN = (
        "In 2015, Liberland was founded on 7 square kilometres. By 2024, "
        "according to Jedlicka, 700000 citizens had registered. The plan targets "
        "100 million dollars in 2026. Three rivers border the territory."
    )

    def test_no_verification_check_without_evidence(self):
        from checks.quality_gate import run_quality_gate
        report = run_quality_gate(self._CLEAN)
        assert "verification" not in report.checks

    def test_verification_runs_with_evidence(self, monkeypatch):
        import pipeline_stages
        monkeypatch.setattr(pipeline_stages, "call_verifier",
                            lambda s, u, **kw: "[]")  # nothing flagged
        from checks.quality_gate import run_quality_gate
        report = run_quality_gate(self._CLEAN, evidence=_EVIDENCE)
        assert "verification" in report.checks
        assert report.checks["verification"]["passed"]

    def test_verification_failure_blocks_publish(self, monkeypatch):
        import pipeline_stages
        claims = [{"claim": f"c{i}", "confidence": "high", "type": "number",
                   "reason": "missing"} for i in range(4)]
        monkeypatch.setattr(pipeline_stages, "call_verifier",
                            lambda s, u, **kw: json.dumps(claims))
        from checks.quality_gate import run_quality_gate
        report = run_quality_gate(self._CLEAN, evidence=_EVIDENCE)
        assert not report.passed
        assert any("verification_failed" in f for f in report.blocking_failures)

    def test_verifier_outage_does_not_block(self, monkeypatch):
        import pipeline_stages
        monkeypatch.setattr(pipeline_stages, "_resolve_zai_key", lambda: None)
        from checks.quality_gate import run_quality_gate
        report = run_quality_gate(self._CLEAN, evidence=_EVIDENCE)
        # Verification skipped gracefully; the clean script still passes.
        assert report.checks["verification"]["passed"]


class TestVerificationStageWiring:
    """_run_verification_stage delegates, writes a report, and never raises."""

    def test_skips_without_evidence(self, capsys):
        from video_downloader import _run_verification_stage
        assert _run_verification_stage("script", []) is None

    def test_writes_report_and_returns_result(self, monkeypatch, tmp_path):
        import pipeline_stages
        monkeypatch.setattr(pipeline_stages, "call_verifier",
                            lambda s, u, **kw: json.dumps([
                                {"claim": "2025", "confidence": "high",
                                 "type": "date", "reason": "no year"}]))
        from video_downloader import _run_verification_stage
        script_path = tmp_path / "ep.podcast.txt"
        script_path.write_text("By 2025, 100 countries…")
        result = _run_verification_stage("By 2025, 100 countries…", _EVIDENCE, script_path)
        assert result is not None
        assert result["high_confidence"] == 1
        report = tmp_path / "ep.podcast.verification_report.json"
        assert report.exists()
        assert json.loads(report.read_text())["high_confidence"] == 1


class TestLiveVerifier:
    """Opt-in live check against Z.ai's coding-plan endpoint (no API credits).

    Skipped unless RUN_LIVE_GLM=1 — keeps the default suite offline and stable.
    """

    def test_live_flags_unattributed_expert(self):
        import os
        if os.environ.get("RUN_LIVE_GLM") != "1":
            pytest.skip("set RUN_LIVE_GLM=1 to run the live GLM verifier check")
        import pipeline_stages
        if not pipeline_stages.verification_available():
            pytest.skip("no Z.ai key resolvable")
        evidence = [{"claim": "90 countries piloting CBDCs",
                     "source_quote": "90 countries piloting CBDCs", "timestamp": "para:0",
                     "source_reliability": "primary", "confidence": "high",
                     "type": "statistic"}]
        script = "In 2024, 90 countries piloted CBDCs, and experts say adoption is inevitable."
        result = pipeline_stages.verify_script(script, evidence)
        # The vague-attribution claim has no support in the evidence map.
        assert any(c.get("type") == "unattributed_expert" for c in result["claims"])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
