#!/usr/bin/env python
"""One-off: re-render the last 10 published episodes (ep106–ep115, ep109 gone)
with the OmniVoice cloned voice, master to -16 LUFS, overwriting the published
MP3s in place. Renders ONLY episodes that already have a published .mp3 (never
creates orphans). Run from podcast-forge with its own venv.

    .venv/bin/python rerender_omnivoice.py
"""
import glob
import os
import time
from pathlib import Path

os.environ.setdefault("TTS_ENGINE", "omnivoice")  # cloning default via voice_ref/

import video_downloader as vd  # noqa: E402
from checks.master_audio import master  # noqa: E402

AUDIO = Path("/Users/lpollington/Dev/personal/freeist-podcast/audio")


def episode_scripts():
    pats = ["ep10[6-9]*.podcast*.txt", "ep11[0-5]*.podcast*.txt"]
    files = []
    for p in pats:
        files.extend(glob.glob(str(AUDIO / p)))
    return sorted(set(files))


def main():
    print(f"OmniVoice ref voice: {vd._OMNI_REF_AUDIO or '(instruct mode)'}")
    scripts = episode_scripts()
    done, failed, skipped = [], [], []
    overall = time.time()

    for txt in scripts:
        p = Path(txt)
        is_es = p.name.endswith(".podcast.es.txt")
        lang = "es" if is_es else "en"
        mp3 = p.with_name(p.name[:-4] + ".mp3")  # .txt -> .mp3
        if not mp3.exists():
            print(f"SKIP (not published): {mp3.name}")
            skipped.append(mp3.name)
            continue

        text = p.read_text().strip()
        if not text:
            print(f"SKIP (empty script): {p.name}")
            skipped.append(mp3.name)
            continue

        t = time.time()
        print(f"\n=== RENDER {mp3.name}  lang={lang}  ({len(text)} chars) ===", flush=True)
        try:
            ok = vd._generate_podcast_audio(text, str(mp3), lang=lang)
        except Exception as exc:
            print(f"FAIL {mp3.name}: {type(exc).__name__}: {exc}")
            failed.append(mp3.name)
            continue
        if not ok:
            print(f"FAIL {mp3.name}: generator returned False")
            failed.append(mp3.name)
            continue
        m = master(str(mp3))
        print(f"DONE {mp3.name} in {time.time()-t:.0f}s "
              f"LUFS={m.get('integrated_lufs')} TP={m.get('true_peak_dbfs')}", flush=True)
        done.append(mp3.name)

    mins = (time.time() - overall) / 60
    print(f"\n===== SUMMARY ({mins:.0f} min) =====")
    print(f"  rendered: {len(done)}")
    print(f"  failed:   {len(failed)} {failed}")
    print(f"  skipped:  {len(skipped)} {skipped}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
