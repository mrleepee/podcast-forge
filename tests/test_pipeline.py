"""Tests for the evidence-first pipeline stages."""
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestPipelineStageError:
    """PipelineStageError carries stage name and artifact path."""

    def test_error_has_stage_and_artifact(self):
        from video_downloader import PipelineStageError
        err = PipelineStageError("evidence_extraction", "no data", "/tmp/evidence.json")
        assert err.stage == "evidence_extraction"
        assert err.artifact_path == "/tmp/evidence.json"
        assert "evidence_extraction" in str(err)


class TestExtractEvidence:
    """extract_evidence returns structured evidence entries."""

    def test_returns_list(self):
        from pipeline_stages import extract_evidence
        result = extract_evidence("A short text under 100 words limit.")
        assert isinstance(result, list)

    def test_empty_for_short_text(self):
        from pipeline_stages import extract_evidence
        result = extract_evidence("Too short.")
        assert result == []

    def test_deterministic_extracts_numbers(self):
        from pipeline_stages import _extract_evidence_deterministic
        text = "By 2024, 90 countries piloted CBDCs. Revenue hit $2.3 million."
        entries = _extract_evidence_deterministic(text)
        assert len(entries) >= 1
        assert any("2024" in e["claim"] or "90" in e["claim"] for e in entries)

    def test_deterministic_has_required_fields(self):
        from pipeline_stages import _extract_evidence_deterministic
        text = "Liberland was proclaimed on 13 April 2015. The area covers 7 square kilometres."
        entries = _extract_evidence_deterministic(text)
        for entry in entries:
            assert "claim" in entry
            assert "source_quote" in entry
            assert "timestamp" in entry
            assert "source_reliability" in entry
            assert "confidence" in entry
            assert "type" in entry
            assert entry["source_reliability"] in ("primary", "secondary", "hearsay")
            assert entry["confidence"] in ("high", "medium", "low")
            assert entry["type"] in ("fact", "opinion", "prediction", "statistic")


class TestGenerateOutline:
    """generate_outline returns a structured outline."""

    def test_deterministic_returns_required_fields(self):
        from pipeline_stages import _generate_outline_deterministic
        evidence = [{"claim": "test", "source_quote": "test", "timestamp": "para:0",
                     "source_reliability": "secondary", "confidence": "high", "type": "fact"}]
        outline = _generate_outline_deterministic(evidence)
        assert "thesis" in outline
        assert "hook" in outline
        assert "stakes" in outline
        assert "evidence_beats" in outline
        assert "counterpoint" in outline
        assert "implication" in outline
        assert "close" in outline
        assert "warnings" in outline

    def test_deterministic_warns_on_thin_evidence(self):
        from pipeline_stages import _generate_outline_deterministic
        evidence = [{"claim": "only one", "source_quote": "x", "timestamp": "para:0",
                     "source_reliability": "secondary", "confidence": "low", "type": "opinion"}]
        outline = _generate_outline_deterministic(evidence)
        assert any("thin evidence" in w for w in outline["warnings"])

    def test_deterministic_no_warning_with_enough_evidence(self):
        from pipeline_stages import _generate_outline_deterministic
        evidence = [
            {"claim": f"claim {i}", "source_quote": f"quote {i}", "timestamp": f"para:{i}",
             "source_reliability": "primary", "confidence": "high", "type": "fact"}
            for i in range(10)
        ]
        outline = _generate_outline_deterministic(evidence)
        assert not any("thin evidence" in w for w in outline["warnings"])


class TestPipelineFlag:
    """produce_podcast accepts pipeline parameter."""

    def test_function_accepts_pipeline_param(self):
        import inspect
        from video_downloader import produce_podcast
        sig = inspect.signature(produce_podcast)
        assert "pipeline" in sig.parameters
        assert sig.parameters["pipeline"].default == "summary"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
