#!/usr/bin/env python3
"""Convert a WebVTT subtitle file into readable paragraphs."""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

TIMING_MARKER = '-->'
META_PREFIXES = ("WEBVTT", "Kind:", "Language:")
TAG_PATTERN = re.compile(r'<[^>]+>')
SENTENCE_END = re.compile(r'[.!?][)"\']?$')
CAP_AFTER_PUNCT = re.compile(r'([.!?][)"\']?\s+)([a-z])')
DUPLICATE_SPACE = re.compile(r'\s+')
NON_US_PATTERN = re.compile(r'non\s*-?\s*us', re.IGNORECASE)
HYPHEN_US_PATTERN = re.compile(r'-\s+US')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a VTT caption file into flowing text paragraphs."
    )
    parser.add_argument("input", type=Path, help="Path to the source .vtt file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Destination file for the transcript (defaults to input with .txt)",
    )
    return parser.parse_args()


def iter_caption_lines(path: Path):
    last = None
    with path.open('r', encoding='utf-8') as handle:
        for raw in handle:
            if TIMING_MARKER in raw:
                continue
            stripped = raw.strip()
            if not stripped or stripped.startswith(META_PREFIXES):
                continue
            cleaned = TAG_PATTERN.sub('', stripped).strip()
            if not cleaned or cleaned == last:
                continue
            yield cleaned
            last = cleaned


def normalize_sentence(text: str) -> str:
    text = DUPLICATE_SPACE.sub(' ', text)
    text = HYPHEN_US_PATTERN.sub('-US', text)
    text = NON_US_PATTERN.sub('non-US', text)
    if text:
        text = text[0].upper() + text[1:]
    text = CAP_AFTER_PUNCT.sub(lambda m: m.group(1) + m.group(2).upper(), text)
    return text


def lines_to_paragraphs(lines):
    buffer = []
    for line in lines:
        buffer.append(line)
        if SENTENCE_END.search(line):
            yield normalize_sentence(' '.join(buffer))
            buffer.clear()
    if buffer:
        yield normalize_sentence(' '.join(buffer))


def convert(input_path: Path, output_path: Path | None) -> None:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    destination = output_path or input_path.with_suffix('.txt')
    paragraphs = list(lines_to_paragraphs(iter_caption_lines(input_path)))
    if not paragraphs:
        raise ValueError("No transcript content detected in the VTT file.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('w', encoding='utf-8') as handle:
        handle.write('\n\n'.join(paragraphs))


def main() -> int:
    args = parse_args()
    try:
        convert(args.input, args.output)
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
