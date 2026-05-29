import argparse
import yt_dlp
import subprocess
import os
import sys
import json
import re
import shutil
import urllib.parse
from pathlib import Path
from yt_dlp.cookies import CookieLoadError, SUPPORTED_BROWSERS, SUPPORTED_KEYRINGS
from yt_dlp.utils import DownloadError


# ---------------------------------------------------------------------------
# .env loader
# ---------------------------------------------------------------------------

def load_dotenv(path=None):
    env_path = Path(path) if path else Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Download videos from supported sites such as YouTube, Instagram, "
            "Vimeo, and X using yt-dlp."
        )
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="Video URL to download."
    )
    parser.add_argument(
        "-list",
        "--list",
        dest="list_file",
        help="Path to a file containing one video URL per line."
    )
    parser.add_argument(
        "-t",
        "--title",
        metavar="TITLE",
        help=(
            "Override the saved filename for a single download. "
            "Example: -t \"My Clip\" saves as My Clip.<ext>."
        ),
    )
    parser.add_argument(
        "--subs",
        action="store_true",
        help="Download subtitles when available (falls back to automatic captions)."
    )
    parser.add_argument(
        "--subs-lang",
        metavar="LANG",
        nargs="+",
        help="Preferred subtitle language codes (space or comma separated)."
    )
    parser.add_argument(
        "--subs-format",
        metavar="FORMAT",
        help="Subtitle format to download (e.g. vtt, srt)."
    )
    parser.add_argument(
        "--subs-manual-only",
        action="store_true",
        help="Only download manually uploaded subtitles (skip automatic captions)."
    )
    parser.add_argument(
        "--cookies",
        metavar="PATH",
        help="Path to a cookies.txt file (useful for sites like Instagram or x.com)."
    )
    parser.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        help=(
            "Read cookies from a browser (e.g. chrome, firefox, safari, edge). "
            "Supports optional profile syntax like chrome:Profile 1. "
            "Use 'auto' to pick a likely local browser automatically. Default: auto."
        ),
    )
    parser.add_argument(
        "--no-cookies-from-browser",
        action="store_const",
        const="none",
        dest="cookies_from_browser",
        help="Disable automatic browser cookie detection for this run."
    )
    parser.add_argument(
        "--user-agent",
        metavar="UA",
        help="Custom User-Agent header to use for downloads."
    )
    parser.add_argument(
        "--js-runtime",
        metavar="RUNTIME",
        nargs="+",
        help=(
            "Preferred JavaScript runtimes for yt-dlp YouTube extraction. "
            "Examples: node, bun, deno, quickjs, or node:/custom/path. "
            "Accepts space- or comma-separated values."
        ),
    )
    parser.add_argument(
        "--remote-component",
        metavar="COMPONENT",
        nargs="+",
        help=(
            "Remote yt-dlp components to allow when required. "
            "Example: ejs:github. Accepts space- or comma-separated values."
        ),
    )
    parser.add_argument(
        "--yt-client",
        default="android,default",
        help=(
            "Comma-separated list of YouTube clients to try (e.g. android,default). "
            "Use 'default' to include yt-dlp's standard web client."
        ),
    )
    parser.add_argument(
        "--summarize",
        action="store_true",
        help="Download English subtitles (or transcribe via whisper), then summarize with MiniMax.",
    )
    parser.add_argument(
        "--podcast",
        action="store_true",
        help="Full podcast pipeline: summarize, convert to podcast narration, generate MP3 with Kokoro TTS.",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="After --podcast, regenerate RSS feed and push to GitHub.",
    )
    parser.add_argument(
        "--prompt",
        metavar="TEXT",
        help="Extra instructions to customize this episode's narration (used with --podcast).",
    )
    parser.add_argument(
        "--duo",
        action="store_true",
        help="Two-speaker conversational podcast with distinct voices (used with --podcast).",
    )
    parser.add_argument(
        "--vimeo-hash",
        metavar="HASH",
        help=(
            "Unlisted Vimeo hash to pair with bare Vimeo/player URLs "
            "(e.g. e214c8ebed)."
        ),
    )

    args = parser.parse_args()

    if args.url and args.list_file:
        parser.error("Please provide either a single URL or use -list/--list, not both.")
    if not args.url and not args.list_file:
        parser.error("Please provide a video URL or specify -list/--list with a file of URLs.")
    if args.list_file and args.title:
        parser.error("Custom titles with -t/--title are only supported for single URL downloads.")

    if args.title is not None:
        args.title = normalize_custom_title(args.title)
        if not args.title:
            parser.error("Please provide a title with at least one valid filename character.")

    args.cookies_from_browser_defaulted = args.cookies_from_browser is None
    cookies_from_browser_value = (
        "auto" if args.cookies_from_browser_defaulted else args.cookies_from_browser
    )

    try:
        args.browser_cookie_sources = expand_browser_cookie_sources(cookies_from_browser_value)
    except ValueError as err:
        parser.error(str(err))
    args.prefer_browser_cookies = (
        not args.cookies_from_browser_defaulted and bool(args.browser_cookie_sources)
    )
    args.js_runtimes = parse_js_runtime_preferences(args.js_runtime)
    args.remote_components = parse_delimited_values(args.remote_component) or None

    return args


_CLIENT_NOT_SET = object()
_ATTEMPT_NOT_SET = object()
_DEFAULT_BROWSER_COOKIE_ORDER = (
    "brave",
    "chrome",
    "chromium",
    "edge",
    "firefox",
    "safari",
)
_AUTO_JS_RUNTIME_CANDIDATES = (
    ("node", "node"),
    ("bun", "bun"),
    ("quickjs", "qjs"),
    ("deno", "deno"),
)
_LIKELY_BROWSER_PROFILE_PATHS = {
    "brave": [
        "~/Library/Application Support/BraveSoftware/Brave-Browser",
    ],
    "chrome": [
        "~/Library/Application Support/Google/Chrome",
    ],
    "chromium": [
        "~/Library/Application Support/Chromium",
    ],
    "edge": [
        "~/Library/Application Support/Microsoft Edge",
    ],
    "firefox": [
        "~/Library/Application Support/Firefox",
        "~/Library/Application Support/Mozilla/Firefox",
    ],
    "opera": [
        "~/Library/Application Support/com.operasoftware.Opera",
    ],
    "safari": [
        "~/Library/Containers/com.apple.Safari",
        "~/Library/Safari",
    ],
    "vivaldi": [
        "~/Library/Application Support/Vivaldi",
    ],
}


def parse_delimited_values(values):
    parsed = []
    for value in values or []:
        parsed.extend(item.strip() for item in value.split(",") if item.strip())
    return parsed


def browser_has_likely_profile(browser_name):
    probe_paths = _LIKELY_BROWSER_PROFILE_PATHS.get(browser_name.lower())
    if not probe_paths:
        return False
    return any(os.path.exists(os.path.expanduser(path)) for path in probe_paths)


def parse_browser_cookie_spec(value):
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError("Please provide a browser name for --cookies-from-browser.")

    mobj = re.fullmatch(
        r"""(?x)
            (?P<name>[^+:]+)
            (?:\s*\+\s*(?P<keyring>[^:]+))?
            (?:\s*:\s*(?!:)(?P<profile>.+?))?
            (?:\s*::\s*(?P<container>.+))?
        """,
        normalized,
    )
    if mobj is None:
        raise ValueError(f"Invalid --cookies-from-browser value: {normalized}")

    browser_name, keyring, profile, container = mobj.group("name", "keyring", "profile", "container")
    browser_name = browser_name.lower()
    if browser_name not in SUPPORTED_BROWSERS:
        raise ValueError(
            f"Unsupported browser for --cookies-from-browser: {browser_name}. "
            f"Supported browsers: {', '.join(sorted(SUPPORTED_BROWSERS))}"
        )
    if keyring is not None:
        keyring = keyring.upper()
        if keyring not in SUPPORTED_KEYRINGS:
            raise ValueError(
                f"Unsupported keyring for --cookies-from-browser: {keyring.lower()}. "
                f"Supported keyrings: {', '.join(map(str.lower, sorted(SUPPORTED_KEYRINGS)))}"
            )

    return {
        "label": normalized,
        "spec": (browser_name, profile, keyring, container),
    }


def expand_browser_cookie_sources(value):
    normalized = (value or "").strip()
    if not normalized:
        return []
    if normalized.lower() in {"none", "off", "false"}:
        return []
    if normalized.lower() != "auto":
        return [parse_browser_cookie_spec(normalized)]

    ordered_browsers = [
        browser for browser in _DEFAULT_BROWSER_COOKIE_ORDER if browser in SUPPORTED_BROWSERS
    ]
    ordered_browsers.extend(
        browser for browser in sorted(SUPPORTED_BROWSERS) if browser not in ordered_browsers
    )
    detected_browsers = [
        browser for browser in ordered_browsers if browser_has_likely_profile(browser)
    ]
    auto_browsers = detected_browsers[:1] or ordered_browsers[:1]
    return [
        {
            "label": browser,
            "spec": (browser, None, None, None),
        }
        for browser in auto_browsers
    ]


def parse_js_runtime_preferences(values):
    runtimes = {}
    for value in parse_delimited_values(values):
        runtime_name, path = [*value.split(":", 1), None][:2]
        runtime_name = runtime_name.strip().lower()
        if not runtime_name:
            continue
        runtime_path = path.strip() if path else None
        if not runtime_path:
            executable = "qjs" if runtime_name == "quickjs" else runtime_name
            runtime_path = shutil.which(executable)
        runtimes[runtime_name] = {"path": runtime_path} if runtime_path else {}
    return runtimes or None


def detect_js_runtimes():
    runtimes = {}
    for runtime_name, executable in _AUTO_JS_RUNTIME_CANDIDATES:
        if runtime_path := shutil.which(executable):
            runtimes[runtime_name] = {"path": runtime_path}
    return runtimes or None


def normalize_youtube_clients(clients):
    if not clients:
        return [None]
    ordered = []
    for client in clients:
        if client not in ordered:
            ordered.append(client)
    return ordered


def is_youtube_url(url):
    host = urllib.parse.urlparse(url).netloc.lower().split(":", 1)[0]
    return (
        host == "youtu.be"
        or host.endswith("youtube.com")
        or host.endswith("youtube-nocookie.com")
    )


