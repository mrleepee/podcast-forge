#!/usr/bin/env python3
"""Standalone smoke test for Z.ai's GLM models via the Anthropic-compatible API.

Mirrors the exact call path used by ``pipeline_stages.call_verifier``:
  - Endpoint: https://api.z.ai/api/anthropic/v1/messages  (Anthropic Messages API)
  - Auth:     x-api-key header, resolved from ZAI_API_KEY or
              ~/.claude/settings-GLM.json -> env.ANTHROPIC_AUTH_TOKEN
  - Body:     {"model", "max_tokens", "temperature", "messages", "system"}

This endpoint is covered by the GLM Coding Plan subscription — it does NOT
draw on prepaid API credits, which is why we use it instead of /api/paas/v4.

Use it to confirm a model slug is valid before wiring it into settings.json.
For example, to probe GLM 5.2::

    python tools/test_glm.py
    python tools/test_glm.py --model glm-5.1
    python tools/test_glm.py --model glm-5.2 --prompt "What is 17 * 23?"

Exit code 0 on a successful 200 with text; non-zero on any error (so the
error body — which usually names the correct slug — prints to stderr).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE = "https://api.z.ai/api/anthropic"
ANTHROPIC_VERSION = "2023-06-01"
GLM_SETTINGS_PATH = Path.home() / ".claude" / "settings-GLM.json"


def read_glm_settings() -> dict:
    """Return the env block of ~/.claude/settings-GLM.json (empty on failure)."""
    try:
        settings = json.loads(GLM_SETTINGS_PATH.read_text(encoding="utf-8"))
        env = settings.get("env", {})
        return env if isinstance(env, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def resolve_key() -> str | None:
    """ZAI_API_KEY first, then env.ANTHROPIC_AUTH_TOKEN from settings-GLM.json."""
    key = os.environ.get("ZAI_API_KEY")
    if key and key.strip():
        return key.strip()
    token = read_glm_settings().get("ANTHROPIC_AUTH_TOKEN")
    if token and token.strip():
        return token.strip()
    return None


def resolve_messages_url() -> str:
    """Honour ANTHROPIC_BASE_URL from settings-GLM.json, else the Z.ai default."""
    base = read_glm_settings().get("ANTHROPIC_BASE_URL") or DEFAULT_BASE
    return base.rstrip("/") + "/v1/messages"


def call_glm(model: str, prompt: str, system: str | None,
             temperature: float, max_tokens: int,
             timeout: int) -> tuple[str, dict, float]:
    """Call GLM and return (text, raw_response_body, elapsed_seconds)."""
    api_key = resolve_key()
    if not api_key:
        raise RuntimeError(
            "Z.ai key not found (set ZAI_API_KEY or env.ANTHROPIC_AUTH_TOKEN "
            f"in {GLM_SETTINGS_PATH})"
        )

    url = resolve_messages_url()
    body: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        },
    )

    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} from {url}:\n{err_body}") from None
    elapsed = time.monotonic() - start

    blocks = raw.get("content") or []
    text = "".join(
        b.get("text", "") for b in blocks if b.get("type") == "text"
    ).strip()
    return text, raw, elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="glm-5.2",
                        help="Model slug to test (default: glm-5.2)")
    parser.add_argument("--prompt", default="Reply with exactly: GLM smoke test OK.",
                        help="User prompt (default: a trivial round-trip)")
    parser.add_argument("--system", default=None,
                        help="Optional system prompt")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--raw", action="store_true",
                        help="Also print the full JSON response body")
    args = parser.parse_args()

    print(f"endpoint : {resolve_messages_url()}")
    print(f"model    : {args.model}")
    print(f"key src  : {'ZAI_API_KEY' if os.environ.get('ZAI_API_KEY') else GLM_SETTINGS_PATH}")
    print(f"prompt   : {args.prompt!r}")
    print("-" * 60)

    try:
        text, raw, elapsed = call_glm(
            args.model, args.prompt, args.system,
            args.temperature, args.max_tokens, args.timeout,
        )
    except RuntimeError as e:
        print(f"FAILED\n{e}", file=sys.stderr)
        return 1

    if not text:
        print("FAILED: empty text in response", file=sys.stderr)
        print(json.dumps(raw, indent=2), file=sys.stderr)
        return 1

    print(f"OK ({elapsed:.2f}s)")
    print(f"usage: {raw.get('usage', {})}")
    print("-" * 60)
    print(text)
    if args.raw:
        print("-" * 60)
        print(json.dumps(raw, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
