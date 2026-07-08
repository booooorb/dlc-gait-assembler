from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np
import pandas as pd

from dlc_gait_assembly.services.domain.videos import VIDEO_EXTENSIONS

COORDINATE_EXTENSIONS = {".csv", ".h5"}
PAIR_EXTENSIONS = COORDINATE_EXTENSIONS | VIDEO_EXTENSIONS


@dataclass(frozen=True)
class CoordinateFilePair:
    directory: Path
    stem: str
    csv_paths: tuple[Path, ...] = ()
    h5_paths: tuple[Path, ...] = ()
    video_paths: tuple[Path, ...] = ()

    @property
    def is_paired(self) -> bool:
        return (
            len(self.csv_paths) == 1
            and len(self.h5_paths) == 1
            and len(self.video_paths) == 1
        )

    @property
    def csv_path(self) -> Path | None:
        return self.csv_paths[0] if len(self.csv_paths) == 1 else None

    @property
    def h5_path(self) -> Path | None:
        return self.h5_paths[0] if len(self.h5_paths) == 1 else None

    @property
    def video_path(self) -> Path | None:
        return self.video_paths[0] if len(self.video_paths) == 1 else None

    @property
    def status(self) -> str:
        if self.is_paired:
            return "Paired"
        problems = []
        for label, paths in (
            ("CSV", self.csv_paths),
            ("H5", self.h5_paths),
            ("Video", self.video_paths),
        ):
            if not paths:
                problems.append(f"Missing {label}")
            elif len(paths) > 1:
                problems.append(f"Duplicate {label}")
        return " + ".join(problems) if problems else "Incomplete"


@dataclass(frozen=True)
class KneeCorrectionSettings:
    hip_knee_length_cm: float
    knee_ankle_length_cm: float
    pixels_per_cm: float
    likelihood_threshold: float = 0.0
    knee_bodyparts: tuple[str, ...] | None = None
    hip_bodypart: str | None = None
    ankle_bodypart: str | None = None
    output_knee_bodypart: str = "knee"
    knee_direction: str = "auto"


@dataclass(frozen=True)
class KneeMarkerReport:
    knee: str
    hip: str
    ankle: str
    hip_knee_length: float
    knee_ankle_length: float
    corrected_frames: int
    retained_frames: int
    frame_statuses: tuple[str, ...]


@dataclass(frozen=True)
class KneeCorrectionResult:
    source_csv: Path
    source_h5: Path
    source_video: Path
    output_csv: Path
    output_h5: Path
    markers: tuple[KneeMarkerReport, ...]


def pair_coordinate_files(paths: list[str | Path]) -> list[CoordinateFilePair]:
    grouped: dict[tuple[Path, str], dict[str, set[Path]]] = {}
    for raw_path in paths:
        path = Path(raw_path).expanduser().resolve()
        extension = path.suffix.lower()
        if extension not in PAIR_EXTENSIONS:
            continue
        key = (path.parent, _pairing_stem(path.stem))
        entry = grouped.setdefault(
            key, {"stem": set(), "csv": set(), "h5": set(), "video": set()}
        )
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


def _pairing_stem(stem: str) -> str:
    """Group original videos with common DeepLabCut output names.

    DeepLabCut labels often look like ``trialDLC_resnet50...csv`` while the
    source video is simply ``trial.mp4``.  Exact stems still work; this just
    strips the generated DLC suffix when present.
    """
    stripped = re.split(r"DLC(?:_|-)?", stem, maxsplit=1, flags=re.IGNORECASE)[0]
    stripped = re.sub(r"(?i)(?:_filtered|_labeled|_labelled)$", "", stripped)
    stripped = stripped.rstrip("._- ")
    return (stripped or stem).casefold()


def read_dlc_csv(path: str | Path) -> pd.DataFrame:
    csv_path = Path(path).expanduser().resolve()
    try:
        dataframe = pd.read_csv(csv_path, header=[0, 1, 2], index_col=0)
    except Exception as exc:
        raise ValueError(f"Could not read DeepLabCut CSV: {csv_path.name}") from exc
    _validate_dlc_dataframe(dataframe, csv_path)
    return dataframe


def read_dlc_bodyparts(path: str | Path) -> tuple[str, ...]:
    csv_path = Path(path).expanduser().resolve()
    try:
        dataframe = pd.read_csv(csv_path, header=[0, 1, 2], index_col=0, nrows=0)
    except Exception as exc:
        raise ValueError(f"Could not read DeepLabCut labels from: {csv_path.name}") from exc
    _validate_dlc_dataframe(dataframe, csv_path)
    bodyparts = []
    for column in dataframe.columns:
        bodypart = str(column[-2])
        if bodypart not in bodyparts:
            bodyparts.append(bodypart)
    return tuple(bodyparts)


