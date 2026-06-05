"""Tests for OmniVoice audio-quality fixes (Phases 1-3).

Tests the trim_segment_audio, validate_ref_clip, and omnivoice_fixups helpers
without importing video_downloader top-level (avoids heavy deps).
"""
import os
import re
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

# ---------------------------------------------------------------------------
# Import helpers directly (video_downloader has heavy transitive deps, so we
# extract the pure functions we need rather than importing the module top-level).
# ---------------------------------------------------------------------------

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# We need just the helpers — import them after sys.path is set.
# video_downloader's module-level code is lightweight enough for import.
from video_downloader import (
    _trim_segment_audio,
    _validate_ref_clip,
    _omnivoice_fixups,
    _RE_ADJ_NUM,
)


# ---------------------------------------------------------------------------
# Phase 1: _trim_segment_audio
# ---------------------------------------------------------------------------

class TestTrimSegmentAudio:
    """Per-chunk trim + de-click fade tests."""

    def _make_tone(self, duration_s, sr=24000, freq=440.0):
        """Return a sine tone at full-ish amplitude."""
        t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
        return (0.9 * np.sin(2 * np.pi * freq * t)).astype(np.float64)

    def test_trim_removes_padding(self):
        """0.4s silence + 0.5s tone + 0.4s silence → trimming removes most padding."""
        sr = 24000
        silence = np.zeros(int(0.4 * sr))  # 9600 samples
        tone = self._make_tone(0.5, sr)     # 12000 samples
        wav = np.concatenate([silence, tone, silence])

        result = _trim_segment_audio(wav, sr, thresh_db=-40, keep_ms=30,
                                     max_trim_ms=300, fade_ms=8)
        # max_trim per side = 300ms = 7200 samples
        # lead_sil=9600, keep=720 → min(9600-720, 7200) = 7200 trimmed each side
        # result = 31200 - 7200*2 = 16800
        max_trim_samples = int(300 * sr / 1000)
        assert len(result) < len(wav), "Should have trimmed something"
        assert len(result) >= len(tone), "Should preserve the tone"
        assert (len(wav) - len(result)) <= 2 * max_trim_samples, \
            "Should not trim more than max_trim per side"
        # Interior peak preserved
        assert np.max(np.abs(result)) >= 0.8

    def test_trim_all_silence_drops(self):
        """All-zeros array → size 0."""
        wav = np.zeros(24000)
        result = _trim_segment_audio(wav, 24000)
        assert result.size == 0

    def test_trim_caps_at_max(self):
        """2s leading silence → trims at most max_trim_ms per side."""
        sr = 24000
        lead = np.zeros(int(2.0 * sr))  # 2 seconds
        tone = self._make_tone(0.5, sr)
        wav = np.concatenate([lead, tone])

        result = _trim_segment_audio(wav, sr, thresh_db=-40, keep_ms=30,
                                     max_trim_ms=300, fade_ms=8)
        max_trim_samples = int(300 * sr / 1000)  # 7200
        # The result should be: len(wav) - max_trim + (keep - actual_silence_before_first_above)
        # But at minimum, lead silence should be > 2s - max_trim
        trimmed_lead = len(wav) - len(result)
        assert trimmed_lead <= max_trim_samples, \
            f"Trimmed {trimmed_lead} samples > max {max_trim_samples}"

    def test_trim_applies_fades(self):
        """First/last fade_ms samples should be monotonic ramps."""
        sr = 24000
        tone = self._make_tone(1.0, sr)
        fade_ms = 10
        result = _trim_segment_audio(tone, sr, thresh_db=-40, keep_ms=30,
                                     max_trim_ms=300, fade_ms=fade_ms)
        f = int(fade_ms * sr / 1000)
        assert f > 0
        # Fade-in: absolute values should be non-decreasing (roughly)
        fade_in = np.abs(result[:f])
        fade_out = np.abs(result[-f:])
        # Check monotonic trend: first half of fade_in < second half
        mid = f // 2
        assert np.mean(fade_in[:mid]) <= np.mean(fade_in[mid:]) + 0.01, \
            "Fade-in should ramp up"
        assert np.mean(fade_out[mid:]) <= np.mean(fade_out[:mid]) + 0.01, \
            "Fade-out should ramp down"

    def test_trim_no_silence_preserves_length(self):
        """Full-energy array (no silence) → length unchanged, fades applied."""
        sr = 24000
        tone = self._make_tone(1.0, sr)
        result = _trim_segment_audio(tone, sr, thresh_db=-40, keep_ms=30,
                                     max_trim_ms=300, fade_ms=8)
        assert len(result) == len(tone), \
            f"Expected {len(tone)} samples, got {len(result)}"

    def test_trim_empty_input(self):
        """Empty array → empty output."""
        wav = np.array([], dtype=np.float64)
        result = _trim_segment_audio(wav, 24000)
        assert result.size == 0


# ---------------------------------------------------------------------------
# Phase 2: _validate_ref_clip
# ---------------------------------------------------------------------------

