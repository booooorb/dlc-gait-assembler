from __future__ import annotations

from dataclasses import dataclass

RUSTLAB1_PARAMETER_NAMES = (
    "LB__avg_Angle",
    "LB__max_Angle",
    "LB__min_Angle",
    "RB__avg_Angle",
    "RB__max_Angle",
    "RB__min_Angle",
    "l-back-ankle__Average_Height",
    "l-back-ankle__Movement",
    "l-back-toe__Average_Height",
    "l-hip__Average_Height",
    "l-hip__Movement",
    "l-iliac-crest__Average_Height",
    "l-iliac-crest__Movement",
    "r-back-ankle__Average_Height",
    "r-back-ankle__Movement",
    "r-back-toe__Average_Height",
    "r-hip__Average_Height",
    "r-hip__Movement",
    "r-iliac-crest__Average_Height",
    "r-iliac-crest__Movement",
    "left__back__average",
    "left__back__median",
    "left__back__protraction",
    "left__back__retraction",
    "right__back__average",
    "right__back__median",
    "right__back__protraction",
    "right__back__retraction",
    "left__back__movement_per_step",
    "right__back__movement_per_step",
)

RUSTLAB1_MARKERS = (
    "d-back-left",
    "d-back-right",
    "d-center-back",
    "l-back-ankle",
    "l-back-toe",
    "l-hip",
    "l-iliac-crest",
    "r-back-ankle",
    "r-back-toe",
    "r-hip",
    "r-iliac-crest",
)

RUSTLAB1_FIGURE_FILENAMES = (
    "1_PLOT_bar_all_videos.svg",
    "2_PLOT_Donut_Summary_Validation.svg",
    "3_1_PLOT_control_for_outliers_before.svg",
    "3_2_PLOT_control_for_outliers_after.svg",
    "4_1_PLOT_Overview_Distribution_X.svg",
    "4_2_PLOT_Overview_Distribution_Y.svg",
    "5_PLOT_overview_steps.svg",
    "6_1_PLOT_DOWN_Analysis_Speed_QC.svg",
    "6_2_sync_plots.svg",
    "7_1_PLOT_FIRST_OVERVIEW_VERTICAL_BARPLOT.svg",
    "7.2_PLOT_SECOND_OVERVIEW_Vertical_TIMECOURSE.svg",
    "8_1_PLOT_Horizontal_Analysis_QC.svg",
    "8.2_PLOT_Protraction_Retraction.svg",
    "8_3_PLOT_Protraction_Retraction_line.svg",
    "9_1_PLOT_DURATION_of_STEPE.svg",
    "9_2_PLOT_Distance_covered_per_step.svg",
    "10_1_PLOT_selected_horizontal_Angle.svg",
    "10_2_PLOT_horizontal_Angle_line.svg",
)


@dataclass(frozen=True)
class RustLab1Extraction:
    dataframe: object | None
    available_parameters: tuple[str, ...]
    missing_markers: tuple[str, ...]
    pixels_per_cm: float | None
    calibration_source: str


def extract_rustlab1_parameters(
    raw_dataframe,
    alma_parameters,
    settings,
    kinematics,
) -> RustLab1Extraction:
    """Calculate the SOP's 30 RustLab1 features on ALMA gait-cycle rows.

    The modified RustLab1 R script summarizes whole videos. Here the same
    calculations are evaluated inside ALMA's stride_start/stride_end windows,
    which gives both outputs an identical row/cycle index as required by the
    SOP's merge step.
    """
    import numpy as np

    columns = coordinate_columns(raw_dataframe)
    present_markers = {marker for marker, _coord in columns}
    if not present_markers.intersection(RUSTLAB1_MARKERS):
        return RustLab1Extraction(None, (), RUSTLAB1_MARKERS, None, "not available")

    pixels_per_cm, calibration_source = _resolve_pixels_per_cm(raw_dataframe, columns, settings)
    cycle_keys = [
        name
        for name in ("limb (hind left / right)", "stride_start (frame)", "stride_end (frame)")
        if name in alma_parameters.columns
    ]
    output = alma_parameters.loc[:, cycle_keys].copy().reset_index(drop=True)
    output.insert(0, "gait_cycle", range(1, len(output) + 1))
    output["pixels_per_cm"] = pixels_per_cm
    for parameter in RUSTLAB1_PARAMETER_NAMES:
        output[parameter] = np.nan

    required_series = {
        marker: {
            coord: filtered_series(raw_dataframe, columns, marker, coord, settings, kinematics)
            for coord in ("x", "y")
        }
        for marker in RUSTLAB1_MARKERS
        if (marker, "x") in columns or (marker, "y") in columns
    }

    hip_cycle_means: dict[str, list[float]] = {"left": [], "right": []}
    cycle_groups: list[str] = []
    for row_index, parameter_row in alma_parameters.reset_index(drop=True).iterrows():
        cycle_groups.append(str(parameter_row.get("limb (hind left / right)", "all")))
        bounds = _cycle_bounds(parameter_row, len(raw_dataframe))
        if bounds is None:
            hip_cycle_means["left"].append(np.nan)
            hip_cycle_means["right"].append(np.nan)
            continue
        start, end = bounds
        cycle_slice = slice(start, end + 1)

        _write_down_view_angles(output, row_index, required_series, cycle_slice, np)
        for side, prefix in (("left", "l"), ("right", "r")):
            _write_side_view_features(
                output,
                row_index,
                side,
                prefix,
                required_series,
                cycle_slice,
                pixels_per_cm,
                np,
            )
            hip = _slice(required_series, f"{prefix}-hip", "x", cycle_slice)
            hip_cycle_means[side].append(_safe_stat(np.nanmean, hip, np))

    if pixels_per_cm and pixels_per_cm > 0:
        for side in ("left", "right"):
            previous_by_group: dict[str, float] = {}
            differences: list[float] = []
            for group, mean in zip(cycle_groups, hip_cycle_means[side], strict=True):
                previous = previous_by_group.get(group, np.nan)
                differences.append((mean - previous) / pixels_per_cm if np.isfinite(mean) else np.nan)
                if np.isfinite(mean):
                    previous_by_group[group] = mean
            output[f"{side}__back__movement_per_step"] = differences

    available = tuple(name for name in RUSTLAB1_PARAMETER_NAMES if output[name].notna().any())
    missing = tuple(marker for marker in RUSTLAB1_MARKERS if marker not in present_markers)
    return RustLab1Extraction(output, available, missing, pixels_per_cm, calibration_source)


