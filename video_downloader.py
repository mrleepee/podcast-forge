import argparse
import subprocess
import os
import sys
import json
import re
import shutil
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

# NOTE: yt_dlp is imported lazily inside the download functions
# (parse_browser_cookie_spec, get_video_info, download_video) so this 4,000-line
# module stays importable without yt_dlp installed — for the test suite and for
# the pipeline-only entry points (synthesis, quality gate, publishing) that never
# download. See checks/run.py and tests/.


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
        help="Download English subtitles (or transcribe via whisper), then summarize with GLM.",
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
        "--force",
        action="store_true",
        help="Bypass the fail-closed similarity/sponsorship gates (manual override).",
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
    from yt_dlp.cookies import SUPPORTED_BROWSERS, SUPPORTED_KEYRINGS
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
    from yt_dlp.cookies import SUPPORTED_BROWSERS
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
    import yt_dlp
    from yt_dlp.cookies import CookieLoadError
    from yt_dlp.utils import DownloadError
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
    import yt_dlp
    from yt_dlp.cookies import CookieLoadError
    from yt_dlp.utils import DownloadError
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

# ---------------------------------------------------------------------------
# GLM (Z.ai) — the pipeline's sole LLM backend.
#
# Uses Z.ai's Anthropic-compatible Messages API (the same coding-plan
# subscription Claude Code uses), so generation draws no prepaid API credits.
# Config is resolved from env (ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN /
# PODCAST_LLM_MODEL) with a fallback to ~/.claude/settings-GLM.json — the same
# source the verifier (pipeline_stages.call_verifier) reads its key from.
#
# urllib's per-operation timeout does not fire on slow-drip SSL reads, so a call
# can hang for many minutes with no exception under degraded network conditions
# (observed: 10+ minute hangs). Each attempt runs in a daemon worker thread that
# is abandoned if it exceeds ``hard_timeout`` seconds; attempts retry on hang or
# error. Returns the model's text, or raises RuntimeError if every attempt fails.
# ---------------------------------------------------------------------------

_GLM_SETTINGS_PATH = Path.home() / ".claude" / "settings-GLM.json"
_GLM_ANTHROPIC_VERSION = "2023-06-01"


