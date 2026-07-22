from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal

from dlc_gait_assembly.services.pipeline.runtime import (
    find_alma_python,
    temporary_directory_root,
)

LadderDetectionMethod = Literal["Deviation", "Baseline", "Threshold"]
LadderClassification = Literal["unreviewed", "footfall", "slip", "fall"]
LadderView = Literal["single", "left", "right"]

LADDER_OUTPUT_COLUMNS = (
    "time (frame)",
    "depth (pixel)",
    "start (frame)",
    "end (frame)",
    "duration (s)",
    "bodypart",
    "slip or fall",
)
COMBINED_LADDER_OUTPUT_COLUMNS = (*LADDER_OUTPUT_COLUMNS, "view", "source file")


@dataclass(frozen=True)
class LadderSettings:
    """Settings used by ALMA's ladder-rung footfall detector."""

    method: LadderDetectionMethod = "Deviation"
    frame_rate: float = 120.0
    likelihood_threshold: float = 0.1
    depth_threshold: float = 0.8
    threshold: float | None = None
    baseline_window_frames: int | None = None


@dataclass(frozen=True)
class LadderEvent:
    bodypart: str
    peak_frame: int
    start_frame: int
    end_frame: int
    peak_y_px: float
    depth_px: float
    duration_s: float
    classification: LadderClassification = "unreviewed"
    included: bool = True
    view: LadderView = "single"
    source_file: str = ""


@dataclass(frozen=True)
class LadderRunResult:
    input_file: Path
    output_file: Path
    events: tuple[LadderEvent, ...]


@dataclass(frozen=True)
class DualLadderRunResult:
    left_result: LadderRunResult
    right_result: LadderRunResult
    output_file: Path
    events: tuple[LadderEvent, ...]


def ladder_settings_from_alma_config(config: dict) -> LadderSettings:
    """Translate ALMA's ladder keys from ``config.yaml`` into typed settings."""

    threshold = config.get("threshold")
    if threshold in (None, ""):
        threshold = None
    return LadderSettings(
        frame_rate=float(config.get("frame_rate", 120.0)),
        likelihood_threshold=float(config.get("likelihood_threshold", 0.1)),
        depth_threshold=float(config.get("depth_threshold", 0.8)),
        threshold=None if threshold is None else float(threshold),
    )


def read_dlc_bodyparts(csv_path: Path) -> list[str]:
    """Read body-part labels without importing the scientific runtime."""

    import csv

    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.reader(handle)
        next(rows, None)
        bodypart_row = next(rows, None)
        coordinate_row = next(rows, None)
    if bodypart_row is None or coordinate_row is None:
        raise ValueError("Expected a three-row DeepLabCut CSV header.")

    bodyparts: list[str] = []
    for bodypart, coordinate in zip(bodypart_row, coordinate_row, strict=False):
        label = bodypart.strip()
        if coordinate.strip().lower() == "y" and label and label not in bodyparts:
            bodyparts.append(label)
    if not bodyparts:
        raise ValueError("No body-part y coordinates were found in the CSV header.")
    return bodyparts


def suggested_ladder_bodyparts(bodyparts: list[str]) -> list[str]:
    """Prefer distal paw/toe markers, matching ALMA's ladder workflow."""

    distal = [
        bodypart
        for bodypart in bodyparts
        if any(token in bodypart.lower() for token in ("toe", "paw", "foot"))
    ]
    return distal or list(bodyparts)


def run_ladder_analysis(
    csv_file: Path,
    output_folder: Path,
    settings: LadderSettings,
    bodyparts: list[str] | None = None,
) -> LadderRunResult:
    """Run the ported ALMA detector and write its standard event CSV."""

    external_python = find_alma_python()
    if external_python is not None:
        return _run_external(csv_file, output_folder, settings, bodyparts, external_python)
    return _run_in_process(csv_file, output_folder, settings, bodyparts)


