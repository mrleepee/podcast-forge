"""Test Kokoro TTS with lexicon golds + text pre-processing for problem words."""
import warnings
warnings.filterwarnings("ignore")
import re
import numpy as np
import soundfile as sf
import subprocess
from pathlib import Path
from kokoro import KPipeline

SAMPLE_RATE = 24000
OUTPUT_DIR = Path("voice_tests")
OUTPUT_DIR.mkdir(exist_ok=True)
VOICE = "bf_emma"

pipeline = KPipeline(lang_code='a', repo_id="hexgrad/Kokoro-82M")

# ============================================================
# 1. LEXICON GOLDS — inject correct pronunciations into g2p
# ============================================================
# These words are looked up in golds by the lexicon BEFORE g2p guesses.

LEXICON_OVERRIDES = {
    # --- Roman numerals (regnal) ---
    'VIII':    'ðə ˈeɪtθ',            # the eighth
    'VII':     'ðə sˈɛvənθ',          # the seventh
    'VI':      'ðə sˈɪksθ',           # the sixth
    'IV':      'ðə fˈɔɹθ',            # the fourth
    'III':     'ðə θˈɹi',             # the third
    'II':      'ðə sˈɛkənd',          # the second
    'XIV':     'ðə fɔɹtˈiːnθ',        # the fourteenth
    'XVI':     'ðə sɪkstˈiːnθ',       # the sixteenth
    'XIII':    'ðə θɜːtˈiːnθ',        # the thirteenth

    # --- Word-pronounced acronyms ---
    'UNESCO':  'junˈɛskO',            # you-NESS-co
    'UNICEF':  'junˈɪsɛf',            # you-NISS-ef
    'NATO':    'nˈeɪtoʊ',             # NAY-toe
    'NASA':    'nˈæsə',               # NA-suh

    # --- Abbreviations (g2p might not expand) ---
    'etc':     'ɛt sˈɛtəɹə',          # et cetera
    'vs':      'vˈɜːsəs',             # versus
    'aka':     'ˈɔlsoʊ nˈoʊn æz',     # also known as

    # --- Crypto/finance ---
    'DeFi':    'diː fˈAɪ',            # dee-fie
    'XRP':     'ɛks ˈɑɹ pi',          # X-R-P
}

for word, phonemes in LEXICON_OVERRIDES.items():
    pipeline.g2p.lexicon.golds[word] = phonemes

# ============================================================
# 2. TEXT PRE-PROCESSING — fix things golds can't reach
# ============================================================
def preprocess_for_g2p(text):
    """Fix dot-acronyms and other patterns before g2p."""
    # Dot-acronyms: A.I. → A I, M.C.P. → M C P
    text = re.sub(
        r'\b([A-Z])\.([A-Z](?:\.[A-Z])*)\.?\b',
        lambda m: ' '.join(m.group(0).replace('.', '')),
        text
    )
    # Symbols
    text = text.replace('%', ' percent ')
    text = text.replace('&', ' and ')
    text = text.replace('@', ' at ')
    text = text.replace('=', ' equals ')
    text = text.replace('+', ' plus ')
    text = text.replace('~', ' approximately ')
    text = text.replace('°', ' degrees ')
    # Currency (basic)
    text = re.sub(r'\$(\d+)', r'\1 dollars', text)
    text = re.sub(r'€(\d+)', r'\1 euros', text)
    text = re.sub(r'£(\d+)', r'\1 pounds', text)
    text = re.sub(r'₺(\d+)', r'\1 Turkish Lira', text)
    text = re.sub(r'₿(\d+)', r'\1 Bitcoin', text)
    # Filenames: soul.md → a markdown file called soul
    text = re.sub(r'(\w+)\.md\b', r'a markdown file called \1', text)
    text = re.sub(r'(\w+)\.py\b', r'a python file called \1', text)
    text = re.sub(r'(\w+)\.yaml\b', r'a config file called \1', text)
    text = re.sub(r'(\w+)\.json\b', r'a JSON file called \1', text)
    # URLs: just the domain part
    text = re.sub(r'https?://', '', text)
    # km/h → kilometers per hour
    text = text.replace('km/h', 'kilometers per hour')
    text = text.replace('mph', 'miles per hour')
    # e.g. → for example, i.e. → that is
    text = re.sub(r'\be\.g\.\b', 'for example', text)
    text = re.sub(r'\bi\.e\.\b', 'that is', text)
    text = re.sub(r'\bvs\.\b', 'versus', text)
    text = re.sub(r'\betc\.\b', 'et cetera', text)
    # Clean up multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ============================================================
