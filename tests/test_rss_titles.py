"""Tests for generate_rss.title_from_slug — the slug-derived fallback title
that must preserve acronyms (AI, API, LLMs, UK, EU...) as all-caps."""
import generate_rss


def test_ai_acronym_preserved():
    assert generate_rss.title_from_slug(
        "ep143-inside-claude-code-design-space-ai-agent-system"
    ) == "Inside Claude Code Design Space AI Agent System"


def test_two_acronyms_in_one_title():
    # 'api' and 'llms' both uppercased; 'an' stays title-cased
    assert generate_rss.title_from_slug(
        "ep9-build-an-api-with-llms-fast"
    ) == "Build An API With LLMs Fast"


def test_uk_and_eu_acronyms():
    assert generate_rss.title_from_slug("ep100-uk-tax-and-the-eu") == "UK Tax And The EU"


def test_no_acronym_plain_title_case():
    assert generate_rss.title_from_slug("ep5-the-history-of-taxation") == "The History Of Taxation"


def test_strips_ep_prefix():
    assert not generate_rss.title_from_slug("ep99-foo-bar").lower().startswith("ep")
