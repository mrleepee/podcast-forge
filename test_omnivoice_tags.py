#!/usr/bin/env python3
"""
Quick OmniVoice non-verbal tags test — throw-away audio sample.
Generates a short clip with all supported tags to hear how they render.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def test_omnivoice_tags():
    """Render a short test with all non-verbal tags."""
    try:
        from video_downloader import _omnivoice_render
    except ImportError as e:
        print(f"Cannot import _omnivoice_render: {e}")
        sys.exit(1)

    # All tags from the official README + [sniff] from the model card
    tags_text = """[laughter] Okay, I did not expect that.

[sigh] Give me a moment.

[question-en] Are you sure about this? It doesn’t quite add up.

[surprise-oh] Oh—now I see it.

[surprise-wa] Wow, that’s wild.

[dissatisfaction-hnn] Hnn. Not great, but not a disaster either.

[confirmation-en] Okay. Let’s keep going."""

    segments = [{"text": tags_text, "language": "English"}]

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        output_path = f.name

    print("Rendering OmniVoice tags test...")
    print(f"Text: {tags_text[:100]}...")
    print(f"Output: {output_path}")

    try:
        _omnivoice_render(segments, output_path, silence_sec=0.12)
        print(f"✓ Rendered successfully: {output_path}")
        return output_path
    except Exception as e:
        print(f"✗ Render failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    output = test_omnivoice_tags()
    print(f"\n🎧 Listen: {output}")