def read_dlc_h5(path: str | Path) -> tuple[pd.DataFrame, str]:
    h5_path = Path(path).expanduser().resolve()
    try:
        with pd.HDFStore(h5_path, mode="r") as store:
            keys = store.keys()
            if len(keys) != 1:
                raise ValueError("The H5 file must contain exactly one coordinate dataset.")
            key = keys[0]
            dataframe = store[key]
    except Exception as exc:
        raise ValueError(f"Could not read DeepLabCut H5: {h5_path.name}") from exc
    _validate_dlc_dataframe(dataframe, h5_path)
    return dataframe, key


def correct_knee_dataframe(
    dataframe: pd.DataFrame,
    settings: KneeCorrectionSettings,
) -> tuple[pd.DataFrame, tuple[KneeMarkerReport, ...]]:
    _validate_dlc_dataframe(dataframe, Path("coordinates"))
    columns = _coordinate_columns(dataframe)
    corrected = dataframe.copy()
    reports: list[KneeMarkerReport] = []
    knee_targets = _knee_targets(columns, settings)
    if not knee_targets:
        raise ValueError(
            "No knee label could be corrected. Select hip and ankle labels, or add labels "
            'containing "hip" and "ankle".'
        )
    direction = _normalised_knee_direction(settings.knee_direction)

    if settings.pixels_per_cm <= 0:
        raise ValueError("Calibration pixels per centimeter must be greater than zero.")
    hip_knee_length = float(settings.hip_knee_length_cm * settings.pixels_per_cm)
    knee_ankle_length = float(settings.knee_ankle_length_cm * settings.pixels_per_cm)
    if settings.hip_knee_length_cm <= 0 or settings.knee_ankle_length_cm <= 0:
        raise ValueError("Femur and tibia/fibula lengths must be greater than zero.")

    for prefix, bodypart in knee_targets:
        knee_columns = columns.get((prefix, bodypart))
        if knee_columns is None or not {"x", "y"}.issubset(knee_columns):
            knee_columns = _new_knee_columns(dataframe, prefix, bodypart)
            raw_knee = np.full((len(dataframe), 2), np.nan, dtype=float)
        else:
            raw_knee = _xy_values(dataframe, knee_columns)
            _ensure_float_columns(corrected, knee_columns)
        hip = _selected_or_matching_bodypart(
            bodypart, "hip", settings.hip_bodypart, prefix, columns
        )
        ankle = _selected_or_matching_bodypart(
            bodypart, "ankle", settings.ankle_bodypart, prefix, columns
        )
        hip_columns = columns[(prefix, hip)]
        ankle_columns = columns[(prefix, ankle)]

        hip_values = _xy_values(dataframe, hip_columns)
        ankle_values = _xy_values(dataframe, ankle_columns)
        hip_coordinates_valid = np.isfinite(hip_values).all(axis=1)
        ankle_coordinates_valid = np.isfinite(ankle_values).all(axis=1)
        hip_likelihood_valid = _likelihood_mask(
            dataframe, hip_columns, settings.likelihood_threshold
        )
        ankle_likelihood_valid = _likelihood_mask(
            dataframe, ankle_columns, settings.likelihood_threshold
        )

        new_knee, corrected_mask, frame_statuses = _triangulated_knees(
            hip_values,
            ankle_values,
            raw_knee,
            hip_coordinates_valid,
            ankle_coordinates_valid,
            hip_likelihood_valid,
            ankle_likelihood_valid,
            hip_knee_length,
            knee_ankle_length,
            direction,
        )
        corrected.loc[:, knee_columns["x"]] = new_knee[:, 0]
        corrected.loc[:, knee_columns["y"]] = new_knee[:, 1]
        if "likelihood" in knee_columns:
            output_likelihood = dataframe.loc[:, knee_columns["likelihood"]].to_numpy(
                dtype=float, copy=True
            )
        else:
            knee_columns["likelihood"] = (*prefix, bodypart, "likelihood")
            output_likelihood = np.full(len(dataframe), np.nan, dtype=float)
        hip_likelihood = _likelihood_values(dataframe, hip_columns)
        ankle_likelihood = _likelihood_values(dataframe, ankle_columns)
        output_likelihood[corrected_mask] = np.minimum(
            hip_likelihood[corrected_mask], ankle_likelihood[corrected_mask]
        )
        corrected.loc[:, knee_columns["likelihood"]] = output_likelihood
        reports.append(
            KneeMarkerReport(
                knee=bodypart,
                hip=hip,
                ankle=ankle,
                hip_knee_length=hip_knee_length,
                knee_ankle_length=knee_ankle_length,
                corrected_frames=int(corrected_mask.sum()),
                retained_frames=int((~corrected_mask).sum()),
                frame_statuses=frame_statuses,
            )
        )

    corrected.columns = pd.MultiIndex.from_tuples(
        [tuple(column) for column in corrected.columns],
        names=dataframe.columns.names,
    )
    return corrected, tuple(reports)


