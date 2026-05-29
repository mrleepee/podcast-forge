"""Local pronunciation database backed by Wiktionary IPA lookups.

Usage:
    # Look up a word (fetches from Wiktionary if not cached)
    python pronunciation_db.py JSON

    # Batch look up multiple words
    python pronunciation_db.py JSON Kubernetes Docker

    # Show all cached entries
    python pronunciation_db.py --list

    # Seed manual entries
    python pronunciation_db.py --seed
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag

CACHE_FILE = Path(__file__).parent / "pronunciation_cache.json"


@dataclass
class PronunciationEntry:
    word: str
    ipa: str
    source: str  # "wiktionary", "manual", "g2p-fallback"
    notes: str = ""


def load_cache() -> dict[str, dict]:
    if CACHE_FILE.exists():
        return json.load(open(CACHE_FILE))
    return {}


def save_cache(cache: dict[str, dict]) -> None:
    json.dump(cache, open(CACHE_FILE, "w"), indent=2, sort_keys=True)


def fetch_wiktionary_ipa(word: str) -> Optional[str]:
    """Fetch the first English IPA pronunciation from Wiktionary."""
    url = f"https://en.wiktionary.org/wiki/{word.lower()}"
    try:
        r = requests.get(url, timeout=15, headers={
            "User-Agent": "pronunciation-db/1.0 (TTS pipeline)"
        })
        r.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(r.text, "lxml")
    content = soup.find("div", class_="mw-parser-output")
    if not content:
        return None

    # Walk direct children of parser output, tracking English section
    in_english = False
    ipas = []
    for child in content.children:
        if not isinstance(child, Tag):
            continue

        # Detect language-level heading containers
        if child.name == "div" and "mw-heading2" in (child.get("class") or []):
            h2 = child.find("h2")
            if h2:
                heading_text = h2.get_text(strip=True)
                if heading_text == "English":
                    in_english = True
                    continue
                elif in_english:
                    break  # End of English section

        if in_english:
            for span in child.find_all("span", class_="IPA"):
                ipas.append(span.get_text(strip=True))

    if not ipas:
        return None

    # Prefer entries with stress markers (real IPA) over short entries
    for ipa in ipas:
        clean = ipa.strip("/[]")
        if ("ˈ" in clean or "ˌ" in clean) and len(clean) > 3:
            return clean

    # Fallback to first entry if nothing has stress
    return ipas[0].strip("/[]") if ipas else None


def lookup(word: str, cache: dict | None = None) -> Optional[str]:
    """Look up pronunciation. Returns IPA string or None."""
    if cache is None:
        cache = load_cache()

    key = word.lower()

    # Check cache
    if key in cache:
        return cache[key]["ipa"]

    # Fetch from Wiktionary
    ipa = fetch_wiktionary_ipa(word)
    if ipa:
        cache[key] = {"word": word, "ipa": ipa, "source": "wiktionary"}
        save_cache(cache)
        return ipa

    return None


def lookup_or_manual(word: str, manual_ipa: str, cache: dict | None = None) -> str:
    """Add a manual pronunciation override."""
    if cache is None:
        cache = load_cache()
    cache[word.lower()] = {"word": word, "ipa": manual_ipa, "source": "manual"}
    save_cache(cache)
    return manual_ipa


def batch_lookup(words: list[str]) -> dict[str, Optional[str]]:
    """Look up multiple words, returning results."""
    cache = load_cache()
    results = {}
    for word in words:
        ipa = lookup(word, cache)
        results[word] = ipa
    return results


def load_golds_into_pipeline(pipeline) -> int:
    """Load all cached pronunciations into Kokoro's lexicon golds."""
    cache = load_cache()
    loaded = 0
    for key, entry in cache.items():
        ipa = entry["ipa"]
        if ipa:
            # Store under original casing for exact match,
            # and lowercase for case-insensitive match
            word = entry["word"]
            pipeline.g2p.lexicon.golds[word] = ipa
            if word != key:
                pipeline.g2p.lexicon.golds[key] = ipa
            loaded += 1
    return loaded


# Seed with common tech terms that Wiktionary may not have or that need
# specific pronunciations.  Wiktionary-retrievable terms (docker, python,
# curl, etc.) are NOT listed here — they'll be auto-fetched by
# _enrich_pronunciation_cache().
MANUAL_SEEDS = {
    # Acronyms pronounced as words
    "JSON": "ˈdʒeɪsən",
    "YAML": "ˈjæməl",
    "GraphQL": "ɡɹæf kju ˈɛl",
    "DevOps": "dɛv ˈɒps",
    "Kubernetes": "ˌkuːbərˈnɛtɪs",
    "MySQL": "maɪ ˌɛskjuːˈɛl",
    "PostgreSQL": "ˈpoʊstɡɹɛs kju ˈɛl",
    # Words Wiktionary doesn't cover (no entry / 404)
    "tmux": "ˈtiːmʌks",
    "Linux": "ˈlɪnəks",
    "HTML": "ˈeɪtʃ tɪ ˈɛm ˈɛl",
    "CSS": "siː ˈɛs ˈɛs",
    "JavaScript": "ˈdʒævəskrɪpt",
    "npm": "ɛn piː ˈɛm",
    "nginx": "ˈɛndʒɪks",
    # Platform / brand names
    "Kafka": "ˈkæfkə",
    "PyTorch": "paɪ tɔːrtʃ",
    "Kotlin": "ˈkɒtlɪn",
    "TensorFlow": "ˈtɛnsəɹfloʊ",
    "Homebrew": "ˈhoʊmbɹu",
    "Elasticsearch": "ɪˌlæstɪkˈsɜːrtʃ",
    "Wireshark": "ˈwaɪəɹʃɑːrk",
    "Ansible": "ˈænsɪbəl",
    "Redis": "ˈrɛdɪs",
}


