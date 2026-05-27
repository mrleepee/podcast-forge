"""Local pronunciation database backed by Wiktionary IPA lookups.

Usage:
    # Look up a word (fetches from Wiktionary if not cached)
    python pronunciation_db.py JSON

    # Batch look up multiple words
    python pronunciation_db.py JSON Kubernetes Docker

    # Show all cached entries
    python pronunciation_db.py --list
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

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

    # Try to find IPA within English language sections specifically.
    # Wiktionary pages have <h2> with <span class="headword-line"> containing "English",
    # or sections marked with id containing "English".
    # Strategy: find English heading, then grab IPA spans within that section.

    # Look for English section heading
    english_start = None
    for heading in soup.find_all(["h2", "h3"]):
        heading_text = heading.get_text(strip=True).lower()
        if heading_text == "english":
            english_start = heading
            break

    if english_start:
        # Collect IPA spans between English heading and next language heading
        ipas = []
        for sibling in english_start.find_next_siblings():
            if sibling.name in ("h2",) and sibling.get_text(strip=True).lower() != "english":
                break
            for span in sibling.find_all("span", class_="IPA"):
                ipas.append(span.get_text(strip=True))
    else:
        # Fallback: no English section found, try all IPA spans
        ipas = [s.get_text(strip=True) for s in soup.select("span.IPA")]

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


# Seed with common tech terms that Wiktionary may not have
MANUAL_SEEDS = {
    "JSON": "ˈdʒeɪsən",
    "YAML": "ˈjæməl",
    "GraphQL": "ɡɹæf kju ˈɛl",
    "DevOps": "dɛv ˈɒps",
    "Kubernetes": "ˌkuːbərˈnɛtɪs",
    "PyTorch": "paɪ tɔːrtʃ",
    "Kafka": "ˈkæfkə",
    "nginx": "ˈɛndʒɪks",
    "PostgreSQL": "ˈpoʊstɡɹɛs kju ˈɛl",
    "MySQL": "maɪ ˌɛskjuːˈɛl",
    "Redis": "ˈrɛdɪs",
    "Kotlin": "ˈkɒtlɪn",
    "TensorFlow": "ˈtɛnsəɹfloʊ",
    "Homebrew": "ˈhoʊmbɹu",
    "Elasticsearch": "ɪˌlæstɪkˈsɜːrtʃ",
    "Wireshark": "ˈwaɪəɹʃɑːrk",
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
