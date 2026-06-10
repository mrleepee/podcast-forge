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
import os
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


def find_podcast_episodes(downloads_dir, metadata=None, suffix=".podcast.mp3", exclude=None):
    """Find podcast MP3 files with their metadata.

    ``exclude`` is an optional set/list of episode stems (slugs) to omit — used
    by the publish gate to keep failing episodes out of the feed.
    """
    downloads = Path(downloads_dir)
    if not downloads.exists():
        print(f"Error: {downloads_dir} not found")
        sys.exit(1)

    exclude = set(exclude or [])
    metadata = metadata or {}
    episodes = []
    for mp3_path in sorted(downloads.glob(f"*{suffix}")):
        stem = mp3_path.name[: -len(suffix)]
        if stem in exclude:
            print(f"  Excluded by publish gate: {stem}")
            continue
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

        transcript = downloads / f"{stem}.podcast.txt"
        episodes.append({
            "title": title,
            "description": description,
            "stem": stem,
            "mp3_path": mp3_path,
            "mp3_filename": mp3_path.name,
            "duration": duration,
            "duration_str": format_duration(duration),
            "filesize": filesize,
            "pub_date": mod_time,
            "transcript_filename": transcript.name if transcript.exists() else None,
        })

    episodes.sort(key=lambda e: e["pub_date"], reverse=True)
    return episodes


def stable_show_guid(feed_title):
    """Deterministic show GUID from the title — stable across rebuilds (P3/R2)."""
    import uuid
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"freeist-podcast:{feed_title}"))


