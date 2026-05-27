#!/usr/bin/env python3
"""Convert summary markdown files to narrative audio using MiniMax + Kokoro."""

import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path


def _load_dotenv():
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

from kokoro import KPipeline
import soundfile as sf


MINIMAX_API_URLS = [
    "https://api.minimax.io/v1/text/chatcompletion_v2",
    "https://api.minimax.chat/v1/text/chatcompletion_v2",
]
VOICE = "bf_emma"
SAMPLE_RATE = 24000


def to_narrative(markdown_text):
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        print("Error: MINIMAX_API_KEY not set")
        return None

    prompt = (
        "Rewrite the following video summary as a flowing narrative suitable for "
        "a text-to-speech voiceover. Use conversational English with a British tone. "
        "Remove all markdown formatting, bullet points, and headers. Write in "
        "paragraphs that flow naturally when read aloud. Keep the same information "
        "and key facts but present them as if a presenter is telling the story.\n\n"
        f"--- SUMMARY START ---\n{markdown_text}\n--- SUMMARY END ---"
    )

    payload = json.dumps({
        "model": "MiniMax-M2.7",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }).encode("utf-8")

    for api_url in MINIMAX_API_URLS:
        req = urllib.request.Request(
            api_url, data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            choices = body.get("choices") or []
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")
            print(f"MiniMax error {e.code}: {err}")
    return None


def text_to_audio(text, output_path, voice=VOICE):
    pipeline = KPipeline(lang_code="a")
    segments = list(pipeline(text, voice=voice))
    if not segments:
        print(f"No audio generated for {output_path}")
        return False

    audio_chunks = []
    for gs, ps, audio in segments:
        audio_chunks.append(audio)
    import numpy as np
    full_audio = np.concatenate(audio_chunks)
    sf.write(str(output_path), full_audio, SAMPLE_RATE)
    duration = len(full_audio) / SAMPLE_RATE
    print(f"  Audio: {duration:.1f}s saved to {output_path.name}")
    return True


def main():
    downloads = Path("/Users/lpollington/Dev/YouTubeDownloader/downloads/raw")
    files = sorted(downloads.glob("*.summary.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]

    print(f"Processing {len(files)} summaries...\n")

    for f in files:
        base = f.stem.replace(".summary", "")
        txt_path = f.parent / f"{base}.narrative.txt"
        wav_path = f.parent / f"{base}.wav"

        print(f"[{base[:60]}]")

        md_text = f.read_text(encoding="utf-8")

        if txt_path.exists():
            print(f"  Narrative exists, skipping MiniMax")
            narrative = txt_path.read_text(encoding="utf-8")
        else:
            print(f"  Converting to narrative...")
            narrative = to_narrative(md_text)
            if not narrative:
                print(f"  Failed, skipping")
                continue
            txt_path.write_text(narrative, encoding="utf-8")
            print(f"  Saved: {txt_path.name}")

        if wav_path.exists():
            print(f"  Audio exists, skipping")
        else:
            text_to_audio(narrative, wav_path)

        print()


if __name__ == "__main__":
    main()
