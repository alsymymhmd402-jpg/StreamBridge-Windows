"""PyInstaller-friendly launcher for the streambridge package."""
from __future__ import annotations

import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    project_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root / "src"))

from streambridge.main import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