def correct_knee_pair(
    pair: CoordinateFilePair,
    output_folder: str | Path,
    settings: KneeCorrectionSettings,
) -> KneeCorrectionResult:
    if (
        not pair.is_paired
        or pair.csv_path is None
        or pair.h5_path is None
        or pair.video_path is None
    ):
        raise ValueError(
            f'"{pair.stem}" does not have exactly one CSV, one H5, and one video file.'
        )
    csv_dataframe = read_dlc_csv(pair.csv_path)
    h5_dataframe, h5_key = read_dlc_h5(pair.h5_path)
    if not csv_dataframe.columns.equals(h5_dataframe.columns) or not csv_dataframe.index.equals(
        h5_dataframe.index
    ):
        raise ValueError(f'CSV and H5 labels do not match for "{pair.stem}".')

    corrected, reports = correct_knee_dataframe(csv_dataframe, settings)
    destination = Path(output_folder).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    output_csv = destination / f"{pair.stem}_knee_corrected.csv"
    output_h5 = destination / f"{pair.stem}_knee_corrected.h5"
    corrected.to_csv(output_csv)
    corrected.to_hdf(output_h5, key=h5_key.lstrip("/"), mode="w", format="table")
    return KneeCorrectionResult(
        source_csv=pair.csv_path,
        source_h5=pair.h5_path,
        source_video=pair.video_path,
        output_csv=output_csv,
        output_h5=output_h5,
        markers=reports,
    )


def _validate_dlc_dataframe(dataframe: pd.DataFrame, path: Path) -> None:
    if not isinstance(dataframe.columns, pd.MultiIndex) or dataframe.columns.nlevels < 2:
        raise ValueError(f"{path.name} is not a DeepLabCut coordinate table.")
    coordinate_names = {str(column[-1]).casefold() for column in dataframe.columns}
    if not {"x", "y"}.issubset(coordinate_names):
        raise ValueError(f"{path.name} does not contain x/y DeepLabCut coordinates.")


def _coordinate_columns(dataframe: pd.DataFrame) -> dict[tuple[tuple[str, ...], str], dict[str, tuple]]:
    result: dict[tuple[tuple[str, ...], str], dict[str, tuple]] = {}
    for raw_column in dataframe.columns:
        column = tuple(raw_column)
        prefix = tuple(str(value) for value in column[:-2])
        bodypart = str(column[-2])
        coordinate = str(column[-1]).casefold()
        result.setdefault((prefix, bodypart), {})[coordinate] = raw_column
    return result


def _knee_targets(
    columns: dict[tuple[tuple[str, ...], str], dict[str, tuple]],
    settings: KneeCorrectionSettings,
) -> tuple[tuple[tuple[str, ...], str], ...]:
    if settings.knee_bodyparts:
        targets: list[tuple[tuple[str, ...], str]] = []
        for requested in settings.knee_bodyparts:
            requested_label = _clean_output_knee_bodypart(requested)
            existing = [
                (prefix, bodypart)
                for (prefix, bodypart), coordinates in columns.items()
                if bodypart.casefold() == requested_label.casefold()
                and {"x", "y"}.issubset(coordinates)
            ]
            if existing:
                targets.extend(existing)
            else:
                targets.extend(
                    (prefix, requested_label)
                    for prefix in _prefixes_with_endpoint_pair(
                        requested_label, columns, settings
                    )
                )
        return tuple(
            sorted(dict.fromkeys(targets), key=lambda item: (str(item[0]), item[1].casefold()))
        )

    existing_knees = [
        (prefix, bodypart)
        for (prefix, bodypart), coordinates in columns.items()
        if "knee" in bodypart.casefold() and {"x", "y"}.issubset(coordinates)
    ]
    if existing_knees:
        return tuple(
            sorted(existing_knees, key=lambda item: (str(item[0]), item[1].casefold()))
        )

    output_label = _clean_output_knee_bodypart(settings.output_knee_bodypart)
    return tuple(
        (prefix, output_label)
        for prefix in _prefixes_with_endpoint_pair(output_label, columns, settings)
    )