def _read_glm_settings() -> dict:
    """Return the env block of ~/.claude/settings-GLM.json (empty on failure)."""
    try:
        settings = json.loads(_GLM_SETTINGS_PATH.read_text(encoding="utf-8"))
        env = settings.get("env", {})
        return env if isinstance(env, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _resolve_glm_config():
    """Resolve (base_url, api_token, model) for GLM generation.

    Each field: explicit env var first, then ~/.claude/settings-GLM.json.
    ``model`` defaults to glm-5.2 (override with PODCAST_LLM_MODEL). Raises
    RuntimeError if base/token are unavailable, so callers can degrade gracefully.
    """
    settings = _read_glm_settings()
    base = (os.environ.get("ANTHROPIC_BASE_URL") or settings.get("ANTHROPIC_BASE_URL") or "").rstrip("/")
    token = os.environ.get("ANTHROPIC_AUTH_TOKEN") or settings.get("ANTHROPIC_AUTH_TOKEN") or ""
    model = os.environ.get("PODCAST_LLM_MODEL") or settings.get("PODCAST_LLM_MODEL") or "glm-5.2"
    if not base or not token:
        raise RuntimeError(
            "GLM config unavailable: set ANTHROPIC_BASE_URL/ANTHROPIC_AUTH_TOKEN "
            f"(or the env block in {_GLM_SETTINGS_PATH})"
        )
    return base, token, model


def _call_llm(system, user, *, temperature=0.3, max_tokens=4096,
              hard_timeout=120, attempts=4):
    """Call GLM (Z.ai Anthropic-compatible API) and return the response text.

    Builds an Anthropic Messages payload, posts it with a daemon-thread hard
    wall-clock timeout + retry (defeats slow-drip SSL hangs that urllib's per-op
    timeout misses), and returns the stripped response text. Raises RuntimeError
    if every attempt fails or GLM config is unavailable.
    """
    import threading
    import time
    base, token, model = _resolve_glm_config()
    body = {"model": model, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": user}]}
    if system:
        body["system"] = system
    if temperature is not None:
        body["temperature"] = temperature
    data = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "x-api-key": token,
        "authorization": f"Bearer {token}",
        "anthropic-version": _GLM_ANTHROPIC_VERSION,
    }
    last_error = None
    for attempt in range(attempts):
        box = {}

        def _work():
            try:
                r = urllib.request.Request(base + "/v1/messages", data=data, headers=headers)
                with urllib.request.urlopen(r, timeout=120) as resp:
                    box["body"] = resp.read()
            except urllib.error.HTTPError as e:
                box["http"] = (e.code, e.read().decode("utf-8", errors="replace"))
            except Exception as e:
                box["err"] = f"{type(e).__name__}: {e}"

        worker = threading.Thread(target=_work, daemon=True)
        worker.start()
        worker.join(hard_timeout)
        if worker.is_alive():
            last_error = f"hard timeout >{hard_timeout}s"
            print(f"    GLM call hung >{hard_timeout}s, retry {attempt + 1}/{attempts}")
            continue
        if "body" in box:
            an = json.loads(box["body"].decode("utf-8"))
            return "".join(
                b.get("text", "") for b in (an.get("content") or []) if b.get("type") == "text"
            ).strip()
        if "http" in box:
            last_error = f"GLM API error {box['http'][0]}: {box['http'][1][:200]}"
        else:
            last_error = f"GLM error: {box.get('err')}"
        time.sleep(1)
    raise RuntimeError(f"GLM failed after {attempts} attempts: {last_error}")


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


def _summarize_with_llm(transcript, video_title=""):
    """Send transcript to GLM and return the summary text (None on failure)."""
    title_ctx = f' titled "{video_title}"' if video_title else ""
    prompt = (
        f"Summarize the following video transcript{title_ctx} in English. "
        "Provide a concise summary with the key points discussed. "
        "Use bullet points for the main topics.\n\n"
        f"--- TRANSCRIPT START ---\n{transcript}\n--- TRANSCRIPT END ---"
    )
    print("Summarizing with GLM...")
    try:
        return _call_llm(None, prompt, temperature=0.3)
    except RuntimeError as e:
        print(str(e))
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
    """Convert a bullet-point summary into a podcast-style narration via GLM.

    language: "en" for British English, "es" for beginner-friendly Spanish.
    duo: if True, generate two-speaker dialogue (Host/Co-host) instead of solo.
    """
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
                "- AVOID ACRONYMS. Write them out: 'United States' not 'US', 'United Kingdom' not "
                "'UK', 'chief executive' not 'CEO', 'large language models' not 'LLMs', "
                "'application programming interface' not 'API'. The exception is 'AI' — it has "
                "become a normal noun in speech, so use 'AI' freely. But for everything else, "
                "spell it out the way a human would say it in conversation.\n"
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
            "- AVOID ACRONYMS. Write them out: 'United States' not 'US', 'United Kingdom' not "
            "'UK', 'chief executive' not 'CEO', 'large language models' not 'LLMs', "
            "'application programming interface' not 'API'. The exception is 'AI' — it has "
            "become a normal noun in speech, so use 'AI' freely. But for everything else, "
            "spell it out the way a human would say it in conversation.\n"
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

    print(f"Generating {'Spanish' if language == 'es' else 'podcast'} narration...")
    try:
        return _call_llm(None, prompt, temperature=0.4, max_tokens=8192)
    except RuntimeError as e:
        print(str(e))
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
    prompt = _load_tts_prompt(language=language, duo=False)
    try:
        return _call_llm(None, prompt + "\n" + narrative_text, temperature=0.1)
    except RuntimeError as e:
        print(f"TTS polish error: {e}")
        return narrative_text


def _polish_for_tts(narrative_text, language="en", duo=False):
    """Polish narration text for natural TTS reading using comprehensive rules."""
    # For bilingual EN:/ES: text, polish EN and ES lines separately
    if narrative_text.lstrip().startswith("EN:") or "\nEN:" in narrative_text:
        return _polish_bilingual_tts(narrative_text)

    prompt = _load_tts_prompt(language=language, duo=duo)
    print("Polishing narration for TTS...")
    try:
        return _call_llm(None, prompt + "\n" + narrative_text, temperature=0.1)
    except RuntimeError as e:
        print(f"TTS polish error: {e}")
        return narrative_text


_BRITISH_VOICES = [
    "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
    "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
]

_SPANISH_VOICES = ["ef_dora", "em_alex", "em_santa"]

# --- OmniVoice TTS (default engine; set TTS_ENGINE=kokoro to fall back) ---
# The worker runs under OmniVoice's own venv (heavy deps isolated from this one).
_OMNIVOICE_PY = os.environ.get(
    "OMNIVOICE_PY",
    str(Path.home() / "Dev" / "OmniVoice-Studio" / ".venv" / "bin" / "python"),
)
_OMNIVOICE_WORKER = str(Path(__file__).resolve().parent / "tts_omnivoice.py")
_OMNIVOICE_MODEL = os.environ.get("OMNIVOICE_MODEL", "k2-fsa/OmniVoice")
# Voice-design instructions. Accents are English-only in OmniVoice, so Spanish
# uses a plain female voice. _B variants give the second speaker in duo mode a
# distinct timbre. Voice-cloning via ref_audio is wired (see _OMNI_REF_AUDIO below).
_OMNI_SPEED = float(os.environ.get("OMNIVOICE_SPEED", "0.9"))

# Per-chunk trim + de-click settings for seamless concatenation.
_OMNI_TRIM_DB       = float(os.environ.get("OMNIVOICE_TRIM_DB", "-40"))    # silence threshold
_OMNI_TRIM_KEEP_MS  = int(os.environ.get("OMNIVOICE_TRIM_KEEP_MS", "30"))  # margin kept each side
_OMNI_TRIM_MAX_MS   = int(os.environ.get("OMNIVOICE_TRIM_MAX_MS", "300"))  # never trim more per side
_OMNI_FADE_MS       = int(os.environ.get("OMNIVOICE_FADE_MS", "8"))        # de-click fade in/out
_OMNI_INSTRUCT_EN = "female, british accent, young adult"
_OMNI_INSTRUCT_EN_B = "male, british accent, young adult"
_OMNI_INSTRUCT_ES = "female, young adult"
_OMNI_INSTRUCT_ES_B = "male, young adult"

# Locked podcast voice: when this reference clip exists, OmniVoice clones it
# (consistent timbre across episodes + both languages) instead of using instruct.
# Override/disable via OMNIVOICE_REF_AUDIO env ("" disables → instruct mode).
_OMNI_REF_DEFAULT = str(Path(__file__).resolve().parent / "voice_ref" / "senora_freedom_en_ref.wav")
_OMNI_REF_AUDIO = os.environ.get("OMNIVOICE_REF_AUDIO", _OMNI_REF_DEFAULT)
if _OMNI_REF_AUDIO and not Path(_OMNI_REF_AUDIO).exists():
    _OMNI_REF_AUDIO = ""  # fall back to instruct mode if the clip is missing
# Explicit transcript of the reference clip. REQUIRED for clean cloning: without
# it OmniVoice auto-transcribes + trims the clip, misaligning audio/text and
# echoing reference fragments (e.g. a stray "fresh") into every chunk.
_OMNI_REF_TEXT = ""
if _OMNI_REF_AUDIO:
    _ref_txt_path = Path(_OMNI_REF_AUDIO).with_suffix(".txt")
    if _ref_txt_path.exists():
        _OMNI_REF_TEXT = _ref_txt_path.read_text().strip()

_REF_CLIP_VALIDATED = False  # guard: validate once per process

# Strict mode: a clone reference that ends mid-speech or whose transcript doesn't
# match the audio is the documented root cause of per-chunk echo. When enabled,
# rendering with a known-defective reference STOPS the run rather than logging and
# proceeding — same fail-closed principle as the publish gate (P2.2).
#
# Defaults OFF: the shipped reference clip is *currently* defective (ends
# mid-speech, 0ms trailing silence) and re-cutting it is a human asset task (see
# voice_ref/ and the omnivoice spec Appendix D). Turning strict on before the
# re-cut would halt all production. Flip the default to "1" (or set
# OMNIVOICE_REF_STRICT=1) the moment a clean clip lands — the warning already
# prints loudly every run until then.
_OMNI_REF_STRICT = os.environ.get("OMNIVOICE_REF_STRICT", "0").lower() not in ("0", "false", "no")

# Substrings marking a ref-clip warning as FATAL (misalignment / echo conditions).
_FATAL_REF_MARKERS = (
    "ends mid-speech",
    "length mismatch",
    "ref_text missing",
    "is silent",
    "could not read",
)


def _blocking_ref_warnings(warns):
    """Return the subset of ref-clip warnings that should stop a strict render."""
    return [w for w in warns if any(m in w for m in _FATAL_REF_MARKERS)]


def _validate_ref_clip(path, ref_text, *, sr_expected=24000, min_trailing_ms=150):
    """Return a list of human-readable warnings ([] == clean) and path to cleaned clip."""
    import numpy as np
    import soundfile as sf
    warns = []
    try:
        wav, sr = sf.read(path)
    except Exception as e:
        return [f"could not read ref clip {path}: {e}"], None
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    if sr != sr_expected:
        warns.append(f"ref sample rate {sr} != expected {sr_expected}")
    amp = np.abs(wav)
    thr = 10.0 ** (-40.0 / 20.0)
    above = np.flatnonzero(amp > thr)
    if above.size == 0:
        return warns + ["ref clip is silent"], None
    trailing_ms = (wav.size - (above[-1] + 1)) / sr * 1000.0
    if trailing_ms < min_trailing_ms:
        warns.append(
            f"ref clip ends mid-speech ({trailing_ms:.0f}ms trailing silence; "
            f"need >= {min_trailing_ms}ms) -- RE-CUT the clip; this causes per-chunk echo")
    if not ref_text or len(ref_text.split()) < 3:
        warns.append("ref_text missing/too short -- required for clean cloning")
    else:
        dur = wav.size / sr
        wps = len(ref_text.split()) / dur if dur > 0 else 0.0
        if not (1.5 <= wps <= 5.0):
            warns.append(
                f"ref_text/clip length mismatch ({wps:.1f} words/sec) -- "
                f"verify the transcript matches the audio exactly")

    # Produce a cleaned copy with trimmed edges
    clean_path = None
    keep = int(_OMNI_TRIM_KEEP_MS * sr / 1000)
    max_trim = int(_OMNI_TRIM_MAX_MS * sr / 1000)
    lead_sil = int(above[0])
    trail_sil = int(wav.size - (above[-1] + 1))
    trim_lead = min(max(0, lead_sil - keep), max_trim)
    trim_trail = min(max(0, trail_sil - keep), max_trim)
    if trim_lead > 0 or trim_trail > 0:
        cleaned = wav[trim_lead: wav.size - trim_trail]
        clean_path = str(Path(path).with_name(
            Path(path).stem + "_clean" + Path(path).suffix))
        sf.write(clean_path, cleaned, sr)
    return warns, clean_path


def _use_omnivoice() -> bool:
    """OmniVoice is the default engine; TTS_ENGINE=kokoro selects the legacy path."""
    return os.environ.get("TTS_ENGINE", "omnivoice").lower() != "kokoro"


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


def _chunk_text(text, max_chars=600):
    """Split text into sentence-grouped chunks of at most ~max_chars.

    Keeps each OmniVoice generate() call bounded (long single calls degrade the
    model's duration estimate) while preserving sentence boundaries for prosody.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks, cur = [], ""
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if cur and len(cur) + 1 + len(s) > max_chars:
            chunks.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        chunks.append(cur)
    return chunks


def _trim_segment_audio(wav, sr, *, thresh_db=-40.0, keep_ms=30,
                        max_trim_ms=300, fade_ms=8):
    """Trim leading/trailing near-silence (bounded) and apply de-click fades.

    wav: 1-D float array in [-1, 1]. Returns a (possibly shorter) 1-D array.
    Never trims more than max_trim_ms per side, so real soft onsets survive.
    """
    import numpy as np
    if wav.size == 0:
        return wav
    amp = np.abs(wav)
    thresh = 10.0 ** (thresh_db / 20.0)          # dBFS -> linear
    above = np.flatnonzero(amp > thresh)
    if above.size == 0:
        return wav[:0]                            # all silence -> drop

    keep = int(keep_ms * sr / 1000)
    max_trim = int(max_trim_ms * sr / 1000)

    lead_sil = int(above[0])
    trail_sil = int(wav.size - (above[-1] + 1))
    trim_lead = min(max(0, lead_sil - keep), max_trim)
    trim_trail = min(max(0, trail_sil - keep), max_trim)

    seg = wav[trim_lead: wav.size - trim_trail].copy()

    f = int(fade_ms * sr / 1000)
    if f > 0 and seg.size > 2 * f:
        ramp = np.linspace(0.0, 1.0, f, dtype=seg.dtype)
        seg[:f] *= ramp
        seg[-f:] *= ramp[::-1]
    return seg


# Literal pre-TTS fixups for the OmniVoice path (engine reads these better than
# the raw form). Grow empirically from verification listen-throughs.
def _load_risky_lexicon():
    """Load the lowercase risky-term → spoken-form map (shared with the
    pronunciation check) so detection and synthesis use the same source (P2.1)."""
    try:
        from checks.check_pronunciation import load_risky_lexicon
        return load_risky_lexicon()
    except Exception:
        return {}


# Curated lowercase technical terms → spoken forms. A cache IPA entry is not the
# same as a spoken-form substitution in the text sent to the TTS, so for these
# terms we substitute the spoken form directly — the proven tmux-incident fix,
# generalized to the whole risky lexicon (P2.1).
_OMNI_TEXT_FIXUPS = sorted(
    _load_risky_lexicon().items(), key=lambda kv: len(kv[0]), reverse=True
) or [("tmux", "tee mux")]

# Adjacent-number separator: when a version number is followed immediately by a
# size/parameter count, insert a comma so the two numbers don't bind in TTS.
# e.g. "Gemma four twelve billion" -> "Gemma four, twelve billion"
# Negative cases that must NOT match: "two hundred thousand", "twenty twenty-six"
_NUM_WORD = (r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
             r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
             r"thirty|forty|fifty|sixty|seventy|eighty|ninety|\d+)"
             r"(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?")
_MAGNITUDE = r"(?:billion|million|thousand|trillion)"
_RE_ADJ_NUM = re.compile(
    rf"\b({_NUM_WORD})\s+({_NUM_WORD}\s+{_MAGNITUDE})\b", re.IGNORECASE)


def _omnivoice_fixups(text):
    for needle, repl in _OMNI_TEXT_FIXUPS:
        text = re.sub(rf'\b{re.escape(needle)}\b', repl, text, flags=re.IGNORECASE)
    # Separate a version number from an immediately-following size, so two
    # numbers don't bind ("Gemma four twelve billion" -> "Gemma four, twelve billion").
    text = _RE_ADJ_NUM.sub(r"\1, \2", text)
    return text


# Intro/outro assets — prepended/appended to every episode before mastering.
_INTRO_AUDIO = Path(__file__).resolve().parent / "assets" / "intro.mp3"
_OUTRO_AUDIO = Path(__file__).resolve().parent / "assets" / "outro.mp3"


def _splice_intro_outro(mp3_path: str | Path) -> bool:
    """Prepend intro.mp3 and append outro.mp3 to a podcast MP3. Returns True on success."""
    mp3_path = Path(mp3_path)
    if not _INTRO_AUDIO.exists() or not _OUTRO_AUDIO.exists():
        return False
    tmp = mp3_path.with_suffix(".stitched.mp3")
    # ffmpeg concat demuxer — re-encodes once for consistent format
    concat_list = tmp.with_suffix(".txt")
    concat_list.write_text(
        f"file '{_INTRO_AUDIO}'\nfile '{mp3_path}'\nfile '{_OUTRO_AUDIO}'\n"
    )
    r = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-codec:a", "libmp3lame", "-qscale:a", "2", str(tmp)],
        capture_output=True, text=True,
    )
    concat_list.unlink(missing_ok=True)
    if r.returncode != 0:
        print(f"  Intro/outro splice failed: {r.stderr[-200:]}")
        tmp.unlink(missing_ok=True)
        return False
    subprocess.run(["mv", str(tmp), str(mp3_path)], check=True)
    return True


def _omnivoice_render(segments, output_mp3_path, *, silence_sec=0.12):
    """Render pre-built segments via the OmniVoice worker subprocess → MP3.

    segments: list of {"text", "language" ("English"|"Spanish"), "instruct"?}.
    Loads the model once in the worker, concatenates the per-segment WAVs with a
    short gap, then reuses the same libmp3lame encode as the Kokoro path. Returns bool.
    """
    import tempfile
    import soundfile as sf
    import numpy as np

    segments = [s for s in segments if s.get("text", "").strip()]
    if not segments:
        print("  OmniVoice: no segments to render.")
        return False

    tmpdir = tempfile.mkdtemp(prefix="omnivoice_")
    try:
        job_segments = []
        for i, seg in enumerate(segments):
            entry = {
                "text": seg["text"],
                "language": seg["language"],
                "out_wav": os.path.join(tmpdir, f"seg{i:03d}.wav"),
            }
            if seg.get("instruct"):
                entry["instruct"] = seg["instruct"]
            job_segments.append(entry)

        # --- Validate reference clip (once per process) ---
        effective_ref_audio = _OMNI_REF_AUDIO
        global _REF_CLIP_VALIDATED
        if _OMNI_REF_AUDIO and not _REF_CLIP_VALIDATED:
            warns, clean_path = _validate_ref_clip(_OMNI_REF_AUDIO, _OMNI_REF_TEXT)
            for w in warns:
                print(f"  [ref] {w}")
            blocking = _blocking_ref_warnings(warns)
            if blocking and _OMNI_REF_STRICT:
                # Don't render every chunk against a misaligned clone reference.
                print("  OmniVoice: ABORTING — reference clip is defective "
                      f"({len(blocking)} blocking issue(s)). Re-cut the clip, or set "
                      "OMNIVOICE_REF_STRICT=0 to override (will echo). See voice_ref/.")
                return False
            _REF_CLIP_VALIDATED = True
            if clean_path:
                effective_ref_audio = clean_path

        job = {
            "model": _OMNIVOICE_MODEL,
            "instruct_en": _OMNI_INSTRUCT_EN,
            "instruct_es": _OMNI_INSTRUCT_ES,
            "speed": _OMNI_SPEED,
            "segments": job_segments,
        }
        if effective_ref_audio:
            # Voice-clone mode: locked timbre overrides instruct for all segments.
            job["ref_audio"] = effective_ref_audio
            if _OMNI_REF_TEXT:
                job["ref_text"] = _OMNI_REF_TEXT
        job_path = os.path.join(tmpdir, "job.json")
        with open(job_path, "w") as fh:
            json.dump(job, fh)

        print(f"  OmniVoice: rendering {len(job_segments)} segment(s)...")
        proc = subprocess.run(
            [_OMNIVOICE_PY, _OMNIVOICE_WORKER, job_path],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            print(f"  OmniVoice worker failed (rc={proc.returncode}): {proc.stderr.strip()[-500:]}")
            return False
        try:
            status = json.loads(proc.stdout.strip().splitlines()[-1])
        except Exception as e:
            print(f"  OmniVoice: unparseable worker output: {e}\n{proc.stdout[-300:]}")
            return False
        if not status.get("ok"):
            print(f"  OmniVoice worker error: {status.get('error')}")
            return False

        sr = status.get("sample_rate", 24000)
        silence = np.zeros(int(silence_sec * sr))
        parts = []
        multi = len(job_segments) > 1
        for seg in job_segments:
            wav, _ = sf.read(seg["out_wav"])
            if wav.ndim > 1:
                wav = wav.mean(axis=1)
            wav = _trim_segment_audio(
                wav, sr,
                thresh_db=_OMNI_TRIM_DB, keep_ms=_OMNI_TRIM_KEEP_MS,
                max_trim_ms=_OMNI_TRIM_MAX_MS, fade_ms=_OMNI_FADE_MS,
            )
            if wav.size == 0:
                continue
            parts.append(wav)
            if multi:
                parts.append(silence)
        if parts and multi and len(parts) > 1:
            parts = parts[:-1]   # drop trailing silence after last segment
        full = np.concatenate(parts) if parts else np.zeros(0)
        duration = len(full) / sr

        wav_path = str(output_mp3_path).rsplit(".", 1)[0] + ".tmp.wav"
        sf.write(wav_path, full, sr)
        cmd = ["ffmpeg", "-y", "-i", wav_path,
               "-codec:a", "libmp3lame", "-qscale:a", "2", str(output_mp3_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        Path(wav_path).unlink(missing_ok=True)
        if result.returncode != 0:
            print(f"  ffmpeg error: {result.stderr.strip()}")
            return False

        size_mb = Path(output_mp3_path).stat().st_size / (1024 * 1024)
        print(f"  OmniVoice MP3 saved: {output_mp3_path} ({size_mb:.1f}MB, {duration/60:.1f}min)")
        return True
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _generate_omnivoice_audio(narrative_text, output_mp3_path, lang="en", mode="solo"):
    """OmniVoice replacement for the Kokoro generators (solo/duo/bilingual)."""
    lang_name = "Spanish" if lang == "es" else "English"

    if mode == "bilingual":
        segs = []
        for line in narrative_text.strip().splitlines():
            line = line.strip()
            if line.startswith("ES:"):
                for ch in _chunk_text(line[3:].strip()):
                    segs.append({"text": ch, "language": "Spanish"})
            elif line.startswith("EN:"):
                for ch in _chunk_text(_omnivoice_fixups(line[3:].strip())):
                    segs.append({"text": ch, "language": "English"})
        if not segs:
            print("  No ES:/EN: lines found in bilingual text.")
            return False
        return _omnivoice_render(segs, output_mp3_path)

    if mode == "duo":
        parsed = _parse_dialogue(narrative_text)
        if len(parsed) < 3:
            return _generate_omnivoice_audio(narrative_text, output_mp3_path, lang=lang, mode="solo")
        seen = []
        for spk, _ in parsed:
            if spk not in seen:
                seen.append(spk)
        speaker_a = seen[0]
        instruct_a = _OMNI_INSTRUCT_ES if lang == "es" else _OMNI_INSTRUCT_EN
        instruct_b = _OMNI_INSTRUCT_ES_B if lang == "es" else _OMNI_INSTRUCT_EN_B
        segs = []
        for spk, text in parsed:
            if lang != "es":
                text = _omnivoice_fixups(text)
            instruct = instruct_a if spk == speaker_a else instruct_b
            for ch in _chunk_text(text):
                segs.append({"text": ch, "language": lang_name, "instruct": instruct})
        print(f"  OmniVoice duo: {len(parsed)} turns, speaker_a={speaker_a}")
        return _omnivoice_render(segs, output_mp3_path)

    # solo
    text = narrative_text if lang == "es" else _omnivoice_fixups(narrative_text)
    segs = [{"text": ch, "language": lang_name} for ch in _chunk_text(text)]
    return _omnivoice_render(segs, output_mp3_path)


def _generate_duo_audio(narrative_text, output_mp3_path, lang="en"):
    """Generate two-speaker podcast audio with distinct voices per speaker."""
    if _use_omnivoice():
        return _generate_omnivoice_audio(narrative_text, output_mp3_path, lang=lang, mode="duo")

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
    if _use_omnivoice():
        return _generate_omnivoice_audio(narrative_text, output_mp3_path, mode="bilingual")

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
    if _use_omnivoice():
        return _generate_omnivoice_audio(narrative_text, output_mp3_path, lang=lang, mode="solo")

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

# Queue of episodes that a fail-closed gate (similarity / sponsorship) skipped in
# non-interactive runs, so a human can review them later (P0.3).
_SKIPPED_QUEUE = _PODCAST_REPO / "skipped-pending-review.json"

# Allowlist consulted by the publish gate: {slug: reason}. Episodes here are
# published even without a passing quality report (e.g. legacy/grandfathered
# episodes, or a deliberate manual override) (P0.2).
_PUBLISH_OVERRIDES = _PODCAST_REPO / "publish_overrides.json"


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

    try:
        text = _call_llm(None, prompt, temperature=0.1, hard_timeout=60, attempts=3)
    except RuntimeError:
        return None
    score_match = re.search(r"SCORE:\s*(\d+)", text)
    reason_match = re.search(r"REASON:\s*(.+)", text)
    if score_match:
        return int(score_match.group(1)), (reason_match.group(1).strip() if reason_match else "")
    return None


# ---------------------------------------------------------------------------
# Title-clarity gate — is the title self-explanatory to a fresh-context reader?
#
# A title is "good" only if a reader given nothing but the title can infer the
# subject. Each round asks GLM (glm-5.2 via _call_llm), given ONLY the title,
# what it thinks the episode is about; a second call judges whether that guess
# matches the real description; if not, a third call rewrites the title toward
# the real topic and we re-test. Caps at max_rounds and returns the best title.
# Mirrors the _run_qa_revision_loop idiom (check → revise → cap).
# ---------------------------------------------------------------------------

_TITLE_GUESS_SYS = (
    "You are given only the TITLE of a podcast episode and nothing else. Based on "
    "the title alone, state in one or two sentences what you believe the episode is "
    "about. Be concrete about the subject. Do not hedge and do not say you are guessing."
)

_TITLE_JUDGE_SYS = (
    "You decide whether a listener's inferred topic for a podcast episode matches "
    "what the episode is actually about. You are given the listener's GUESS and the "
    "episode's actual DESCRIPTION. On the first line reply with exactly one word — "
    "MATCH or NO_MATCH — where MATCH means the guess captures the same core subject "
    "as the description (a close approximation counts; only answer NO_MATCH if the "
    "guess is about a clearly different topic). You may add a one-sentence reason on "
    "the next line."
)

_TITLE_REVISE_SYS = (
    "Rewrite a podcast episode TITLE so a brand-new listener can infer the episode's "
    "actual topic from the title alone. Keep it punchy and attention-grabbing, at most "
    "about 80 characters, plain prose (no surrounding quotation marks, no clickbait, "
    "no trailing flourish). Return ONLY the new title on a single line, with no preamble."
)


def _ensure_title_clarity(title, description, *, max_rounds=3):
    """Revise ``title`` until a fresh-context GLM guess of the topic aligns with
    ``description``.

    Each round: (1) ask GLM, given ONLY the title, what the episode is about — the
    description never enters that call, so the guess is genuinely fresh-context;
    (2) judge whether the guess matches the description; (3) if not, rewrite the
    title toward the real topic and repeat. Caps at ``max_rounds`` and returns the
    best title found. Never raises — on GLM unavailability it returns the current
    title (graceful degradation, consistent with the polish/TTS call sites).
    """
    title = (title or "").strip()
    if not title:
        return title
    desc_preview = (description or "")[:1500]
    for attempt in range(max_rounds):
        try:
            guess = _call_llm(_TITLE_GUESS_SYS, title,
                              temperature=0.2, max_tokens=120, hard_timeout=60, attempts=3)
            verdict = _call_llm(_TITLE_JUDGE_SYS,
                                f"GUESS:\n{guess}\n\nDESCRIPTION:\n{desc_preview}",
                                temperature=0.1, max_tokens=60, hard_timeout=60, attempts=3)
        except RuntimeError as e:
            print(f"  Title-clarity check unavailable ({e}); keeping current title")
            return title

        first_line = next((ln for ln in verdict.splitlines() if ln.strip()), "").strip().upper()
        if first_line.startswith("MATCH"):
            print(f"  Title clarity OK (round {attempt + 1}/{max_rounds}): {title}")
            return title
        if attempt >= max_rounds - 1:
            break  # final round failed; stop before a pointless revise

        try:
            revised = _call_llm(_TITLE_REVISE_SYS,
                                f"CURRENT TITLE:\n{title}\n\nDESCRIPTION (the real topic):\n{desc_preview}",
                                temperature=0.4, max_tokens=80, hard_timeout=60, attempts=3)
        except RuntimeError as e:
            print(f"  Title revision unavailable ({e}); keeping current title")
            return title
        revised = next((ln for ln in revised.splitlines() if ln.strip()), "").strip().strip("\"'").strip()
        if not revised or revised == title:
            break  # no progress — avoid a pointless loop
        print(f"  Title unclear (round {attempt + 1}/{max_rounds}); revising: {title!r} -> {revised!r}")
        title = revised

    print(f"  Title clarity not confirmed after {max_rounds} rounds; using best title: {title}")
    return title


def _next_episode_number(podcast_dir=None, episodes_json=None):
    """Find the next episode number from the union of the local audio dir and the
    published registry (episodes.json).

    Scanning only the local dir let two different episodes ship as the same epNN
    when the local dir was out of sync with the feed (the documented ep122
    collision). Consult both so the next number is past everything we've ever
    published (P1.4).
    """
    if podcast_dir is None:
        podcast_dir = _AUDIO_DIR
    if episodes_json is None:
        episodes_json = _EPISODES_JSON
    highest = 0
    for f in Path(podcast_dir).glob("ep*.podcast.mp3"):
        m = re.match(r"ep(\d+)", f.name)
        if m:
            highest = max(highest, int(m.group(1)))
    try:
        episodes_json = Path(episodes_json)
        if episodes_json.exists():
            for slug in json.loads(episodes_json.read_text(encoding="utf-8")):
                m = re.match(r"ep(\d+)", str(slug))
                if m:
                    highest = max(highest, int(m.group(1)))
    except (OSError, json.JSONDecodeError):
        pass  # registry unreadable — fall back to local-dir scan only
    return highest + 1


def _record_episode_lufs(slug, lufs, episodes_json=None):
    """Persist an episode's measured integrated LUFS into episodes.json (P4.4).

    No-op when there's no measurement. Best-effort: a missing/corrupt registry is
    left untouched rather than raising.
    """
    if lufs is None:
        return
    path = Path(episodes_json) if episodes_json else _EPISODES_JSON
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    data.setdefault(slug, {})["lufs"] = round(float(lufs), 1)
    try:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        print(f"  Could not record LUFS in {path.name}: {e}")


def _episode_blurb(summary_text, limit=280):
    """First blurb-length excerpt of a research summary, for the RSS description
    when no curated description has been written yet."""
    text = re.sub(r"\s+", " ", summary_text or "").strip()
    if len(text) <= limit:
        return text
    snippet = text[:limit]
    for sep in (". ", "? ", "! "):
        cut = snippet.rfind(sep)
        if cut > limit // 2:
            return snippet[:cut + 1].strip()
    return snippet.rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _register_episode_metadata(slug, title, description, guid, episodes_json=None):
    """Record an episode's title/description/guid in episodes.json so it never
    ships under the slug-derived fallback title.

    Uses ``setdefault`` so a curated value (written by the publishing step) is
    never overwritten — this only fills in fields that are missing. Best-effort:
    a missing/corrupt registry is left untouched rather than raising. This is
    the fix for episodes (e.g. ep142/ep143) that shipped with only a ``lufs``
    entry because the separate registration step was skipped.
    """
    if not title:
        return
    path = Path(episodes_json) if episodes_json else _EPISODES_JSON
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    entry = data.setdefault(slug, {})
    entry.setdefault("title", title)
    if description:
        entry.setdefault("description", description)
    if guid:
        entry.setdefault("guid", guid)
    try:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        print(f"  Could not register episode metadata in {path.name}: {e}")


# ---------------------------------------------------------------------------
# Evidence-first pipeline
# ---------------------------------------------------------------------------

class PipelineStageError(Exception):
    """Raised when an evidence-first pipeline stage fails."""
    def __init__(self, stage, message, artifact_path=None):
        self.stage = stage
        self.artifact_path = artifact_path
        super().__init__(f"{stage}: {message}")


def _run_evidence_pipeline(summary_text, clean_name, podcast_path,
                           video_title="", extra_prompt="", target_words=700, duo=False):
    """Run the evidence-first pipeline: evidence → outline → script → QA → audio.

    Returns (en_txt_path, en_mp3_path) on success.
    Raises PipelineStageError on stage failure.
    """
    import json as _json

    artifacts_dir = podcast_path / clean_name
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Load the persona once, unconditionally. On the resume path (outline and
    # script artifacts already exist) this used to stay unbound, so QA revisions
    # re-drafted without SOUL.md and lost the persona (P1.3).
    soul_path = Path(__file__).parent / "SOUL.md"
    soul_text = soul_path.read_text(encoding="utf-8") if soul_path.exists() else ""

    # Stage 1: Evidence extraction
    print("  Stage 1: Extracting evidence...")
    evidence_path = artifacts_dir / "evidence_map.json"
    if evidence_path.exists():
        print(f"    Evidence map exists: {evidence_path.name}")
        evidence = _json.loads(evidence_path.read_text(encoding="utf-8"))
    else:
        from pipeline_stages import extract_evidence
        evidence = extract_evidence(summary_text)
        evidence_path.write_text(_json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"    Extracted {len(evidence)} evidence entries → {evidence_path.name}")

    if not evidence:
        raise PipelineStageError("evidence_extraction",
            "no evidence extracted from source material", str(evidence_path))

    # Stage 2: Outline generation
    print("  Stage 2: Generating outline...")
    outline_path = artifacts_dir / "outline.json"
    if outline_path.exists():
        print(f"    Outline exists: {outline_path.name}")
        outline = _json.loads(outline_path.read_text(encoding="utf-8"))
    else:
        from pipeline_stages import generate_outline
        outline = generate_outline(evidence, soul_text)
        outline_path.write_text(_json.dumps(outline, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"    Outline generated → {outline_path.name}")

    # Stage 3: Script drafting
    print("  Stage 3: Drafting script...")
    en_txt = podcast_path / f"{clean_name}.podcast.txt"
    en_mp3 = podcast_path / f"{clean_name}.podcast.mp3"

    if en_txt.exists():
        print(f"    Script exists: {en_txt.name}")
        en_narrative = en_txt.read_text(encoding="utf-8")
    else:
        from pipeline_stages import draft_script
        en_narrative = draft_script(
            outline, evidence, soul_text,
            video_title=video_title, extra_prompt=extra_prompt,
            target_words=target_words, duo=duo,
        )
        if not en_narrative:
            raise PipelineStageError("script_draft",
                "script generation returned empty", str(outline_path))
        en_narrative = _polish_for_tts(en_narrative, language="en", duo=duo)
        en_txt.write_text(en_narrative, encoding="utf-8")
        print(f"    Script saved: {en_txt.name}")

    # Stage 4: Content QA (with revision loop). The loop may rewrite the script;
    # reassign en_narrative so the opening check (4b), verification (4c), and audio
    # (5) all run on the *revised* text rather than the stale original (P0.1).
    print("  Stage 4: Content QA...")
    en_narrative = _run_qa_revision_loop(en_narrative, en_txt, outline, evidence,
                                         soul_text, video_title, extra_prompt,
                                         target_words, duo, max_revisions=3)

    # Stage 4b: Opening sentence freshness check
    try:
        from checks.check_opening import run as check_opening, update_opening_log
        log_path = Path(__file__).parent / "checks" / "opening_log.json"
        opening_result = check_opening({"script_text": en_narrative}, log_path)
        if opening_result.passed:
            print(f"    Opening check: {opening_result.reason}")
        else:
            print(f"    ⚠️ Opening check: {opening_result.reason}")
            print(f"      (episode produced — consider revising the opening)")
    except ImportError:
        print("    Opening check not available, skipping.")

    # Stage 4c: Independent verification against evidence (Phase 8)
    _run_verification_stage(en_narrative, evidence, en_txt)

    # Stage 5: Audio generation
    print("  Stage 5: Audio generation...")
    if not en_mp3.exists():
        _gen_fn = _generate_duo_audio if duo else _generate_podcast_audio
        if not _gen_fn(en_narrative, en_mp3, lang="en"):
            raise PipelineStageError("audio_generation",
                "Kokoro synthesis failed", str(en_txt))

    # Intro/outro and mastering are handled by the caller (produce_podcast)
    # to avoid double-splicing. Do NOT splice here.

    print(f"  Evidence-first pipeline complete: {en_mp3.name}")

    # Update opening log with this episode's first sentence
    try:
        from checks.check_opening import _extract_first_sentence, update_opening_log
        log_path = Path(__file__).parent / "checks" / "opening_log.json"
        opening = _extract_first_sentence(en_narrative)
        if opening:
            update_opening_log(log_path, clean_name, opening)
    except Exception:
        pass  # non-critical

    return en_txt, en_mp3


def _run_verification_stage(script_text: str, evidence: list[dict],
                            script_path=None) -> dict | None:
    """Phase 8: Run independent verification of the script against the evidence map.

    Uses a different model than the drafter to decorrelate errors. Best-effort:
    if the verifier is unavailable the stage is skipped with a warning and the
    episode still produces. When a verification report is produced it is written
    to ``<script>.verification_report.json`` alongside the script.

    Returns the verification result dict (see ``verify_script``), or None when
    the stage was skipped.
    """
    import json as _json
    try:
        from pipeline_stages import verify_script
    except ImportError:
        print("    Verification: pipeline_stages not available, skipping.")
        return None

    if not evidence:
        print("    Verification: no evidence map, skipping.")
        return None

    try:
        result = verify_script(script_text, evidence)
    except RuntimeError as e:
        print(f"    Verification: skipped ({e})")
        return None
    except ValueError as e:
        # Unparseable report is an error, not a pass — write a failing report so
        # the publish gate treats it as "verification not performed" (P1.2).
        print(f"    Verification: unparseable report (recorded as error) ({e})")
        result = {
            "claims": [], "high_confidence": 0, "threshold": 3,
            "passed": False, "status": "error", "error": str(e),
        }

    # A verifier that returned prose instead of a verdict did not actually run.
    # Surface it distinctly and let the failing report block at publish (P1.2).
    if result.get("status") == "error":
        print(f"    ⚠️ Verification ERROR: {result.get('error', 'no verdict returned')}")
        print("      (recorded as not-performed — will be held back at publish)")
        if script_path is not None:
            try:
                report_path = Path(script_path).with_suffix(".verification_report.json")
                report_path.write_text(
                    _json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"    Verification report: {report_path.name}")
            except OSError as e:
                print(f"    Verification report not written: {e}")
        return result

    claims = result["claims"]
    high = result["high_confidence"]
    threshold = result["threshold"]

    for c in claims:
        conf = c.get("confidence", "?")
        ctype = c.get("type", "?")
        claim_text = c.get("claim", "")[:60]
        print(f"    ⚠️ Untraceable ({conf}/{ctype}): {claim_text}")

    if not claims:
        print("    Verification: all claims traceable ✓")
    elif result["passed"]:
        print(f"    Verification passed: {high} high-confidence "
              f"untraceable claims (within threshold of {threshold})")
    else:
        print(f"    Verification FAILED: {high} high-confidence "
              f"untraceable claims (threshold: {threshold}) "
              f"— verification_failed: {high} untraceable claims")

    # Persist the report next to the script for later inspection / QA.
    if script_path is not None:
        try:
            report_path = Path(script_path).with_suffix(".verification_report.json")
            report_path.write_text(
                _json.dumps(result, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"    Verification report: {report_path.name}")
        except OSError as e:
            print(f"    Verification report not written: {e}")

    return result


def _check_opening_freshness(script_text):
    """Return a reason string if the opening is too similar to recent episodes,
    else None. Best-effort — never raises (P4.2)."""
    try:
        from checks.check_opening import run as check_opening
        log_path = Path(__file__).parent / "checks" / "opening_log.json"
        result = check_opening({"script_text": script_text}, log_path)
        return None if result.passed else result.reason
    except Exception:
        return None


def _run_qa_revision_loop(script_text, script_path, outline, evidence,
                          soul_text, video_title, extra_prompt, target_words, duo,
                          max_revisions=3):
    """Run content QA and revise script up to max_revisions times.

    Revision is triggered by a failing quality gate OR a stale opening (P4.2) —
    the opening check is no longer a post-hoc shrug; it forces a re-draft, and
    draft_script already injects the avoidance instruction.

    Returns the final script text — the last accepted revision if the loop
    revised, otherwise the original. Callers MUST use the return value so the
    revised draft reaches verification, the opening check, and audio (P0.1).
    """
    try:
        from checks.quality_gate import run_quality_gate
    except ImportError:
        print("    Quality gate not available, skipping QA loop.")
        return script_text

    for attempt in range(max_revisions):
        report = run_quality_gate(script_text)
        opening_issue = _check_opening_freshness(script_text)
        if report.passed and not opening_issue:
            print(f"    QA passed on attempt {attempt + 1}")
            return script_text
        issues = list(report.blocking_failures)
        if opening_issue:
            issues.append(f"stale opening: {opening_issue}")
        status = "QA failed" if not report.passed else "opening not fresh"
        print(f"    {status} (attempt {attempt + 1}/{max_revisions}):")
        for f in issues[:3]:
            print(f"      - {f}")

        if attempt < max_revisions - 1:
            print("    Revising script...")
            from pipeline_stages import draft_script
            qa_feedback = "Previous draft failed QA: " + "; ".join(issues)
            revised = draft_script(
                outline, evidence, soul_text,
                video_title=video_title,
                extra_prompt=f"{extra_prompt}\n{qa_feedback}" if extra_prompt else qa_feedback,
                target_words=target_words, duo=duo,
            )
            if revised:
                revised = _polish_for_tts(revised, language="en", duo=duo)
                script_path.write_text(revised, encoding="utf-8")
                script_text = revised
                print(f"    Revised script saved")

    print(f"    QA exhausted after {max_revisions} revisions, proceeding with best draft")
    qa_report_path = script_path.parent / f"{script_path.stem}.quality_report.json"
    from checks.quality_gate import write_quality_report
    report.checks["qa_exhausted"] = True
    write_quality_report(report, qa_report_path)
    return script_text


def _run_quality_gate(episode_slug, script_path, audio_path, podcast_dir):
    """Run quality checks and write quality_report.json. Warns on failure."""
    try:
        from checks.quality_gate import run_quality_gate, write_quality_report
    except ImportError:
        print("  Quality gate not available (checks/ not found). Skipping.")
        return True

    script_text = Path(script_path).read_text(encoding="utf-8") if Path(script_path).exists() else ""
    report = run_quality_gate(script_text, audio_path)
    report_path = Path(podcast_dir) / f"{episode_slug}.quality_report.json"
    write_quality_report(report, report_path)

    if report.passed:
        print(f"  Quality gate PASSED — report: {report_path.name}")
    else:
        print(f"\n  ⚠️  Quality gate FAILED:")
        for failure in report.blocking_failures:
            print(f"    - {failure}")
        print(f"  Report: {report_path}")
        print("  (episode produced but review recommended before publish)\n")

    return report.passed


def _queue_skipped_episode(clean_name, video_title, gate, detail, queue_path=None):
    """Append a fail-closed gate skip to the review queue (P0.3).

    Production runs non-interactively (scheduled tasks), so a tripped similarity
    or sponsorship gate can't prompt a human. Instead of proceeding anyway we
    record the episode here for later review and move on to the next backlog item.
    """
    from datetime import datetime, timezone
    queue_path = Path(queue_path) if queue_path else _SKIPPED_QUEUE
    try:
        queue = json.loads(queue_path.read_text(encoding="utf-8")) if queue_path.exists() else []
    except (json.JSONDecodeError, OSError):
        queue = []
    if not isinstance(queue, list):
        queue = []
    queue.append({
        "clean_name": clean_name,
        "title": video_title,
        "gate": gate,
        "detail": detail,
        "skipped_at": datetime.now(tz=timezone.utc).isoformat(),
    })
    try:
        queue_path.write_text(json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        print(f"  Could not write review queue {queue_path.name}: {e}")
    return queue_path


def produce_podcast(summary_path, video_title="", podcast_dir=None,
                    extra_prompt="", video_duration_seconds=0, duo=False,
                    pipeline="summary", force=False):
    """Full podcast pipeline: summary → narrate → TTS → MP3 (English + Spanish).

    pipeline: "summary" (default) or "evidence" for the evidence-first path.
    force:    bypass the fail-closed similarity/sponsorship gates (manual override).
    """
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
        if force:
            print("  (--force — proceeding despite sponsorship gate)")
        elif sys.stdin.isatty():
            try:
                answer = input("  Proceed anyway? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "n"
            if answer not in ("y", "yes"):
                print("  Skipping podcast production.")
                return None
        else:
            # Fail closed: production is non-interactive, so don't ship a likely
            # ad. Queue it for review and move on to the next backlog item (P0.3).
            queue = _queue_skipped_episode(
                clean_name, video_title, "sponsorship",
                {"score": score, "reason": reason})
            print(f"  Non-interactive: skipped pending review → {queue.name}")
            return None

    # --- Similarity check ---
    sim_matches = _check_episode_similarity(summary_text, video_title or "")
    if sim_matches:
        _display_similarity_table(sim_matches)
        if force:
            print("  (--force — proceeding despite similarity gate)")
        elif sys.stdin.isatty():
            try:
                answer = input("\n  Episode may be a duplicate. Proceed anyway? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "n"
            if answer not in ("y", "yes"):
                print("  Skipping podcast production.")
                return None
        else:
            # Fail closed: likely duplicate and no human to confirm. Queue with the
            # match table so a reviewer can see exactly what it collided with (P0.3).
            queue = _queue_skipped_episode(
                clean_name, video_title, "similarity",
                {"matches": sim_matches})
            print(f"  Non-interactive: skipped pending review → {queue.name}")
            return None
    else:
        print("  Similarity check passed.")

    # --- Title-clarity gate (fresh-context: does the title alone convey the topic?) ---
    # Runs after the sponsor/similarity gates so we don't spend LLM calls on episodes
    # that'll be skipped; the (possibly revised) title then flows into narration and
    # re-derives the slug/filename.
    if os.environ.get("TITLE_CLARITY_CHECK", "1") != "0" and (video_title or "").strip():
        _tc_rounds = int(os.environ.get("TITLE_CLARITY_MAX_ROUNDS", "3"))
        clarified = _ensure_title_clarity(video_title, summary_text, max_rounds=_tc_rounds)
        if clarified and clarified != video_title:
            video_title = clarified
            slug = _slugify(video_title or summary_path.stem.replace(".summary", ""))
            clean_name = f"ep{ep_num:02d}-{slug}"
            print(f"  Title clarified → {clean_name}")

    # Resolve the audio generator once, before the pipeline branch. The evidence
    # path never set it, so a non-bilingual Spanish narration later raised
    # NameError after the (expensive) English production had already run (P1.1).
    _gen_fn = _generate_duo_audio if duo else _generate_podcast_audio

    # --- Evidence-first pipeline ---
    if pipeline == "evidence":
        print(f"\n  Using evidence-first pipeline for {clean_name}")
        try:
            en_txt, en_mp3 = _run_evidence_pipeline(
                summary_text, clean_name, podcast_path,
                video_title=video_title, extra_prompt=extra_prompt,
                target_words=target_words, duo=duo,
            )
        except PipelineStageError as e:
            print(f"\n  Pipeline failed at stage '{e.stage}': {e}")
            print(f"  Last artifact: {e.artifact_path or 'none'}")
            return None
    else:
        # --- Summary-first pipeline (existing) ---
        en_txt = podcast_path / f"{clean_name}.podcast.txt"
        en_mp3 = podcast_path / f"{clean_name}.podcast.mp3"

        if en_mp3.exists():
            print(f"English podcast already exists: {en_mp3}")
        else:
            if en_txt.exists():
                print(f"English narration exists, skipping narration generation")
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

            if not _gen_fn(en_narrative, en_mp3, lang="en"):
                return None

    # --- Spanish (optional; off by default — set PRODUCE_SPANISH=1 to re-enable) ---
    # es_mp3 is always defined so the mastering/intro-splice loops below can guard on exists().
    es_mp3 = podcast_path / f"{clean_name}.podcast.es.mp3"
    if os.environ.get("PRODUCE_SPANISH", "0") == "1":
        es_txt = podcast_path / f"{clean_name}.podcast.es.txt"

        if es_mp3.exists():
            print(f"Spanish podcast already exists: {es_mp3}")
        else:
            if es_txt.exists():
                print(f"Spanish narration exists, skipping narration generation")
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
    else:
        print("  Spanish track disabled (PRODUCE_SPANISH != 1); producing English-only.")

    # --- Splice intro/outro before mastering ---
    for mp3_path in [en_mp3, es_mp3]:
        if mp3_path.exists() and _splice_intro_outro(mp3_path):
            print(f"  Intro/outro added: {mp3_path.name}")

    # --- Master audio to broadcast loudness (-16 LUFS) ---
    en_lufs = None
    try:
        from checks.master_audio import master
        for mp3_path in [en_mp3, es_mp3]:
            if mp3_path.exists():
                result = master(str(mp3_path))
                if mp3_path == en_mp3:
                    en_lufs = result.get("integrated_lufs")
                if result.get("normalised"):
                    print(f"  Mastered: {mp3_path.name} ({result.get('integrated_lufs')} LUFS)")
                else:
                    print(f"  Audio already in range: {mp3_path.name}")
    except ImportError:
        print("  Audio mastering not available (checks/master_audio.py not found).")
    except Exception as e:
        print(f"  Audio mastering failed: {e}")

    # Persist the measured loudness so the feed work can expose it (P4.4).
    _record_episode_lufs(clean_name, en_lufs)

    # Register title/description/guid so the episode never ships under the
    # slug-derived fallback title (fix for ep142/ep143 shipping lufs-only).
    # setdefault preserves any curated value the publishing step already wrote.
    _register_episode_metadata(
        clean_name, video_title, _episode_blurb(summary_text), f"freeist:{clean_name}")

    # --- Quality gate ---
    _run_quality_gate(clean_name, en_txt, en_mp3, podcast_path)

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


def _run_publish_gate(audio_dir=None, overrides_path=None):
    """Evaluate every produced episode and report which may be published (P0.2).

    Returns the :class:`PublishGateResult`. Episodes without a passing quality
    report (and not allowlisted) are printed as a ``needs-review`` list and their
    slugs returned in ``blocked_slugs`` so the feed can exclude them.
    """
    audio_dir = Path(audio_dir) if audio_dir else _AUDIO_DIR
    overrides_path = overrides_path or _PUBLISH_OVERRIDES
    try:
        from checks.publish_gate import run_publish_gate
    except ImportError:
        print("  Publish gate not available (checks/ not found). Publishing all.")
        return None

    gate = run_publish_gate(audio_dir, overrides_path=overrides_path)
    overrides_count = sum(1 for v in gate.publishable if v.overridden)
    print(f"  Publish gate: {len(gate.publishable)} publishable "
          f"({overrides_count} allowlisted), {len(gate.needs_review)} need review.")
    for v in gate.needs_review:
        print(f"    ✗ {v.slug}: {v.reason}")
    return gate


def _verify_feed_landed(local_feed=None):
    """Confirm the remote rss/feed.xml matches the local copy after an API-fallback
    publish (the git reset trusts the uploads landed but never re-checks) (P4.3).

    Returns True on match, False otherwise (and logs). Best-effort.
    """
    import base64
    local = Path(local_feed) if local_feed else (_PUBLISH_REPO / "rss" / "feed.xml")
    if not local.exists():
        print("  Feed verification: no local feed.xml to compare.")
        return False
    r = subprocess.run(
        ["gh", "api", "repos/mrleepee/freeist-podcast/contents/rss/feed.xml", "--jq", ".content"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"  ⚠️ Feed verification: could not fetch remote feed.xml "
              f"({r.stderr.strip()[:120]})")
        return False
    try:
        remote_bytes = base64.b64decode(r.stdout.strip())
    except (ValueError, TypeError):
        print("  ⚠️ Feed verification: unreadable remote content.")
        return False
    if remote_bytes == local.read_bytes():
        print("  Feed verified: remote rss/feed.xml matches local.")
        return True
    print("  ⚠️ Feed verification FAILED: remote rss/feed.xml differs from local — "
          "the push may not have landed. Re-run publish_feed().")
    return False


def publish_feed():
    """Regenerate RSS feed and push to GitHub."""
    print("\nPublishing to feed...")

    # Publish gate: nothing ships unless it earned it (P0.2). Failing episodes are
    # excluded from the feed and not uploaded; the rest publish as usual.
    gate = _run_publish_gate()
    excluded = list(gate.blocked_slugs) if gate else []

    generate_rss = _PODCAST_REPO / "generate_rss.py"
    rss_cmd = [
        sys.executable, str(generate_rss),
        "--base-url", "https://mrleepee.github.io/freeist-podcast/audio/",
        "--title", "Señora Freedom",
        "--output", str(_RSS_OUTPUT),
    ]
    if excluded:
        rss_cmd += ["--exclude", *excluded]
    result = subprocess.run(rss_cmd, capture_output=True, text=True)
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
            if f.name[: -len(".podcast.mp3")] in excluded:
                continue  # publish gate blocked this episode — don't upload it
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
        # The reset trusts that the API uploads landed — verify the remote feed
        # actually matches what we generated (P4.3).
        _verify_feed_landed()
    else:
        print("Feed pushed to GitHub.")

    if gate and gate.needs_review:
        print(f"\n  ⚠️  {len(gate.needs_review)} episode(s) held back, needs-review:")
        for v in gate.needs_review:
            print(f"    - {v.slug}: {v.reason}")
        print(f"  Allowlist in {_PUBLISH_OVERRIDES.name} to publish anyway.")
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

    # 3. Summarize with GLM
    summary = _summarize_with_llm(transcript, video_title=video_title)
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
                                    duo=args.duo, force=args.force)
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
                                duo=args.duo, force=args.force)


if __name__ == "__main__":
    main()
