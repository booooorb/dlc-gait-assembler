"""Define gait-analysis results and returned recording artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AlmaRunResult:
    input_file: Path
    output_files: tuple[Path, ...]
    messages: tuple[str, ...] = ()
