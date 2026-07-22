"""Compatibility launcher; prefer the installed command or ``python -m dlc_gait_assembly``."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dlc_gait_assembly.gui.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
