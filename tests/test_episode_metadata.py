"""Tests for _register_episode_metadata / _episode_blurb and their wiring in
produce_podcast (episodes must never ship with only a 'lufs' registry entry)."""
import json
import video_downloader


# --- _episode_blurb ---

def test_blurb_short_returned_as_is():
    assert video_downloader._episode_blurb("A short summary.") == "A short summary."


def test_blurb_long_snaps_to_sentence():
    summary = "First sentence here. " + ("filler " * 200) + "End."
    out = video_downloader._episode_blurb(summary, limit=40)
    assert len(out) <= 40
    assert out.endswith(".") or out.endswith("…")
    assert out.startswith("First sentence")


# --- _register_episode_metadata ---

def test_register_fills_missing_fields(tmp_path):
    epj = tmp_path / "episodes.json"
    epj.write_text("{}", encoding="utf-8")
    video_downloader._register_episode_metadata(
        "ep99-slug", "The Title", "The description.", "freeist:ep99-slug",
        episodes_json=epj)
    data = json.loads(epj.read_text(encoding="utf-8"))
    assert data["ep99-slug"]["title"] == "The Title"
    assert data["ep99-slug"]["description"] == "The description."
    assert data["ep99-slug"]["guid"] == "freeist:ep99-slug"


def test_register_preserves_curated_title_and_lufs(tmp_path):
    epj = tmp_path / "episodes.json"
    epj.write_text(json.dumps({
        "ep99-slug": {"title": "Curated Title", "lufs": -16.0}
    }), encoding="utf-8")
    video_downloader._register_episode_metadata(
        "ep99-slug", "Auto Title", "Auto desc.", "freeist:ep99-slug",
        episodes_json=epj)
    entry = json.loads(epj.read_text(encoding="utf-8"))["ep99-slug"]
    assert entry["title"] == "Curated Title"      # NOT overwritten
    assert entry["lufs"] == -16.0                  # preserved
    assert entry["description"] == "Auto desc."    # filled in (was missing)
    assert entry["guid"] == "freeist:ep99-slug"    # filled in


def test_register_empty_title_is_noop(tmp_path):
    epj = tmp_path / "episodes.json"
    epj.write_text("{}", encoding="utf-8")
    video_downloader._register_episode_metadata(
        "ep99-slug", "", "desc", "freeist:ep99-slug", episodes_json=epj)
    assert json.loads(epj.read_text(encoding="utf-8")) == {}


# --- integration: produce_podcast registers metadata ---

def test_produce_podcast_registers_title_desc_guid(monkeypatch, tmp_path):
    monkeypatch.setenv("TITLE_CLARITY_CHECK", "0")
    monkeypatch.delenv("PRODUCE_SPANISH", raising=False)
    # redirect the registry to a tmp file so we don't touch the real one
    epj = tmp_path / "episodes.json"
    epj.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(video_downloader, "_EPISODES_JSON", epj)

    # mock the heavy/network/TTS stages
    monkeypatch.setattr(video_downloader, "_check_sponsored_content", lambda *a, **k: None)
    monkeypatch.setattr(video_downloader, "_check_episode_similarity", lambda *a, **k: [])
    monkeypatch.setattr(video_downloader, "_polish_for_tts", lambda text, **k: text)
    monkeypatch.setattr(video_downloader, "_generate_podcast_audio", lambda *a, **k: True)
    monkeypatch.setattr(video_downloader, "_splice_intro_outro", lambda *a, **k: False)
    monkeypatch.setattr(video_downloader, "_run_quality_gate", lambda *a, **k: True)
    monkeypatch.setattr(video_downloader, "_update_vector_index", lambda *a, **k: None)
    monkeypatch.setattr(video_downloader, "_narrate_as_podcast", lambda *a, **k: "narration text")

    summary = tmp_path / "in.summary.md"
    summary.write_text("This episode is about the future of work and AI agents.", encoding="utf-8")
    video_downloader.produce_podcast(summary, video_title="The Future of Work",
                                     podcast_dir=tmp_path, force=True)

    data = json.loads(epj.read_text(encoding="utf-8"))
    [slug] = data  # exactly one episode registered
    entry = data[slug]
    assert entry["title"] == "The Future of Work"
    assert entry["guid"] == f"freeist:{slug}"
    assert entry["description"]            # non-empty blurb
