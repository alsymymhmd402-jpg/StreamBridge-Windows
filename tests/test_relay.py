import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

from streambridge.relay import LocalHlsRelay


class RelayHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/source.m3u8":
            body = b"#EXTM3U\n#EXTINF:1,\nsegment.ts\n"
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.apple.mpegurl")
        elif self.path == "/segment.ts":
            body = b"FAKE-TS-DATA"
            self.send_response(200)
            self.send_header("Content-Type", "video/mp2t")
        else:
            self.send_error(404)
            return
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


class RelayTests(unittest.TestCase):
    def test_local_relay_rewrites_playlist_and_proxies_segment(self):
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), RelayHandler)
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        relay = LocalHlsRelay(f"http://127.0.0.1:{upstream.server_address[1]}/source.m3u8")
        try:
            local_url = relay.start(timeout=3)
            playlist = urlopen(local_url, timeout=2).read().decode()
            self.assertIn("#EXTM3U", playlist)
            segment_url = next(line for line in playlist.splitlines() if line.startswith("/segment?url="))
            segment = urlopen(f"http://127.0.0.1:{relay.port}{segment_url}", timeout=2).read()
            self.assertEqual(segment, b"FAKE-TS-DATA")
        finally:
            relay.stop()
            upstream.shutdown()
            upstream.server_close()
            thread.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
