"""Input URL normalization and optional share-page extraction."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from .core import InvalidStreamUrl, SUPPORTED_SCHEMES


@dataclass(frozen=True)
class ResolvedStream:
    input_url: str
    media_url: str
    source_kind: str  # direct or share_page
    title: str = ""


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


def resolve_stream_url(value: str, *, timeout: float = 20.0) -> ResolvedStream:
    """Resolve direct media or a supported public share page via optional yt-dlp.

    This does not bypass authentication, cookies, geo restrictions, or access controls.
    """
    normalized = normalize_input_url(value)
    kind = classify_input_url(normalized)
    if kind == "direct":
        return ResolvedStream(normalized, normalized, kind)
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("TikTok share links require the optional yt-dlp package.") from exc

    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": timeout,
        "extract_flat": False,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(normalized, download=False)
    except Exception as exc:
        raise RuntimeError(f"Share-link extraction failed: {type(exc).__name__}: {exc}") from exc
    media_url = info.get("url")
    if not media_url and info.get("formats"):
        candidates = [item for item in info["formats"] if item.get("url")]
        candidates.sort(key=lambda item: (item.get("height") or 0, item.get("tbr") or 0), reverse=True)
        media_url = candidates[0]["url"] if candidates else None
    if not media_url:
        raise RuntimeError("The share page did not expose a playable media URL.")
    return ResolvedStream(normalized, media_url, kind, str(info.get("title") or ""))
