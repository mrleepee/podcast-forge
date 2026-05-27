#!/usr/bin/env python3
"""Convert video summary markdown files to audio using VibeVoice TTS."""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import time
import copy
from pathlib import Path

import torch
from transformers.cache_utils import DynamicCache
from transformers.modeling_outputs import BaseModelOutputWithPast

VIBEVOICE_DIR = Path(__file__).resolve().parent.parent / "VibeVoice"
VOICES_DIR = VIBEVOICE_DIR / "demo" / "voices" / "streaming_model"
SAMPLE_RATE = 24000
MAX_CHARS = 15000  # ~8k token context window safety margin


def find_voices():
    """Scan voices directory and return {name: path} mapping."""
    voices = {}
    if not VOICES_DIR.exists():
        return voices
    for pt_file in glob.glob(str(VOICES_DIR / "**" / "*.pt"), recursive=True):
        p = Path(pt_file)
        name = p.stem.lower()
        voices[name] = p
    return dict(sorted(voices.items()))


def resolve_speaker(name, voices):
    """Resolve speaker name to voice file path, with partial matching."""
    name = name.lower()
    if name in voices:
        return voices[name]
    matches = [k for k in voices if name in k or k in name]
    if len(matches) == 1:
        return voices[matches[0]]
    if len(matches) > 1:
        print(f"Ambiguous speaker '{name}', matches: {', '.join(matches)}")
        sys.exit(1)
    print(f"Speaker '{name}' not found. Available: {', '.join(voices.keys())}")
    sys.exit(1)


def clean_markdown(text):
    """Strip markdown formatting to plain text suitable for TTS."""
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^[|>]\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    return text.strip()


def generate_audio(text, speaker_path, output_path, device, cfg_scale=1.5, steps=5, speed=1.0, format="wav"):
    """Generate audio from text using VibeVoice."""
    from vibevoice.modular.modeling_vibevoice_streaming_inference import (
        VibeVoiceStreamingForConditionalGenerationInference,
    )
    from vibevoice.processor.vibevoice_streaming_processor import (
        VibeVoiceStreamingProcessor,
    )

    model_id = "microsoft/VibeVoice-Realtime-0.5B"
    load_dtype = torch.float32
    attn_impl = "sdpa"

    print(f"Loading model ({device}, {load_dtype}, {attn_impl})...")
    model = VibeVoiceStreamingForConditionalGenerationInference.from_pretrained(
        model_id,
        torch_dtype=load_dtype,
        attn_implementation=attn_impl,
        device_map=None,
    )
    model.to(device)
    model.eval()
    model.set_ddpm_inference_steps(num_steps=steps)

    processor = VibeVoiceStreamingProcessor.from_pretrained(model_id)

    print(f"Loading voice: {speaker_path}")
    try:
        with torch.serialization.safe_globals([BaseModelOutputWithPast, DynamicCache]):
            cached_prompt = torch.load(speaker_path, map_location=device, weights_only=True)
    except Exception:
        cached_prompt = torch.load(speaker_path, map_location=device, weights_only=False)

    inputs = processor.process_input_with_cached_prompt(
        text=text,
        cached_prompt=cached_prompt,
        padding=True,
        return_tensors="pt",
        return_attention_mask=True,
    )
    for k, v in inputs.items():
        if torch.is_tensor(v):
            inputs[k] = v.to(device)

    print(f"Generating audio ({len(text)} chars, cfg_scale={cfg_scale}, steps={steps})...")
    start = time.time()
    outputs = model.generate(
        **inputs,
        max_new_tokens=None,
        cfg_scale=cfg_scale,
        tokenizer=processor.tokenizer,
        generation_config={"do_sample": False},
        verbose=True,
        all_prefilled_outputs=copy.deepcopy(cached_prompt),
    )
    elapsed = time.time() - start

    if not outputs.speech_outputs or outputs.speech_outputs[0] is None:
        print("No audio generated.")
        return False

    audio_samples = outputs.speech_outputs[0].shape[-1]
    duration = audio_samples / SAMPLE_RATE
    rtf = elapsed / duration if duration > 0 else float("inf")
    print(f"Generated {duration:.1f}s audio in {elapsed:.1f}s (RTF: {rtf:.2f}x)")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wav_path = output_path.with_suffix(".wav") if format != "wav" else output_path
    processor.save_audio(outputs.speech_outputs[0], output_path=str(wav_path))

    if speed != 1.0 or format != "wav":
        wav_path = _postprocess(wav_path, output_path.with_suffix(f".{format}"), speed, format)
    elif speed != 1.0:
        wav_path = _postprocess(wav_path, wav_path, speed, "wav")

    print(f"Saved: {wav_path}")
    return True


