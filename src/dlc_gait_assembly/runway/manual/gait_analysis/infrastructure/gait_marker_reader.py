"""Inspect coordinate-table headers for available gait body-part labels."""

from __future__ import annotations

import csv
from pathlib import Path


def read_dlc_bodyparts(csv_path: Path) -> list[str]:
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            next(reader)
            bodyparts = next(reader)
            coords = next(reader)
        except StopIteration as exc:
            raise ValueError(
                f"{csv_path} does not look like a DeepLabCut CSV with scorer/bodyparts/coords rows."
            ) from exc
    labels: list[str] = []
    seen: set[str] = set()
    for bodypart, coord in zip(bodyparts, coords, strict=False):
        label = bodypart.strip()
        if coord.strip().lower() == "x" and label and (label not in seen):
            labels.append(label)
            seen.add(label)
    if not labels:
        raise ValueError(f"No body part labels were found in {csv_path}.")
    return labels
