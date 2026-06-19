"""Tests for the --expect-topic content-match guard (feed-safety fix)."""
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestTopicMatches:
    def test_verbatim_substring_match(self):
        from video_downloader import topic_matches
        ok, _ = topic_matches(
            "This week we discuss UK emigration trends post-Brexit.",
            "UK emigration")
        assert ok

    def test_case_insensitive_match(self):
        from video_downloader import topic_matches
        ok, _ = topic_matches("all about PAVEL DUROV and telegram", "Pavel Durov")
        assert ok

    def test_token_overlap_passes_with_rewording(self):
        from video_downloader import topic_matches
        # Expected "UK emigration"; source rewords to "emigration from the UK".
        # Tokens: uk, emigration — both present -> 2/2 = 100% >= 0.5.
        ok, _ = topic_matches(
            "A deep look at emigration from the UK after the referendum.",
            "UK emigration")
        assert ok

    def test_partial_overlap_at_threshold(self):
        from video_downloader import topic_matches
        # 4-token phrase, 2 present -> exactly 50% threshold passes.
        ok, _ = topic_matches(
            "The UK budget and taxes this year.",
            "UK taxes spending deficit")
        assert ok

    def test_no_overlap_aborts(self):
        from video_downloader import topic_matches
        # The real-world bug: a URL meant for "UK emigration" produced a
        # Pavel Durov video — must NOT match.
        ok, reason = topic_matches(
            "Pavel Durov talks about Telegram, free speech, and crypto.",
            "UK emigration")
        assert not ok
        assert "not found" in reason

    def test_empty_expectation_passes(self):
        from video_downloader import topic_matches
        ok, _ = topic_matches("anything", "")
        assert ok

    def test_short_single_token_requires_token(self):
        from video_downloader import topic_matches
        ok, _ = topic_matches("nothing about the topic here", "karpathy")
        assert not ok


class TestCheckExpectedTopic:
    def test_match_proceeds(self):
        from video_downloader import check_expected_topic
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.summary.md"
            p.write_text("UK emigration hit a record this year.")
            assert check_expected_topic(str(p), "UK emigration") is True

    def test_mismatch_aborts(self):
        from video_downloader import check_expected_topic
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.summary.md"
            p.write_text("Pavel Durov founded Telegram and loves crypto.")
            assert check_expected_topic(str(p), "UK emigration") is False

    def test_missing_summary_skips_guard(self):
        from video_downloader import check_expected_topic
        # Unreadable path -> guard skipped (defensive, does not block).
        assert check_expected_topic("/no/such/file.summary.md", "anything") is True
