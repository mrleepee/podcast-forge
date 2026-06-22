"""Tests for the humanize step (humanize_script), the agentic-engineering
callout detector (is_agentic_topic), and its prompt-clause wiring through
_narrate_as_podcast (agentic_takeaway on/off/auto). _call_llm is monkeypatched
so no network is needed.

These three features are defined in video_downloader.py:
  * humanize_script(text, *, language="en") -> str  (post-draft humanizer pass)
  * is_agentic_topic(summary_text, video_title) -> bool  (precision detector)
  * agentic_takeaway threading through _narrate_as_podcast / produce_podcast
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import video_downloader  # noqa: E402


# Local mirror of the _HUMANIZE_SCRIPT gate expression, for table-testing the
# documented env values without re-importing the module under different envs.
def _gate(value):
    return value.lower() not in ("0", "false", "no")


# --- is_agentic_topic: precision ---------------------------------------------

class TestIsAgenticTopicPositive:
    """Strong keywords + 2+ moderate keywords must fire."""

    def test_claude_code_agent_harness(self):
        # Two strong keywords: "Claude Code" and "agent harness".
        assert video_downloader.is_agentic_topic(
            "Building an agent harness inside Claude Code for daily work.",
            "Claude Code agent harness")

    def test_fine_tuning_the_llm(self):
        # Strong: "fine-tuning" (fine-tun) and "LLM".
        assert video_downloader.is_agentic_topic(
            "We are fine-tuning the LLM on agent traces to improve tool use.",
            "Fine-tuning the LLM")

    def test_multi_agent_rag_workflow(self):
        # Strong: "multi-agent", "RAG"; plus moderate "workflow".
        assert video_downloader.is_agentic_topic(
            "A multi-agent RAG workflow for retrieving and synthesizing docs.",
            "Multi-agent RAG workflow")

    def test_mcp_model_context_protocol(self):
        assert video_downloader.is_agentic_topic(
            "Exploring MCP, the model context protocol, for tool integration.",
            "MCP intro")

    def test_prompt_engineering_system_prompt(self):
        assert video_downloader.is_agentic_topic(
            "Prompt engineering tricks: rewrite your system prompt for better results.",
            "Prompt engineering")

    def test_two_distinct_moderate_tokens(self):
        # No strong keyword, but two distinct moderate: "agent" + "transformer".
        assert video_downloader.is_agentic_topic(
            "An agent that wraps a transformer model for inference.",
            "Agent + transformer")

    def test_title_only_match_fires(self):
        # The summary is generic but the title carries a strong keyword.
        assert video_downloader.is_agentic_topic(
            "A wide-ranging conversation about software and the future.",
            "Inside a Claude Code agent loop")


class TestIsAgenticTopicNegative:
    """Precision: Nomad/Finance/Libertarian episodes that merely mention 'AI'
    or one ambiguous word must NOT fire."""

    def test_panama_real_estate_residency(self):
        assert not video_downloader.is_agentic_topic(
            "Panama real estate residency and the friendly nations visa. "
            "Property in a jurisdiction you don't control is a rental.",
            "Panama real estate residency")

    def test_bitcoin_at_200k(self):
        # "Bitcoin" is not a keyword; "model" appears once (fashion model) but
        # only one moderate hit -> must NOT fire.
        assert not video_downloader.is_agentic_topic(
            "Bitcoin at $200K: the model portfolio for sound money.",
            "Bitcoin at $200K")

    def test_ubi_walmart_incentive(self):
        # "incentive" and "Walmart" are not keywords.
        assert not video_downloader.is_agentic_topic(
            "UBI and the Walmart incentive structure. A policy discussion.",
            "UBI Walmart incentive")

    def test_single_moderate_word_does_not_fire(self):
        # Only one moderate keyword ("agent") -> ambiguous, must not fire.
        assert not video_downloader.is_agentic_topic(
            "A travel agent discusses second passports and golden visas.",
            "Travel agent residency")

    def test_ai_mention_alone_does_not_fire(self):
        # A finance episode that name-drops AI in passing. "AI" is not a
        # keyword by design (too common in non-technical episodes).
        assert not video_downloader.is_agentic_topic(
            "How AI might affect gold prices and the bond market going forward.",
            "Gold and AI")

    def test_empty_inputs(self):
        assert not video_downloader.is_agentic_topic("", "")


# --- agentic_takeaway clause wiring in _narrate_as_podcast -------------------

_AGENTIC_MARKER = "AGENTIC-ENGINEERING TAKEAWAY"


def _install_narrate_llm(monkeypatch, capture):
    """Mock _call_llm to record the user prompt and return canned narration."""
    def fake(system, user, *, temperature=0.4, max_tokens=8192, **kw):
        capture["prompts"].append(user)
        return "Canned narration output."
    monkeypatch.setattr(video_downloader, "_call_llm", fake)


class TestAgenticTakeawayClause:
    def test_off_suppresses_clause_on_ai_text(self, monkeypatch):
        cap = {"prompts": []}
        _install_narrate_llm(monkeypatch, cap)
        video_downloader._narrate_as_podcast(
            "Building an agent harness with Claude Code and RAG.",
            video_title="Claude Code agent harness",
            language="en", agentic_takeaway="off")
        assert cap["prompts"], "expected at least one _call_llm call"
        assert _AGENTIC_MARKER not in cap["prompts"][-1]

    def test_on_forces_clause_on_non_ai_text(self, monkeypatch):
        cap = {"prompts": []}
        _install_narrate_llm(monkeypatch, cap)
        video_downloader._narrate_as_podcast(
            "Panama real estate residency and the friendly nations visa.",
            video_title="Panama real estate",
            language="en", agentic_takeaway="on")
        assert cap["prompts"]
        assert _AGENTIC_MARKER in cap["prompts"][-1]

    def test_auto_fires_on_detected_topic(self, monkeypatch):
        cap = {"prompts": []}
        _install_narrate_llm(monkeypatch, cap)
        video_downloader._narrate_as_podcast(
            "A multi-agent RAG workflow for code retrieval.",
            video_title="Multi-agent RAG",
            language="en", agentic_takeaway="auto")
        assert cap["prompts"]
        assert _AGENTIC_MARKER in cap["prompts"][-1]

    def test_auto_suppresses_on_non_ai_text(self, monkeypatch):
        cap = {"prompts": []}
        _install_narrate_llm(monkeypatch, cap)
        video_downloader._narrate_as_podcast(
            "Bitcoin at $200K and the model sound-money portfolio.",
            video_title="Bitcoin $200K",
            language="en", agentic_takeaway="auto")
        assert cap["prompts"]
        assert _AGENTIC_MARKER not in cap["prompts"][-1]

    def test_clause_skipped_on_spanish_path_even_when_on(self, monkeypatch):
        # The callout is English prose; Spanish track is off by default and the
        # clause should not bleed into the ES prompt even when forced on.
        cap = {"prompts": []}
        _install_narrate_llm(monkeypatch, cap)
        video_downloader._narrate_as_podcast(
            "Construyendo un agent harness con Claude Code.",
            video_title="Claude Code agent harness",
            language="es", agentic_takeaway="on")
        assert cap["prompts"]
        assert _AGENTIC_MARKER not in cap["prompts"][-1]



# --- humanize_script ---------------------------------------------------------

def _install_humanize_llm(monkeypatch, capture, *, return_text="HUMANIZED OUTPUT"):
    capture.setdefault("calls", [])
    capture.setdefault("kwargs", [])

    def fake(system, user, *, temperature=0.4, max_tokens=8192, **kw):
        capture["calls"].append({"system": system, "user": user})
        capture["kwargs"].append({"temperature": temperature, "max_tokens": max_tokens})
        return return_text
    monkeypatch.setattr(video_downloader, "_call_llm", fake)


class TestHumanizeScript:
    def test_calls_llm_with_rubric_and_returns_output(self, monkeypatch):
        cap = {"calls": [], "kwargs": []}
        _install_humanize_llm(monkeypatch, cap)
        drafted = "Here is a concise summary of the video transcript. " \
                  "The episode delves into the tapestry of agentic tools."
        out = video_downloader.humanize_script(drafted, language="en")
        assert out == "HUMANIZED OUTPUT"
        assert len(cap["calls"]) == 1
        system = cap["calls"][0]["system"]
        user = cap["calls"][0]["user"]
        # Rubric markers from the condensed humanizer system prompt.
        assert "STRIP THE PREAMBLE" in system
        assert "Here is a concise summary" in system
        assert "NO EM DASHES" in system
        assert "tapestry" in system  # AI vocabulary callout
        # The drafted text is passed as the user message.
        assert user == drafted
        # Temperature + max_tokens match the draft call.
        assert cap["kwargs"][0]["temperature"] == 0.4
        assert cap["kwargs"][0]["max_tokens"] == 8192

    def test_appends_soul_persona_to_system(self, monkeypatch):
        cap = {"calls": [], "kwargs": []}
        _install_humanize_llm(monkeypatch, cap)
        video_downloader.humanize_script("Some drafted narration.", language="en")
        system = cap["calls"][0]["system"]
        # SOUL.md persona is appended (same load path as _narrate_as_podcast).
        assert "PERSONA" in system
        assert "Señora Freedom" in system or "SOUL" in system

    def test_returns_input_on_llm_failure(self, monkeypatch):
        def fake(system, user, **kw):
            raise RuntimeError("glm unavailable")
        monkeypatch.setattr(video_downloader, "_call_llm", fake)
        drafted = "Drafted narration that should pass through on failure."
        out = video_downloader.humanize_script(drafted, language="en")
        assert out == drafted

    def test_empty_input_passthrough(self, monkeypatch):
        called = {"n": 0}

        def fake(system, user, **kw):
            called["n"] += 1
            return "should not happen"

        monkeypatch.setattr(video_downloader, "_call_llm", fake)
        assert video_downloader.humanize_script("", language="en") == ""
        assert video_downloader.humanize_script("   ", language="en") == "   "
        assert called["n"] == 0

    def test_empty_llm_output_falls_back_to_input(self, monkeypatch):
        cap = {"calls": []}
        _install_humanize_llm(monkeypatch, cap, return_text="   ")
        drafted = "Drafted narration."
        out = video_downloader.humanize_script(drafted, language="en")
        assert out == drafted


# --- _HUMANIZE_SCRIPT gate constant ------------------------------------------

class TestHumanizeGateConstant:
    """The gate is a module constant read at import time from HUMANIZE_SCRIPT.
    These tests confirm the constant exists and is a bool, and table-test the
    gate expression's semantics for the documented ON/OFF env values."""

    def test_constant_is_bool(self):
        assert isinstance(video_downloader._HUMANIZE_SCRIPT, bool)

    def test_gate_logic_off_values(self):
        for off in ("0", "false", "no", "FALSE", "No", "FALSE "):
            assert _gate(off.strip()) is False

    def test_gate_logic_on_values(self):
        for on in ("1", "true", "yes", "", "anything-else"):
            assert _gate(on) is True