def _prefixes_with_endpoint_pair(
    knee_bodypart: str,
    columns: dict[tuple[tuple[str, ...], str], dict[str, tuple]],
    settings: KneeCorrectionSettings,
) -> tuple[tuple[str, ...], ...]:
    prefixes = sorted({prefix for prefix, _bodypart in columns}, key=str)
    matches: list[tuple[str, ...]] = []
    for prefix in prefixes:
        try:
            _selected_or_matching_bodypart(
                knee_bodypart, "hip", settings.hip_bodypart, prefix, columns
            )
            _selected_or_matching_bodypart(
                knee_bodypart, "ankle", settings.ankle_bodypart, prefix, columns
            )
        except ValueError:
            continue
        matches.append(prefix)
    return tuple(matches)


def _clean_output_knee_bodypart(bodypart: str | None) -> str:
    cleaned = str(bodypart or "").strip()
    if not cleaned:
        raise ValueError("Output knee label must not be blank.")
    return cleaned


def _normalised_knee_direction(direction: str) -> str:
    normalised = str(direction or "auto").strip().casefold().replace("-", "_").replace(" ", "_")
    aliases = {
        "auto": "auto",
        "automatic": "auto",
        "side_a": "positive",
        "a": "positive",
        "positive": "positive",
        "plus": "positive",
        "side_b": "negative",
        "b": "negative",
        "negative": "negative",
        "minus": "negative",
    }
    if normalised not in aliases:
        raise ValueError("Knee direction must be auto, side A, or side B.")
    return aliases[normalised]


def _new_knee_columns(
    dataframe: pd.DataFrame,
    prefix: tuple[str, ...],
    bodypart: str,
) -> dict[str, tuple]:
    if len(prefix) != dataframe.columns.nlevels - 2:
        raise ValueError("Could not create a knee label for this DeepLabCut table.")
    return {
        "x": (*prefix, bodypart, "x"),
        "y": (*prefix, bodypart, "y"),
    }


def _matching_bodypart(
    knee: str,
    target: str,
    prefix: tuple[str, ...],
    columns: dict[tuple[tuple[str, ...], str], dict[str, tuple]],
) -> str:
    candidates = [
        bodypart
        for candidate_prefix, bodypart in columns
        if candidate_prefix == prefix
        and target in bodypart.casefold()
        and {"x", "y"}.issubset(columns[(candidate_prefix, bodypart)])
    ]
    if not candidates:
        raise ValueError(f'No {target} marker matches knee marker "{knee}".')
    exact = re.sub("knee", target, knee, flags=re.IGNORECASE)
    for candidate in candidates:
        if candidate.casefold() == exact.casefold():
            return candidate
    knee_side = _marker_side(knee)
    ranked = sorted(
        candidates,
        key=lambda candidate: (
            _marker_side(candidate) != knee_side if knee_side else False,
            -len(_marker_tokens(knee, "knee") & _marker_tokens(candidate, target)),
            candidate.casefold(),
        ),
    )
    return ranked[0]


def _selected_or_matching_bodypart(
    knee: str,
    target: str,
    selected: str | None,
    prefix: tuple[str, ...],
    columns: dict[tuple[tuple[str, ...], str], dict[str, tuple]],
) -> str:
    if selected is None:
        return _matching_bodypart(knee, target, prefix, columns)
    for candidate_prefix, bodypart in columns:
        if (
            candidate_prefix == prefix
            and bodypart.casefold() == selected.casefold()
            and {"x", "y"}.issubset(columns[(candidate_prefix, bodypart)])
        ):
            return bodypart
    raise ValueError(
        f'Selected {target} label "{selected}" was not found for knee marker "{knee}".'
    )


def _marker_side(name: str) -> str | None:
    lowered = name.casefold()
    tokens = set(filter(None, re.split(r"[^a-z0-9]+", lowered)))
    if "left" in tokens or "l" in tokens or lowered.startswith("l-") or lowered.endswith("l"):
        return "left"
    if "right" in tokens or "r" in tokens or lowered.startswith("r-") or lowered.endswith("r"):
        return "right"
    return None


def _marker_tokens(name: str, joint: str) -> set[str]:
    lowered = name.casefold().replace(joint, " ")
    return set(filter(None, re.split(r"[^a-z0-9]+", lowered)))