def seed_manual_entries() -> int:
    """Add manual seeds to cache if not already present."""
    cache = load_cache()
    added = 0
    for word, ipa in MANUAL_SEEDS.items():
        key = word.lower()
        if key not in cache:
            cache[key] = {"word": word, "ipa": ipa, "source": "manual"}
            added += 1
    if added:
        save_cache(cache)
    return added


def extract_candidate_words(text: str) -> list[str]:
    """Extract words likely to need pronunciation lookup from TTS text.

    Targets: ALL_CAPS (2+ letters), CamelCase, dot.separated, slash-separated,
    hyphenated compounds, and known tech-like tokens.
    """
    candidates = set()

    # ALL_CAPS tokens (2+ chars) — likely acronyms
    for m in re.finditer(r'\b([A-Z]{2,}s?)\b', text):
        candidates.add(m.group(1))

    # CamelCase / PascalCase tokens
    for m in re.finditer(r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)+s?)\b', text):
        candidates.add(m.group(1))

    # dot-separated identifiers (e.g. A.I., M.C.P.)
    for m in re.finditer(r'\b([A-Z](?:\.[A-Z])+\.?)\b', text):
        cleaned = m.group(1).replace('.', '')
        candidates.add(cleaned)

    # Spaced single letters (e.g. "A I", "A P I") — collapsed by caller
    # These are handled by _pronunciation_postprocess, not here.

    # Known tech patterns: lowercase tech words that g2p often gets wrong
    tech_words = {
        "tmux", "bash", "curl", "wget", "grep", "linux", "ubuntu", "npm",
        "pip", "rust", "vim", "neovim", "zsh", "sudo", "docker", "python",
        "typescript", "javascript", "html", "css",
    }
    for tw in tech_words:
        if re.search(r'\b' + re.escape(tw) + r'\b', text, re.IGNORECASE):
            candidates.add(tw)

    return sorted(candidates)


def enrich_pronunciation_cache(text: str) -> int:
    """Auto-lookup uncached words from text via Wiktionary.

    Call this BEFORE TTS generation so new golds are available.
    Returns number of newly cached entries.
    """
    cache = load_cache()
    # Ensure manual seeds are present first
    seed_manual_entries()
    cache = load_cache()  # reload after seeding

    candidates = extract_candidate_words(text)
    added = 0
    for word in candidates:
        key = word.lower()
        if key in cache:
            continue
        ipa = fetch_wiktionary_ipa(word)
        if ipa:
            cache[key] = {"word": word, "ipa": ipa, "source": "wiktionary"}
            added += 1
            print(f"  Wiktionary: {word} → {ipa}")
    if added:
        save_cache(cache)
    return added


def pronunciation_postprocess(text: str) -> str:
    """Post-LLM pronunciation fix: collapse spaced acronyms so Kokoro golds match.

    The LLM normalization prompt converts "AI" → "A I", "API" → "A P I" etc.
    Kokoro's golds lexicon maps "AI" → correct IPA, but only if the token
    arrives as a single word.  This function reverses the split so golds work.

    Also handles edge cases like "A I-powered" → "AI-powered".
    """
    cache = load_cache()

    # Build lookup: normalized_key → original_word for all cached entries
    # E.g. "ai" → "AI", "api" → "API"
    cache_words = {}
    for key, entry in cache.items():
        cache_words[key] = entry["word"]

    def collapse_spaced_acronym(match: re.Match) -> str:
        """Replace "A I" → "AI" if the collapsed form is in our cache."""
        spaced = match.group(0)
        collapsed = spaced.replace(" ", "")
        if collapsed.lower() in cache_words:
            return cache_words[collapsed.lower()]
        return spaced  # Not a known term — leave as-is

    # Match 2+ consecutive single uppercase letters separated by spaces,
    # optionally followed by lowercase 's' (plurals like "L L M s").
    # Handles: "A I", "A P I", "H T T P", "L L M s"
    text = re.sub(
        r'\b([A-Z](?:\s[A-Z])+(?:\ss)?)\b',
        collapse_spaced_acronym,
        text,
    )

    return text


def main() -> int:
    if "--list" in sys.argv:
        cache = load_cache()
        if not cache:
            print("Cache is empty.")
            return 0
        for key, entry in sorted(cache.items()):
            src = entry.get("source", "?")
            print(f"  {entry['word']:20s} [{src:10s}] {entry['ipa']}")
        print(f"\n{len(cache)} entries total")
        return 0

    if "--seed" in sys.argv:
        added = seed_manual_entries()
        print(f"Seeded {added} new manual entries")
        return 0

    if len(sys.argv) < 2:
        print("Usage: pronunciation_db.py <word> [word2 ...] [--list] [--seed]")
        return 1

    words = [w for w in sys.argv[1:] if not w.startswith("--")]
    results = batch_lookup(words)
    for word, ipa in results.items():
        if ipa:
            print(f"  {word}: {ipa}")
        else:
            print(f"  {word}: NOT FOUND (consider adding manually)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
