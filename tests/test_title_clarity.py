"""Tests for the title-clarity gate (_ensure_title_clarity) and its wiring in
produce_podcast (TITLE_CLARITY_CHECK toggle) plus the Spanish-track disable
(PRODUCE_SPANISH). _call_llm is monkeypatched so no network is needed.
"""
import video_downloader


# --- helpers -----------------------------------------------------------------

def _make_llm(monkeypatch, *, guesses=None, verdicts=None, revisions=None, raise_on=None):
    """Replace video_downloader._call_llm with a dispatcher keyed on the system
    prompt. Returns a dict recording every call's (system, user) for assertions."""
    guesses = list(guesses or [])
    verdicts = list(verdicts or [])
    revisions = list(revisions or [])
    calls = {"guess": [], "judge": [], "revise": []}

    def fake(system, user, **kwargs):
        if raise_on == "guess" and not calls["guess"]:
            raise RuntimeError("glm unavailable")
        if system is video_downloader._TITLE_GUESS_SYS:
            calls["guess"].append(user)
            return guesses.pop(0)
        if system is video_downloader._TITLE_JUDGE_SYS:
            calls["judge"].append(user)
            return verdicts.pop(0)
        if system is video_downloader._TITLE_REVISE_SYS:
            calls["revise"].append(user)
            return revisions.pop(0)
        raise AssertionError(f"unexpected system prompt: {system!r}")

    monkeypatch.setattr(video_downloader, "_call_llm", fake)
    return calls


# --- unit tests --------------------------------------------------------------

def test_clear_title_returns_unchanged(monkeypatch):
    calls = _make_llm(monkeypatch, guesses=["A podcast about cheese"],
                      verdicts=["MATCH"])
    out = video_downloader._ensure_title_clarity("The Cheese Episode", "desc about cheese")
    assert out == "The Cheese Episode"
    assert len(calls["guess"]) == 1
    assert len(calls["judge"]) == 1
    assert len(calls["revise"]) == 0


def test_unclear_title_revised_then_matches(monkeypatch):
    calls = _make_llm(monkeypatch,
                      guesses=["g1", "g2"],
                      verdicts=["NO_MATCH", "MATCH"],
                      revisions=["The Hidden Cheese Wealth Transfer"])
    out = video_downloader._ensure_title_clarity("A Thing About Stuff", "desc about cheese wealth")
    assert out == "The Hidden Cheese Wealth Transfer"
    assert len(calls["revise"]) == 1  # revised once, then matched


def test_exhaustion_returns_best_effort_and_warns(monkeypatch, capsys):
    _make_llm(monkeypatch,
              guesses=["g"] * 3,
              verdicts=["NO_MATCH"] * 3,
              revisions=["Rev1", "Rev2"])
    out = video_downloader._ensure_title_clarity("Vague Title", "desc", max_rounds=3)
    assert out == "Rev2"  # last accepted revision
    assert "not confirmed after 3 rounds" in capsys.readouterr().out


def test_guess_call_is_fresh_context(monkeypatch):
    """The GUESS call must receive ONLY the title — the description never leaks in."""
    title = "The Cheese Episode"
    calls = _make_llm(monkeypatch, guesses=["about cheese"], verdicts=["MATCH"])
    video_downloader._ensure_title_clarity(title, "A long description about cheese that must NOT appear in the guess call")
    assert calls["guess"][0] == title
    assert "must NOT appear" not in calls["guess"][0]
    # And the judge call does carry the description (it's allowed to see it).
    assert "must NOT appear" in calls["judge"][0]


def test_revise_no_progress_breaks_early(monkeypatch):
    """If revision returns the same title, stop — don't loop pointlessly."""
    title = "Same Title"
    calls = _make_llm(monkeypatch, guesses=["g"], verdicts=["NO_MATCH"], revisions=[title])
    out = video_downloader._ensure_title_clarity(title, "desc", max_rounds=5)
    assert out == title
    assert len(calls["revise"]) == 1  # one revise that made no progress, then stopped


def test_glm_unavailable_returns_current(monkeypatch, capsys):
    _make_llm(monkeypatch, raise_on="guess")
    out = video_downloader._ensure_title_clarity("Some Title", "desc")
    assert out == "Some Title"
    assert "unavailable" in capsys.readouterr().out


