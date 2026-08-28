from __future__ import annotations

from dataclasses import dataclass

RUSTLAB1_HINDLIMB_PARAMETER_NAMES = (
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

RUSTLAB1_FORELIMB_PARAMETER_NAMES = (
    "LF__avg_Angle",
    "LF__max_Angle",
    "LF__min_Angle",
    "RF__avg_Angle",
    "RF__max_Angle",
    "RF__min_Angle",
    "l-front-toe-tip__Average_Height",
    "l-front-toe-tip__Movement",
    "l-wrist__Average_Height",
    "l-wrist__Movement",
    "l-elbow__Average_Height",
    "l-elbow__Movement",
    "l-shoulder__Average_Height",
    "l-shoulder__Movement",
    "r-front-toe-tip__Average_Height",
    "r-front-toe-tip__Movement",
    "r-wrist__Average_Height",
    "r-wrist__Movement",
    "r-elbow__Average_Height",
    "r-elbow__Movement",
    "r-shoulder__Average_Height",
    "r-shoulder__Movement",
    "left__front__average",
    "left__front__median",
    "left__front__protraction",
    "left__front__retraction",
    "right__front__average",
    "right__front__median",
    "right__front__protraction",
    "right__front__retraction",
    "avg_Angle__left__front__shoulder_ellbow_wrist",
    "max_Angle__left__front__shoulder_ellbow_wrist",
    "min_Angle__left__front__shoulder_ellbow_wrist",
    "avg_Angle__left__front__ellbow_wrist_toetip",
    "max_Angle__left__front__ellbow_wrist_toetip",
    "min_Angle__left__front__ellbow_wrist_toetip",
    "avg_Angle__right__front__shoulder_ellbow_wrist",
    "max_Angle__right__front__shoulder_ellbow_wrist",
    "min_Angle__right__front__shoulder_ellbow_wrist",
    "avg_Angle__right__front__ellbow_wrist_toetip",
    "max_Angle__right__front__ellbow_wrist_toetip",
    "min_Angle__right__front__ellbow_wrist_toetip",
    "left__front__seconds",
    "right__front__seconds",
    "FLBR_RATIO",
    "FRBL_RATIO",
)

RUSTLAB1_PARAMETER_NAMES = RUSTLAB1_HINDLIMB_PARAMETER_NAMES + RUSTLAB1_FORELIMB_PARAMETER_NAMES

RUSTLAB1_HINDLIMB_MARKERS = (
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

RUSTLAB1_FORELIMB_MARKERS = (
    "d-center-front",
    "d-front-left",
    "d-front-right",
    "l-front-toe-tip",
    "l-wrist",
    "l-elbow",
    "l-shoulder",
    "r-front-toe-tip",
    "r-wrist",
    "r-elbow",
    "r-shoulder",
)

RUSTLAB1_MARKERS = RUSTLAB1_HINDLIMB_MARKERS + RUSTLAB1_FORELIMB_MARKERS

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

CUSTOM_SOP_PARAMETER_NAMES = (
    "mean_hindlimb_base_support",
    "variance_hindlimb_base_support",
    "left_hindpaw_midline_distance",
    "right_hindpaw_midline_distance",
    "left_right_hindlimb_phase_offset",
    "hindlimb_stance_overlap_fraction",
    "left_mtp_average_height",
    "left_mtp_vertical_excursion",
    "right_mtp_average_height",
    "right_mtp_vertical_excursion",
    "left_knee_average_height",
    "left_knee_vertical_excursion",
    "right_knee_average_height",
    "right_knee_vertical_excursion",
)

CUSTOM_SOP_MARKERS = (
    "d-back-left",
    "d-back-right",
    "d-center-back",
    "l-back-mtp",
    "l-back-knee",
    "r-back-mtp",
    "r-back-knee",
)


@dataclass(frozen=True)
class RustLab1Extraction:
    dataframe: object | None
    available_parameters: tuple[str, ...]
    missing_markers: tuple[str, ...]
    pixels_per_cm: float | None
    calibration_source: str


@dataclass(frozen=True)
class CustomSopExtraction:
    dataframe: object
    available_parameters: tuple[str, ...]
    missing_markers: tuple[str, ...]


@dataclass(frozen=True)
class AlmaPreprocessedCoordinates:
    """Coordinate series prepared with ALMA's configured filtering contract."""

    columns: dict[tuple[str, str], object]
    series: dict[str, dict[str, object | None]]
    frame_count: int
    likelihood_threshold: float
    frame_rate: float
    filter_cutoff: float


def prepare_alma_coordinates(
    raw_dataframe,
    settings,
    kinematics,
    markers: tuple[str, ...] | None = None,
) -> AlmaPreprocessedCoordinates:
    """Confidence-filter, interpolate, and low-pass-filter marker coordinates.

    This is the shared preprocessing boundary for ALMA-adjacent RustLab1 and
    custom measures. It deliberately uses the same likelihood cutoff, frame
    rate, Butterworth implementation, and cutoff frequency configured for
    ALMA, and it computes every coordinate series only once.
    """
    columns = coordinate_columns(raw_dataframe)
    selected_markers = (
        tuple(dict.fromkeys(markers))
        if markers is not None
        else tuple(dict.fromkeys(marker for marker, _coord in columns))
    )
    series = {
        marker: {
            coord: filtered_series(raw_dataframe, columns, marker, coord, settings, kinematics)
            for coord in ("x", "y")
        }
        for marker in selected_markers
        if (marker, "x") in columns or (marker, "y") in columns
    }
    return AlmaPreprocessedCoordinates(
        columns=columns,
        series=series,
        frame_count=len(raw_dataframe),
        likelihood_threshold=float(getattr(settings, "likelihood_threshold", 0.0) or 0.0),
        frame_rate=float(settings.frame_rate),
        filter_cutoff=float(settings.filter_cutoff),
    )


def extract_rustlab1_parameters(
    raw_dataframe,
    alma_parameters,
    settings,
    kinematics,
    preprocessed: AlmaPreprocessedCoordinates | None = None,
) -> RustLab1Extraction:
    """Calculate the selected RustLab1 limb features on ALMA gait-cycle rows.

    The modified RustLab1 R script summarizes whole videos. Here the same
    calculations are evaluated inside ALMA's stride_start/stride_end windows,
    which gives both outputs an identical row/cycle index as required by the
    SOP's merge step.
    """
    import numpy as np

    preprocessed = preprocessed or prepare_alma_coordinates(
        raw_dataframe,
        settings,
        kinematics,
        rustlab1_markers_for_scope(getattr(settings, "limb_scope", "Hindlimb")),
    )
    _validate_preprocessed_coordinates(preprocessed, raw_dataframe, settings)
    columns = preprocessed.columns
    present_markers = {marker for marker, _coord in columns}
    limb_scope = getattr(settings, "limb_scope", "Hindlimb")
    parameter_names = rustlab1_parameter_names_for_scope(limb_scope)
    required_markers = rustlab1_markers_for_scope(limb_scope)
    if not present_markers.intersection(required_markers):
        return RustLab1Extraction(None, (), required_markers, None, "not available")

    pixels_per_cm, calibration_source = _resolve_pixels_per_cm(raw_dataframe, columns, settings)
    cycle_keys = [
        name
        for name in ("limb (hind left / right)", "stride_start (frame)", "stride_end (frame)")
        if name in alma_parameters.columns
    ]
    output = alma_parameters.loc[:, cycle_keys].copy().reset_index(drop=True)
    output.insert(0, "gait_cycle", range(1, len(output) + 1))
    output["pixels_per_cm"] = pixels_per_cm
    enabled_parameters = _enabled_parameters(settings, parameter_names)
    for parameter in enabled_parameters:
        output[parameter] = np.nan

    required_series = {
        marker: preprocessed.series[marker]
        for marker in required_markers
        if marker in preprocessed.series
    }
    bottom_stance = {
        marker: _rustlab1_stance_mask(required_series, marker, np)
        for marker in ("d-front-left", "d-front-right", "d-back-left", "d-back-right")
        if marker in required_series
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
        _write_interlimb_coordination(output, row_index, bottom_stance, cycle_slice, np)
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
            _write_forelimb_side_angles(
                output,
                row_index,
                side,
                prefix,
                required_series,
                cycle_slice,
                np,
            )
            duration_name = f"{side}__front__seconds"
            if duration_name in output.columns:
                output.at[row_index, duration_name] = _step_duration_seconds(
                    bottom_stance.get(f"d-front-{side}"),
                    start,
                    end,
                    float(settings.frame_rate),
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
            movement_name = f"{side}__back__movement_per_step"
            if movement_name in output.columns:
                output[movement_name] = differences

    available = tuple(name for name in enabled_parameters if output[name].notna().any())
    missing = tuple(marker for marker in required_markers if marker not in present_markers)
    return RustLab1Extraction(output, available, missing, pixels_per_cm, calibration_source)


def rustlab1_parameter_names_for_scope(limb_scope: str) -> tuple[str, ...]:
    if str(limb_scope).strip().casefold() == "hindlimb + forelimb".casefold():
        return RUSTLAB1_PARAMETER_NAMES
    return RUSTLAB1_HINDLIMB_PARAMETER_NAMES


def rustlab1_markers_for_scope(limb_scope: str) -> tuple[str, ...]:
    if str(limb_scope).strip().casefold() == "hindlimb + forelimb".casefold():
        return RUSTLAB1_MARKERS
    return RUSTLAB1_HINDLIMB_MARKERS


def extract_custom_sop_parameters(
    raw_dataframe,
    alma_parameters,
    settings,
    kinematics,
    preprocessed: AlmaPreprocessedCoordinates | None = None,
) -> CustomSopExtraction:
    """Calculate the SOP's 14 custom measures on ALMA gait-cycle windows."""
    import numpy as np

    preprocessed = preprocessed or prepare_alma_coordinates(
        raw_dataframe,
        settings,
        kinematics,
        CUSTOM_SOP_MARKERS,
    )
    _validate_preprocessed_coordinates(preprocessed, raw_dataframe, settings)
    columns = preprocessed.columns
    present_markers = {marker for marker, _coord in columns}
    scalar_scale, _source = _resolve_pixels_per_cm(raw_dataframe, columns, settings)
    bottom_x_scale = _configured_axis_scale(settings, "bottom", "x", scalar_scale)
    bottom_y_scale = _configured_axis_scale(settings, "bottom", "y", scalar_scale)
    side_y_scales = {side: _configured_axis_scale(settings, side, "y", scalar_scale) for side in ("left", "right")}
    required_series = {
        marker: preprocessed.series[marker]
        for marker in CUSTOM_SOP_MARKERS
        if marker in preprocessed.series
    }
    left_stance = _stance_mask(
        required_series,
        "d-back-left",
        bottom_x_scale,
        bottom_y_scale,
        settings,
        np,
    )
    right_stance = _stance_mask(
        required_series,
        "d-back-right",
        bottom_x_scale,
        bottom_y_scale,
        settings,
        np,
    )

    cycle_keys = [
        name
        for name in ("limb (hind left / right)", "stride_start (frame)", "stride_end (frame)")
        if name in alma_parameters.columns
    ]
    output = alma_parameters.loc[:, cycle_keys].copy().reset_index(drop=True)
    output.insert(0, "gait_cycle", range(1, len(output) + 1))
    enabled_parameters = _enabled_parameters(settings, CUSTOM_SOP_PARAMETER_NAMES)
    for parameter in enabled_parameters:
        output[parameter] = np.nan

    for row_index, parameter_row in alma_parameters.reset_index(drop=True).iterrows():
        bounds = _cycle_bounds(parameter_row, len(raw_dataframe))
        if bounds is None:
            continue
        start, end = bounds
        cycle_slice = slice(start, end + 1)
        duration = end - start + 1
        left_cycle_stance = _mask_slice(left_stance, cycle_slice, duration, np)
        right_cycle_stance = _mask_slice(right_stance, cycle_slice, duration, np)

        left_x = _slice(required_series, "d-back-left", "x", cycle_slice)
        left_y = _slice(required_series, "d-back-left", "y", cycle_slice)
        right_x = _slice(required_series, "d-back-right", "x", cycle_slice)
        right_y = _slice(required_series, "d-back-right", "y", cycle_slice)
        center_x = _slice(required_series, "d-center-back", "x", cycle_slice)
        center_y = _slice(required_series, "d-center-back", "y", cycle_slice)

        if (
            all(value is not None for value in (left_x, left_y, right_x, right_y, center_x, center_y))
            and bottom_x_scale
            and bottom_y_scale
        ):
            bilateral = left_cycle_stance & right_cycle_stance
            separation = np.sqrt(
                ((left_x - right_x) / bottom_x_scale) ** 2 + ((left_y - right_y) / bottom_y_scale) ** 2
            )
            left_midline = np.sqrt(
                ((left_x - center_x) / bottom_x_scale) ** 2 + ((left_y - center_y) / bottom_y_scale) ** 2
            )
            right_midline = np.sqrt(
                ((right_x - center_x) / bottom_x_scale) ** 2 + ((right_y - center_y) / bottom_y_scale) ** 2
            )
            values = {
                "mean_hindlimb_base_support": _masked_stat(separation, bilateral, np.nanmean, np),
                "variance_hindlimb_base_support": _masked_variance(separation, bilateral, np),
                "left_hindpaw_midline_distance": _masked_stat(left_midline, left_cycle_stance, np.nanmean, np),
                "right_hindpaw_midline_distance": _masked_stat(right_midline, right_cycle_stance, np.nanmean, np),
            }
            for name, value in values.items():
                if name in output.columns:
                    output.at[row_index, name] = value

        right_onsets = np.flatnonzero(right_cycle_stance & ~np.r_[False, right_cycle_stance[:-1]])
        if len(right_onsets):
            if "left_right_hindlimb_phase_offset" in output.columns:
                output.at[row_index, "left_right_hindlimb_phase_offset"] = 100.0 * float(right_onsets[0]) / duration
        if "hindlimb_stance_overlap_fraction" in output.columns:
            output.at[row_index, "hindlimb_stance_overlap_fraction"] = (
                100.0 * float(np.count_nonzero(left_cycle_stance & right_cycle_stance)) / duration
            )

        for side, prefix in (("left", "l"), ("right", "r")):
            for bodypart in ("mtp", "knee"):
                y = _slice(required_series, f"{prefix}-back-{bodypart}", "y", cycle_slice)
                average, excursion = _height_metrics(y, side_y_scales[side], np)
                average_name = f"{side}_{bodypart}_average_height"
                excursion_name = f"{side}_{bodypart}_vertical_excursion"
                if average_name in output.columns:
                    output.at[row_index, average_name] = average
                if excursion_name in output.columns:
                    output.at[row_index, excursion_name] = excursion

    available = tuple(name for name in enabled_parameters if output[name].notna().any())
    missing = tuple(marker for marker in CUSTOM_SOP_MARKERS if marker not in present_markers)
    return CustomSopExtraction(output, available, missing)


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
        "l-front-toe": "l-front-toe-tip",
        "r-front-toe": "r-front-toe-tip",
        "left-front-toe": "l-front-toe-tip",
        "right-front-toe": "r-front-toe-tip",
        "left-front-toe-tip": "l-front-toe-tip",
        "right-front-toe-tip": "r-front-toe-tip",
        "left-wrist": "l-wrist",
        "right-wrist": "r-wrist",
        "left-elbow": "l-elbow",
        "right-elbow": "r-elbow",
        "left-shoulder": "l-shoulder",
        "right-shoulder": "r-shoulder",
        "center-front": "d-center-front",
        "front-center": "d-center-front",
        "front-left": "d-front-left",
        "front-right": "d-front-right",
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
    likelihood_threshold = float(getattr(settings, "likelihood_threshold", 0.0) or 0.0)
    if likelihood_column is not None and likelihood_threshold > 0:
        likelihood = pd.to_numeric(dataframe[likelihood_column], errors="coerce")
        valid = likelihood.ge(likelihood_threshold).fillna(False)
        values = values.mask(~valid)
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


def _validate_preprocessed_coordinates(preprocessed, raw_dataframe, settings) -> None:
    expected = (
        len(raw_dataframe),
        float(getattr(settings, "likelihood_threshold", 0.0) or 0.0),
        float(settings.frame_rate),
        float(settings.filter_cutoff),
    )
    actual = (
        preprocessed.frame_count,
        preprocessed.likelihood_threshold,
        preprocessed.frame_rate,
        preprocessed.filter_cutoff,
    )
    if actual != expected:
        raise ValueError(
            "Preprocessed coordinates do not match the current ALMA frame count or filtering settings."
        )


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
    for label, marker, center in (
        ("LB", "d-back-left", "d-center-back"),
        ("RB", "d-back-right", "d-center-back"),
        ("LF", "d-front-left", "d-center-front"),
        ("RF", "d-front-right", "d-center-front"),
    ):
        center_x = _slice(series, center, "x", cycle_slice)
        center_y = _slice(series, center, "y", cycle_slice)
        paw_x = _slice(series, marker, "x", cycle_slice)
        paw_y = _slice(series, marker, "y", cycle_slice)
        if any(value is None for value in (center_x, center_y, paw_x, paw_y)):
            continue
        angle = np.abs(np.degrees(np.arctan2(paw_y - center_y, paw_x - center_x)))
        angle = np.where(angle > 90.0, angle - 90.0, angle)
        values = {
            f"{label}__avg_Angle": _safe_stat(np.nanmean, angle, np),
            f"{label}__max_Angle": _safe_percentile(angle, 95, np),
            f"{label}__min_Angle": _safe_percentile(angle, 10, np),
        }
        for name, value in values.items():
            if name in output.columns:
                output.at[row_index, name] = value


def _write_side_view_features(output, row_index, side, prefix, series, cycle_slice, pixels_per_cm, np) -> None:
    if not pixels_per_cm or pixels_per_cm <= 0:
        return
    millimeters_per_pixel = 10.0 / pixels_per_cm
    for marker_suffix in (
        "back-ankle",
        "back-toe",
        "hip",
        "iliac-crest",
        "front-toe-tip",
        "wrist",
        "elbow",
        "shoulder",
    ):
        marker = f"{prefix}-{marker_suffix}"
        y = _slice(series, marker, "y", cycle_slice)
        if y is None or not np.isfinite(y).any():
            continue
        # RustLab1 flips the left mirror view before calculating its heights.
        oriented_y = -y if prefix == "l" else y
        average_height = (np.nanmean(oriented_y) - np.nanmin(oriented_y)) * millimeters_per_pixel
        movement = (np.nanmax(oriented_y) - np.nanmin(oriented_y)) * millimeters_per_pixel
        average_name = f"{marker}__Average_Height"
        if average_name in output.columns:
            output.at[row_index, average_name] = average_height
        movement_name = f"{marker}__Movement"
        if movement_name in output.columns:
            output.at[row_index, movement_name] = movement

    for limb, toe_marker, reference_marker in (
        ("back", f"{prefix}-back-toe", f"{prefix}-hip"),
        ("front", f"{prefix}-front-toe-tip", f"{prefix}-shoulder"),
    ):
        toe_x = _slice(series, toe_marker, "x", cycle_slice)
        reference_x = _slice(series, reference_marker, "x", cycle_slice)
        if toe_x is None or reference_x is None:
            continue
        distance_mm = (toe_x - reference_x) * millimeters_per_pixel
        values = {
            f"{side}__{limb}__average": _safe_stat(np.nanmean, distance_mm, np),
            f"{side}__{limb}__median": _safe_stat(np.nanmedian, distance_mm, np),
            f"{side}__{limb}__protraction": _safe_percentile(distance_mm, 95, np),
            f"{side}__{limb}__retraction": _safe_percentile(distance_mm, 5, np),
        }
        for name, value in values.items():
            if name in output.columns:
                output.at[row_index, name] = value


def _write_forelimb_side_angles(output, row_index, side, prefix, series, cycle_slice, np) -> None:
    points = {
        name: (
            _slice(series, f"{prefix}-{name}", "x", cycle_slice),
            _slice(series, f"{prefix}-{name}", "y", cycle_slice),
        )
        for name in ("shoulder", "elbow", "wrist", "front-toe-tip")
    }
    angle_definitions = (
        ("shoulder_ellbow_wrist", "elbow", "wrist", "shoulder"),
        ("ellbow_wrist_toetip", "wrist", "front-toe-tip", "elbow"),
    )
    for joint_name, center_name, first_name, second_name in angle_definitions:
        arrays = (*points[center_name], *points[first_name], *points[second_name])
        if any(value is None for value in arrays):
            continue
        center_x, center_y = points[center_name]
        first_x, first_y = points[first_name]
        second_x, second_y = points[second_name]
        if prefix == "l":
            # RustLab1 mirrors the left side-view y-axis before calculating
            # joint angles. The +1506 translation in the R notebook cancels
            # in vector differences, so only the sign inversion is needed.
            center_y, first_y, second_y = -center_y, -first_y, -second_y
        angle = np.degrees(
            np.arctan2(first_y - center_y, first_x - center_x)
            - np.arctan2(second_y - center_y, second_x - center_x)
        )
        angle = angle[np.isfinite(angle) & (angle < 180.0)]
        # RustLab1 summarizes the signed joint angle first and applies abs() to
        # each summary value afterwards (Runway_Analysis.Rmd, section 9.1).
        values = {
            f"avg_Angle__{side}__front__{joint_name}": abs(_safe_stat(np.nanmean, angle, np)),
            f"max_Angle__{side}__front__{joint_name}": abs(_safe_percentile(angle, 95, np)),
            f"min_Angle__{side}__front__{joint_name}": abs(_safe_percentile(angle, 10, np)),
        }
        for name, value in values.items():
            if name in output.columns:
                output.at[row_index, name] = value


def _rustlab1_stance_mask(series, marker, np):
    x = _slice(series, marker, "x", slice(None))
    if x is None or len(x) == 0:
        return None
    speed = np.abs(np.diff(x, prepend=x[0]))
    stance = np.isfinite(speed) & (speed <= 7.0)
    if len(stance) > 1:
        stance[0] = stance[1]
    return stance


def _write_interlimb_coordination(output, row_index, stance_masks, cycle_slice, np) -> None:
    if not {"FLBR_RATIO", "FRBL_RATIO"}.intersection(output.columns):
        return
    markers = ("d-front-left", "d-front-right", "d-back-left", "d-back-right")
    if any(stance_masks.get(marker) is None for marker in markers):
        return
    fl, fr, bl, br = (np.asarray(stance_masks[marker][cycle_slice], dtype=bool) for marker in markers)
    length = min(map(len, (fl, fr, bl, br)))
    if length == 0:
        return
    fl, fr, bl, br = (values[:length] for values in (fl, fr, bl, br))
    included = ~(fl & fr & bl & br)
    if not np.any(included):
        return
    if "FLBR_RATIO" in output.columns:
        output.at[row_index, "FLBR_RATIO"] = float(np.mean(fl[included] != br[included]))
    if "FRBL_RATIO" in output.columns:
        output.at[row_index, "FRBL_RATIO"] = float(np.mean(fr[included] != bl[included]))


def _step_duration_seconds(stance, start: int, end: int, frame_rate: float, np) -> float:
    if stance is None or frame_rate <= 0:
        return np.nan
    stance = np.asarray(stance, dtype=bool)
    onsets = np.flatnonzero(stance & ~np.r_[False, stance[:-1]])
    if len(onsets) < 2:
        return np.nan
    intervals = np.diff(onsets).astype(float) / frame_rate
    overlaps = (onsets[:-1] <= end) & (onsets[1:] >= start)
    return _safe_stat(np.nanmedian, intervals[overlaps], np)


def _enabled_parameters(settings, available: tuple[str, ...]) -> tuple[str, ...]:
    selected = getattr(settings, "enabled_parameter_names", None)
    if selected is None:
        return available
    selected_set = set(selected)
    return tuple(name for name in available if name in selected_set)


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


def _configured_axis_scale(settings, view: str, axis: str, fallback):
    configured = (settings.view_calibration or {}).get(view)
    if isinstance(configured, (int, float)) and float(configured) > 0:
        return float(configured)
    if isinstance(configured, dict):
        value = configured.get(f"{axis}_pixels_per_cm", configured.get("pixels_per_cm"))
        if value and float(value) > 0:
            return float(value)
    return float(fallback) if fallback and float(fallback) > 0 else None


def _stance_mask(series, marker, x_scale, y_scale, settings, np):
    x = _slice(series, marker, "x", slice(None))
    y = _slice(series, marker, "y", slice(None))
    if x is None or y is None or not x_scale or not y_scale:
        return None
    dx = np.diff(x, prepend=np.nan) / float(x_scale)
    dy = np.diff(y, prepend=np.nan) / float(y_scale)
    speed = np.sqrt(dx**2 + dy**2) * float(settings.frame_rate)
    stance = np.isfinite(speed) & (speed <= float(settings.swing_speed_threshold_cm_s))
    if len(stance) > 1:
        stance[0] = stance[1]
    return stance


def _mask_slice(mask, cycle_slice, duration: int, np):
    if mask is None:
        return np.zeros(duration, dtype=bool)
    output = np.asarray(mask[cycle_slice], dtype=bool)
    if len(output) == duration:
        return output
    padded = np.zeros(duration, dtype=bool)
    padded[: min(duration, len(output))] = output[:duration]
    return padded


def _masked_stat(values, mask, function, np):
    selected = np.asarray(values, dtype=float)[np.asarray(mask, dtype=bool)]
    return _safe_stat(function, selected, np)


def _masked_variance(values, mask, np):
    selected = np.asarray(values, dtype=float)[np.asarray(mask, dtype=bool)]
    selected = selected[np.isfinite(selected)]
    return float(np.var(selected, ddof=1)) if len(selected) > 1 else np.nan


def _height_metrics(values, pixels_per_cm, np):
    if values is None or not pixels_per_cm or float(pixels_per_cm) <= 0:
        return np.nan, np.nan
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if len(finite) == 0:
        return np.nan, np.nan
    height = (float(np.max(finite)) - finite) / float(pixels_per_cm)
    return float(np.mean(height)), float(np.max(height) - np.min(height))
