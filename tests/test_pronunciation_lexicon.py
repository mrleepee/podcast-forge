"""Phase 3 tests: lowercase risky-term lexicon + spoken-form substitution (P2.1).

The tmux episode shipped with "t-max" because the detector only saw ALL-CAPS
acronyms. These tests prove lowercase technical terms are detected, required to
have a spoken form, and substituted into the text sent to the TTS.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestDetection:
    def test_detects_lowercase_core_terms(self):
        from checks.check_pronunciation import detect_risky_tokens
        tokens = detect_risky_tokens("Run tmux, nginx and kubectl together.")
        assert {"tmux", "nginx", "kubectl"} <= tokens

    def test_plain_words_not_flagged(self):
        from checks.check_pronunciation import detect_risky_tokens
        tokens = detect_risky_tokens("The cat sat on the mat by the river.")
        assert tokens == set()

    def test_arxiv_detected(self):
        from checks.check_pronunciation import detect_risky_tokens
        assert "arxiv" in detect_risky_tokens("See the arxiv paper.")


class TestCoverage:
    def _fixture(self, tmp_path, lexicon, script):
        path = tmp_path / "risky_terms.json"
        path.write_text(json.dumps(lexicon), encoding="utf-8")
        return {"script_text": script, "risky_lexicon_path": path}

    def test_passes_when_all_terms_in_lexicon(self, tmp_path):
        from checks.check_pronunciation import run
        fx = self._fixture(
            tmp_path,
            {"tmux": "tee mux", "nginx": "engine X", "kubectl": "cube control"},
            "Use tmux, nginx and kubectl.")
        result = run(fx)
        assert result.passed, result.reason

    def test_removing_one_entry_fails(self, tmp_path):
        """Known-bad twin: drop kubectl's spoken form → it's detected but uncovered."""
        from checks.check_pronunciation import run
        fx = self._fixture(
            tmp_path,
            {"tmux": "tee mux", "nginx": "engine X"},  # kubectl removed
            "Use tmux, nginx and kubectl.")
        result = run(fx)
        assert not result.passed
        assert "kubectl" in result.reason

    def test_empty_spoken_form_does_not_cover(self, tmp_path):
        # A novel lexicon term (not in the pronunciation cache) with an empty
        # spoken form is detected but uncovered → fail.
        from checks.check_pronunciation import run
        fx = self._fixture(tmp_path, {"frobnicate": ""}, "We frobnicate the data.")
        result = run(fx)
        assert not result.passed
        assert "frobnicate" in result.reason


class TestSubstitutionReachesTts:
    def test_omnivoice_fixups_substitutes_spoken_forms(self, monkeypatch):
        import video_downloader as v
        monkeypatch.setattr(v, "_OMNI_TEXT_FIXUPS",
                            [("kubectl", "cube control"), ("tmux", "tee mux"),
                             ("nginx", "engine X")])
        out = v._omnivoice_fixups("Use tmux, nginx and kubectl now.")
        assert "tee mux" in out
        assert "engine X" in out
        assert "cube control" in out
        # The raw risky tokens are gone from the TTS-bound text.
        assert "tmux" not in out
        assert "kubectl" not in out

    def test_substitution_is_case_insensitive(self, monkeypatch):
        import video_downloader as v
        monkeypatch.setattr(v, "_OMNI_TEXT_FIXUPS", [("tmux", "tee mux")])
        out = v._omnivoice_fixups("Tmux is great. Also tmux.")
        assert "Tmux" not in out
        assert out.count("tee mux") == 2

    def test_default_lexicon_loaded_at_import(self):
        """The shipped lexicon is wired into the fixups list."""
        import video_downloader as v
        terms = {k for k, _ in v._OMNI_TEXT_FIXUPS}
        assert "tmux" in terms and "arxiv" in terms


class TestShippedCiEd:
    """ep131 ships 'CI' (Continuous Integration) and ep133 ships 'ED' (the 1970s
    Unix line editor) as ALL-CAPS tokens. Both are real terms, not false
    positives, so the shipped lexicon must carry spoken forms for them — one
    edit fixes both the pronunciation coverage check and the TTS substitution."""

    def test_shipped_lexicon_has_ci_and_ed(self):
        from checks.check_pronunciation import load_risky_lexicon
        lex = load_risky_lexicon()
        assert lex.get("ci"), "shipped lexicon must map 'ci' -> 'C I'"
        assert lex.get("ed"), "shipped lexicon must map 'ed' -> 'E D'"

    def test_ci_passes_coverage_with_shipped_lexicon(self):
        from checks.check_pronunciation import run
        shipped = REPO / "checks" / "risky_terms.json"
        fx = {"script_text": "a single repository with CI checks",
              "risky_lexicon_path": shipped}
        result = run(fx)
        assert result.passed, result.reason

    def test_ed_passes_coverage_with_shipped_lexicon(self):
        from checks.check_pronunciation import run
        shipped = REPO / "checks" / "risky_terms.json"
        fx = {"script_text": "an old text editor called ED from the seventies",
              "risky_lexicon_path": shipped}
        result = run(fx)
        assert result.passed, result.reason


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
