#!/usr/bin/env python3
"""Convert a text file to audio using Kokoro TTS with a random British voice."""

import argparse
import os
import random
import subprocess
import sys
import warnings
from pathlib import Path

os.environ["PYTORCH_JIT"] = "0"
warnings.filterwarnings("ignore")

import numpy as np
import soundfile as sf
from kokoro import KPipeline

BRITISH_VOICES = [
    "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
]
SAMPLE_RATE = 24000


def main():
    parser = argparse.ArgumentParser(description="Text file to audio via Kokoro TTS")
    parser.add_argument("input", help="Path to .txt file")
    parser.add_argument("-o", "--output", help="Output path (default: input name .mp3)")
    parser.add_argument("-v", "--voice", help="Voice name (default: random British)")
    parser.add_argument("-f", "--format", default="mp3", choices=["wav", "mp3"])
    args = parser.parse_args()

    src = Path(args.input)
    if not src.exists():
        sys.exit(f"File not found: {src}")

    text = src.read_text(encoding="utf-8").strip()
    if not text:
        sys.exit("File is empty")

    voice = args.voice or random.choice(BRITISH_VOICES)
    output = Path(args.output) if args.output else src.with_suffix(f".{args.format}")

    print(f"Voice: {voice}")
    print(f"Text:  {len(text)} chars")

    pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    segments = list(pipeline(text, voice=voice))
    if not segments:
        sys.exit("No audio generated")

    audio = np.concatenate([a for _, _, a in segments])
    duration = len(audio) / SAMPLE_RATE
    print(f"Audio: {duration:.1f}s ({duration/60:.1f}min)")

    wav_path = output.with_suffix(".wav") if args.format == "mp3" else output
    sf.write(str(wav_path), audio, SAMPLE_RATE)

    if args.format == "mp3":
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav_path),
             "-codec:a", "libmp3lame", "-qscale:a", "2", str(output)],
            capture_output=True, text=True,
        )
        wav_path.unlink(missing_ok=True)
        if result.returncode != 0:
            sys.exit(f"ffmpeg error: {result.stderr.strip()}")

    size_mb = output.stat().st_size / (1024 * 1024)
    print(f"Saved: {output} ({size_mb:.1f}MB)")


if __name__ == "__main__":
    main()
