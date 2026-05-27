#!/usr/bin/env python3
"""Publish podcast: regenerate RSS feed and push to GitHub.

Usage:
    python publish_feed.py           # regenerate RSS and push
    python publish_feed.py --dry-run # regenerate RSS, print only
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLISH_REPO = ROOT.parent / "freeist-podcast"


def main():
    dry_run = "--dry-run" in sys.argv

    print("Regenerating RSS feed...")
    rss_output = PUBLISH_REPO / "rss" / "feed.xml"
    result = subprocess.run(
        [sys.executable, str(ROOT / "generate_rss.py"),
         "--base-url", "https://mrleepee.github.io/freeist-podcast/audio/",
         "--output", str(rss_output)],
        capture_output=True, text=True,
    )
    print(result.stdout.strip())
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)

    if dry_run:
        print("\nDry run — not pushing.")
        return

    # Copy RSS to repo root
    shutil.copy2(rss_output, PUBLISH_REPO / "feed.xml")

    subprocess.run(["git", "add", "-A"], cwd=PUBLISH_REPO, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Update podcast feed"], cwd=PUBLISH_REPO, capture_output=True)
    push = subprocess.run(["git", "push"], cwd=PUBLISH_REPO, capture_output=True, text=True)
    if push.returncode != 0:
        print(f"Push failed: {push.stderr}")
        sys.exit(1)
    print("Pushed to GitHub.")


if __name__ == "__main__":
    main()
