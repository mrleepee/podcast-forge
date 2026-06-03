"""
pipeline_stages.py — Evidence-first pipeline stages.

Each function is a focused agent with its own prompt.
Stage 1: extract_evidence() — forensic evidence extraction from transcript
Stage 2: generate_outline() — thesis and outline from evidence + SOUL.md
Stage 3: draft_script() — narration script from outline + evidence
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Shared MiniMax call — sends system+user prompts, uses same API as
# _summarize_with_minimax but with the stage-specific system prompt
# ---------------------------------------------------------------------------

_MINIMAX_API_URLS = [
    "https://api.minimax.chat/v1/text/chatcompletion_v2",
    "https://api.minimax.io/v1/text/chatcompletion_v2",
]


def _call_minimax(system_prompt: str, user_prompt: str,
                  temperature: float = 0.3) -> str:
    """Call MiniMax API with a system + user prompt.

    Uses the same model (MiniMax-M2.7) and URL rotation as the existing
    _summarize_with_minimax, but sends a proper system message so the
    stage-specific agent persona is applied.
    """
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        raise RuntimeError("MINIMAX_API_KEY not set")

    payload = json.dumps({
        "model": "MiniMax-M2.7",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }).encode("utf-8")

    last_error = None
    for api_url in _MINIMAX_API_URLS:
        req = urllib.request.Request(
            api_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            choices = body.get("choices") or []
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
            last_error = f"Unexpected MiniMax response: {body}"
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            last_error = f"MiniMax API error {e.code} ({api_url}): {err_body}"
            continue
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_error = f"MiniMax API connection error ({api_url}): {e}"
            continue

    raise RuntimeError(last_error or "All MiniMax API URLs failed")


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

    Returns a JSON array of evidence entries. Raises RuntimeError for
    insufficient source material or LLM failure.
    """
    if not text or len(text.split()) < 100:
        raise RuntimeError(
            f"Not enough source material to extract evidence "
            f"(received {len(text.split()) if text else 0} words, need ≥100)"
        )

    prompt = f"Extract all evidence from the following text:\n\n{text[:8000]}"

    response = _call_minimax(EXTRACTION_SYSTEM_PROMPT, prompt)

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

    raise RuntimeError(
        f"Evidence extraction LLM returned non-JSON response "
        f"(first 200 chars: {response[:200]})"
    )


def _extract_evidence_deterministic(text: str) -> list[dict]:
    """Deterministic evidence extraction for testing — NOT used in production pipeline."""
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
- close: the actual closing lines (2-3 sentences), NOT a label or strategy. Land the \
thesis as a personal stake, call back to the hook's specific image, and end on a short \
declarative button line. You may end on a question ONLY if it is sharp, concrete, and \
aimed straight at the listener — never an abstract "the question is whether..." \
restatement. Do not trail off or end on a generic wrap-up.
- warnings: array of strings (include "thin evidence: only N claims available" \
if fewer than 5 evidence entries)"""


def generate_outline(evidence: list[dict], soul_text: str) -> dict:
    """Generate a thesis and outline from evidence + SOUL.md.

    Raises RuntimeError if the LLM fails or returns non-JSON.
    """
    evidence_summary = json.dumps(evidence[:20], indent=2, ensure_ascii=False)
    soul_excerpt = soul_text[:2000] if soul_text else "(no SOUL.md provided)"

    prompt = (
        f"Evidence ({len(evidence)} entries):\n{evidence_summary}\n\n"
        f"Show bible (SOUL.md):\n{soul_excerpt}"
    )

    response = _call_minimax(OUTLINE_SYSTEM_PROMPT, prompt)

    try:
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            outline = json.loads(match.group(0))
            if isinstance(outline, dict) and "thesis" in outline:
                return outline
    except json.JSONDecodeError:
        pass

    raise RuntimeError(
        f"Outline generation LLM returned non-JSON or missing 'thesis' "
        f"(first 200 chars: {response[:200]})"
    )


def _generate_outline_deterministic(evidence: list[dict]) -> dict:
    """Deterministic outline for testing — NOT used in production pipeline."""
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


def _build_opening_avoidance() -> str:
    """Build an instruction telling the narrator which opening words to avoid."""
    log_path = Path(__file__).parent / "checks" / "opening_log.json"
    if not log_path.exists():
        return ""

    try:
        from checks.check_opening import _load_opening_log, _get_recent_openings
        log = _load_opening_log(log_path)
        recent = _get_recent_openings(log, n=10)
    except Exception:
        return ""

    if not recent:
        return ""

    # Count first words
    word_counts: dict[str, int] = {}
    for opening in recent:
        m = re.match(r"[a-zA-Z]+", opening)
        if m:
            w = m.group(0).lower()
            word_counts[w] = word_counts.get(w, 0) + 1

    overused = [w for w, c in word_counts.items() if c >= 2]
    if not overused:
        return ""

    words_str = ", ".join(f'"{w.capitalize()}..."' for w in overused)
    examples = "; ".join(f'"{r[:60]}"' for r in recent[:3])
    return (
        f"IMPORTANT: Do NOT start the script with {words_str}. "
        f"These openings have been used recently: {examples}. "
        f"Choose a fresh opening — a specific number, a name, a bold claim, "
        f"or a question the listener hasn't heard before."
    )


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

    # Build opening-freshness instruction from the log
    opening_instruction = _build_opening_avoidance()

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
        f"traceable to the evidence above. Do not introduce facts not in the evidence.\n\n"
        f"FINALE: End deliberately — do not trail off or stop on a flat restatement. "
        f"Develop the CLOSE into a real ending: in your final two to four sentences, land "
        f"the implication as a personal stake and call back to the opening hook's specific "
        f"image. Finish on a short, punchy, declarative line — or, when the hook invites it, "
        f"a single sharp question aimed straight at the listener. Never end on an abstract "
        f"\"the question you should ask is...\" construction, a generic summary, or a cliche "
        f"like \"only time will tell\".\n\n"
        f"{opening_instruction}"
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