def _postprocess(wav_path, output_path, speed, format):
    """Apply tempo change and format conversion via ffmpeg."""
    if not shutil.which("ffmpeg"):
        print("Warning: ffmpeg not found, skipping post-processing")
        return wav_path

    cmd = ["ffmpeg", "-y", "-i", str(wav_path)]
    filters = []
    if speed != 1.0:
        filters.append(f"atempo={speed}")
    if filters:
        cmd.extend(["-af", ",".join(filters)])
    if format == "mp3":
        cmd.extend(["-codec:a", "libmp3lame", "-qscale:a", "2"])
    elif format == "ogg":
        cmd.extend(["-codec:a", "libvorbis", "-qscale:a", "4"])
    cmd.append(str(output_path))

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        if wav_path != output_path:
            wav_path.unlink()
        return output_path
    print(f"Warning: ffmpeg post-processing failed: {result.stderr.strip()}")
    return wav_path


def main():
    parser = argparse.ArgumentParser(description="Convert summary markdown to audio via VibeVoice TTS")
    parser.add_argument("input", nargs="?", help="Path to .summary.md file or directory to scan")
    parser.add_argument("--speaker", default="en-Clarion_man", help="Speaker name (default: en-Clarion_man)")
    parser.add_argument("--output", help="Output .wav path (default: same name as input)")
    parser.add_argument("--cfg-scale", type=float, default=1.0, help="CFG scale: lower = less expressive (default: 1.0)")
    parser.add_argument("--steps", type=int, default=3, help="Diffusion steps: fewer = faster (default: 3)")
    parser.add_argument("--speed", type=float, default=1.25, help="Playback speed multiplier (default: 1.25)")
    parser.add_argument("--format", default="wav", choices=["wav", "mp3", "ogg"], help="Output format (default: wav)")
    parser.add_argument("--device", default=None, help="Force device: mps, cpu")
    parser.add_argument("--list-voices", action="store_true", help="List available speakers and exit")
    args = parser.parse_args()

    voices = find_voices()
    if args.list_voices:
        if not voices:
            print(f"No voices found in {VOICES_DIR}")
            print("Run: bash /Users/lpollington/Dev/VibeVoice/demo/download_experimental_voices.sh")
        else:
            print(f"Available voices ({len(voices)}):")
            for name, path in voices.items():
                rel = path.relative_to(VOICES_DIR)
                print(f"  {name:30s}  {rel}")
        return

    if not voices:
        print(f"Error: No voices found in {VOICES_DIR}")
        print("Run: bash /Users/lpollington/Dev/VibeVoice/demo/download_experimental_voices.sh")
        sys.exit(1)

    speaker_path = resolve_speaker(args.speaker, voices)
    device = args.device or ("mps" if torch.backends.mps.is_available() else "cpu")

    input_path = Path(args.input)
    if input_path.is_dir():
        md_files = sorted(input_path.glob("*.summary.md"))
        if not md_files:
            print(f"No .summary.md files found in {input_path}")
            sys.exit(1)
        print(f"Found {len(md_files)} summary files in {input_path}")
        for md_file in md_files:
            output_wav = md_file.with_name(md_file.stem).with_suffix(".wav")
            if output_wav.exists():
                print(f"Skipping {md_file.name} (audio exists)")
                continue
            text = clean_markdown(md_file.read_text(encoding="utf-8"))
            if len(text) > MAX_CHARS:
                print(f"Warning: {md_file.name} is {len(text)} chars, truncating to {MAX_CHARS}")
                text = text[:MAX_CHARS]
            generate_audio(text, speaker_path, output_wav, device,
                           cfg_scale=args.cfg_scale, steps=args.steps,
                           speed=args.speed, format=args.format)
        return

    if not input_path.exists():
        print(f"Error: {input_path} not found")
        sys.exit(1)

    output_path = args.output or str(input_path.with_name(input_path.stem).with_suffix(f".{args.format}"))
    text = clean_markdown(input_path.read_text(encoding="utf-8"))
    if len(text) > MAX_CHARS:
        print(f"Warning: text is {len(text)} chars, truncating to {MAX_CHARS}")
        text = text[:MAX_CHARS]

    generate_audio(text, speaker_path, output_path, device,
                   cfg_scale=args.cfg_scale, steps=args.steps,
                   speed=args.speed, format=args.format)


if __name__ == "__main__":
    main()
