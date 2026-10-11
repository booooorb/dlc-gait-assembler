"""Define standalone gait inputs, calibrated view data, and numerical result contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RustLab1RunResult:
    input_file: Path
    output_files: tuple[Path, ...]
    messages: tuple[str, ...] = ()
