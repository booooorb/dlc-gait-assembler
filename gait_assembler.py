"""Launch from a source checkout with the same command as earlier versions."""

import sys
from pathlib import Path


def main():
    source = Path(__file__).resolve().parent / "src"
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    from dlc_gait_assembly.app.app_bootstrap import main as launch

    return launch()


if __name__ == "__main__":
    raise SystemExit(main())