def _xy_values(dataframe: pd.DataFrame, columns: dict[str, tuple]) -> np.ndarray:
    return dataframe.loc[:, [columns["x"], columns["y"]]].to_numpy(dtype=float, copy=True)


def _ensure_float_columns(dataframe: pd.DataFrame, columns: dict[str, tuple]) -> None:
    for coordinate in ("x", "y", "likelihood"):
        column = columns.get(coordinate)
        if column is not None and column in dataframe.columns:
            dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce").astype(float)


def _likelihood_values(dataframe: pd.DataFrame, columns: dict[str, tuple]) -> np.ndarray:
    if "likelihood" not in columns:
        return np.ones(len(dataframe), dtype=float)
    return dataframe.loc[:, columns["likelihood"]].to_numpy(dtype=float, copy=True)


def _likelihood_mask(
    dataframe: pd.DataFrame,
    columns: dict[str, tuple],
    threshold: float,
) -> np.ndarray:
    values = _likelihood_values(dataframe, columns)
    return np.isfinite(values) & (values >= threshold)


def _triangulated_knees(
    hips: np.ndarray,
    ankles: np.ndarray,
    raw_knees: np.ndarray,
    hip_coordinates_valid: np.ndarray,
    ankle_coordinates_valid: np.ndarray,
    hip_likelihood_valid: np.ndarray,
    ankle_likelihood_valid: np.ndarray,
    hip_knee_length: float,
    knee_ankle_length: float,
    knee_direction: str,
) -> tuple[np.ndarray, np.ndarray, tuple[str, ...]]:
    output = raw_knees.copy()
    corrected = np.zeros(len(output), dtype=bool)
    statuses = ["Not evaluated"] * len(output)
    previous: np.ndarray | None = None
    preferred_signs = []
    for hip, ankle, knee in zip(hips, ankles, raw_knees):
        if np.isfinite(hip).all() and np.isfinite(ankle).all() and np.isfinite(knee).all():
            cross = np.cross(ankle - hip, knee - hip)
            if cross != 0:
                preferred_signs.append(float(np.sign(cross)))
    preferred_sign = float(np.sign(np.median(preferred_signs))) if preferred_signs else 1.0

    for index, (hip, ankle, raw_knee) in enumerate(zip(hips, ankles, raw_knees)):
        if not hip_coordinates_valid[index]:
            statuses[index] = "Missing hip coordinates"
            continue
        if not ankle_coordinates_valid[index]:
            statuses[index] = "Missing ankle coordinates"
            continue
        if not hip_likelihood_valid[index]:
            statuses[index] = "Low-confidence hip"
            continue
        if not ankle_likelihood_valid[index]:
            statuses[index] = "Low-confidence ankle"
            continue
        delta = ankle - hip
        distance = float(np.linalg.norm(delta))
        if distance <= 0:
            statuses[index] = "Zero hip–ankle distance"
            continue
        if distance > hip_knee_length + knee_ankle_length:
            statuses[index] = "Segment lengths cannot form a triangle"
            continue
        if distance < abs(hip_knee_length - knee_ankle_length):
            statuses[index] = "Segment lengths cannot form a triangle"
            continue
        unit = delta / distance
        along = (
            hip_knee_length**2 - knee_ankle_length**2 + distance**2
        ) / (2 * distance)
        perpendicular_distance_sq = hip_knee_length**2 - along**2
        if not np.isfinite(perpendicular_distance_sq) or perpendicular_distance_sq < -1e-8:
            statuses[index] = "No valid circle intersection"
            continue
        perpendicular_distance = float(np.sqrt(max(0.0, perpendicular_distance_sq)))
        base = hip + along * unit
        perpendicular = np.array([-unit[1], unit[0]])
        candidates = (
            base + perpendicular_distance * perpendicular,
            base - perpendicular_distance * perpendicular,
        )
        if knee_direction == "positive":
            chosen = candidates[0]
        elif knee_direction == "negative":
            chosen = candidates[1]
        elif np.isfinite(raw_knee).all():
            reference = raw_knee
            chosen = min(candidates, key=lambda candidate: np.linalg.norm(candidate - reference))
        elif previous is not None:
            chosen = min(candidates, key=lambda candidate: np.linalg.norm(candidate - previous))
        else:
            chosen = candidates[0] if preferred_sign >= 0 else candidates[1]
        output[index] = chosen
        corrected[index] = True
        statuses[index] = "Corrected"
        previous = chosen
    return output, corrected, tuple(statuses)
