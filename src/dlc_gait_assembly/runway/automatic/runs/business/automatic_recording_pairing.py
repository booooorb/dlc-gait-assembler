"""Associate processing regions and DeepLabCut coordinate artifacts with recording/view identities."""

from __future__ import annotations

import re
from pathlib import Path

from dlc_gait_assembly.runway.manual.deeplabcut.business.deeplabcut_job_contracts import DlcAnalysisResult
from dlc_gait_assembly.runway.manual.knee_correction.business.knee_correction_contracts import CoordinateFilePair

VIEW_ALIASES = {
    "left": {"left", "lh", "leftside", "leftview"},
    "right": {"right", "rh", "rightside", "rightview"},
    "bottom": {"bottom", "down", "downward", "ventral", "below", "bottomview"},
}


def trim_ranges_for_video(trim_ranges: dict[str, tuple], video_path: Path) -> tuple:
    resolved = str(video_path)
    for key in (resolved, str(video_path), video_path.name, video_path.stem):
        if key in trim_ranges:
            return trim_ranges[key]
    for key, ranges in trim_ranges.items():
        if Path(key).name == video_path.name:
            return ranges
    return ()


def view_regions(regions: tuple[str, ...]) -> dict[str, str]:
    matches: dict[str, list[str]] = {role: [] for role in VIEW_ALIASES}
    for region in regions:
        role = view_role(region)
        if role is not None:
            matches[role].append(region)
    invalid = [role for (role, names) in matches.items() if len(names) != 1]
    if invalid:
        raise ValueError(
            "Multi side view requires exactly one crop region named for each view: left, right, and bottom. Rename the regions in the video settings manifest."
        )
    return {role: names[0] for (role, names) in matches.items()}


def view_role(region: str) -> str | None:
    tokens = set(re.findall("[a-z0-9]+", region.casefold()))
    compact = "".join(tokens)
    matching_roles = [role for (role, names) in VIEW_ALIASES.items() if tokens & names or compact in names]
    return matching_roles[0] if len(matching_roles) == 1 else None


def input_name(path: Path, index: int) -> str:
    stem = re.split("DLC(?:_|-)?", path.stem, maxsplit=1, flags=re.IGNORECASE)[0]
    stem = re.sub("(?i)(?:_processed|_knee_corrected)$", "", stem).strip("._- ")
    return stem or f"recording_{index + 1}"


def pair_dlc_result(result: DlcAnalysisResult) -> list[CoordinateFilePair]:
    pairs = []
    for video_path in result.video_paths:
        base = video_path.stem.casefold()
        csv_paths = tuple(path for path in result.csv_paths if dlc_source_stem(path) == base)
        h5_paths = tuple(path for path in result.h5_paths if dlc_source_stem(path) == base)
        pairs.append(
            CoordinateFilePair(
                directory=csv_paths[0].parent if csv_paths else video_path.parent,
                stem=video_path.stem,
                csv_paths=csv_paths,
                h5_paths=h5_paths,
                video_paths=(video_path,),
            )
        )
    return pairs


def dlc_source_stem(path: Path) -> str:
    stem = re.split("DLC(?:_|-)?", path.stem, maxsplit=1, flags=re.IGNORECASE)[0]
    return re.sub("(?i)(?:_filtered)$", "", stem).rstrip("._- ").casefold()


def safe_name(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in "-_" else "_" for character in value)
    return safe.strip("_") or "pipeline"