def run_dual_view_ladder_analysis(
    left_csv_file: Path,
    right_csv_file: Path,
    output_folder: Path,
    left_settings: LadderSettings,
    right_settings: LadderSettings,
    left_bodyparts: list[str],
    right_bodyparts: list[str],
) -> DualLadderRunResult:
    """Analyze two side cameras independently and combine their ladder events.

    Each view keeps its own pixel-domain settings because resolution, framing,
    and camera angle can differ. Frame numbers are not rescaled or synchronized;
    the output records the source view/file for every event.
    """

    if len(left_bodyparts) != 2 or len(right_bodyparts) != 2:
        raise ValueError("Dual-view ladder analysis requires exactly two body parts per side.")

    output_folder = Path(output_folder).expanduser().resolve()
    left_result = run_ladder_analysis(
        left_csv_file, output_folder / "left", left_settings, left_bodyparts
    )
    right_result = run_ladder_analysis(
        right_csv_file, output_folder / "right", right_settings, right_bodyparts
    )
    left_name = Path(left_csv_file).name
    right_name = Path(right_csv_file).name
    events = [
        replace(event, view="left", source_file=left_name)
        for event in left_result.events
    ]
    events.extend(
        replace(event, view="right", source_file=right_name)
        for event in right_result.events
    )
    events.sort(key=lambda event: (event.peak_frame, event.view, event.bodypart))

    combined_name = (
        f"{Path(left_csv_file).stem}__{Path(right_csv_file).stem}"
        "_ladder_combined.csv"
    )
    output_file = write_ladder_events(events, output_folder / combined_name, combined=True)
    return DualLadderRunResult(left_result, right_result, output_file, tuple(events))


def write_ladder_events(
    events: list[LadderEvent] | tuple[LadderEvent, ...],
    output_file: Path,
    *,
    combined: bool | None = None,
) -> Path:
    """Write reviewed events using ALMA-compatible columns."""

    import csv

    if combined is None:
        combined = any(event.view != "single" or event.source_file for event in events)
    columns = COMBINED_LADDER_OUTPUT_COLUMNS if combined else LADDER_OUTPUT_COLUMNS
    rows = []
    for event in events:
        if not event.included:
            continue
        classification = "" if event.classification in ("unreviewed", "footfall") else event.classification
        row = {
            "time (frame)": int(event.peak_frame),
            "depth (pixel)": float(event.depth_px),
            "start (frame)": int(event.start_frame),
            "end (frame)": int(event.end_frame),
            "duration (s)": float(event.duration_s),
            "bodypart": event.bodypart,
            "slip or fall": classification,
        }
        if combined:
            row["view"] = event.view
            row["source file"] = event.source_file
        rows.append(row)
    output_file = Path(output_file).expanduser().resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return output_file


def _run_in_process(
    csv_file: Path,
    output_folder: Path,
    settings: LadderSettings,
    bodyparts: list[str] | None,
) -> LadderRunResult:
    pd, np, find_peaks, sparse, spsolve = _load_dependencies()
    dataframe, detected_bodyparts = _read_coordinate_dataframe(csv_file, pd)
    selected = list(bodyparts) if bodyparts is not None else suggested_ladder_bodyparts(detected_bodyparts)
    unknown = [bodypart for bodypart in selected if bodypart not in detected_bodyparts]
    if unknown:
        raise ValueError("Body parts not found in the CSV: " + ", ".join(unknown))
    if not selected:
        raise ValueError("Select at least one body part for ladder analysis.")

    events: list[LadderEvent] = []
    for bodypart in selected:
        events.extend(_detect_bodypart(dataframe, bodypart, settings, np, find_peaks, sparse, spsolve))
    events.sort(key=lambda event: (event.peak_frame, event.bodypart))

    output_folder = Path(output_folder).expanduser().resolve()
    output_file = output_folder / f"{Path(csv_file).stem}_ladder_footfalls.csv"
    write_ladder_events(events, output_file)
    return LadderRunResult(Path(csv_file).expanduser().resolve(), output_file, tuple(events))


def _read_coordinate_dataframe(csv_file: Path, pd):
    dataframe = pd.read_csv(csv_file, header=[1, 2])
    flattened: list[str] = []
    bodyparts: list[str] = []
    for bodypart, coordinate in dataframe.columns:
        bodypart = str(bodypart).strip()
        coordinate = str(coordinate).strip().lower()
        flattened.append(f"{bodypart} {coordinate}")
        if coordinate == "y" and bodypart != "bodyparts" and bodypart not in bodyparts:
            bodyparts.append(bodypart)
    dataframe.columns = flattened
    return dataframe, bodyparts


