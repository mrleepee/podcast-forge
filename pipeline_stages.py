"""
pipeline_stages.py — Evidence-first pipeline stages.

Each function is a focused agent with its own prompt.
Stage 1: extract_evidence() — forensic evidence extraction from transcript
Stage 2: generate_outline() — thesis and outline from evidence + SOUL.md
Stage 3: draft_script() — narration script from outline + evidence
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Shared MiniMax call (reuses existing infrastructure)
# ---------------------------------------------------------------------------

def _call_minimax(system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
    """Call MiniMax API with a system + user prompt. Returns raw text response."""
    import urllib.request
    import os

    api_url = os.environ.get("MINIMAX_API_URL", "")
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_url or not api_key:
        # Fallback: use the existing _summarize_with_minimax infrastructure
        raise RuntimeError("MiniMax API credentials not configured")

    payload = json.dumps({
        "model": "MiniMax-Text-01",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    # Try to use existing session/cookie infrastructure
    req = urllib.request.Request(api_url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        raise RuntimeError(f"MiniMax API call failed: {e}")


def _call_minimax_via_existing(system_prompt: str, user_prompt: str,
                               temperature: float = 0.3) -> str:
    """Call MiniMax using the existing video_downloader infrastructure."""
    import subprocess
    import sys

    # Use the existing _summarize_with_minimax pattern but with custom prompts
    combined = f"{system_prompt}\n\n---\n\n{user_prompt}"

    script = f"""
import sys
sys.path.insert(0, '.')
from video_downloader import _summarize_with_minimax
# Reuse the existing MiniMax call infrastructure
result = _summarize_with_minimax('''{user_prompt}''')
print(result)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(f"MiniMax call failed: {result.stderr[-200:]}")
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Stage 1: Evidence extraction
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """You are a forensic evidence analyst. Extract every \
factual claim, statistic, named source, and specific number from the transcript. \
For each claim, preserve the original quote, note the paragraph number, and classify \
source reliability and confidence.

Return ONLY a JSON array. No prose, no markdown fences. Each entry must have:
- claim: the factual claim (string)
- source_quote: the original text supporting the claim (string)
- timestamp: paragraph index or time offset (string, e.g. "para:3" or "12:34")
- source_reliability: one of "primary", "secondary", "hearsay"
- confidence: one of "high", "medium", "low"
- type: one of "fact", "opinion", "prediction", "statistic"

If unsure about any field, use low confidence and secondary reliability."""


def extract_evidence(text: str) -> list[dict]:
    """Extract evidence entries from transcript or source text.

    Returns a JSON array of evidence entries. Returns empty list for
    insufficient source material.
    """
    if not text or len(text.split()) < 100:
        return []

    prompt = f"Extract all evidence from the following text:\n\n{text[:8000]}"

    try:
        response = _call_minimax_via_existing(EXTRACTION_SYSTEM_PROMPT, prompt)
    except Exception as e:
        # If MiniMax fails, do basic extraction as fallback
        return _extract_evidence_deterministic(text)

    # Parse JSON from response
    try:
        # Try to find JSON array in the response
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            entries = json.loads(match.group(0))
            if isinstance(entries, list):
                return entries
    except json.JSONDecodeError:
        pass

    # Fallback to deterministic extraction
    return _extract_evidence_deterministic(text)


def _extract_evidence_deterministic(text: str) -> list[dict]:
    """Basic deterministic evidence extraction when LLM is unavailable."""
    entries = []
    sentences = re.split(r'(?<=[.!?])\s+', text)

    # Patterns that suggest factual claims
    number_pattern = re.compile(r'\b\d+\.?\d*%?\b')
    year_pattern = re.compile(r'\b(18|19|20)\d{2}\b')
    quote_pattern = re.compile(r'"[^"]+"')

    for i, sentence in enumerate(sentences):
        has_number = bool(number_pattern.search(sentence))
        has_year = bool(year_pattern.search(sentence))
        has_quote = bool(quote_pattern.search(sentence))

        if has_number or has_year or has_quote:
            entry = {
                "claim": sentence.strip(),
                "source_quote": sentence.strip(),
                "timestamp": f"para:{i}",
                "source_reliability": "secondary",
                "confidence": "high" if has_number else "medium",
                "type": "statistic" if has_number else "fact",
            }
            entries.append(entry)

    return entries


