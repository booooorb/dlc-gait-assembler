"""Allocate collision-safe session directories without overwriting prior recordings."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def make_session_output_dir(output_root: str | Path, now: datetime | None = None) -> Path:
    root = Path(output_root).expanduser().resolve()
    stamp = (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    session_dir = root / stamp
    if not session_dir.exists():
        session_dir.mkdir(parents=True, exist_ok=False)
        return session_dir
    for index in range(2, 1000):
        candidate = root / f"{stamp}_{index:02d}"
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
    raise RuntimeError(f"Could not create a unique output folder under {root}")