# 3. GENERATE AUDIO
# ============================================================
def generate(text, voice, filename, label):
    """Generate audio from text using g2p + golds + pre-processing."""
    print(f"\n{'='*60}")
    print(f"{label}")
    print(f"{'='*60}")
    print(f"  Text: {text[:80]}...")

    processed = preprocess_for_g2p(text)
    if processed != text:
        print(f"  Pre-processed: {processed[:80]}...")

    # Run g2p to get phonemes (golds are already loaded)
    _, tokens = pipeline.g2p(processed)

    # Show phonemes for interesting tokens
    print(f"  Tokens ({len(tokens)}):")
    for t in tokens:
        if len(t.phonemes) > 4 and t.text.rstrip('.,') not in ('the', 'is', 'a', 'an', 'and', 'to', 'of', 'in', 'with', 'for', 'this', 'that', 'from'):
            print(f"    {t.text:20s} → {t.phonemes}")

    # Build phoneme string and chunk if needed
    parts = []
    for t in tokens:
        prespace = " " if t.whitespace else ""
        parts.append(f"{prespace}{t.phonemes}")
    phoneme_str = "".join(parts)

    # Chunk at sentence boundaries (510 char limit)
    chunks = []
    if len(phoneme_str) <= 510:
        chunks = [phoneme_str]
    else:
        sentences = phoneme_str.replace("?", "?|").replace("!", "!|").replace(".", ".|").split("|")
        current = ""
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if len(current) + len(s) + 1 > 500:
                if current:
                    chunks.append(current.strip())
                current = s
            else:
                current = (current + " " + s).strip()
        if current.strip():
            chunks.append(current.strip())

    print(f"  Phonemes: {len(phoneme_str)} chars, {len(chunks)} chunk(s)")

    all_audio = []
    for chunk in chunks:
        results = list(pipeline.generate_from_tokens(tokens=chunk, voice=voice, speed=1.0))
        for r in results:
            if r.audio is not None:
                all_audio.append(r.audio.cpu().numpy())

    if all_audio:
        audio = np.concatenate(all_audio)
        wav_path = OUTPUT_DIR / f"{filename}.wav"
        mp3_path = OUTPUT_DIR / f"{filename}.mp3"
        sf.write(str(wav_path), audio, SAMPLE_RATE)
        subprocess.run(["ffmpeg", "-y", "-i", str(wav_path), "-codec:a", "libmp3lame",
                        "-qscale:a", "2", str(mp3_path)], capture_output=True)
        wav_path.unlink()
        duration = len(audio) / SAMPLE_RATE
        print(f"  → {mp3_path.name} ({duration:.1f}s)")
    else:
        print("  → No audio generated!")


def generate_raw(text, voice, filename, label):
    """Generate audio from raw text without any processing (baseline)."""
    print(f"\n{'='*60}")
    print(f"{label}")
    print(f"{'='*60}")
    results = list(pipeline(text, voice=voice, speed=1.0))
    all_audio = [r[2].cpu().numpy() for r in results if r[2] is not None]
    if all_audio:
        audio = np.concatenate(all_audio)
        wav_path = OUTPUT_DIR / f"{filename}.wav"
        mp3_path = OUTPUT_DIR / f"{filename}.mp3"
        sf.write(str(wav_path), audio, SAMPLE_RATE)
        subprocess.run(["ffmpeg", "-y", "-i", str(wav_path), "-codec:a", "libmp3lame",
                        "-qscale:a", "2", str(mp3_path)], capture_output=True)
        wav_path.unlink()
        duration = len(audio) / SAMPLE_RATE
        print(f"  → {mp3_path.name} ({duration:.1f}s)")


# ============================================================
# TEST PARAGRAPH — covers all TTS normalization categories
# ============================================================
TEST_TEXT = (
    "Welcome to the show. "
    "AI agents are transforming API development across the LLM landscape. "
    "The HTTP protocol powers the web, while UNESCO recognized digital heritage in two thousand twenty four. "
    "Henry VIII had six wives, and Louis XIV built the palace of Versailles. "
    "Anthropic released Claude with MCP support via their A.I. safety team. "
    "The S.D.K. supports Web3 and IPv6 connectivity. "
    "For example, speeds of one hundred km/h and fifty mph on the highway. "
    "The project costs fifty million dollars with a thirty percent overhead. "
    "This is versus forty euros in the EU. "
    "The config lives in a YAML file called soul.md, not a JSON file called config.json. "
    "DeFi protocols like XRP are changing finance. "
    "That is the future of agentic payments."
)

# Generate baseline (raw text, no fixes)
generate_raw(TEST_TEXT, VOICE, "baseline_raw", "BASELINE: Raw text, no processing")

# Generate with golds + preprocessing
generate(TEST_TEXT, VOICE, "golds_preprocessed", "FIXED: Lexicon golds + text pre-processing")

print(f"\n{'='*60}")
print("Compare the two files:")
print(f"  1. {OUTPUT_DIR}/baseline_raw.mp3        (Kokoro default)")
print(f"  2. {OUTPUT_DIR}/golds_preprocessed.mp3   (golds + pre-processing)")
print(f"{'='*60}")