def get_active_youtube_clients(url_attempts, youtube_clients):
    if any(is_youtube_url((attempt or {}).get("url", "")) for attempt in url_attempts):
        return normalize_youtube_clients(youtube_clients)
    return [None]


def _attempt_key(attempt):
    headers = tuple(sorted((attempt.get("http_headers") or {}).items()))
    return attempt.get("url"), headers


def _append_attempt(attempts, attempt, seen):
    key = _attempt_key(attempt)
    if key not in seen:
        seen.add(key)
        attempts.append(attempt)


def build_url_attempts(url, vimeo_hash=None):
    attempts = []
    seen = set()
    base_attempt = {"url": url, "http_headers": {}}
    _append_attempt(attempts, base_attempt, seen)

    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    is_vimeo_player = host in {"player.vimeo.com", "www.player.vimeo.com"}
    match = re.match(r"^/video/(?P<id>\d+)/?$", parsed.path)

    if is_vimeo_player and match:
        video_id = match.group("id")
        query = urllib.parse.parse_qs(parsed.query)
        unlisted_hash = (query.get("h") or query.get("unlisted_hash") or [None])[0]
        if not unlisted_hash and vimeo_hash:
            unlisted_hash = vimeo_hash
        referer_headers = {"Referer": url}

        if unlisted_hash:
            player_url_with_hash = f"https://player.vimeo.com/video/{video_id}?h={unlisted_hash}"
            canonical_url = f"https://vimeo.com/{video_id}/{unlisted_hash}"
        else:
            player_url_with_hash = None
            canonical_url = f"https://vimeo.com/{video_id}"

        if player_url_with_hash:
            _append_attempt(
                attempts,
                {"url": player_url_with_hash, "http_headers": referer_headers},
                seen,
            )
        _append_attempt(
            attempts,
            {"url": canonical_url, "http_headers": referer_headers},
            seen,
        )
        _append_attempt(
            attempts,
            {"url": url, "http_headers": referer_headers},
            seen,
        )

    is_vimeo_page = host in {"vimeo.com", "www.vimeo.com"}
    page_match = re.match(
        r"^/(?P<id>\d+)(?:/(?P<unlisted_hash>[\da-fA-F]{10}))?/?$",
        parsed.path,
    )
    if is_vimeo_page and page_match:
        video_id = page_match.group("id")
        unlisted_hash = page_match.group("unlisted_hash") or vimeo_hash
        if unlisted_hash:
            player_url = f"https://player.vimeo.com/video/{video_id}?h={unlisted_hash}"
            _append_attempt(
                attempts,
                {"url": player_url, "http_headers": {"Referer": url}},
                seen,
            )

    return attempts


def parse_youtube_client_preference(value):
    if not value:
        return [None]
    clients = []
    for entry in value.split(","):
        normalized = entry.strip().lower()
        if not normalized:
            continue
        if normalized in {"default", "auto", "none"}:
            clients.append(None)
        else:
            clients.append(normalized)
    return normalize_youtube_clients(clients or [None])


def format_client_label(client):
    return client if client else "default"


def format_attempt_label(attempt):
    attempt = attempt or {}
    url = attempt.get("url", "unknown-url")
    headers = attempt.get("http_headers") or {}
    referer = headers.get("Referer")
    if referer:
        return f"{url} (Referer: {referer})"
    return url


def format_cookie_source_label(cookie_source):
    if not cookie_source or not cookie_source.get("spec"):
        return "none"
    return cookie_source["label"]


def prioritize_cookie_sources(browser_cookie_sources, prefer_browser_cookies=False):
    cookie_sources = list(browser_cookie_sources or [])
    anonymous_source = [{"label": "none", "spec": None}]
    if prefer_browser_cookies:
        return cookie_sources + anonymous_source
    return anonymous_source + cookie_sources


def prioritize_client(clients, preferred_client=_CLIENT_NOT_SET):
    ordered = []

    def add_client(client):
        if client not in ordered:
            ordered.append(client)

    if preferred_client is not _CLIENT_NOT_SET:
        add_client(preferred_client)

    for client in normalize_youtube_clients(clients):
        add_client(client)

    return ordered or [None]


def prioritize_attempt(attempts, preferred_attempt=_ATTEMPT_NOT_SET):
    ordered = []

    def add_attempt(attempt):
        if attempt is None:
            return
        key = _attempt_key(attempt)
        if not any(_attempt_key(existing) == key for existing in ordered):
            ordered.append(attempt)

    if preferred_attempt is not _ATTEMPT_NOT_SET:
        add_attempt(preferred_attempt)

    for attempt in attempts:
        add_attempt(attempt)

    return ordered


def build_common_ydl_opts(
    *,
    attempt=None,
    client=None,
    cookies_file=None,
    cookie_source=None,
    user_agent=None,
    js_runtimes=None,
    remote_components=None,
    quiet=False,
):
    ydl_opts = {}
    if quiet:
        ydl_opts["quiet"] = True

    attempt_headers = (attempt or {}).get("http_headers") or {}
    if attempt_headers:
        ydl_opts["http_headers"] = dict(attempt_headers)

    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file

    if cookie_source and cookie_source.get("spec"):
        ydl_opts["cookiesfrombrowser"] = cookie_source["spec"]

    if user_agent:
        ydl_opts["user_agent"] = user_agent

    if client:
        ydl_opts["extractor_args"] = {"youtube": {"player_client": [client]}}

    if js_runtimes:
        ydl_opts["js_runtimes"] = js_runtimes

    if remote_components:
        ydl_opts["remote_components"] = remote_components

    return ydl_opts


def get_video_info(
    url_attempts,
    youtube_clients=None,
    cookies_file=None,
    browser_cookie_sources=None,
    prefer_browser_cookies=False,
    user_agent=None,
    js_runtimes=None,
    remote_components=None,
):
    clients = get_active_youtube_clients(url_attempts, youtube_clients)
    cookie_sources = prioritize_cookie_sources(
        browser_cookie_sources,
        prefer_browser_cookies=prefer_browser_cookies,
    )
    last_error = None
    for attempt in url_attempts:
        for client in clients:
            for cookie_source in cookie_sources:
                ydl_opts = build_common_ydl_opts(
                    attempt=attempt,
                    client=client,
                    cookies_file=cookies_file,
                    cookie_source=cookie_source,
                    user_agent=user_agent,
                    js_runtimes=js_runtimes,
                    remote_components=remote_components,
                    quiet=True,
                )
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(attempt["url"], download=False)
                        return info, client, attempt
                except DownloadError as err:
                    if "No video formats found" in str(err):
                        retry_opts = dict(ydl_opts)
                        retry_opts["ignoreerrors"] = "only_download"
                        try:
                            with yt_dlp.YoutubeDL(retry_opts) as ydl:
                                info = ydl.extract_info(attempt["url"], download=False)
                            if info:
                                return info, client, attempt
                        except (CookieLoadError, DownloadError) as retry_err:
                            last_error = retry_err
                            continue
                    last_error = err
                    continue
                except CookieLoadError as err:
                    last_error = err
                    continue
    raise last_error or DownloadError("Unable to retrieve video info.")


def get_vimeo_hash_hint(url, vimeo_hash=None):
    if vimeo_hash:
        return None

    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()

    if host in {"player.vimeo.com", "www.player.vimeo.com"}:
        match = re.match(r"^/video/(?P<id>\d+)/?$", parsed.path)
        query = urllib.parse.parse_qs(parsed.query)
        has_hash = bool((query.get("h") or query.get("unlisted_hash") or [None])[0])
        if match and not has_hash:
            video_id = match.group("id")
            return (
                "Tip: this may be an unlisted Vimeo video. Retry with "
                f"https://vimeo.com/{video_id}/<hash> or use --vimeo-hash <hash>."
            )

    if host in {"vimeo.com", "www.vimeo.com"}:
        match = re.match(r"^/(?P<id>\d+)/?$", parsed.path)
        if match:
            video_id = match.group("id")
            return (
                "Tip: this may be an unlisted Vimeo video. Retry with "
                f"https://vimeo.com/{video_id}/<hash> or use --vimeo-hash <hash>."
            )

    return None


def list_formats(info):
    formats = get_available_formats(info)
    if not formats:
        print("No explicit formats were reported for this item.")
        return

    print("Available formats:")
    for format in formats:
        filesize = format.get('filesize')
        if filesize is not None:
            filesize_mb = filesize / (1024 * 1024)  # Convert bytes to MB
            print(
                f"Format ID: {format['format_id']}, Resolution: {format.get('resolution', 'N/A')}, "
                f"Extension: {format['ext']}, Filesize: {filesize_mb:.2f} MB"
            )


def get_available_formats(info):
    formats = info.get("formats")
    if not isinstance(formats, list):
        return []
    return [format_item for format_item in formats if isinstance(format_item, dict)]


def get_best_format(info):
    formats_with_video_and_audio = [
        f
        for f in get_available_formats(info)
        if f.get("vcodec") != "none" and f.get("acodec") != "none"
    ]
    if len(formats_with_video_and_audio) == 1:
        return formats_with_video_and_audio[0]["format_id"]
    return None


def is_playlist_result(info):
    if not isinstance(info, dict):
        return False
    return info.get("_type") in {"playlist", "multi_video"} or isinstance(info.get("entries"), list)


def iter_downloaded_media_info(info):
    if not isinstance(info, dict):
        return

    entries = info.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            yield from iter_downloaded_media_info(entry)
        return

    yield info


def collect_downloaded_video_paths(info):
    filepaths = []
    for media_info in iter_downloaded_media_info(info):
        filepath = media_info.get("filepath")
        if filepath:
            filepaths.append(filepath)

        for requested_download in media_info.get("requested_downloads") or []:
            requested_path = requested_download.get("filepath")
            if requested_path:
                filepaths.append(requested_path)

        filename = media_info.get("_filename")
        if filename and os.path.exists(filename):
            filepaths.append(filename)

    return list(dict.fromkeys(filepaths))