def generate_rss(episodes, base_url, feed_title, feed_description, feed_author,
                 feed_language="en", *, site_url="", owner_email="", image_url="",
                 show_guid=""):
    """Generate RSS 2.0 XML with iTunes + Podcast-namespace extensions (P3)."""
    rss = Element("rss")
    rss.set("version", "2.0")
    rss.set("xmlns:itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    rss.set("xmlns:content", "http://purl.org/rss/1.0/modules/content/")
    rss.set("xmlns:podcast", "https://podcastindex.org/namespace/1.0")

    channel = SubElement(rss, "channel")
    base_url = base_url.rstrip("/")
    site_url = (site_url or "").rstrip("/")

    SubElement(channel, "title").text = feed_title
    SubElement(channel, "description").text = feed_description
    SubElement(channel, "language").text = feed_language
    if site_url:
        SubElement(channel, "link").text = site_url + "/"
    SubElement(channel, "lastBuildDate").text = datetime.now(tz=timezone.utc).strftime(
        "%a, %d %b %Y %H:%M:%S %z"
    )

    # Stable identity + always-on treatment (R2).
    SubElement(channel, "itunes:type").text = "episodic"
    SubElement(channel, "podcast:guid").text = show_guid or stable_show_guid(feed_title)

    SubElement(channel, "itunes:author").text = feed_author

    itunes_owner = SubElement(channel, "itunes:owner")
    SubElement(itunes_owner, "itunes:name").text = feed_author
    # Owner email is configurable and never hardcoded — emitted only when set.
    if owner_email:
        SubElement(itunes_owner, "itunes:email").text = owner_email

    # Show cover art for non-Spotify directories (R1). Emitted only when the asset
    # is available so the feed never references a 404 image.
    if image_url:
        SubElement(channel, "itunes:image").set("href", image_url)
        image = SubElement(channel, "image")
        SubElement(image, "url").text = image_url
        SubElement(image, "title").text = feed_title
        SubElement(image, "link").text = site_url + "/" if site_url else image_url

    SubElement(channel, "itunes:explicit").text = "false"
    SubElement(channel, "itunes:category").set("text", "Technology")

    for ep in episodes:
        item = SubElement(channel, "item")
        stem = ep.get("stem", "")

        SubElement(item, "title").text = ep["title"]
        SubElement(item, "description").text = ep["description"]
        SubElement(item, "pubDate").text = ep["pub_date"].strftime(
            "%a, %d %b %Y %H:%M:%S %z"
        )
        SubElement(item, "itunes:duration").text = ep["duration_str"]
        SubElement(item, "itunes:summary").text = ep["description"]

        m = re.match(r"ep0*(\d+)", stem)
        if m:
            SubElement(item, "itunes:episode").text = m.group(1)
        SubElement(item, "itunes:episodeType").text = "full"
        SubElement(item, "itunes:explicit").text = "false"
        if image_url:
            SubElement(item, "itunes:image").set("href", image_url)

        enclosure = SubElement(item, "enclosure")
        enclosure.set("url", f"{base_url}/{ep['mp3_filename']}")
        enclosure.set("length", str(ep["filesize"]))
        enclosure.set("type", "audio/mpeg")

        # Stable GUID independent of the hosting URL (R3). Changing --base-url no
        # longer re-creates the whole catalog as duplicates. This identity is
        # PERMANENT — do not change the "freeist:" prefix or slug derivation.
        guid = SubElement(item, "guid")
        guid.text = f"freeist:{stem}" if stem else f"{base_url}/{ep['mp3_filename']}"
        guid.set("isPermaLink", "false")

        # Link the already-published transcript when it exists (R6).
        if ep.get("transcript_filename"):
            tr = SubElement(item, "podcast:transcript")
            tr.set("url", f"{base_url}/{ep['transcript_filename']}")
            tr.set("type", "text/plain")

    return rss


def main():
    parser = argparse.ArgumentParser(description="Generate podcast RSS feed from MP3 files")
    parser.add_argument("--base-url", required=True,
                        help="Base URL where MP3s will be hosted (e.g. https://user.github.io/repo/audio/)")
    parser.add_argument("--downloads", default=str(Path(__file__).resolve().parent.parent / "freeist-podcast" / "audio"),
                        help="Path to podcast audio directory")
    parser.add_argument("--output", default="rss/feed.xml",
                        help="Output path for RSS XML (default: rss/feed.xml)")
    parser.add_argument("--title", default="Señora Freedom",
                        help="Podcast feed title (default: Señora Freedom)")
    parser.add_argument("--description", default="Short-form podcast covering technology, finance, and global affairs.",
                        help="Podcast feed description")
    parser.add_argument("--author", default="Señora Freedom",
                        help="Podcast author (default: Señora Freedom)")
    parser.add_argument("--language", default="en",
                        help="Feed language code (default: en)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print RSS to stdout instead of writing file")
    parser.add_argument("--metadata", default=str(Path(__file__).resolve().parent.parent / "freeist-podcast" / "episodes.json"),
                        help="Episode metadata JSON file")
    parser.add_argument("--suffix", default=".podcast.mp3",
                        help="File suffix to scan for (default: .podcast.mp3)")
    parser.add_argument("--exclude", nargs="*", default=[],
                        help="Episode slugs to exclude from the feed (publish gate)")
    parser.add_argument("--site-url", default="https://mrleepee.github.io/freeist-podcast/",
                        help="GitHub Pages site root for the channel <link>")
    parser.add_argument("--owner-email", default=os.environ.get("PODCAST_OWNER_EMAIL", ""),
                        help="itunes:owner email (or PODCAST_OWNER_EMAIL); never hardcoded")
    parser.add_argument("--image-url", default="",
                        help="Show cover art URL; auto-detected from cover.png if present")
    parser.add_argument("--podcast-guid", default=os.environ.get("PODCAST_SHOW_GUID", ""),
                        help="Stable show GUID (default: derived from the title)")
    args = parser.parse_args()

    metadata = load_episode_metadata(args.metadata)
    episodes = find_podcast_episodes(args.downloads, metadata=metadata,
                                     suffix=args.suffix, exclude=args.exclude)
    if not episodes:
        print(f"No .podcast.mp3 files found in {args.downloads}/")
        sys.exit(1)

    # Resolve cover art: explicit --image-url wins; else use cover.png in the
    # publish repo root only if it actually exists (don't ship a 404 image).
    image_url = args.image_url
    if not image_url:
        cover = Path(args.downloads).parent / "cover.png"
        if cover.exists():
            image_url = f"{args.site_url.rstrip('/')}/cover.png"
        else:
            print(f"  No cover.png in {cover.parent} — itunes:image omitted "
                  "(host cover.png to enable show art).")

    print(f"Found {len(episodes)} episodes:")
    for ep in episodes:
        print(f"  [{ep['duration_str']}] {ep['title'][:60]}... ({ep['filesize']/1024/1024:.1f}MB)")

    rss = generate_rss(episodes, args.base_url, args.title, args.description,
                       args.author, args.language, site_url=args.site_url,
                       owner_email=args.owner_email, image_url=image_url,
                       show_guid=args.podcast_guid)

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