def coordinate_columns(dataframe) -> dict[tuple[str, str], object]:
    columns: dict[tuple[str, str], object] = {}
    for column in dataframe.columns:
        if isinstance(column, tuple) and len(column) >= 2:
            marker = _canonical_marker(column[0])
            coord = str(column[1]).strip().lower()
        else:
            parts = str(column).rsplit(" ", 1)
            if len(parts) != 2:
                continue
            marker, coord = _canonical_marker(parts[0]), parts[1].strip().lower()
        if coord in {"x", "y", "likelihood"}:
            columns[(marker, coord)] = column
    return columns


def _canonical_marker(value) -> str:
    marker = str(value).strip().lower().replace("_", "-").replace(" ", "-")
    while "--" in marker:
        marker = marker.replace("--", "-")
    aliases = {
        "l-back-toe-tip": "l-back-toe",
        "r-back-toe-tip": "r-back-toe",
        "left-back-toe": "l-back-toe",
        "right-back-toe": "r-back-toe",
        "left-back-ankle": "l-back-ankle",
        "right-back-ankle": "r-back-ankle",
        "left-hip": "l-hip",
        "right-hip": "r-hip",
        "left-iliac-crest": "l-iliac-crest",
        "right-iliac-crest": "r-iliac-crest",
    }
    return aliases.get(marker, marker)


def filtered_series(dataframe, columns, marker, coord, settings, kinematics):
    import numpy as np
    import pandas as pd

    column = columns.get((marker, coord))
    if column is None:
        return None
    values = pd.to_numeric(dataframe[column], errors="coerce").astype(float)
    likelihood_column = columns.get((marker, "likelihood"))
    if likelihood_column is not None:
        likelihood = pd.to_numeric(dataframe[likelihood_column], errors="coerce")
        values = values.mask(likelihood < 0.95)
    values = values.interpolate(limit_direction="both")
    array = values.to_numpy(dtype=float)
    if np.count_nonzero(np.isfinite(array)) < 2:
        return array
    try:
        return np.asarray(
            kinematics.butterworth_filter(array, settings.frame_rate, settings.filter_cutoff),
            dtype=float,
        )
    except (ValueError, TypeError):
        # Very short clips cannot satisfy scipy.filtfilt's padding requirement.
        return array