def collect_subtitle_paths(info):
    subtitle_paths = []
    for media_info in iter_downloaded_media_info(info):
        requested_subtitles = media_info.get("requested_subtitles") or {}
        for subtitle_info in requested_subtitles.values():
            subtitle_path = subtitle_info.get("filepath")
            if subtitle_path:
                subtitle_paths.append(subtitle_path)
    return list(dict.fromkeys(subtitle_paths))


def sanitize_filename(filename, max_length=200):
    # Remove invalid filename characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '')
    
    # Truncate the filename if it's too long
    name, ext = os.path.splitext(filename)
    if len(name) > max_length:
        name = name[:max_length]
    
    return name + ext


KNOWN_MEDIA_EXTENSIONS = {
    ".mp4",
    ".m4v",
    ".mkv",
    ".mov",
    ".webm",
    ".avi",
    ".flv",
    ".wmv",
    ".mp3",
    ".m4a",
    ".aac",
    ".wav",
    ".ogg",
    ".opus",
}


def normalize_custom_title(title, max_length=200):
    normalized_title = title.strip()
    _, ext = os.path.splitext(normalized_title)
    if ext.lower() in KNOWN_MEDIA_EXTENSIONS:
        normalized_title = os.path.splitext(normalized_title)[0]
    normalized_title = sanitize_filename(normalized_title, max_length=max_length)
    normalized_title = re.sub(r"\s+", " ", normalized_title)
    return normalized_title.rstrip(". ").strip()


def build_output_template(custom_title=None):
    if custom_title:
        safe_custom_title = custom_title.replace("%", "%%")
        return {
            "default": f"{safe_custom_title}.%(ext)s",
            "subtitle": f"{safe_custom_title}.%(lang)s.%(ext)s",
        }
    return {
        "default": "%(title).200s.%(ext)s",
        "subtitle": "%(title).200s.%(lang)s.%(ext)s",
    }


def sanitize_downloaded_path(path):
    absolute_path = path if os.path.isabs(path) else os.path.join(os.getcwd(), path)
    base_name = os.path.basename(absolute_path)
    sanitized_name = sanitize_filename(base_name)
    sanitized_path = os.path.join(os.path.dirname(absolute_path), sanitized_name)

    if sanitized_path != absolute_path and os.path.exists(absolute_path):
        os.rename(absolute_path, sanitized_path)
        return sanitized_path
    return absolute_path


def get_actionable_error_hint(url, error, browser_cookie_sources=None):
    error_message = str(error)
    normalized_error = error_message.lower()

    if "failed to resolve 'www.youtube.com'" in normalized_error or "nodename nor servname provided" in normalized_error:
        return "Tip: this looks like a DNS/network resolution failure while contacting YouTube."

    if not is_youtube_url(url):
        return None

    is_bot_check = (
        "sign in to confirm you're not a bot" in normalized_error
        or "sign in to confirm you’re not a bot" in normalized_error
    )
    if not is_bot_check:
        return None

    if browser_cookie_sources:
        tried_sources = ", ".join(source["label"] for source in browser_cookie_sources)
        return (
            "Tip: YouTube is still blocking this video after trying browser cookies from: "
            f"{tried_sources}. Retry with a different browser/profile, "
            "or export cookies.txt and pass --cookies <path>."
        )

    return (
        "Tip: YouTube is blocking anonymous access for this video. "
        "Retry with --cookies-from-browser auto, "
        "or specify a browser/profile such as --cookies-from-browser chrome."
    )


def describe_retry_context(attempt, client, cookie_source, *, show_attempt=False, show_client=False, show_cookies=False):
    context_parts = []
    if show_attempt:
        context_parts.append(f"attempt '{format_attempt_label(attempt)}'")
    if show_client:
        context_parts.append(f"client '{format_client_label(client)}'")
    if show_cookies and cookie_source and cookie_source.get("spec"):
        context_parts.append(f"cookies '{format_cookie_source_label(cookie_source)}'")
    return ", ".join(context_parts)


def download_video(
    url,
    format_id=None,
    subtitle_config=None,
    youtube_clients=None,
    cookies_file=None,
    browser_cookie_sources=None,
    prefer_browser_cookies=False,
    user_agent=None,
    vimeo_hash=None,
    custom_title=None,
    js_runtimes=None,
    remote_components=None,
):
    url_attempts = build_url_attempts(url, vimeo_hash=vimeo_hash)
    active_youtube_clients = get_active_youtube_clients(url_attempts, youtube_clients)
    cookie_sources = prioritize_cookie_sources(
        browser_cookie_sources,
        prefer_browser_cookies=prefer_browser_cookies,
    )
    effective_js_runtimes = js_runtimes
    effective_remote_components = remote_components

    if is_youtube_url(url):
        effective_js_runtimes = effective_js_runtimes or detect_js_runtimes()
        if effective_js_runtimes and effective_remote_components is None:
            effective_remote_components = ["ejs:github"]

    info_client = _CLIENT_NOT_SET
    info_attempt = _ATTEMPT_NOT_SET
    info = None
    info_is_playlist = False
    if format_id is None:
        try:
            info, info_client, info_attempt = get_video_info(
                url_attempts,
                active_youtube_clients,
                cookies_file=cookies_file,
                browser_cookie_sources=browser_cookie_sources,
                prefer_browser_cookies=prefer_browser_cookies,
                user_agent=user_agent,
                js_runtimes=effective_js_runtimes,
                remote_components=effective_remote_components,
            )
            info_is_playlist = is_playlist_result(info)
            format_id = get_best_format(info)
        except (CookieLoadError, DownloadError) as e:
            print(f"An error occurred while retrieving video info: {str(e)}")
            if hint := get_actionable_error_hint(
                url,
                e,
                browser_cookie_sources=browser_cookie_sources,
            ):
                print(hint)
            if hint := get_vimeo_hash_hint(url, vimeo_hash):
                print(hint)
            return {"video": None, "subtitles": []}

    subtitle_config = subtitle_config or {}

    # Create directories
    raw_dir = "downloads/raw"
    podcast_dir = "downloads/podcast"
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(podcast_dir, exist_ok=True)

    # Change to raw directory for download (videos go here)
    original_cwd = os.getcwd()
    os.chdir(raw_dir)

    base_ydl_opts = {
        "outtmpl": build_output_template(custom_title=custom_title),
    }
    if cookies_file:
        base_ydl_opts["cookiefile"] = cookies_file
    if user_agent:
        base_ydl_opts["user_agent"] = user_agent
    if format_id:
        base_ydl_opts["format"] = format_id
    if effective_js_runtimes:
        base_ydl_opts["js_runtimes"] = effective_js_runtimes
    if effective_remote_components:
        base_ydl_opts["remote_components"] = effective_remote_components
    if info_is_playlist:
        base_ydl_opts["ignoreerrors"] = "only_download"

    if subtitle_config.get("download_subtitles"):
        base_ydl_opts["writesubtitles"] = True
        if subtitle_config.get("write_automatic_subtitles"):
            base_ydl_opts["writeautomaticsub"] = True
        languages = subtitle_config.get("subtitleslangs")
        if languages:
            base_ydl_opts["subtitleslangs"] = languages
        subtitle_format = subtitle_config.get("subtitlesformat")
        if subtitle_format:
            base_ydl_opts["subtitlesformat"] = subtitle_format

    clients_to_try = prioritize_client(active_youtube_clients, info_client)
    attempts_to_try = prioritize_attempt(url_attempts, info_attempt)
    has_multiple_retry_paths = (
        len(clients_to_try) > 1
        or len(attempts_to_try) > 1
        or len(cookie_sources) > 1
    )

    try:
        last_error = None
        for attempt in attempts_to_try:
            for client in clients_to_try:
                for cookie_source in cookie_sources:
                    ydl_opts = dict(base_ydl_opts)
                    attempt_headers = attempt.get("http_headers") or {}
                    if attempt_headers:
                        merged_headers = dict(base_ydl_opts.get("http_headers", {}))
                        merged_headers.update(attempt_headers)
                        ydl_opts["http_headers"] = merged_headers
                    if client:
                        ydl_opts["extractor_args"] = {"youtube": {"player_client": [client]}}
                    if cookie_source and cookie_source.get("spec"):
                        ydl_opts["cookiesfrombrowser"] = cookie_source["spec"]
                    try:
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            # Download the video (and subtitles if requested)
                            info = ydl.extract_info(attempt["url"], download=True)
                            if info is None:
                                raise DownloadError("No downloadable media info was returned.")
                            downloaded_video_paths = []
                            for downloaded_path in collect_downloaded_video_paths(info):
                                absolute_video_path = sanitize_downloaded_path(downloaded_path)
                                downloaded_video_paths.append(
                                    os.path.join(raw_dir, os.path.basename(absolute_video_path))
                                )

                            if not downloaded_video_paths and not is_playlist_result(info):
                                filename = os.path.basename(ydl.prepare_filename(info))
                                absolute_video_path = sanitize_downloaded_path(filename)
                                downloaded_video_paths.append(
                                    os.path.join(raw_dir, os.path.basename(absolute_video_path))
                                )

                            subtitle_paths = []
                            if subtitle_config.get("download_subtitles"):
                                for sub_filepath in collect_subtitle_paths(info):
                                    absolute_sub_path = sanitize_downloaded_path(sub_filepath)
                                    subtitle_paths.append(
                                        os.path.join(raw_dir, os.path.basename(absolute_sub_path))
                                    )

                            downloaded_video_paths = list(dict.fromkeys(downloaded_video_paths))
                            subtitle_paths = list(dict.fromkeys(subtitle_paths))

                            if not downloaded_video_paths and not subtitle_paths:
                                raise DownloadError("No downloadable video files were saved.")

                            # Return the full path to the downloaded file(s)
                            return {
                                "video": downloaded_video_paths[0] if downloaded_video_paths else None,
                                "videos": downloaded_video_paths,
                                "subtitles": subtitle_paths,
                            }
                    except (CookieLoadError, DownloadError) as e:
                        if has_multiple_retry_paths:
                            context = describe_retry_context(
                                attempt,
                                client,
                                cookie_source,
                                show_attempt=len(attempts_to_try) > 1,
                                show_client=len(clients_to_try) > 1,
                                show_cookies=len(cookie_sources) > 1 or bool(cookie_source.get("spec")),
                            )
                            prefix = f"{context} failed" if context else "Download attempt failed"
                            print(f"{prefix}: {str(e)}")
                        else:
                            print(f"Client '{format_client_label(client)}' failed: {str(e)}")
                        last_error = e
                        continue
        if last_error:
            print(f"An error occurred: {str(last_error)}")
            if hint := get_actionable_error_hint(
                url,
                last_error,
                browser_cookie_sources=browser_cookie_sources,
            ):
                print(hint)
        return {"video": None, "subtitles": []}
    except OSError as e:
        print(f"An OS error occurred: {str(e)}")
        return {"video": None, "subtitles": []}
    finally:
        os.chdir(original_cwd)


