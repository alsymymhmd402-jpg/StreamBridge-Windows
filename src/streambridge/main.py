"""Application entry point."""
from __future__ import annotations

import argparse
import sys
import tkinter as tk

from .ui import StreamBridgeApp


def main() -> int:
    parser = argparse.ArgumentParser(description="Stream a direct URL into a Windows DirectShow virtual camera.")
    parser.add_argument("url", nargs="?", default="", help="Optional RTSP/HLS/HTTP stream URL to prefill")
    args = parser.parse_args()
    try:
        app = StreamBridgeApp(initial_url=args.url)
        app.mainloop()
        return 0
    except tk.TclError as exc:
        print(f"Unable to start the desktop UI: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