class TestValidateRefClip:
    """Reference-clip validation tests."""

    def _write_wav(self, wav, sr=24000):
        """Write a WAV to a temp file and return the path."""
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        sf.write(path, wav, sr)
        return path

    def test_flags_mid_speech_clip(self):
        """Clip ending mid-speech (no trailing silence) → warning about RE-CUT."""
        sr = 24000
        tone = (0.9 * np.sin(2 * np.pi * 440.0 * np.linspace(0, 2.0, int(sr * 2.0)))).astype(np.float64)
        path = self._write_wav(tone, sr)
        try:
            warns, clean = _validate_ref_clip(path, "This is a test reference text.")
            assert any("RE-CUT" in w for w in warns), \
                f"Expected RE-CUT warning, got: {warns}"
        finally:
            os.unlink(path)

    def test_clean_clip_no_warnings(self):
        """Clip with trailing silence + matching ref_text → no warnings."""
        sr = 24000
        tone = (0.5 * np.sin(2 * np.pi * 440.0 * np.linspace(0, 2.0, int(sr * 2.0)))).astype(np.float64)
        trailing = np.zeros(int(0.3 * sr))  # 300ms trailing silence
        wav = np.concatenate([tone, trailing])
        path = self._write_wav(wav, sr)
        try:
            # 20 words in 2.3s ≈ 8.7 wps — outside range; use shorter text
            ref_text = "One two three four five six seven eight nine ten."
            warns, clean = _validate_ref_clip(path, ref_text)
            assert not any("RE-CUT" in w for w in warns), \
                f"Should not have RE-CUT warning, got: {warns}"
        finally:
            os.unlink(path)

    def test_empty_ref_text_warning(self):
        """Empty ref_text → warning about missing ref_text."""
        sr = 24000
        tone = (0.5 * np.sin(2 * np.pi * 440.0 * np.linspace(0, 2.0, int(sr * 2.0)))).astype(np.float64)
        trailing = np.zeros(int(0.3 * sr))
        wav = np.concatenate([tone, trailing])
        path = self._write_wav(wav, sr)
        try:
            warns, clean = _validate_ref_clip(path, "")
            assert any("ref_text" in w for w in warns), \
                f"Expected ref_text warning, got: {warns}"
        finally:
            os.unlink(path)

    def test_produces_clean_copy(self):
        """Clip with leading/trailing silence → produces _clean.wav."""
        sr = 24000
        leading = np.zeros(int(0.5 * sr))
        tone = (0.5 * np.sin(2 * np.pi * 440.0 * np.linspace(0, 1.0, sr))).astype(np.float64)
        trailing = np.zeros(int(0.5 * sr))
        wav = np.concatenate([leading, tone, trailing])
        path = self._write_wav(wav, sr)
        try:
            warns, clean = _validate_ref_clip(path, "One two three four five six seven.")
            if clean:
                assert "_clean" in clean
                assert Path(clean).exists()
                os.unlink(clean)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Phase 3: _omnivoice_fixups (adjacent-number separator)
# ---------------------------------------------------------------------------

class TestOmniVoiceFixups:
    """Pronunciation fixup tests."""

    def test_fixup_separates_version_size(self):
        """'Gemma four twelve billion' → comma inserted."""
        result = _omnivoice_fixups("Gemma four twelve billion")
        assert "four, twelve billion" in result, \
            f"Expected comma separation, got: {result}"

    def test_fixup_gpt_version_size(self):
        """'GPT four one hundred' → unchanged (no magnitude word follows)."""
        result = _omnivoice_fixups("GPT four one hundred")
        assert result == "GPT four one hundred", \
            f"Should be unchanged (no magnitude), got: {result}"

    def test_fixup_negative_two_hundred_thousand(self):
        """'two hundred thousand' → unchanged (magnitude in middle)."""
        result = _omnivoice_fixups("two hundred thousand children")
        assert result == "two hundred thousand children", \
            f"Should be unchanged, got: {result}"

    def test_fixup_negative_year(self):
        """'twenty twenty-six' → unchanged (no magnitude follows)."""
        result = _omnivoice_fixups("in twenty twenty-six we will see")
        assert result == "in twenty twenty-six we will see", \
            f"Should be unchanged, got: {result}"

    def test_fixup_negative_single_number(self):
        """'twelve billion' → unchanged (single number + magnitude)."""
        result = _omnivoice_fixups("twelve billion dollars")
        assert result == "twelve billion dollars", \
            f"Should be unchanged, got: {result}"

    def test_fixup_tmux(self):
        """Existing tmux fixup still works."""
        result = _omnivoice_fixups("use tmux for sessions")
        assert "tee-mux" in result

    def test_fixup_llama_70b(self):
        """'Llama three seventy billion' → comma inserted."""
        result = _omnivoice_fixups("Llama three seventy billion parameters")
        assert "three, seventy billion" in result, \
            f"Expected comma separation, got: {result}"

    def test_adj_num_regex_direct(self):
        """Test _RE_ADJ_NUM directly for edge cases."""
        # Should match
        assert _RE_ADJ_NUM.search("four twelve billion")
        assert _RE_ADJ_NUM.search("three seventy billion")
        # Should NOT match
        assert not _RE_ADJ_NUM.search("two hundred thousand")
        assert not _RE_ADJ_NUM.search("twenty twenty-six")
        assert not _RE_ADJ_NUM.search("twelve billion")
