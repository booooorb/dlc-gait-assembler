"""Allocate collision-safe processed-video paths while preserving recording names."""

from __future__ import annotations

import re
from pathlib import Path


def unique_output_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.stem}_{index:02d}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not create a unique output path for {path}")


def output_path_for_input(
    input_path: str | Path,
    output_dir: str | Path,
    crop_region_name: str | None = None,
    include_crop_region_name: bool = False,
) -> Path:
    input_path = Path(input_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = ""
    if include_crop_region_name:
        suffix = f"_{sanitize_output_suffix(crop_region_name or 'crop')}"
    output_path = unique_output_path(output_dir / f"{input_path.stem}_processed{suffix}.mp4")
    if output_path == input_path:
        raise RuntimeError("Refusing to overwrite the original input video.")
    return output_path


def sanitize_output_suffix(value: str) -> str:
    sanitized = re.sub("[^A-Za-z0-9._-]+", "_", value.strip())
    sanitized = re.sub("_+", "_", sanitized).strip("._-")
    return sanitized or "crop"
