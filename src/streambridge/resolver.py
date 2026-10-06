"""Input URL normalization and resilient TikTok share-page extraction."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from .core import InvalidStreamUrl, SUPPORTED_SCHEMES

DEFAULT_TIMEOUT = 30.0
MOBILE_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
)


@dataclass(frozen=True)
class ResolvedStream:
    input_url: str
    media_url: str
    source_kind: str  # direct or share_page
    title: str = ""
    resolved_page_url: str = ""


def normalize_input_url(value: str) -> str:
    """Normalize an unambiguous host-only/share URL without changing direct URLs."""
    raw = (value or "").strip()
    if not raw:
        raise InvalidStreamUrl("Enter a stream or TikTok share URL.")
    if raw.startswith("//"):
        raw = "https:" + raw
    elif "://" not in raw and (raw.startswith("www.") or "." in raw.split("/", 1)[0]):
        raw = "https://" + raw
    return raw


def classify_input_url(value: str) -> str:
    normalized = normalize_input_url(value)
    parsed = urlsplit(normalized)
    if parsed.scheme.lower() not in SUPPORTED_SCHEMES or not parsed.hostname:
        raise InvalidStreamUrl("Use a complete http(s):// or rtsp(s):// URL.")
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    if host in {"vt.tiktok.com", "vm.tiktok.com", "tiktok.com", "www.tiktok.com", "m.tiktok.com"}:
        return "share_page"
    if host.endswith("tiktok.com") and ("/live" in path or "/@" in path):
        return "share_page"
    return "direct"


def _resolve_redirect_url(url: str, timeout: float) -> str:
    """Follow TikTok short-link redirects before invoking the extractor."""
    request = Request(
        url,
        headers={
            "User-Agent": MOBILE_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
        },
    )
    try:
        with build_opener().open(request, timeout=timeout) as response:
            return response.geturl() or url
    except (HTTPError, URLError, TimeoutError, OSError):
        # yt-dlp can sometimes resolve a link that rejects a preliminary HTTP request.
        return url


def _build_yt_dlp_options(timeout: float) -> dict:
    timeout = max(DEFAULT_TIMEOUT, float(timeout))
    return {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": timeout,
        "extractor_retries": 2,
        "retries": 2,
        "fragment_retries": 2,
        "extract_flat": False,
        "http_headers": {
            "User-Agent": MOBILE_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.tiktok.com/",
        },
    }


def resolve_stream_url(value: str, *, timeout: float = DEFAULT_TIMEOUT) -> ResolvedStream:
    """Resolve direct media or a public share page without blocking the Tk thread."""
    normalized = normalize_input_url(value)
    kind = classify_input_url(normalized)
    if kind == "direct":
        return ResolvedStream(normalized, normalized, kind, resolved_page_url=normalized)
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("TikTok share links require the optional yt-dlp package.") from exc

    page_url = _resolve_redirect_url(normalized, max(DEFAULT_TIMEOUT, float(timeout)))
    options = _build_yt_dlp_options(max(DEFAULT_TIMEOUT, float(timeout)))
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(page_url, download=False)
    except Exception as exc:
        raise RuntimeError(f"Share-link extraction failed: {type(exc).__name__}: {exc}") from exc
    media_url = info.get("url")
    if not media_url and info.get("formats"):
        candidates = [item for item in info["formats"] if item.get("url")]
        candidates.sort(key=lambda item: (item.get("height") or 0, item.get("tbr") or 0), reverse=True)
        media_url = candidates[0]["url"] if candidates else None
    if not media_url:
        raise RuntimeError("The share page did not expose a playable media URL.")
    return ResolvedStream(normalized, media_url, kind, str(info.get("title") or ""), page_url)