# ... existing convert_video function ...


# ---------------------------------------------------------------------------
# Transcription & Summarization
# ---------------------------------------------------------------------------

_MINIMAX_API_URLS = [
    "https://api.minimax.io/v1/text/chatcompletion_v2",
    "https://api.minimax.chat/v1/text/chatcompletion_v2",
]


def _vtt_to_text(vtt_path):
    """Convert a VTT subtitle file to plain text using the project's vtt_to_text module."""
    from vtt_to_text import iter_caption_lines, lines_to_paragraphs
    lines = list(iter_caption_lines(Path(vtt_path)))
    if not lines:
        return None
    return "\n\n".join(lines_to_paragraphs(lines))


def _transcribe_with_whisper(video_path):
    """Transcribe a video file using the local whisper CLI, return plain text."""
    print("No subtitles found — transcribing with whisper...")
    video_path = Path(video_path)
    output_dir = video_path.parent / "_whisper_tmp"
    output_dir.mkdir(exist_ok=True)
    try:
        cmd = [
            "whisper", str(video_path),
            "--model", "base",
            "--language", "en",
            "--output_format", "txt",
            "--output_dir", str(output_dir),
            "--verbose", "False",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Whisper error: {result.stderr.strip()}")
            return None
        # whisper outputs a .txt file named after the input stem
        expected = output_dir / video_path.with_suffix(".txt").name
        candidates = list(output_dir.glob("*.txt"))
        txt_file = expected if expected.exists() else (candidates[0] if candidates else None)
        if txt_file and txt_file.exists():
            return txt_file.read_text(encoding="utf-8").strip()
        print("Whisper produced no output file.")
        return None
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def _summarize_with_minimax(transcript, video_title=""):
    """Send transcript to MiniMax and return the summary text."""
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        print("Error: MINIMAX_API_KEY not set. Create a .env file with MINIMAX_API_KEY=...")
        return None

    import urllib.request
    import urllib.error

    title_ctx = f' titled "{video_title}"' if video_title else ""
    prompt = (
        f"Summarize the following video transcript{title_ctx} in English. "
        "Provide a concise summary with the key points discussed. "
        "Use bullet points for the main topics.\n\n"
        f"--- TRANSCRIPT START ---\n{transcript}\n--- TRANSCRIPT END ---"
    )

    payload = json.dumps({
        "model": "MiniMax-M2.7",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }).encode("utf-8")

    print("Summarizing with MiniMax...")
    last_error = None
    for api_url in _MINIMAX_API_URLS:
        req = urllib.request.Request(
            api_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            choices = body.get("choices") or []
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
            # Non-choice response means auth worked but something else failed
            print(f"Unexpected MiniMax response: {body}")
            return None
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            last_error = f"MiniMax API error {e.code} ({api_url}): {err_body}"
            continue

    if last_error:
        print(last_error)
    return None


# ---------------------------------------------------------------------------
# Podcast Pipeline
# ---------------------------------------------------------------------------

def _get_video_duration(video_path):
    """Get video duration in seconds via ffprobe, or 0 if unavailable."""
    if not video_path or not Path(video_path).exists():
        return 0
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except FileNotFoundError:
        pass
    return 0


def _target_word_count(video_duration_seconds):
    """Calculate target narration word count based on source video duration.

    Uses a ~1:10 ratio (1 minute podcast per 10 minutes source),
    at ~150 words/min speech rate. Floor 400 words (~3 min), cap 1800 (~12 min).
    """
    if video_duration_seconds <= 0:
        return 700
    src_minutes = video_duration_seconds / 60
    podcast_minutes = max(3, min(12, src_minutes / 10))
    return int(podcast_minutes * 150)


def _narrate_as_podcast(summary_text, video_title="", extra_prompt="",
                        target_words=700, language="en", duo=False):
    """Convert a bullet-point summary into a podcast-style narration via MiniMax.

    language: "en" for British English, "es" for beginner-friendly Spanish.
    duo: if True, generate two-speaker dialogue (Host/Co-host) instead of solo.
    """
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        print("Error: MINIMAX_API_KEY not set.")
        return None

    title_ctx = f' about "{video_title}"' if video_title else ""

    if duo:
        # Load the dialogue craft prompt for two-host episodes
        craft_file = Path(__file__).parent / "two-host-dialogue-craft-prompt.md"
        craft_rules = ""
        if craft_file.exists():
            craft_text = craft_file.read_text(encoding="utf-8")
            if "---" in craft_text:
                craft_text = craft_text.split("---", 1)[1].strip()
            craft_rules = craft_text + "\n\n"

        if language == "es":
            prompt = (
                craft_rules +
                f"Ahora aplica todas las reglas anteriores para escribir un episodio corto{title_ctx} "
                "con DOS presentadores: Host y Co-host. "
                "Reescribe el siguiente resumen como una conversación entre ellos. Reglas adicionales:\n"
                "- Formato: cada línea debe empezar con 'Host: ' o 'Co-host: ' seguido del texto hablado.\n"
                "- NO uses otras etiquetas, direcciones de escena, ni markdown.\n"
                "- Cuando menciones archivos, escríbelos como se dicen en voz alta: nunca "
                "escribas nombres como 'soul.md'. Escribe 'un archivo markdown llamado soul'.\n"
                "- Este es un podcast para ESTUDIANTES PRINCIPIANTES de español. "
                "Usa vocabulario simple, oraciones cortas, y tiempos verbales básicos.\n"
                f"- Apunta a {target_words} palabras en total entre ambos presentadores "
                f"(aprox. {target_words // 150} minutos).\n"
                "- Usa un tono cálido y conversacional.\n"
                "- Cuando menciones archivos o rutas, escríbelos como se dicen en voz alta: "
                "nunca escribas nombres de archivo como 'soul.md' o 'config.yaml'. En su lugar "
                "escribe 'un archivo markdown llamado soul' o 'un archivo de configuración'. "
                "Si la extensión importa, deletréala: 'punto em de', 'punto y a m l'.\n"
            )
        else:
            prompt = (
                craft_rules +
                f"Now apply all the above rules to write a short episode{title_ctx} "
                "with TWO speakers: Host and Co-host. "
                "Rewrite the following summary as a conversation between them. Additional rules:\n"
                "- Format: each line must start with 'Host: ' or 'Co-host: ' followed by the spoken text.\n"
                "- Do NOT use any other speaker labels, stage directions, or markdown.\n"
                "- OPEN WITH THE TOPIC. The Host's first line must name the specific thing they "
                "saw or read (e.g. 'This week I saw X and I'm not sure what to make of it'). "
                "Do NOT open with adversarial fencing like 'talk me out of this' or 'convince me' "
                "that delays the subject. The listener came for the content, not the sparring.\n"
                "- Interplay is collaborative ('yes, and'): each speaker builds on what the other "
                "said, adds something new, and moves the conversation forward. Friction comes from "
                "sharpening questions and demanding specifics, not from manufactured opposition.\n"
                "- When mentioning filenames, file paths, or code references, write them as spoken "
                "aloud: never write raw filenames like 'soul.md'. Instead write 'a markdown file "
                "called soul'. Spell extensions if needed: 'dot em dee'.\n"
                f"- Target {target_words} words total across both speakers "
                f"(roughly {target_words // 150} minutes when read aloud).\n"
            )
    elif language == "es":
        prompt = (
            "You are a Spanish-learning podcast producer. Rewrite the following summary as a "
            f"bilingual podcast episode{title_ctx} that teaches Spanish through immersion.\n\n"
            "Format — every line must start with EN: or ES: followed by the spoken text:\n"
            "EN: [sentence in English]\n"
            "ES: [same sentence in beginner-friendly Spanish]\n"
            "EN: [next English sentence]\n"
            "ES: [same sentence in Spanish]\n\n"
            "Rules:\n"
            "- Each ES/EN pair covers one idea (1-2 sentences per line).\n"
            "- ES lines use simple vocabulary, short sentences, basic tenses "
            "(present, simple past). Avoid complex subjunctive or technical jargon.\n"
            "- EN lines are the natural English equivalent — not word-for-word, but "
            "conveying the same meaning the way a native speaker would say it.\n"
            "- The flow should feel like a continuous podcast narration, not a vocabulary list. "
            "Open with a hook, build through the content, close with a takeaway.\n"
            "- Do NOT include any speaker labels, stage directions, or markdown. "
            "Only ES: and EN: lines.\n"
            "- After the opening hook, go DIRECTLY into the topic. No filler like "
            "'Bienvenidos' or 'Let's begin.'\n"
            f"- Target {target_words} words total across both languages "
            f"(approx. {target_words // 150} minutes when read aloud).\n"
        )
    else:
        prompt = (
            f"You are a podcast host writing a short episode script{title_ctx}. "
            "Rewrite the following summary as a conversational narration in British English. "
            "Rules:\n"
            "- Write in plain text paragraphs, no markdown, no bullet points, no headers.\n"
            "- Open with something that draws the listener in — a surprising fact, a question, "
            "a bold statement, or a brief tease of what the episode covers. You can signal what "
            "the episode is about, but avoid rigid formulas like 'In this episode you will learn "
            "X things.' Be natural and varied.\n"
            "- After the opening, go DIRECTLY into the topic. Do NOT open with filler like "
            "'Right', 'Alright', 'Hey there', 'So', 'Welcome back', 'Let me tell you', or "
            "any variation. Begin with a specific fact, question, or statement about the topic.\n"
            "- Do NOT mention a guest, interview, or conversation partner. This is a solo podcast. "
            "There are no guests. Present the information as your own commentary and analysis.\n"
            "- Cover the key facts and insights from the summary naturally.\n"
            "- Close with a brief wrap-up — it could be a reflection, a takeaway, a forward-looking "
            "thought, or a short summary. Keep it to 2-3 sentences and avoid clichés like "
            "'So today we learned...' every time.\n"
            f"- Target {target_words} words (roughly {target_words // 150} minutes when read aloud).\n"
            "- Use a warm, conversational tone as if speaking to a friend.\n"
            "- When mentioning filenames, file paths, or code references, write them as spoken "
            "aloud: never write raw filenames like 'soul.md' or 'config.yaml'. Instead write "
            "'a markdown file called soul' or 'a config file'. If the extension matters, "
            "spell it: 'dot em dee', 'dot y a m l'. Same for folder paths — write "
            "'the source folder' not 'src/'.\n"
        )
    if extra_prompt:
        prompt += f"\nAdditional instructions for this episode:\n{extra_prompt}\n"

    # Load SOUL.md for consistent persona across all episodes
    soul_file = Path(__file__).parent / "SOUL.md"
    if soul_file.exists():
        soul_text = soul_file.read_text(encoding="utf-8")
        prompt += f"\n--- PERSONA ---\n{soul_text}\n--- END PERSONA ---\n"

    prompt += (
        f"\n--- SUMMARY START ---\n{summary_text}\n--- SUMMARY END ---"
    )

    payload = json.dumps({
        "model": "MiniMax-M2.7",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
    }).encode("utf-8")

    print(f"Generating {'Spanish' if language == 'es' else 'podcast'} narration...")
    for api_url in _MINIMAX_API_URLS:
        req = urllib.request.Request(
            api_url, data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            choices = body.get("choices") or []
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")
            print(f"MiniMax error {e.code}: {err}")
    return None


def _load_tts_prompt(language="en", duo=False):
    """Load TTS normalization prompt from tts-normalization-prompt.md."""
    prompt_file = Path(__file__).parent / "tts-normalization-prompt.md"
    if prompt_file.exists():
        text = prompt_file.read_text(encoding="utf-8")
        # Strip the header/intro up to the first ---
        if "---" in text:
            text = text.split("---", 1)[1].strip()
        # Add language-specific override for Spanish
        if language == "es":
            text = (
                "## LANGUAGE\n\n"
                "Apply all rules below in Spanish. Use Spanish number words, "
                "Spanish ordinal/cardinal forms, and Spanish abbreviations.\n"
                "Siglas leídas letra por letra se separan con puntos "
                "(ej: 'O.N.U.', 'E.E.U.U.'). Las que se leen como palabra, se quedan igual.\n\n"
                + text
            )
        if duo:
            text += (
                "\n\n## DIALOGUE MODE\n\n"
                "Preserve all speaker label prefixes exactly (e.g. 'Host:', 'Co-host:', "
                "'MAYA:', 'DEV:'). Only normalize the spoken text after the colon.\n"
                "Apply Category 14 structural smoothing for flat-prosody engines.\n"
            )
        return text
    # Fallback to minimal inline prompt if file missing
    if language == "es":
        return (
            "Reescribe para lectura natural en voz alta. Convierte números romanos, "
            "siglas, símbolos y abreviaturas. Devuelve SOLO el texto corregido.\n"
        )
    return (
        "Rewrite for natural TTS reading. Convert Roman numerals, acronyms, "
        "symbols, and abbreviations to spoken form. Return ONLY the corrected text.\n"
    )


def _polish_bilingual_tts(narrative_text):
    """Bilingual text is already TTS-ready from the narration prompt. Skip polish to preserve EN:/ES: structure."""
    # Clean up empty lines but preserve tag structure
    lines = [l.strip() for l in narrative_text.strip().splitlines() if l.strip()]
    return "\n".join(lines)


def _polish_for_tts_raw(narrative_text, language="en"):
    """Polish narration text for TTS without bilingual awareness."""
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        return narrative_text

    prompt = _load_tts_prompt(language=language, duo=False)

    payload = json.dumps({
        "model": "MiniMax-M2.7",
        "messages": [{"role": "user", "content": prompt + "\n" + narrative_text}],
        "temperature": 0.1,
    }).encode("utf-8")

    for api_url in _MINIMAX_API_URLS:
        req = urllib.request.Request(
            api_url, data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            choices = body.get("choices") or []
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
        except (urllib.error.HTTPError, TimeoutError, OSError) as e:
            print(f"TTS polish error ({type(e).__name__}): {e}")
            continue
    return narrative_text


def _polish_for_tts(narrative_text, language="en", duo=False):
    """Polish narration text for natural TTS reading using comprehensive rules."""
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        return narrative_text

    # For bilingual EN:/ES: text, polish EN and ES lines separately
    if narrative_text.lstrip().startswith("EN:") or "\nEN:" in narrative_text:
        return _polish_bilingual_tts(narrative_text)

    prompt = _load_tts_prompt(language=language, duo=duo)

    payload = json.dumps({
        "model": "MiniMax-M2.7",
        "messages": [{"role": "user", "content": prompt + "\n" + narrative_text}],
        "temperature": 0.1,
    }).encode("utf-8")

    print("Polishing narration for TTS...")
    for api_url in _MINIMAX_API_URLS:
        req = urllib.request.Request(
            api_url, data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            choices = body.get("choices") or []
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
        except (urllib.error.HTTPError, TimeoutError, OSError) as e:
            print(f"TTS polish error ({type(e).__name__}): {e}")
            continue
    return narrative_text


_BRITISH_VOICES = [
    "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
    "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
]

_SPANISH_VOICES = ["ef_dora", "em_alex", "em_santa"]


def _parse_dialogue(text):
    """Parse duo narration text into list of (speaker, text) tuples.

    Accepts any uppercase label prefix: MAYA:, DEV:, Host:, Co-host:, etc.
    Lines not matching a speaker label are ignored.
    """
    import re
    segments = []
    pattern = re.compile(r'^([A-Za-z][A-Za-z\-]{1,20}):\s*(.+)$', re.MULTILINE)
    for match in pattern.finditer(text):
        speaker_raw = match.group(1).strip().lower()
        spoken_text = match.group(2).strip()
        if spoken_text:
            segments.append((speaker_raw, spoken_text))
    return segments


def _generate_duo_audio(narrative_text, output_mp3_path, lang="en"):
    """Generate two-speaker podcast audio with distinct voices per speaker."""
    from kokoro import KPipeline
    import soundfile as sf
    import numpy as np
    import random

    segments = _parse_dialogue(narrative_text)
    if len(segments) < 3:
        print(f"  Duo: only {len(segments)} dialogue segments found — falling back to solo.")
        return _generate_podcast_audio(narrative_text, output_mp3_path, lang=lang)

    # Fix pronunciation: enrich cache + collapse spaced acronyms
    if lang == "en":
        narrative_text = _prepare_pronunciation(narrative_text)
        # Re-parse after pronunciation fixes
        segments = _parse_dialogue(narrative_text)

    # Detect the two unique speakers (first-seen order)
    seen = []
    for speaker, _ in segments:
        if speaker not in seen:
            seen.append(speaker)
    speaker_a, speaker_b = seen[0], seen[1] if len(seen) > 1 else seen[0]

    SAMPLE_RATE = 24000
    if lang == "es":
        voice_a, voice_b = "ef_dora", "em_alex"
        lang_code = "e"
    else:
        voice_a = random.choice(["bf_alice", "bf_emma", "bf_isabella", "bf_lily"])
        voice_b = random.choice(["bm_daniel", "bm_fable"])
        lang_code = "a"

    print(f"  Duo mode: {len(segments)} segments, {speaker_a}={voice_a} / {speaker_b}={voice_b}")

    pipeline = KPipeline(lang_code=lang_code, repo_id="hexgrad/Kokoro-82M")

    # Load pronunciation golds into Kokoro's lexicon for correct g2p output
    try:
        from pronunciation_db import load_golds_into_pipeline
        n = load_golds_into_pipeline(pipeline)
        if n:
            print(f"  Loaded {n} pronunciation golds into Kokoro lexicon")
    except Exception as e:
        print(f"  Warning: could not load pronunciation golds: {e}")

    silence = np.zeros(int(0.15 * SAMPLE_RATE))

    audio_parts = []
    for speaker, text in segments:
        voice = voice_a if speaker == speaker_a else voice_b
        kokoro_segments = list(pipeline(text, voice=voice))
        if kokoro_segments:
            chunk = np.concatenate([audio for gs, ps, audio in kokoro_segments])
            audio_parts.append(chunk)
            audio_parts.append(silence)

    if not audio_parts:
        print("  No audio generated for duo mode.")
        return False

    full_audio = np.concatenate(audio_parts)
    duration = len(full_audio) / SAMPLE_RATE
    print(f"  Duo audio generated: {duration:.1f}s ({duration/60:.1f}min)")

    wav_path = str(output_mp3_path).rsplit(".", 1)[0] + ".tmp.wav"
    sf.write(wav_path, full_audio, SAMPLE_RATE)

    cmd = [
        "ffmpeg", "-y", "-i", wav_path,
        "-codec:a", "libmp3lame", "-qscale:a", "2",
    ]
    if lang == "es":
        cmd.extend(["-af", "atempo=0.85"])
    cmd.append(str(output_mp3_path))
    result = subprocess.run(cmd, capture_output=True, text=True)
    Path(wav_path).unlink(missing_ok=True)

    if result.returncode != 0:
        print(f"ffmpeg error: {result.stderr.strip()}")
        return False

    size_mb = Path(output_mp3_path).stat().st_size / (1024 * 1024)
    print(f"  Duo MP3 saved: {output_mp3_path} ({size_mb:.1f}MB, {duration/60:.1f}min)")
    return True


def _generate_bilingual_audio(narrative_text, output_mp3_path):
    """Generate bilingual podcast audio: ES lines in Spanish voice, EN lines in English voice."""
    from kokoro import KPipeline
    import soundfile as sf
    import numpy as np

    SAMPLE_RATE = 24000

    # Parse ES:/EN: lines
    segments = []
    for line in narrative_text.strip().splitlines():
        line = line.strip()
        if line.startswith("ES:"):
            segments.append(("ES", line[3:].strip()))
        elif line.startswith("EN:"):
            segments.append(("EN", line[3:].strip()))

    if not segments:
        print("  No ES:/EN: lines found in bilingual text.")
        return False

    print(f"  Bilingual mode: {len(segments)} segments "
          f"({sum(1 for l,_ in segments if l=='ES')} ES, {sum(1 for l,_ in segments if l=='EN')} EN)")

    # Create two pipelines — one per language
    pipeline_es = KPipeline(lang_code="e", repo_id="hexgrad/Kokoro-82M")
    pipeline_en = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")

    # Load pronunciation golds into both
    try:
        from pronunciation_db import load_golds_into_pipeline
        n_es = load_golds_into_pipeline(pipeline_es)
        n_en = load_golds_into_pipeline(pipeline_en)
        if n_es or n_en:
            print(f"  Loaded {n_en} pronunciation golds into bilingual pipelines")
    except Exception as e:
        print(f"  Warning: could not load pronunciation golds: {e}")

    voice_es = "ef_dora"
    voice_en = "bm_fable"
    silence = np.zeros(int(0.15 * SAMPLE_RATE))

    wav_path = str(Path(output_mp3_path).with_suffix(".wav"))
    audio_parts = []

    for lang_tag, text in segments:
        if not text:
            continue
        pipeline = pipeline_es if lang_tag == "ES" else pipeline_en
        voice = voice_es if lang_tag == "ES" else voice_en
        kokoro_segments = list(pipeline(text, voice=voice))
        if kokoro_segments:
            chunk = np.concatenate([audio for gs, ps, audio in kokoro_segments])
            audio_parts.append(chunk)
            audio_parts.append(silence)

    if not audio_parts:
        print("  No audio generated for bilingual segments.")
        return False

    combined = np.concatenate(audio_parts)
    duration = len(combined) / SAMPLE_RATE
    sf.write(wav_path, combined, SAMPLE_RATE)

    cmd = [
        "ffmpeg", "-y", "-i", wav_path,
        "-codec:a", "libmp3lame", "-qscale:a", "2",
        "-af", "atempo=0.9",
        str(output_mp3_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    Path(wav_path).unlink(missing_ok=True)
    if result.returncode != 0:
        print(f"ffmpeg error: {result.stderr.strip()}")
        return False

    size_mb = Path(output_mp3_path).stat().st_size / (1024 * 1024)
    print(f"  Bilingual MP3 saved: {output_mp3_path} ({size_mb:.1f}MB, {duration/60:.1f}min)")
    return True


def _prepare_pronunciation(text: str):
    """Enrich pronunciation cache from text and return postprocessed text.

    1. Auto-lookup uncached words via Wiktionary
    2. Collapse spaced acronyms (e.g. "A I" → "AI") so Kokoro golds match
    """
    try:
        from pronunciation_db import enrich_pronunciation_cache, pronunciation_postprocess
        new = enrich_pronunciation_cache(text)
        if new:
            print(f"  Enriched {new} new Wiktionary pronunciations")
        text = pronunciation_postprocess(text)
    except Exception as e:
        print(f"  Warning: pronunciation pass failed: {e}")
    return text


def _generate_podcast_audio(narrative_text, output_mp3_path, lang="en"):
    """Generate podcast audio using Kokoro TTS and convert to MP3."""
    from kokoro import KPipeline
    import soundfile as sf
    import numpy as np
    import random

    # Fix pronunciation before TTS: auto-lookup + collapse spaced acronyms
    if lang == "en":
        narrative_text = _prepare_pronunciation(narrative_text)

    SAMPLE_RATE = 24000
    if lang == "es":
        voice = random.choice(_SPANISH_VOICES)
        lang_code = "e"
    else:
        voice = random.choice(_BRITISH_VOICES)
        lang_code = "a"

    print(f"Generating audio ({len(narrative_text)} chars, voice: {voice}, lang: {lang})...")
    pipeline = KPipeline(lang_code=lang_code, repo_id="hexgrad/Kokoro-82M")

    # Load pronunciation golds into Kokoro's lexicon for correct g2p output
    try:
        from pronunciation_db import load_golds_into_pipeline
        n = load_golds_into_pipeline(pipeline)
        if n:
            print(f"  Loaded {n} pronunciation golds into Kokoro lexicon")
    except Exception as e:
        print(f"  Warning: could not load pronunciation golds: {e}")

    segments = list(pipeline(narrative_text, voice=voice, speed=0.9))
    if not segments:
        print("No audio generated.")
        return False

    audio_chunks = [audio for gs, ps, audio in segments]
    full_audio = np.concatenate(audio_chunks)
    duration = len(full_audio) / SAMPLE_RATE
    print(f"  Audio generated: {duration:.1f}s ({duration/60:.1f}min, voice: {voice})")

    wav_path = str(output_mp3_path).rsplit(".", 1)[0] + ".tmp.wav"
    sf.write(wav_path, full_audio, SAMPLE_RATE)

    cmd = [
        "ffmpeg", "-y", "-i", wav_path,
        "-codec:a", "libmp3lame", "-qscale:a", "2",
    ]
    if lang == "es":
        cmd.extend(["-af", "atempo=0.85"])
    else:
        cmd.extend(["-af", "atempo=0.9"])
    cmd.append(str(output_mp3_path))
    result = subprocess.run(cmd, capture_output=True, text=True)
    Path(wav_path).unlink(missing_ok=True)

    if result.returncode != 0:
        print(f"ffmpeg error: {result.stderr.strip()}")
        return False

    size_mb = Path(output_mp3_path).stat().st_size / (1024 * 1024)
    print(f"  MP3 saved: {output_mp3_path} ({size_mb:.1f}MB, {duration/60:.1f}min)")
    return True


_PODCAST_REPO = Path(__file__).resolve().parent
_PUBLISH_REPO = Path(__file__).resolve().parent.parent / "freeist-podcast"
_AUDIO_DIR = _PUBLISH_REPO / "audio"
_EPISODES_JSON = _PUBLISH_REPO / "episodes.json"
_RSS_OUTPUT = _PUBLISH_REPO / "rss" / "feed.xml"
_VECTOR_INDEX_PATH = _PODCAST_REPO / "episode_vectors.npz"
_VECTORIZER_PATH = _PODCAST_REPO / "episode_vectorizer.pkl"
_VECTOR_SLUGS_PATH = _PODCAST_REPO / "episode_vector_slugs.json"
_SIMILARITY_THRESHOLD = 0.20


def _slugify(text, max_words=8):
    """Create a URL-safe slug from text."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    words = [w for w in text.split("-") if w and w not in {
        "the", "a", "an", "is", "of", "in", "to", "for", "and", "on", "with", "by",
    }]
    return "-".join(words[:max_words]).strip("-")


def _rebuild_vector_index():
    """Build TF-IDF index from all entries in episodes.json."""
    import pickle
    from sklearn.feature_extraction.text import TfidfVectorizer
    import scipy.sparse

    episodes = json.loads(_EPISODES_JSON.read_text(encoding="utf-8"))
    if not episodes:
        return None, None, []

    slugs = list(episodes.keys())
    corpus = []
    for slug in slugs:
        ep = episodes[slug]
        corpus.append(f"{ep.get('title', '')} {ep.get('description', '')}")

    vectorizer = TfidfVectorizer(stop_words="english", max_features=5000, ngram_range=(1, 2))
    matrix = vectorizer.fit_transform(corpus)

    scipy.sparse.save_npz(str(_VECTOR_INDEX_PATH), matrix)
    with open(_VECTORIZER_PATH, "wb") as f:
        pickle.dump(vectorizer, f)
    _VECTOR_SLUGS_PATH.write_text(json.dumps(slugs), encoding="utf-8")

    print(f"  Vector index built: {len(slugs)} episodes, {matrix.shape[1]} features")
    return vectorizer, matrix, slugs


def _load_or_build_vector_index():
    """Load persisted TF-IDF index or rebuild from episodes.json."""
    import pickle

    if not _EPISODES_JSON.exists():
        return None, None, []

    current_slugs = list(json.loads(_EPISODES_JSON.read_text(encoding="utf-8")).keys())

    if not current_slugs:
        return None, None, []

    if _VECTOR_INDEX_PATH.exists() and _VECTORIZER_PATH.exists() and _VECTOR_SLUGS_PATH.exists():
        indexed_slugs = json.loads(_VECTOR_SLUGS_PATH.read_text(encoding="utf-8"))
        if indexed_slugs == current_slugs:
            import scipy.sparse
            matrix = scipy.sparse.load_npz(str(_VECTOR_INDEX_PATH))
            with open(_VECTORIZER_PATH, "rb") as f:
                vectorizer = pickle.load(f)
            return vectorizer, matrix, indexed_slugs

    return _rebuild_vector_index()


def _update_vector_index(slug, title, description):
    """Add a single new episode to the existing vector index."""
    import scipy.sparse

    vectorizer, matrix, slugs = _load_or_build_vector_index()
    if vectorizer is None:
        return

    text = f"{title} {description}"
    new_vec = vectorizer.transform([text])
    matrix = scipy.sparse.vstack([matrix, new_vec])
    slugs.append(slug)

    scipy.sparse.save_npz(str(_VECTOR_INDEX_PATH), matrix)
    _VECTOR_SLUGS_PATH.write_text(json.dumps(slugs), encoding="utf-8")


def _check_episode_similarity(summary_text, video_title):
    """Compare new episode summary against existing episodes.

    Returns list of top 5 matches above threshold, each with
    slug, title, similarity, and shared_terms.
    """
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np

    vectorizer, matrix, slugs = _load_or_build_vector_index()
    if vectorizer is None or matrix.shape[0] == 0:
        return []

    query = f"{video_title} {summary_text[:500]}"
    query_vec = vectorizer.transform([query])
    scores = cosine_similarity(query_vec, matrix).flatten()

    feature_names = vectorizer.get_feature_names_out()
    query_features = set(feature_names[query_vec.indices])

    matches = []
    top_indices = scores.argsort()[::-1][:10]
    episodes = json.loads(_EPISODES_JSON.read_text(encoding="utf-8"))

    for idx in top_indices:
        score = float(scores[idx])
        if score < _SIMILARITY_THRESHOLD:
            break
        slug = slugs[idx]
        ep = episodes.get(slug, {})
        doc_features = set(feature_names[matrix[idx].indices])
        shared = sorted(query_features & doc_features)[:6]
        matches.append({
            "slug": slug,
            "title": ep.get("title", slug),
            "similarity": round(score, 3),
            "shared_terms": shared,
        })
        if len(matches) >= 5:
            break

    return matches


def _display_similarity_table(matches):
    """Render a rich table showing similar episodes."""
    from rich.console import Console
    from rich.table import Table

    console = Console(stderr=True)
    table = Table(title="Similar Episodes Found", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Title", min_width=30, max_width=50)
    table.add_column("Match", width=8, justify="center")
    table.add_column("Key Overlap", min_width=20, max_width=40, style="dim")

    for i, m in enumerate(matches, 1):
        score = m["similarity"]
        if score >= 0.40:
            score_str = f"[bold red]{score:.0%}[/bold red]"
        elif score >= 0.25:
            score_str = f"[yellow]{score:.0%}[/yellow]"
        else:
            score_str = f"{score:.0%}"
        table.add_row(str(i), m["title"], score_str, ", ".join(m["shared_terms"]))

    console.print(table)


def _check_sponsored_content(summary_text, source_label=""):
    """Check if content looks like sponsored product marketing. Returns (score, reason) or None."""
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        return None

    import urllib.request
    import urllib.error

    label_ctx = f" (source: {source_label})" if source_label else ""
    prompt = (
        "You are a media literacy analyst. Read the following content summary"
        f"{label_ctx} and assess whether it is sponsored product marketing "
        "disguised as organic/educational content.\n\n"
        "Rate 1-10 how likely this is a sponsored/promotional piece:\n"
        "- 1-3: Genuine educational or informational content\n"
        "- 4-5: Mixed — some promotional undertones but mostly educational\n"
        "- 6-8: Likely sponsored — heavy product focus, marketing language, "
        "call-to-action to use/buy something\n"
        "- 9-10: Clearly a paid promotion — pure product demo or ad\n\n"
        "Respond in EXACTLY this format (no other text):\n"
        "SCORE: <number>\n"
        "REASON: <one sentence>\n"
        f"\n--- CONTENT START ---\n{summary_text[:3000]}\n--- CONTENT END ---"
    )

    payload = json.dumps({
        "model": "MiniMax-M2.7",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }).encode("utf-8")

    for api_url in _MINIMAX_API_URLS:
        req = urllib.request.Request(
            api_url, data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            choices = body.get("choices") or []
            if choices:
                text = choices[0].get("message", {}).get("content", "").strip()
                score_match = re.search(r"SCORE:\s*(\d+)", text)
                reason_match = re.search(r"REASON:\s*(.+)", text)
                if score_match:
                    return int(score_match.group(1)), (reason_match.group(1).strip() if reason_match else "")
        except (urllib.error.HTTPError, TimeoutError, OSError):
            continue
    return None


def _next_episode_number(podcast_dir=None):
    """Find the next episode number by scanning existing ep##.podcast.mp3 files."""
    if podcast_dir is None:
        podcast_dir = _AUDIO_DIR
    highest = 0
    for f in Path(podcast_dir).glob("ep*.podcast.mp3"):
        m = re.match(r"ep(\d+)", f.name)
        if m:
            highest = max(highest, int(m.group(1)))
    return highest + 1


def produce_podcast(summary_path, video_title="", podcast_dir=None,
                    extra_prompt="", video_duration_seconds=0, duo=False):
    """Full podcast pipeline: summary → narrate → TTS → MP3 (English + Spanish)."""
    if podcast_dir is None:
        podcast_dir = _AUDIO_DIR
    summary_path = Path(summary_path)
    podcast_path = Path(podcast_dir)
    podcast_path.mkdir(parents=True, exist_ok=True)

    ep_num = _next_episode_number(podcast_dir)
    slug = _slugify(video_title or summary_path.stem.replace(".summary", ""))
    clean_name = f"ep{ep_num:02d}-{slug}"

    target_words = _target_word_count(video_duration_seconds)
    src_min = video_duration_seconds / 60 if video_duration_seconds else 0
    print(f"  Source: {src_min:.1f}min → target: {target_words} words (~{target_words // 150}min podcast)")

    summary_text = summary_path.read_text(encoding="utf-8")

    # --- Sponsored content check ---
    result = _check_sponsored_content(summary_text, source_label=video_title)
    if result and result[0] >= 6:
        score, reason = result
        print(f"\n  WARNING: Sponsored content detected (score: {score}/10)")
        print(f"  Reason: {reason}")
        if sys.stdin.isatty():
            try:
                answer = input("  Proceed anyway? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "n"
            if answer not in ("y", "yes"):
                print("  Skipping podcast production.")
                return None
        else:
            print("  (non-interactive mode — proceeding anyway)")

    # --- Similarity check ---
    sim_matches = _check_episode_similarity(summary_text, video_title or "")
    if sim_matches:
        _display_similarity_table(sim_matches)
        if sys.stdin.isatty():
            try:
                answer = input("\n  Episode may be a duplicate. Proceed anyway? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "n"
            if answer not in ("y", "yes"):
                print("  Skipping podcast production.")
                return None
        else:
            print("  (non-interactive mode — proceeding anyway)")
    else:
        print("  Similarity check passed.")

    # --- English ---
    en_txt = podcast_path / f"{clean_name}.podcast.txt"
    en_mp3 = podcast_path / f"{clean_name}.podcast.mp3"

    if en_mp3.exists():
        print(f"English podcast already exists: {en_mp3}")
    else:
        if en_txt.exists():
            print(f"English narration exists, skipping MiniMax")
            en_narrative = en_txt.read_text(encoding="utf-8")
        else:
            en_narrative = _narrate_as_podcast(
                summary_text, video_title=video_title,
                extra_prompt=extra_prompt, target_words=target_words, language="en", duo=duo)
            if not en_narrative:
                print("Failed to generate English narration.")
                return None
            en_narrative = _polish_for_tts(en_narrative, language="en", duo=duo)
            en_txt.write_text(en_narrative, encoding="utf-8")
            print(f"  English narration saved: {en_txt.name}")

        _gen_fn = _generate_duo_audio if duo else _generate_podcast_audio
        if not _gen_fn(en_narrative, en_mp3, lang="en"):
            return None

    # --- Spanish ---
    es_txt = podcast_path / f"{clean_name}.podcast.es.txt"
    es_mp3 = podcast_path / f"{clean_name}.podcast.es.mp3"

    if es_mp3.exists():
        print(f"Spanish podcast already exists: {es_mp3}")
    else:
        if es_txt.exists():
            print(f"Spanish narration exists, skipping MiniMax")
            es_narrative = es_txt.read_text(encoding="utf-8")
        else:
            es_narrative = _narrate_as_podcast(
                summary_text, video_title=video_title,
                extra_prompt=extra_prompt, target_words=target_words, language="es", duo=duo)
            if not es_narrative:
                print("Failed to generate Spanish narration.")
            else:
                es_narrative = _polish_for_tts(es_narrative, language="es", duo=duo)
                es_txt.write_text(es_narrative, encoding="utf-8")
                print(f"  Spanish narration saved: {es_txt.name}")

        if es_txt.exists():
            es_narrative = es_txt.read_text(encoding="utf-8")
            # Detect bilingual ES:/EN: format and route to bilingual audio
            if es_narrative.lstrip().startswith("EN:") or "\nEN:" in es_narrative:
                if not _generate_bilingual_audio(es_narrative, es_mp3):
                    print("Bilingual audio generation failed.")
            else:
                if not _gen_fn(es_narrative, es_mp3, lang="es"):
                    print("Spanish audio generation failed.")

    # Update vector index with new episode
    desc_preview = summary_text[:500]
    _update_vector_index(clean_name, video_title or "", desc_preview)

    return str(en_mp3)


def _upload_file_gh_api(repo_path, local_file, remote_path):
    """Upload a file to GitHub via the Contents API (files <5MB) or Git Data API (larger)."""
    import base64
    file_size = os.path.getsize(local_file)
    with open(local_file, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()

    # Try Contents API first (simpler, works for files <~5MB)
    payload_json = json.dumps({"message": f"Add {Path(remote_path).name}", "content": content_b64})
    if len(payload_json) < 4_500_000:
        payload_path = _PUBLISH_REPO / ".tmp_upload.json"
        payload_path.write_text(payload_json)
        r = subprocess.run(
            ["gh", "api", f"repos/mrleepee/freeist-podcast/contents/{remote_path}",
             "-X", "PUT", "--input", str(payload_path)],
            capture_output=True, text=True,
        )
        payload_path.unlink(missing_ok=True)
        if r.returncode == 0:
            print(f"  Uploaded via Contents API: {remote_path}")
            return True
        # If it failed (not because file exists), fall through to Git Data API

    # Git Data API for larger files: create blob → tree → commit → update ref
    blob_payload = json.dumps({"content": content_b64, "encoding": "base64"})
    blob_path = _PUBLISH_REPO / ".tmp_blob.json"
    blob_path.write_text(blob_payload)

    r = subprocess.run(
        ["gh", "api", "repos/mrleepee/freeist-podcast/git/blobs",
         "--input", str(blob_path), "--jq", ".sha"],
        capture_output=True, text=True,
    )
    blob_path.unlink(missing_ok=True)
    if r.returncode != 0:
        print(f"  Blob upload failed: {r.stderr}")
        return False
    blob_sha = r.stdout.strip()

    r = subprocess.run(
        ["gh", "api", "repos/mrleepee/freeist-podcast/git/refs/heads/main",
         "--jq", ".object.sha"],
        capture_output=True, text=True,
    )
    head_sha = r.stdout.strip()

    r = subprocess.run(
        ["gh", "api", f"repos/mrleepee/freeist-podcast/git/commits/{head_sha}",
         "--jq", ".tree.sha"],
        capture_output=True, text=True,
    )
    tree_sha = r.stdout.strip()

    r = subprocess.run(
        ["gh", "api", "repos/mrleepee/freeist-podcast/git/trees",
         "-f", f"base_tree={tree_sha}",
         "-f", f"tree[][path]={remote_path}",
         "-f", "tree[][mode]=100644",
         "-f", "tree[][type]=blob",
         "-f", f"tree[][sha]={blob_sha}",
         "--jq", ".sha"],
        capture_output=True, text=True,
    )
    new_tree = r.stdout.strip()

    r = subprocess.run(
        ["gh", "api", "repos/mrleepee/freeist-podcast/git/commits",
         "-f", f"message=Add {Path(remote_path).name}",
         "-f", f"tree={new_tree}",
         "-f", f"parent={head_sha}",
         "--jq", ".sha"],
        capture_output=True, text=True,
    )
    commit_sha = r.stdout.strip()

    ref_payload = json.dumps({"sha": commit_sha, "force": True})
    ref_path = _PUBLISH_REPO / ".tmp_ref.json"
    ref_path.write_text(ref_payload)
    r = subprocess.run(
        ["gh", "api", "repos/mrleepee/freeist-podcast/git/refs/heads/main",
         "-X", "PATCH", "--input", str(ref_path)],
        capture_output=True, text=True,
    )
    ref_path.unlink(missing_ok=True)
    if r.returncode != 0:
        print(f"  Ref update failed: {r.stderr}")
        return False
    print(f"  Uploaded via Git Data API: {remote_path}")
    return True


def publish_feed():
    """Regenerate RSS feed and push to GitHub."""
    print("\nPublishing to feed...")
    generate_rss = _PODCAST_REPO / "generate_rss.py"
    result = subprocess.run(
        [sys.executable, str(generate_rss),
         "--base-url", "https://mrleepee.github.io/freeist-podcast/audio/",
         "--title", "Señor Freedom",
         "--output", str(_RSS_OUTPUT)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"RSS generation failed: {result.stderr}")
        return False
    print(result.stdout.strip())

    if not _PUBLISH_REPO.exists():
        print(f"Publish repo not found at {_PUBLISH_REPO}. Clone it first:")
        print(f"  git clone https://github.com/mrleepee/freeist-podcast.git {_PUBLISH_REPO}")
        return False

    # Copy RSS to repo root as well
    import shutil
    shutil.copy2(_RSS_OUTPUT, _PUBLISH_REPO / "feed.xml")

    # Commit and push from publish repo
    subprocess.run(["git", "add", "-A"], cwd=_PUBLISH_REPO, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Update podcast feed"],
        cwd=_PUBLISH_REPO, capture_output=True,
    )
    push = subprocess.run(["git", "push"], cwd=_PUBLISH_REPO, capture_output=True, text=True)
    if push.returncode != 0:
        print(f"Git push failed: {push.stderr.strip()}")
        print("Falling back to GitHub API upload...")
        audio_dir = _PUBLISH_REPO / "audio"
        # Upload any new audio/ files via API
        for f in audio_dir.glob("ep*.podcast.mp3"):
            # Check if file exists on remote
            check = subprocess.run(
                ["gh", "api", f"repos/mrleepee/freeist-podcast/contents/audio/{f.name}",
                 "--jq", ".size"],
                capture_output=True, text=True,
            )
            if check.returncode != 0:
                print(f"  Uploading {f.name}...")
                _upload_file_gh_api(_PUBLISH_REPO, str(f), f"audio/{f.name}")
        # Upload feed.xml and episodes.json via Contents API (small files)
        rss_dst = _PUBLISH_REPO / "rss"
        for small_file, remote in [(rss_dst / "feed.xml", "rss/feed.xml"), (_PUBLISH_REPO / "episodes.json", "episodes.json")]:
            if small_file.exists():
                _upload_file_gh_api(_PUBLISH_REPO, str(small_file), remote)
        # Sync local with remote
        subprocess.run(["git", "fetch", "origin"], cwd=_PUBLISH_REPO, capture_output=True)
        subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=_PUBLISH_REPO, capture_output=True)
    else:
        print("Feed pushed to GitHub.")
    return True


def summarize_video(result, video_title=""):
    """Try to get transcript from subtitles or whisper, then summarize.

    Returns the path to the saved summary file, or None on failure.
    """
    video_path = result.get("video")
    subtitle_paths = result.get("subtitles", [])
    transcript = None

    # 1. Try downloaded subtitles
    if subtitle_paths:
        for sub_path in subtitle_paths:
            if sub_path.endswith((".vtt", ".srt")):
                # yt-dlp may rename subtitle files after download (e.g. .en.vtt → .NA.en.vtt)
                actual_path = sub_path
                if not os.path.exists(actual_path):
                    stem = sub_path.rsplit(".", 2)[0] if sub_path.endswith(".vtt") else sub_path.rsplit(".", 2)[0]
                    candidates = list(Path(stem).parent.glob(Path(stem).name.rsplit(".", 1)[0] + "*.*"))
                    candidates = [c for c in candidates if str(c).endswith((".vtt", ".srt"))]
                    if candidates:
                        actual_path = str(candidates[0])
                transcript = _vtt_to_text(actual_path)
                if transcript:
                    print(f"Extracted transcript from subtitles: {actual_path}")
                    break

    # 2. Fallback to whisper transcription
    if not transcript and video_path and os.path.exists(video_path):
        transcript = _transcribe_with_whisper(video_path)

    if not transcript:
        print("Could not obtain a transcript — skipping summarization.")
        return None

    # 3. Summarize with MiniMax
    summary = _summarize_with_minimax(transcript, video_title=video_title)
    if not summary:
        return None

    # 4. Save summary alongside the video
    if video_path:
        summary_path = Path(video_path).with_suffix(".summary.md")
    else:
        summary_path = Path("downloads/raw") / f"{sanitize_filename(video_title or 'summary')}.summary.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(summary, encoding="utf-8")
    print(f"Summary saved to: {summary_path}")
    return str(summary_path)



def main():
    args = parse_arguments()

    subtitle_langs = []
    if args.subs_lang:
        for entry in args.subs_lang:
            subtitle_langs.extend(
                lang.strip()
                for lang in entry.split(",")
                if lang.strip()
            )

    do_summarize = args.summarize or args.podcast

    subtitle_config = {
        "download_subtitles": args.subs or do_summarize,
        "subtitleslangs": subtitle_langs or (["en"] if do_summarize else None),
        "subtitlesformat": "vtt" if do_summarize else args.subs_format,
        "write_automatic_subtitles": (args.subs and not args.subs_manual_only) or do_summarize,
    }
    youtube_clients = parse_youtube_client_preference(args.yt_client)

    if args.list_file:
        file_path = args.list_file
        downloaded_items = []

        try:
            with open(file_path, 'r') as file:
                urls = file.readlines()
                for url in urls:
                    url = url.strip()
                    if not url:
                        continue
                    result = download_video(
                        url,
                        subtitle_config=subtitle_config,
                        youtube_clients=youtube_clients,
                        cookies_file=args.cookies,
                        browser_cookie_sources=args.browser_cookie_sources,
                        prefer_browser_cookies=args.prefer_browser_cookies,
                        user_agent=args.user_agent,
                        vimeo_hash=args.vimeo_hash,
                        js_runtimes=args.js_runtimes,
                        remote_components=args.remote_components,
                    )
                    if result.get("video") or result.get("subtitles"):
                        downloaded_items.append({"url": url, **result})
                    else:
                        print(f"Error downloading: {url}. Skipping to next URL.")
        except FileNotFoundError:
            print(f"Error: File not found at {file_path}")
            sys.exit(1)

        print("\nSummary of downloaded items:")
        for item in downloaded_items:
            print(f"URL: {item['url']}")
            if item.get("videos"):
                if len(item["videos"]) == 1:
                    print(f"Downloaded file: {item['videos'][0]}")
                else:
                    print("Downloaded files:")
                    for video_path in item["videos"]:
                        print(f" - {video_path}")
            elif item.get("video"):
                print(f"Downloaded file: {item['video']}")
            else:
                print("Video download failed.")
            if subtitle_config["download_subtitles"]:
                if item.get("subtitles"):
                    print("Subtitles:")
                    for subtitle_path in item["subtitles"]:
                        print(f" - {subtitle_path}")
                else:
                    print("Subtitles: none downloaded")
            if do_summarize:
                summary_path = summarize_video(item, video_title="")
                if summary_path and args.podcast:
                    vid_dur = _get_video_duration(item.get("video"))
                    produce_podcast(summary_path, video_title="",
                                    extra_prompt=args.prompt or "",
                                    video_duration_seconds=vid_dur,
                                    duo=args.duo)
            print()
    else:
        url = args.url
        result = download_video(
            url,
            subtitle_config=subtitle_config,
            youtube_clients=youtube_clients,
            cookies_file=args.cookies,
            browser_cookie_sources=args.browser_cookie_sources,
            prefer_browser_cookies=args.prefer_browser_cookies,
            user_agent=args.user_agent,
            vimeo_hash=args.vimeo_hash,
            custom_title=args.title,
            js_runtimes=args.js_runtimes,
            remote_components=args.remote_components,
        )

        if result.get("videos"):
            if len(result["videos"]) == 1:
                print(f"Video downloaded successfully: {result['videos'][0]}")
            else:
                print("Videos downloaded successfully:")
                for video_path in result["videos"]:
                    print(f" - {video_path}")
        elif result.get("video"):
            print(f"Video downloaded successfully: {result['video']}")
        else:
            print("Video download failed.")

        if subtitle_config["download_subtitles"]:
            if result.get("subtitles"):
                print("Downloaded subtitles:")
                for subtitle_path in result["subtitles"]:
                    print(f" - {subtitle_path}")
            else:
                print("No subtitles were downloaded.")

        if do_summarize:
            summary_path = summarize_video(result, video_title=args.title or "")
            if summary_path and args.podcast:
                vid_dur = _get_video_duration(result.get("video"))
                produce_podcast(summary_path, video_title=args.title or "",
                                extra_prompt=args.prompt or "",
                                video_duration_seconds=vid_dur,
                                duo=args.duo)


if __name__ == "__main__":
    main()