def _resolve_pixels_per_cm(dataframe, columns, settings) -> tuple[float | None, str]:
    import numpy as np
    import pandas as pd

    if settings.calibration_method == "manual" and settings.pixels_per_cm:
        return float(settings.pixels_per_cm), "manual calibration"

    first, second = settings.reference_segment.split("_", 1)
    aliases = {"toe": "back-toe", "mtp": "back-mtp", "ankle": "back-ankle", "knee": "back-knee"}
    first, second = aliases.get(first, first), aliases.get(second, second)
    for prefix in ("l", "r"):
        marker_a, marker_b = f"{prefix}-{first}", f"{prefix}-{second}"
        required = [(marker_a, "x"), (marker_a, "y"), (marker_b, "x"), (marker_b, "y")]
        if not all(key in columns for key in required):
            continue
        arrays = [pd.to_numeric(dataframe[columns[key]], errors="coerce").to_numpy(float) for key in required]
        distance = np.sqrt((arrays[0] - arrays[2]) ** 2 + (arrays[1] - arrays[3]) ** 2)
        likelihoods = []
        for marker in (marker_a, marker_b):
            likelihood_column = columns.get((marker, "likelihood"))
            if likelihood_column is not None:
                likelihoods.append(pd.to_numeric(dataframe[likelihood_column], errors="coerce").to_numpy(float))
        valid = np.isfinite(distance)
        for likelihood in likelihoods:
            valid &= likelihood >= 0.9
        if np.count_nonzero(valid):
            value = float(np.nanmedian(distance[valid]) / settings.reference_length_cm)
            return value, f"{prefix}-{settings.reference_segment} reference"

    if settings.pixels_per_cm:
        return float(settings.pixels_per_cm), "configured pixel ratio fallback"
    return 49.143, "ALMA 49.143 px/cm fallback (reference markers unavailable)"


def _cycle_bounds(row, frame_count: int) -> tuple[int, int] | None:
    try:
        start = int(float(row["stride_start (frame)"]))
        end = int(float(row["stride_end (frame)"]))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if frame_count <= 0 or end < start:
        return None
    start = max(0, min(start, frame_count - 1))
    end = max(start, min(end, frame_count - 1))
    return start, end


def _write_down_view_angles(output, row_index, series, cycle_slice, np) -> None:
    center_x = _slice(series, "d-center-back", "x", cycle_slice)
    center_y = _slice(series, "d-center-back", "y", cycle_slice)
    for label, marker in (("LB", "d-back-left"), ("RB", "d-back-right")):
        paw_x = _slice(series, marker, "x", cycle_slice)
        paw_y = _slice(series, marker, "y", cycle_slice)
        if any(value is None for value in (center_x, center_y, paw_x, paw_y)):
            continue
        angle = np.abs(np.degrees(np.arctan2(paw_y - center_y, paw_x - center_x)))
        angle = np.where(angle > 90.0, angle - 90.0, angle)
        output.at[row_index, f"{label}__avg_Angle"] = _safe_stat(np.nanmean, angle, np)
        output.at[row_index, f"{label}__max_Angle"] = _safe_percentile(angle, 95, np)
        output.at[row_index, f"{label}__min_Angle"] = _safe_percentile(angle, 10, np)


def _write_side_view_features(output, row_index, side, prefix, series, cycle_slice, pixels_per_cm, np) -> None:
    if not pixels_per_cm or pixels_per_cm <= 0:
        return
    millimeters_per_pixel = 10.0 / pixels_per_cm
    for marker_suffix in ("back-ankle", "back-toe", "hip", "iliac-crest"):
        marker = f"{prefix}-{marker_suffix}"
        y = _slice(series, marker, "y", cycle_slice)
        if y is None or not np.isfinite(y).any():
            continue
        # RustLab1 flips the left mirror view before calculating its heights.
        oriented_y = -y if prefix == "l" else y
        average_height = (np.nanmean(oriented_y) - np.nanmin(oriented_y)) * millimeters_per_pixel
        movement = (np.nanmax(oriented_y) - np.nanmin(oriented_y)) * millimeters_per_pixel
        output.at[row_index, f"{marker}__Average_Height"] = average_height
        movement_name = f"{marker}__Movement"
        if movement_name in output.columns:
            output.at[row_index, movement_name] = movement

    toe_x = _slice(series, f"{prefix}-back-toe", "x", cycle_slice)
    hip_x = _slice(series, f"{prefix}-hip", "x", cycle_slice)
    if toe_x is None or hip_x is None:
        return
    distance_mm = (toe_x - hip_x) * millimeters_per_pixel
    output.at[row_index, f"{side}__back__average"] = _safe_stat(np.nanmean, distance_mm, np)
    output.at[row_index, f"{side}__back__median"] = _safe_stat(np.nanmedian, distance_mm, np)
    output.at[row_index, f"{side}__back__protraction"] = _safe_percentile(distance_mm, 95, np)
    output.at[row_index, f"{side}__back__retraction"] = _safe_percentile(distance_mm, 5, np)


def _slice(series, marker, coord, cycle_slice):
    marker_series = series.get(marker)
    if not marker_series:
        return None
    values = marker_series.get(coord)
    return None if values is None else values[cycle_slice]


def _safe_stat(function, values, np) -> float:
    if values is None or not np.isfinite(values).any():
        return np.nan
    return float(function(values))


def _safe_percentile(values, percentile, np) -> float:
    if values is None or not np.isfinite(values).any():
        return np.nan
    return float(np.nanpercentile(values, percentile))

