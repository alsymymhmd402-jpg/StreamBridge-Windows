"""Local HTTP HLS proxy shared by preview and UnityCapture pipelines."""
from __future__ import annotations

import http.server
import threading
import time
from http import HTTPStatus
from urllib.parse import parse_qs, quote, unquote, urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener
from http.cookiejar import CookieJar

from .resolver import MOBILE_USER_AGENT


class LocalHlsRelay:
    """Proxy a remote HLS playlist and its segments through localhost."""

    def __init__(self, source_url: str):
        self.source_url = source_url
        self.server: http.server.ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.port: int | None = None
        self.session = build_opener(HTTPCookieProcessor(CookieJar()))
        self._lock = threading.RLock()

    @property
    def url(self) -> str:
        if not self.port:
            raise RuntimeError("HLS relay is not running")
        return f"http://127.0.0.1:{self.port}/stream.m3u8"

    def is_running(self) -> bool:
        return self.server is not None and self.thread is not None and self.thread.is_alive()

    def _fetch(self, url: str) -> tuple[bytes, str, str]:
        req = Request(url, headers={
            "User-Agent": MOBILE_USER_AGENT,
            "Referer": "https://www.tiktok.com/",
            "Accept": "application/vnd.apple.mpegurl,application/x-mpegURL,*/*",
            "Accept-Language": "en-US,en;q=0.9",
        })
        with self.session.open(req, timeout=30) as response:
            return response.read(), response.headers.get("Content-Type", "application/octet-stream"), response.geturl()

    def _playlist(self) -> bytes:
        body, _content_type, final_url = self._fetch(self.source_url)
        text = body.decode("utf-8", errors="replace")
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                absolute = urljoin(final_url, stripped)
                line = f"/segment?url={quote(absolute, safe='')}"
            elif "URI=" in line:
                # HLS encryption/map URI attributes are proxied too.
                prefix, value = line.split("URI=", 1)
                end = value.find('"', 1)
                if value.startswith('"') and end > 0:
                    absolute = urljoin(final_url, value[1:end])
                    line = f'{prefix}URI="/segment?url={quote(absolute, safe="")}"{value[end+1:]}'
            lines.append(line)
        return ("\n".join(lines) + "\n").encode("utf-8")

    def start(self, timeout: float = 30.0) -> str:
        relay = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                try:
                    parsed = urlsplit(self.path)
                    if parsed.path == "/stream.m3u8":
                        body = relay._playlist()
                        content_type = "application/vnd.apple.mpegurl"
                    elif parsed.path == "/segment":
                        target = parse_qs(parsed.query).get("url", [""])[0]
                        if not target or urlsplit(target).scheme not in ("http", "https"):
                            self.send_error(HTTPStatus.BAD_REQUEST, "invalid segment URL")
                            return
                        body, content_type, _ = relay._fetch(target)
                    else:
                        self.send_error(HTTPStatus.NOT_FOUND)
                        return
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)
                except Exception as exc:
                    self.send_error(HTTPStatus.BAD_GATEWAY, str(exc)[:240])

            def log_message(self, *_args):
                return

        with self._lock:
            self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            self.server.daemon_threads = True
            self.port = int(self.server.server_address[1])
            self.thread = threading.Thread(target=self.server.serve_forever, name="LocalHlsHttp", daemon=True)
            self.thread.start()
        deadline = time.monotonic() + timeout
        last_error = None
        while time.monotonic() < deadline:
            try:
                body = self._playlist()
                if body.startswith(b"#EXTM3U"):
                    return self.url
            except Exception as exc:
                last_error = exc
            time.sleep(0.2)
        self.stop()
        raise TimeoutError(f"Local HLS relay did not return a playlist: {last_error}")

    def stop(self) -> None:
        with self._lock:
            server, thread = self.server, self.thread
            self.server = None
            self.thread = None
        if server:
            server.shutdown()
            server.server_close()
        if thread and thread.is_alive():
            thread.join(timeout=2)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_args):
        self.stop()
        return False