def _detect_bodypart(dataframe, bodypart, settings, np, find_peaks, sparse, spsolve) -> list[LadderEvent]:
    y_column = f"{bodypart} y"
    likelihood_column = f"{bodypart} likelihood"
    if y_column not in dataframe or likelihood_column not in dataframe:
        raise ValueError(f"{bodypart!r} does not have y and likelihood coordinates.")

    y = np.asarray(dataframe[y_column], dtype=float)
    likelihood = np.asarray(dataframe[likelihood_column], dtype=float)
    if settings.method == "Deviation":
        peaks, properties = find_peaks(y, height=-10000, prominence=(45, 100000))
    elif settings.method == "Baseline":
        valid_positions = np.flatnonzero(np.isfinite(y) & (likelihood >= settings.likelihood_threshold))
        if len(valid_positions) < 3:
            return []
        baseline = _baseline_als(y[valid_positions], 10**2, 0.1, np, sparse, spsolve)
        peaks, properties = find_peaks(baseline, prominence=(10, 100000))
        peaks = valid_positions[peaks]
        properties["left_bases"] = valid_positions[properties["left_bases"]]
        properties["right_bases"] = valid_positions[properties["right_bases"]]
    elif settings.method == "Threshold":
        threshold = settings.threshold
        if threshold is None:
            threshold = float(np.nanmean(y) + np.nanstd(y))
        adjusted = np.full(len(y), threshold, dtype=float)
        adjusted[y > threshold] = y[y > threshold]
        peaks, properties = find_peaks(adjusted, prominence=(10, 1000))
    else:
        raise ValueError(f"Unsupported ladder detection method: {settings.method}")

    peaks, left_bases, right_bases = _filter_predictions(
        peaks,
        properties,
        y,
        likelihood,
        settings.likelihood_threshold,
        settings.depth_threshold,
        np,
    )
    if settings.method == "Baseline" and len(peaks):
        window = settings.baseline_window_frames
        if window is None:
            window = max(1, int(settings.frame_rate // 5))
        peaks = _adjust_times(y, peaks, window, np)

    events: list[LadderEvent] = []
    for peak, start, end in zip(peaks, left_bases, right_bases, strict=False):
        peak = int(peak)
        start = int(start)
        end = int(end)
        depth = float(((y[peak] - y[start]) + (y[peak] - y[end])) / 2.0)
        events.append(
            LadderEvent(
                bodypart=bodypart,
                peak_frame=peak,
                start_frame=start,
                end_frame=end,
                peak_y_px=float(y[peak]),
                depth_px=depth,
                duration_s=round((end - start) / settings.frame_rate, 3),
            )
        )
    return events


def _filter_predictions(
    peaks,
    properties,
    y,
    likelihood,
    likelihood_threshold,
    depth_threshold,
    np,
):
    """Faithful, bounds-safe port of ALMA ``filter_predictions``."""

    peaks = np.asarray(peaks, dtype=int)
    if len(peaks) == 0:
        empty = np.asarray([], dtype=int)
        return empty, empty, empty
    left_bases = np.asarray(properties["left_bases"], dtype=int).copy()
    right_bases = np.asarray(properties["right_bases"], dtype=int).copy()
    valid = [index for index, peak in enumerate(peaks) if np.isfinite(likelihood[peak]) and likelihood[peak] >= likelihood_threshold]
    if not valid:
        empty = np.asarray([], dtype=int)
        return empty, empty, empty

    kept = [valid[0]]
    # ALMA deliberately compares adjacent *candidate* peaks here, even when the
    # previous candidate was merged into an earlier event. Keeping that detail
    # is important for parity on long, noisy ladder recordings.
    for valid_position, current_index in enumerate(valid[1:], start=1):
        previous_index = valid[valid_position - 1]
        previous_peak = int(peaks[previous_index])
        current_peak = int(peaks[current_index])
        between_positions = np.arange(previous_peak, current_peak, dtype=int)
        between_positions = between_positions[
            np.isfinite(y[between_positions]) & (likelihood[between_positions] >= likelihood_threshold)
        ]
        if len(between_positions):
            recovery_frame = int(between_positions[np.argmin(y[between_positions])])
            recovery_y = float(y[recovery_frame])
        else:
            recovery_frame = previous_peak
            recovery_y = float(y[previous_peak])

        previous_depth = float(y[previous_peak] - y[left_bases[previous_index]])
        if left_bases[current_index] > right_bases[previous_index]:
            kept.append(current_index)
        elif y[current_peak] - recovery_y >= depth_threshold * previous_depth:
            left_bases[current_index] = recovery_frame
            kept.append(current_index)
        elif y[current_peak] > y[previous_peak]:
            if kept:
                kept.pop()
            kept.append(current_index)
            left_bases[current_index] = left_bases[previous_index]
        else:
            right_bases[previous_index] = right_bases[current_index]

    selected_peaks = peaks[kept].copy()
    selected_left = left_bases[kept].copy()
    selected_right = right_bases[kept].copy()
    for index, start in enumerate(selected_left):
        if likelihood[start] < likelihood_threshold:
            selected_left[index] = max(0, selected_peaks[index] - 1)
            selected_right[index] = min(len(y) - 1, selected_peaks[index] + 1)
    return selected_peaks, selected_left, selected_right


def _baseline_als(y, lam, asymmetry, np, sparse, spsolve, iterations=10):
    length = len(y)
    difference = sparse.csc_matrix(np.diff(np.eye(length), 2))
    weights = np.ones(length)
    for _ in range(iterations):
        weight_matrix = sparse.spdiags(weights, 0, length, length)
        system = weight_matrix + lam * difference.dot(difference.transpose())
        baseline = spsolve(system, weights * y)
        weights = asymmetry * (y > baseline) + (1 - asymmetry) * (y < baseline)
    return baseline


def _adjust_times(y, peaks, window, np):
    adjusted = np.asarray(peaks, dtype=int).copy()
    for index, peak in enumerate(adjusted):
        start = max(0, int(peak) - int(window))
        end = min(len(y), int(peak) + int(window))
        if end > start:
            adjusted[index] = start + int(np.nanargmax(y[start:end]))
    return adjusted


def _load_dependencies():
    try:
        import numpy as np
        import pandas as pd
        from scipy import sparse
        from scipy.signal import find_peaks
        from scipy.sparse.linalg import spsolve
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "ALMA ladder analysis requires numpy, pandas, and scipy. "
            "Install the scientific dependencies or configure DLC_GAIT_ALMA_PYTHON."
        ) from exc
    return pd, np, find_peaks, sparse, spsolve


def _run_external(csv_file, output_folder, settings, bodyparts, python_executable):
    with tempfile.TemporaryDirectory(prefix="alma-ladder-", dir=temporary_directory_root()) as temp_dir:
        request_path = Path(temp_dir) / "request.json"
        result_path = Path(temp_dir) / "result.json"
        request_path.write_text(
            json.dumps(
                {
                    "csv_file": str(Path(csv_file).expanduser().resolve()),
                    "output_folder": str(Path(output_folder).expanduser().resolve()),
                    "settings": asdict(settings),
                    "bodyparts": bodyparts,
                    "result_path": str(result_path),
                }
            ),
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["DLC_GAIT_ALMA_PIPELINE_CHILD"] = "1"
        source_root = str(Path(__file__).resolve().parents[3])
        env["PYTHONPATH"] = source_root if not env.get("PYTHONPATH") else f"{source_root}{os.pathsep}{env['PYTHONPATH']}"
        completed = subprocess.run(
            [str(python_executable), str(Path(__file__).resolve()), "--run-request", str(request_path)],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "ALMA ladder analysis failed.\n"
                f"Python: {python_executable}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
            )
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        return LadderRunResult(
            input_file=Path(payload["input_file"]),
            output_file=Path(payload["output_file"]),
            events=tuple(LadderEvent(**event) for event in payload["events"]),
        )


def _run_request(request_path: Path) -> None:
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    result = _run_in_process(
        Path(payload["csv_file"]),
        Path(payload["output_folder"]),
        LadderSettings(**payload["settings"]),
        payload.get("bodyparts"),
    )
    Path(payload["result_path"]).write_text(
        json.dumps(
            {
                "input_file": str(result.input_file),
                "output_file": str(result.output_file),
                "events": [asdict(event) for event in result.events],
            }
        ),
        encoding="utf-8",
    )


def _main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--run-request":
        _run_request(Path(sys.argv[2]))
        return
    raise SystemExit("Usage: ladder.py --run-request REQUEST.json")


if __name__ == "__main__":
    _main()
