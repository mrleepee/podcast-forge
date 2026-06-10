"""Phase 4 tests: ref-clip hard-fail (P2.2 part 2) and seam-QC harness (part 3).

Each behaviour has a known-bad twin proving the assertion can fail.
"""
import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


# ---------------------------------------------------------------------------
# P2.2 part 2 — defective clone reference stops the render (strict mode)
# ---------------------------------------------------------------------------

class TestBlockingRefWarnings:
    def test_mid_speech_is_blocking(self):
        import video_downloader as v
        warns = ["ref clip ends mid-speech (0ms trailing silence; need >= 150ms) -- RE-CUT"]
        assert v._blocking_ref_warnings(warns) == warns

    def test_length_mismatch_is_blocking(self):
        import video_downloader as v
        warns = ["ref_text/clip length mismatch (8.1 words/sec) -- verify the transcript"]
        assert v._blocking_ref_warnings(warns)

    def test_sample_rate_warning_is_not_blocking(self):
        import video_downloader as v
        warns = ["ref sample rate 22050 != expected 24000"]
        assert v._blocking_ref_warnings(warns) == []

    def test_clean_has_no_blocking(self):
        import video_downloader as v
        assert v._blocking_ref_warnings([]) == []


class TestRenderAbortsOnDefectiveRef:
    def _setup(self, monkeypatch, tmp_path, *, strict):
        import video_downloader as v
        ref = tmp_path / "ref.wav"
        ref.write_bytes(b"fake")
        monkeypatch.setattr(v, "_OMNI_REF_AUDIO", str(ref))
        monkeypatch.setattr(v, "_OMNI_REF_TEXT", "some reference text here")
        monkeypatch.setattr(v, "_OMNI_REF_STRICT", strict)
        monkeypatch.setattr(v, "_REF_CLIP_VALIDATED", False)
        monkeypatch.setattr(
            v, "_validate_ref_clip",
            lambda p, t, **k: (["ref clip ends mid-speech (0ms trailing silence)"], None))
        return v

    def test_strict_aborts_render(self, monkeypatch, tmp_path):
        v = self._setup(monkeypatch, tmp_path, strict=True)
        ok = v._omnivoice_render(
            [{"text": "hello there", "language": "English"}], str(tmp_path / "out.mp3"))
        assert ok is False

    def test_non_strict_proceeds_to_worker(self, monkeypatch, tmp_path):
        """Known-bad twin: with strict off, the same defective clip does NOT abort."""
        v = self._setup(monkeypatch, tmp_path, strict=False)

        class _ReachedWorker(Exception):
            pass

        def fake_run(*a, **k):
            raise _ReachedWorker()
        monkeypatch.setattr(v.subprocess, "run", fake_run)
        with pytest.raises(_ReachedWorker):
            v._omnivoice_render(
                [{"text": "hello there", "language": "English"}], str(tmp_path / "out.mp3"))


# ---------------------------------------------------------------------------
# P2.2 part 3 — seam QC harness
# ---------------------------------------------------------------------------

class TestPeakDbfs:
    def test_silence_is_neg_inf(self):
        from checks.seam_qc import peak_dbfs
        import numpy as np
        assert peak_dbfs(np.zeros(100)) == -math.inf

    def test_full_scale_is_zero_db(self):
        from checks.seam_qc import peak_dbfs
        import numpy as np
        assert abs(peak_dbfs(np.array([1.0, -1.0, 0.5])) - 0.0) < 1e-6

    def test_half_scale_is_about_minus_six_db(self):
        from checks.seam_qc import peak_dbfs
        import numpy as np
        assert abs(peak_dbfs(np.array([0.5])) - (-6.02)) < 0.1


class TestGapEnergy:
    def test_silent_tails_are_clean(self):
        from checks.seam_qc import analyze_gap_energy
        import numpy as np
        # Each segment is a tone followed by a faded-to-silence tail (>40ms at 24k).
        segs = [np.concatenate([np.ones(2400) * 0.3, np.zeros(2400)]) for _ in range(4)]
        result = analyze_gap_energy(segs, sr=24000, edge_ms=40.0)
        assert result["clean"]
        assert result["worst_gap_dbfs"] < -60

    def test_leaked_tail_flagged(self):
        from checks.seam_qc import analyze_gap_energy
        import numpy as np
        # One segment leaks a loud token into its trailing edge (no fade).
        good = np.concatenate([np.ones(2400) * 0.3, np.zeros(2400)])
        leaky = np.concatenate([np.ones(2400) * 0.3, np.ones(2400) * 0.5])
        result = analyze_gap_energy([good, leaky, good], sr=24000, edge_ms=40.0)
        assert not result["clean"]
        assert result["worst_gap_dbfs"] > -60


class TestEchoSignature:
    def test_recurring_start_token_flagged(self):
        from checks.seam_qc import detect_recurring_start_token
        transcripts = ["Fresh ideas today", "Fresh take here", "Fresh angle",
                       "Something else", "Another point"]
        result = detect_recurring_start_token(transcripts)
        assert result["token"] == "fresh"
        assert result["flagged"]  # 3/5 = 60% >= 30%

    def test_varied_starts_not_flagged(self):
        from checks.seam_qc import detect_recurring_start_token
        transcripts = ["Alpha one", "Beta two", "Gamma three", "Delta four", "Epsilon five"]
        assert not detect_recurring_start_token(transcripts)["flagged"]

    def test_empty_transcripts_safe(self):
        from checks.seam_qc import detect_recurring_start_token
        assert detect_recurring_start_token([])["flagged"] is False


class TestRunSeamQc:
    def test_clean_render_with_transcripts(self, tmp_path):
        from checks.seam_qc import run_seam_qc
        import numpy as np
        import soundfile as sf
        paths = []
        for i in range(3):
            p = tmp_path / f"seg{i:03d}.wav"
            sf.write(p, np.concatenate([np.ones(2400) * 0.3, np.zeros(2400)]), 24000)
            paths.append(p)
        report = run_seam_qc(paths, transcripts=["Alpha", "Beta", "Gamma"])
        assert report["clean"]
        assert report["segments"] == 3

    def test_echo_makes_report_unclean(self, tmp_path):
        from checks.seam_qc import run_seam_qc
        import numpy as np
        import soundfile as sf
        paths = []
        for i in range(4):
            p = tmp_path / f"seg{i:03d}.wav"
            sf.write(p, np.concatenate([np.ones(2400) * 0.3, np.zeros(2400)]), 24000)
            paths.append(p)
        # Energy clean, but every segment starts with the same leaked token.
        report = run_seam_qc(paths, transcripts=["Fresh a", "Fresh b", "Fresh c", "Fresh d"])
        assert report["echo"]["flagged"]
        assert not report["clean"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