def test_empty_title_short_circuits(monkeypatch):
    calls = _make_llm(monkeypatch)
    assert video_downloader._ensure_title_clarity("", "desc") == ""
    assert calls["guess"] == []  # no LLM calls for an empty title


# --- integration: produce_podcast wiring -------------------------------------

def _mock_produce_podcast_heavy_stages(monkeypatch, narrations):
    """Mock every network/TTS/IO-heavy stage so produce_podcast runs offline."""
    monkeypatch.setattr(video_downloader, "_check_sponsored_content", lambda *a, **k: None)
    monkeypatch.setattr(video_downloader, "_check_episode_similarity", lambda *a, **k: [])
    monkeypatch.setattr(video_downloader, "_polish_for_tts", lambda text, **k: text)
    monkeypatch.setattr(video_downloader, "_polish_for_tts_raw", lambda text, **k: text)
    monkeypatch.setattr(video_downloader, "_generate_podcast_audio", lambda *a, **k: True)
    monkeypatch.setattr(video_downloader, "_generate_duo_audio", lambda *a, **k: True)
    monkeypatch.setattr(video_downloader, "_splice_intro_outro", lambda *a, **k: False)
    monkeypatch.setattr(video_downloader, "_run_quality_gate", lambda *a, **k: True)
    monkeypatch.setattr(video_downloader, "_update_vector_index", lambda *a, **k: None)
    monkeypatch.setattr(video_downloader, "_record_episode_lufs", lambda *a, **k: None)

    def narrate(summary_text, video_title="", **kwargs):
        narrations.append(kwargs.get("language", "en"))
        return f"narration for {kwargs.get('language', 'en')}"

    monkeypatch.setattr(video_downloader, "_narrate_as_podcast", narrate)


def test_title_clarity_gate_respects_env(monkeypatch, tmp_path):
    # TITLE_CLARITY_CHECK=0 -> gate skipped entirely.
    monkeypatch.setenv("TITLE_CLARITY_CHECK", "0")
    monkeypatch.delenv("PRODUCE_SPANISH", raising=False)
    spy = []
    monkeypatch.setattr(video_downloader, "_ensure_title_clarity",
                        lambda *a, **k: spy.append(a) or a[0])
    _mock_produce_podcast_heavy_stages(monkeypatch, [])

    summary = tmp_path / "in.summary.md"
    summary.write_text("some summary text", encoding="utf-8")
    video_downloader.produce_podcast(summary, video_title="Original Title",
                                      podcast_dir=tmp_path, force=True)
    assert spy == []  # gate never ran


def test_spanish_disabled_by_default(monkeypatch, tmp_path):
    # PRODUCE_SPANISH unset -> only English narration is produced.
    monkeypatch.setenv("TITLE_CLARITY_CHECK", "0")
    monkeypatch.delenv("PRODUCE_SPANISH", raising=False)
    narrations = []
    _mock_produce_podcast_heavy_stages(monkeypatch, narrations)

    summary = tmp_path / "in.summary.md"
    summary.write_text("some summary text", encoding="utf-8")
    video_downloader.produce_podcast(summary, video_title="Some Title",
                                      podcast_dir=tmp_path, force=True)
    assert "en" in narrations
    assert "es" not in narrations
    assert list(tmp_path.glob("*.podcast.es.mp3")) == []
    assert list(tmp_path.glob("*.podcast.es.txt")) == []


def test_spanish_enabled_when_env_set(monkeypatch, tmp_path):
    # PRODUCE_SPANISH=1 -> Spanish narration runs too.
    monkeypatch.setenv("TITLE_CLARITY_CHECK", "0")
    monkeypatch.setenv("PRODUCE_SPANISH", "1")
    narrations = []
    _mock_produce_podcast_heavy_stages(monkeypatch, narrations)

    summary = tmp_path / "in.summary.md"
    summary.write_text("some summary text", encoding="utf-8")
    video_downloader.produce_podcast(summary, video_title="Some Title",
                                      podcast_dir=tmp_path, force=True)
    assert "es" in narrations