# ---------------------------------------------------------------------------
# Stage 2: Thesis and outline generation
# ---------------------------------------------------------------------------

OUTLINE_SYSTEM_PROMPT = """You are a podcast editor. Given a set of evidence claims \
and the show bible SOUL.md, choose the strongest angle for a short podcast episode.

Return ONLY a JSON object. No prose, no markdown fences. The object must have:
- thesis: one sentence stating the central argument
- hook: the opening strategy (surprising fact, question, or bold statement)
- stakes: why the listener should care (1-2 sentences)
- evidence_beats: array of integers referencing evidence entry indices
- counterpoint: the opposing view or limitation (1-2 sentences)
- implication: what it means for the listener (1-2 sentences)
- close: the ending strategy (implication, not generic wrap-up)
- warnings: array of strings (include "thin evidence: only N claims available" \
if fewer than 5 evidence entries)"""


def generate_outline(evidence: list[dict], soul_text: str) -> dict:
    """Generate a thesis and outline from evidence + SOUL.md."""
    evidence_summary = json.dumps(evidence[:20], indent=2, ensure_ascii=False)
    soul_excerpt = soul_text[:2000] if soul_text else "(no SOUL.md provided)"

    prompt = (
        f"Evidence ({len(evidence)} entries):\n{evidence_summary}\n\n"
        f"Show bible (SOUL.md):\n{soul_excerpt}"
    )

    try:
        response = _call_minimax_via_existing(OUTLINE_SYSTEM_PROMPT, prompt)
    except Exception:
        return _generate_outline_deterministic(evidence)

    try:
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            outline = json.loads(match.group(0))
            if isinstance(outline, dict) and "thesis" in outline:
                return outline
    except json.JSONDecodeError:
        pass

    return _generate_outline_deterministic(evidence)


def _generate_outline_deterministic(evidence: list[dict]) -> dict:
    """Basic deterministic outline when LLM is unavailable."""
    warnings = []
    if len(evidence) < 5:
        warnings.append(f"thin evidence: only {len(evidence)} claims available")

    return {
        "thesis": "Analysis of the key claims in the source material.",
        "hook": "surprising_fact",
        "stakes": "These claims affect how we understand the topic.",
        "evidence_beats": list(range(min(len(evidence), 10))),
        "counterpoint": "The source material may present a limited perspective.",
        "implication": "Listeners should verify these claims independently.",
        "close": "implication",
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Stage 3: Script drafting
# ---------------------------------------------------------------------------

def draft_script(outline: dict, evidence: list[dict], soul_text: str,
                 video_title: str = "", extra_prompt: str = "",
                 target_words: int = 700, duo: bool = False) -> str:
    """Draft a narration script from outline + evidence.

    Uses the existing _narrate_as_podcast infrastructure but with
    structured input instead of flat summary.
    """
    from video_downloader import _narrate_as_podcast

    # Build a structured input that combines outline + evidence
    evidence_claims = "\n".join(
        f"  [{i}] {e.get('claim', '')} (confidence: {e.get('confidence', 'unknown')})"
        for i, e in enumerate(evidence[:20])
    )

    structured_input = (
        f"THESIS: {outline.get('thesis', '')}\n"
        f"HOOK: {outline.get('hook', '')}\n"
        f"STAKES: {outline.get('stakes', '')}\n"
        f"EVIDENCE BEATS: {outline.get('evidence_beats', [])}\n"
        f"COUNTERPOINT: {outline.get('counterpoint', '')}\n"
        f"IMPLICATION: {outline.get('implication', '')}\n"
        f"CLOSE: {outline.get('close', '')}\n\n"
        f"EVIDENCE:\n{evidence_claims}\n\n"
        f"Write the narration following this outline. Every factual claim must be "
        f"traceable to the evidence above. Do not introduce facts not in the evidence."
    )

    # Use existing narration infrastructure with the structured input
    narrative = _narrate_as_podcast(
        structured_input,
        video_title=video_title,
        extra_prompt=extra_prompt,
        target_words=target_words,
        language="en",
        duo=duo,
    )

    return narrative or ""
