"""Phase 6 tests: RSS distribution fixes (P3) — stable GUIDs, metadata, transcripts."""
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree.ElementTree import fromstring, tostring

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

NS = {
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    "podcast": "https://podcastindex.org/namespace/1.0",
}


def _episode(stem="ep07-tmux-power-user", transcript=True):
    return {
        "title": "Tmux for Power Users",
        "description": "A deep dive.",
        "stem": stem,
        "mp3_path": Path(f"/x/{stem}.podcast.mp3"),
        "mp3_filename": f"{stem}.podcast.mp3",
        "duration": 600,
        "duration_str": "10:00",
        "filesize": 1234,
        "pub_date": datetime(2026, 6, 1, tzinfo=timezone.utc),
        "transcript_filename": f"{stem}.podcast.txt" if transcript else None,
    }


def _build(eps, base_url="https://host.example/audio/", **kw):
    import generate_rss
    rss = generate_rss.generate_rss(
        eps, base_url, "Señora Freedom", "desc", "Señora Freedom", **kw)
    # Round-trip proves the feed is well-formed XML.
    return fromstring(tostring(rss, encoding="unicode"))


class TestStableGuid:
    def test_guid_is_slug_derived_not_url(self):
        root = _build([_episode()])
        guid = root.find(".//item/guid")
        assert guid.text == "freeist:ep07-tmux-power-user"
        assert guid.get("isPermaLink") == "false"

    def test_guid_unchanged_when_base_url_changes(self):
        a = _build([_episode()], base_url="https://A.example/audio/")
        b = _build([_episode()], base_url="https://B.example/audio/")
        assert a.find(".//item/guid").text == b.find(".//item/guid").text

    def test_show_guid_is_deterministic(self):
        import generate_rss
        assert generate_rss.stable_show_guid("X") == generate_rss.stable_show_guid("X")
        assert generate_rss.stable_show_guid("X") != generate_rss.stable_show_guid("Y")


class TestChannelMetadata:
    def test_itunes_type_episodic(self):
        root = _build([_episode()])
        assert root.find(".//channel/itunes:type", NS).text == "episodic"

    def test_podcast_guid_present(self):
        root = _build([_episode()])
        assert root.find(".//channel/podcast:guid", NS) is not None

    def test_owner_email_emitted_when_set(self):
        root = _build([_episode()], owner_email="host@example.com")
        assert root.find(".//channel/itunes:owner/itunes:email", NS).text == "host@example.com"

    def test_owner_email_omitted_when_empty(self):
        root = _build([_episode()], owner_email="")
        assert root.find(".//channel/itunes:owner/itunes:email", NS) is None

    def test_image_emitted_only_when_url_given(self):
        with_img = _build([_episode()], image_url="https://host.example/cover.png")
        assert with_img.find(".//channel/itunes:image", NS).get("href") == \
            "https://host.example/cover.png"
        without = _build([_episode()])
        assert without.find(".//channel/itunes:image", NS) is None


class TestTranscripts:
    def test_transcript_linked_when_present(self):
        root = _build([_episode(transcript=True)])
        tr = root.find(".//item/podcast:transcript", NS)
        assert tr.get("url") == "https://host.example/audio/ep07-tmux-power-user.podcast.txt"
        assert tr.get("type") == "text/plain"

    def test_no_transcript_tag_when_absent(self):
        root = _build([_episode(transcript=False)])
        assert root.find(".//item/podcast:transcript", NS) is None


class TestEpisodeNumber:
    def test_itunes_episode_from_stem(self):
        root = _build([_episode(stem="ep42-foo")])
        assert root.find(".//item/itunes:episode", NS).text == "42"
        assert root.find(".//item/itunes:episodeType", NS).text == "full"


class TestFindEpisodesCarriesFields:
    def test_stem_and_transcript_flag(self, tmp_path):
        import generate_rss
        (tmp_path / "ep05-x.podcast.mp3").write_bytes(b"ID3")
        (tmp_path / "ep05-x.podcast.txt").write_text("transcript", encoding="utf-8")
        (tmp_path / "ep06-y.podcast.mp3").write_bytes(b"ID3")  # no transcript
        eps = {e["stem"]: e for e in generate_rss.find_podcast_episodes(tmp_path)}
        assert eps["ep05-x"]["transcript_filename"] == "ep05-x.podcast.txt"
        assert eps["ep06-y"]["transcript_filename"] is None


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
