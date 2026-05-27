#!/usr/bin/env python3
"""Generate a podcast RSS 2.0 feed from .podcast.mp3 files.

Scans the freeist-podcast/audio/ directory for files matching *.podcast.mp3,
reads episode metadata from episodes.json, and produces a valid RSS feed
with iTunes podcast namespace extensions.

Usage:
    python generate_rss.py --base-url https://username.github.io/repo/audio/

    # Custom feed metadata:
    python generate_rss.py --base-url https://example.github.io/podcast/audio/ \
        --title "My Podcast" --description "A podcast about things" --author "Me"

    # Dry run (print feed to stdout instead of writing file):
    python generate_rss.py --base-url https://example.github.io/podcast/audio/ --dry-run
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString


def get_audio_duration(mp3_path):
    """Get audio duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(mp3_path)],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except FileNotFoundError:
        pass
    return 0


def get_audio_filesize(mp3_path):
    """Get file size in bytes."""
    return Path(mp3_path).stat().st_size


def format_duration(seconds):
    """Format duration as HH:MM:SS for iTunes."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def load_episode_metadata(metadata_path):
    """Load episode titles and descriptions from JSON metadata file."""
    path = Path(metadata_path)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def find_podcast_episodes(downloads_dir, metadata=None, suffix=".podcast.mp3"):
    """Find podcast MP3 files with their metadata."""
    downloads = Path(downloads_dir)
    if not downloads.exists():
        print(f"Error: {downloads_dir} not found")
        sys.exit(1)

    metadata = metadata or {}
    episodes = []
    for mp3_path in sorted(downloads.glob(f"*{suffix}")):
        stem = mp3_path.name[: -len(suffix)]
        meta = metadata.get(stem, {})

        title = meta.get("title", re.sub(r"^ep\d+\s*", "", stem.replace("-", " ")).strip().title())
        description = meta.get("description", "")

        duration = get_audio_duration(mp3_path)
        filesize = get_audio_filesize(mp3_path)
        # Use original publish date from metadata (episodes.json) if available,
        # otherwise fall back to file mtime
        if "date" in meta and meta["date"]:
            mod_time = datetime.fromisoformat(meta["date"]).replace(tzinfo=timezone.utc)
        else:
            mod_time = datetime.fromtimestamp(mp3_path.stat().st_mtime, tz=timezone.utc)

        episodes.append({
            "title": title,
            "description": description,
            "mp3_path": mp3_path,
            "mp3_filename": mp3_path.name,
            "duration": duration,
            "duration_str": format_duration(duration),
            "filesize": filesize,
            "pub_date": mod_time,
        })

    episodes.sort(key=lambda e: e["pub_date"], reverse=True)
    return episodes


def generate_rss(episodes, base_url, feed_title, feed_description, feed_author, feed_language="en"):
    """Generate RSS 2.0 XML with iTunes podcast extensions."""
    rss = Element("rss")
    rss.set("version", "2.0")
    rss.set("xmlns:itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    rss.set("xmlns:content", "http://purl.org/rss/1.0/modules/content/")

    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text = feed_title
    SubElement(channel, "description").text = feed_description
    SubElement(channel, "language").text = feed_language
    SubElement(channel, "lastBuildDate").text = datetime.now(tz=timezone.utc).strftime(
        "%a, %d %b %Y %H:%M:%S %z"
    )

    itunes_author = SubElement(channel, "itunes:author")
    itunes_author.text = feed_author

    itunes_owner = SubElement(channel, "itunes:owner")
    SubElement(itunes_owner, "itunes:name").text = feed_author

    SubElement(channel, "itunes:explicit").text = "false"
    SubElement(channel, "itunes:category").set("text", "Technology")

    base_url = base_url.rstrip("/")

    for ep in episodes:
        item = SubElement(channel, "item")

        SubElement(item, "title").text = ep["title"]
        SubElement(item, "description").text = ep["description"]
        SubElement(item, "pubDate").text = ep["pub_date"].strftime(
            "%a, %d %b %Y %H:%M:%S %z"
        )
        SubElement(item, "itunes:duration").text = ep["duration_str"]
        SubElement(item, "itunes:summary").text = ep["description"]

        enclosure = SubElement(item, "enclosure")
        enclosure.set("url", f"{base_url}/{ep['mp3_filename']}")
        enclosure.set("length", str(ep["filesize"]))
        enclosure.set("type", "audio/mpeg")

        SubElement(item, "guid").text = f"{base_url}/{ep['mp3_filename']}"

    return rss


def main():
    parser = argparse.ArgumentParser(description="Generate podcast RSS feed from MP3 files")
    parser.add_argument("--base-url", required=True,
                        help="Base URL where MP3s will be hosted (e.g. https://user.github.io/repo/audio/)")
    parser.add_argument("--downloads", default=str(Path(__file__).resolve().parent.parent / "freeist-podcast" / "audio"),
                        help="Path to podcast audio directory")
    parser.add_argument("--output", default="rss/feed.xml",
                        help="Output path for RSS XML (default: rss/feed.xml)")
    parser.add_argument("--title", default="Señor Freedom",
                        help="Podcast feed title (default: Señor Freedom)")
    parser.add_argument("--description", default="Short-form podcast covering technology, finance, and global affairs.",
                        help="Podcast feed description")
    parser.add_argument("--author", default="Señor Freedom",
                        help="Podcast author (default: Señor Freedom)")
    parser.add_argument("--language", default="en",
                        help="Feed language code (default: en)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print RSS to stdout instead of writing file")
    parser.add_argument("--metadata", default=str(Path(__file__).resolve().parent.parent / "freeist-podcast" / "episodes.json"),
                        help="Episode metadata JSON file")
    parser.add_argument("--suffix", default=".podcast.mp3",
                        help="File suffix to scan for (default: .podcast.mp3)")
    args = parser.parse_args()

    metadata = load_episode_metadata(args.metadata)
    episodes = find_podcast_episodes(args.downloads, metadata=metadata, suffix=args.suffix)
    if not episodes:
        print(f"No .podcast.mp3 files found in {args.downloads}/")
        sys.exit(1)

    print(f"Found {len(episodes)} episodes:")
    for ep in episodes:
        print(f"  [{ep['duration_str']}] {ep['title'][:60]}... ({ep['filesize']/1024/1024:.1f}MB)")

    rss = generate_rss(episodes, args.base_url, args.title, args.description,
                       args.author, args.language)

    xml_string = tostring(rss, encoding="unicode", xml_declaration=False)
    pretty_xml = parseString(xml_string).toprettyxml(indent="  ", encoding=None)

    if args.dry_run:
        print("\n" + pretty_xml)
    else:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(pretty_xml, encoding="utf-8")
        print(f"\nRSS feed written to: {output_path}")


if __name__ == "__main__":
    main()
