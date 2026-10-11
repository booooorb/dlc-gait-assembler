"""Match coordinate CSV/H5 pairs and optional source videos by recording identity."""

from __future__ import annotations

import re
from pathlib import Path

from dlc_gait_assembly.runway.manual.knee_correction.business.knee_coordinate_correction import PAIR_EXTENSIONS
from dlc_gait_assembly.runway.manual.knee_correction.business.knee_correction_contracts import CoordinateFilePair
from dlc_gait_assembly.shared.business.media_access_contracts import VIDEO_EXTENSIONS


def pair_coordinate_files(paths: list[str | Path]) -> list[CoordinateFilePair]:
    grouped: dict[tuple[Path, str], dict[str, set[Path]]] = {}
    for raw_path in paths:
        path = Path(raw_path)
        extension = path.suffix.lower()
        if extension not in PAIR_EXTENSIONS:
            continue
        key = (path.parent, pairing_stem(path.stem))
        entry = grouped.setdefault(key, {"stem": set(), "csv": set(), "h5": set(), "video": set()})
        entry["stem"].add(Path(path.stem))
        if extension in VIDEO_EXTENSIONS:
            entry["video"].add(path)
        else:
            entry[extension[1:]].add(path)
    pairs = []
    for (directory, _folded_stem), entry in grouped.items():
        stems = sorted(str(value) for value in entry["stem"])
        pairs.append(
            CoordinateFilePair(
                directory=directory,
                stem=stems[0],
                csv_paths=tuple(sorted(entry["csv"])),
                h5_paths=tuple(sorted(entry["h5"])),
                video_paths=tuple(sorted(entry["video"])),
            )
        )
    return sorted(pairs, key=lambda pair: (str(pair.directory).casefold(), pair.stem.casefold()))


def pairing_stem(stem: str) -> str:
    """Group original videos with common DeepLabCut output names.

    DeepLabCut labels often look like ``trialDLC_resnet50...csv`` while the
    source video is simply ``trial.mp4``.  Exact stems still work; this just
    strips the generated DLC suffix when present.
    """
    stripped = re.split("DLC(?:_|-)?", stem, maxsplit=1, flags=re.IGNORECASE)[0]
    stripped = re.sub("(?i)(?:_filtered|_labeled|_labelled)$", "", stripped)
    stripped = stripped.rstrip("._- ")
    return (stripped or stem).casefold()
