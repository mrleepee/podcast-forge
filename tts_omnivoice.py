#!/usr/bin/env python
"""OmniVoice TTS worker — runs under the OmniVoice venv, not podcast-forge's.

Loads the OmniVoice diffusion model once and synthesizes a batch of segments
described by a JSON job file. Invoked as a subprocess from video_downloader.py
so the main pipeline never imports OmniVoice's heavy deps.

Usage:
    <omnivoice-venv>/bin/python tts_omnivoice.py job.json

Job JSON:
    {
      "model": "k2-fsa/OmniVoice",          # optional, this is the default
      "instruct_en": "female, british accent, young adult",
      "instruct_es": "female",              # accents are English-only in OmniVoice
      "speed": 1.0,                          # optional
      "ref_audio": null,                     # cloning seam — when set, overrides instruct
      "ref_text": null,                      # optional transcript for the ref clip
      "segments": [
        {"text": "...", "language": "English", "out_wav": "/abs/seg0.wav"},
        {"text": "...", "language": "Spanish", "out_wav": "/abs/seg1.wav"}
      ]
    }

Emits a single JSON object on stdout: {"ok": bool, "sample_rate": int,
"segments": [{"out_wav", "sec"}...], "error": str|null}. All diagnostic/library
chatter goes to stderr so stdout stays parseable.
"""

import json
import sys

import torch
import torchaudio


def _eprint(*a):
    print(*a, file=sys.stderr, flush=True)


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"ok": False, "error": "usage: tts_omnivoice.py job.json"}))
        return 2

    with open(sys.argv[1]) as fh:
        job = json.load(fh)

    model_id = job.get("model", "k2-fsa/OmniVoice")
    instruct_en = job.get("instruct_en", "female, british accent, young adult")
    instruct_es = job.get("instruct_es", "female")
    speed = job.get("speed")
    ref_audio = job.get("ref_audio")  # cloning seam — unused in instruct mode
    ref_text = job.get("ref_text")
    segments = job["segments"]

    from omnivoice.cli.infer import get_best_device
    from omnivoice.models.omnivoice import OmniVoice

    device = get_best_device()
    _eprint(f"[tts_omnivoice] loading {model_id} on {device}")
    model = OmniVoice.from_pretrained(model_id, device_map=device, dtype=torch.float16)
    sr = model.sampling_rate

    results = []
    for i, seg in enumerate(segments):
        language = seg.get("language") or None
        out_wav = seg["out_wav"]
        is_es = (str(language).lower().startswith("span") or str(language).lower() == "es")

        gen_kwargs = {"text": seg["text"], "language": language}
        if speed is not None:
            gen_kwargs["speed"] = speed
        if ref_audio:
            # Voice-cloning mode (locked timbre) — overrides instruct for every segment.
            gen_kwargs["ref_audio"] = ref_audio
            if ref_text:
                gen_kwargs["ref_text"] = ref_text
        else:
            # Per-segment instruct (e.g. duo speaker B) wins over the language default.
            gen_kwargs["instruct"] = seg.get("instruct") or (instruct_es if is_es else instruct_en)

        _eprint(f"[tts_omnivoice] segment {i+1}/{len(segments)} "
                f"({language}, {len(seg['text'])} chars) -> {out_wav}")
        audios = model.generate(**gen_kwargs)
        wav = audios[0]
        if wav.dim() == 1:
            wav = wav.unsqueeze(0)
        torchaudio.save(out_wav, wav.cpu(), sr)
        results.append({"out_wav": out_wav, "sec": round(wav.shape[-1] / sr, 2)})

    print(json.dumps({"ok": True, "sample_rate": sr, "segments": results}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # surface a parseable failure to the parent
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        raise
