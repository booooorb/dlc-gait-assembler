"""Synchronized, animal-aware outputs for longitudinal stroke gait studies."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from dlc_gait_assembly.services.pipeline.alma.models import (
    AlmaSettings,
    AlmaViewCsvSet,
    StrokeStudyMetadata,
)
from dlc_gait_assembly.services.pipeline.alma.multiview import (
    merge_multiview_rustlab1_dataframe,
)
from dlc_gait_assembly.services.pipeline.rustlab1.extraction import (
    RUSTLAB1_PARAMETER_NAMES,
    coordinate_columns,
    extract_rustlab1_parameters,
)

CUSTOM_STROKE_PARAMETER_NAMES = (
    "mean_hindlimb_base_support",
    "variance_hindlimb_base_support",
    "left_hindpaw_midline_distance",
    "right_hindpaw_midline_distance",
    "left_right_hindlimb_phase_offset",
    "hindlimb_stance_overlap_fraction",
)

ASYMMETRY_PARAMETER_NAMES = (
    "step_height_asymmetry",
    "stride_length_asymmetry",
    "stance_percentage_asymmetry",
    "knee_range_of_motion_asymmetry",
    "protraction_retraction_excursion_asymmetry",
    "dragging_percentage_asymmetry",
)

PRIMARY_STROKE_PARAMETER_NAMES = (
    "hindlimb_phase_offset_deviation_from_baseline",
    "hindlimb_stance_overlap_fraction",
    "step_height_asymmetry",
    "stride_length_asymmetry",
    "knee_range_of_motion_asymmetry",
    "protraction_retraction_excursion_asymmetry",
)

IDENTIFIER_COLUMNS = (
    "animal_id",
    "group",
    "sex",
    "lesion_hemisphere",
    "timepoint",
    "trial",
    "session_id",
    "cycle_id",
)

CANONICAL_CYCLE_COLUMNS = (
    *IDENTIFIER_COLUMNS,
    "contralesional_side",
    "ipsilesional_side",
    "frame_rate_hz",
    "bottom_x_pixels_per_cm",
    "bottom_y_pixels_per_cm",
    "calibration_source",
    "left_calibration_source",
    "right_calibration_source",
    "left_view_csv",
    "right_view_csv",
    "bottom_view_csv",
    "stride_start (frame)",
    "stride_end (frame)",
    "left_stance_start_frame",
    "left_stance_end_frame",
    "right_stance_start_frame",
    "right_stance_end_frame",
    "cycle_duration_frames",
    "left_right_hindlimb_phase_offset",
    "hindlimb_stance_overlap_fraction",
    "tracking_coverage",
    "mean_speed_cm_s",
    "speed_cv",
    "cycle_valid",
    "rejection_reason",
)

_ALMA_ASYMMETRY_COLUMNS = {
    "step_height_asymmetry": "step height (cm)",
    "stride_length_asymmetry": "stride length (cm)",
    "stance_percentage_asymmetry": "stance percentage (%)",
    "knee_range_of_motion_asymmetry": "knee joint amplitude (deg)",
    "dragging_percentage_asymmetry": "drag percentage (%)",
}


@dataclass(frozen=True)
class StrokeOutputBundle:
    canonical_cycles: Path
    stride_features: Path
    session_summary: Path
    primary_stroke_panel: Path
    feature_dictionary: Path
    qc_report: Path
    messages: tuple[str, ...] = ()

    @property
    def output_files(self) -> tuple[Path, ...]:
        return (
            self.canonical_cycles,
            self.stride_features,
            self.session_summary,
            self.primary_stroke_panel,
            self.feature_dictionary,
            self.qc_report,
        )


def generate_stroke_analysis_outputs(
    view_set: AlmaViewCsvSet,
    output_folder: Path,
    settings: AlmaSettings,
    left_parameters,
    right_parameters,
    view_mappings,
    kinematics,
    pd,
) -> StrokeOutputBundle:
    """Generate synchronized multi-view feature tables for one recording."""

    import numpy as np

    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    merged = merge_multiview_rustlab1_dataframe(view_set, pd, view_mappings)
    metadata, metadata_warnings = _resolved_metadata(view_set)
    calibration = _view_calibration(settings, "bottom")
    messages = list(metadata_warnings)

    if calibration is None:
        raise ValueError(
            "Stroke analysis requires a bottom-view pixel calibration. "
            "Set pixels_per_cm or view_calibration['bottom']; no scientific fallback is used."
        )

    trajectories, trajectory_qc = _bottom_trajectories(
        merged,
        settings,
        calibration,
        kinematics,
        pd,
        np,
    )
    cycles = detect_canonical_cycles(trajectories, settings, metadata, pd, np)
    cycles["frame_rate_hz"] = float(settings.frame_rate)
    cycles["bottom_x_pixels_per_cm"] = float(calibration["x_pixels_per_cm"])
    cycles["bottom_y_pixels_per_cm"] = float(calibration["y_pixels_per_cm"])
    cycles["calibration_source"] = calibration["source"]
    cycles["left_calibration_source"] = _side_calibration_source(settings, "left")
    cycles["right_calibration_source"] = _side_calibration_source(settings, "right")
    cycles["left_view_csv"] = str(Path(view_set.left_csv).expanduser().resolve())
    cycles["right_view_csv"] = str(Path(view_set.right_csv).expanduser().resolve())
    cycles["bottom_view_csv"] = str(Path(view_set.bottom_csv).expanduser().resolve())
    cycles = cycles.reindex(columns=CANONICAL_CYCLE_COLUMNS)
    valid_count = int(cycles["cycle_valid"].sum()) if len(cycles) else 0
    session_usable = valid_count >= int(settings.minimum_synchronized_cycles)
    cycles["session_usable"] = session_usable

    left_aligned = align_parameters_to_cycles(cycles, left_parameters, "left", pd, np)
    right_aligned = align_parameters_to_cycles(cycles, right_parameters, "right", pd, np)
    cycle_bounds = cycles.loc[
        :,
        ["cycle_id", "stride_start (frame)", "stride_end (frame)"],
    ].copy()
    cycle_bounds["limb (hind left / right)"] = "left"
    rustlab = extract_rustlab1_parameters(merged, cycle_bounds, settings, kinematics)
    if rustlab.dataframe is None:
        rustlab_features = pd.DataFrame(
            np.nan,
            index=range(len(cycles)),
            columns=list(RUSTLAB1_PARAMETER_NAMES),
        )
        messages.append("RustLab1 features unavailable: required side/down markers were not found.")
    else:
        rustlab_features = rustlab.dataframe.loc[:, list(RUSTLAB1_PARAMETER_NAMES)].reset_index(drop=True)
        if rustlab.missing_markers:
            messages.append("Missing RustLab1 markers: " + ", ".join(rustlab.missing_markers))

    custom = calculate_stroke_features(cycles, trajectories, calibration, pd, np)
    metadata_frame = _metadata_frame(metadata, cycles, pd)
    stride_features = pd.concat(
        [
            metadata_frame,
            cycles.drop(
                columns=[
                    *[column for column in IDENTIFIER_COLUMNS if column in cycles],
                    "left_right_hindlimb_phase_offset",
                    "hindlimb_stance_overlap_fraction",
                ],
                errors="ignore",
            ),
            left_aligned,
            right_aligned,
            rustlab_features,
            custom,
        ],
        axis=1,
    )
    stride_features = add_asymmetry_features(stride_features, metadata.lesion_hemisphere, np)
    stride_features["hindlimb_phase_offset_deviation_from_baseline"] = np.nan

    session_summary = summarize_session(stride_features, metadata, trajectory_qc, session_usable, pd, np)
    primary_columns = [
        *[column for column in IDENTIFIER_COLUMNS if column in stride_features],
        "cycle_valid",
        "session_usable",
        *PRIMARY_STROKE_PARAMETER_NAMES,
    ]
    primary_panel = stride_features.loc[:, [column for column in primary_columns if column in stride_features]]
    dictionary = build_feature_dictionary(stride_features, pd)

    stem = view_set.name
    paths = {
        "canonical_cycles": output_folder / f"{stem}_canonical_cycles.csv",
        "stride_features": output_folder / f"{stem}_stride_features.csv",
        "session_summary": output_folder / f"{stem}_session_summary.csv",
        "primary_stroke_panel": output_folder / f"{stem}_primary_stroke_panel.csv",
        "feature_dictionary": output_folder / f"{stem}_feature_dictionary.csv",
        "qc_report": output_folder / f"{stem}_qc_report.json",
    }
    cycles.to_csv(paths["canonical_cycles"], index=False)
    stride_features.to_csv(paths["stride_features"], index=False)
    session_summary.to_csv(paths["session_summary"], index=False)
    primary_panel.to_csv(paths["primary_stroke_panel"], index=False)
    dictionary.to_csv(paths["feature_dictionary"], index=False)

    qc_payload = {
        "schema_version": 1,
        "metadata": asdict(metadata),
        "view_assignment": {
            "left": str(view_set.left_csv),
            "right": str(view_set.right_csv),
            "bottom": str(view_set.bottom_csv),
            "middle_assigned_to": "right",
        },
        "calibration": {
            "bottom": calibration,
            "left": _side_calibration_source(settings, "left"),
            "right": _side_calibration_source(settings, "right"),
        },
        "settings": {
            "likelihood_threshold": settings.stroke_likelihood_threshold,
            "filter_cutoff_hz": settings.filter_cutoff,
            "max_interpolation_gap_frames": settings.max_interpolation_gap_frames,
            "swing_speed_threshold_cm_s": settings.swing_speed_threshold_cm_s,
            "minimum_synchronized_cycles": settings.minimum_synchronized_cycles,
        },
        "tracking": trajectory_qc,
        "cycles": {
            "detected": int(len(cycles)),
            "valid": valid_count,
            "rejected": int(len(cycles) - valid_count),
            "session_usable": bool(session_usable),
        },
        "warnings": messages,
    }
    paths["qc_report"].write_text(json.dumps(qc_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not session_usable:
        messages.append(
            f"Stroke pilot QC: only {valid_count} valid synchronized cycles; "
            f"{settings.minimum_synchronized_cycles} required."
        )
    else:
        messages.append(f"Stroke pilot QC: {valid_count} valid synchronized cycles.")

    return StrokeOutputBundle(
        canonical_cycles=paths["canonical_cycles"],
        stride_features=paths["stride_features"],
        session_summary=paths["session_summary"],
        primary_stroke_panel=paths["primary_stroke_panel"],
        feature_dictionary=paths["feature_dictionary"],
        qc_report=paths["qc_report"],
        messages=tuple(messages),
    )


def detect_canonical_cycles(trajectories, settings: AlmaSettings, metadata, pd, np):
    """Detect left-onset cycles and pair the right stance onset by source frame."""

    left_stance = _debounce_boolean(
        trajectories["left_stance"].fillna(False).to_numpy(dtype=bool),
        minimum_run=2,
        np=np,
    )
    right_stance = _debounce_boolean(
        trajectories["right_stance"].fillna(False).to_numpy(dtype=bool),
        minimum_run=2,
        np=np,
    )
    left_onsets = _onsets(left_stance, np)
    right_onsets = _onsets(right_stance, np)
    rows = []
    session_id = metadata.session_id or metadata.animal_id or "session"
    metadata_values = asdict(metadata)
    if metadata.lesion_hemisphere == "right":
        contralesional_side, ipsilesional_side = "left", "right"
    elif metadata.lesion_hemisphere == "left":
        contralesional_side, ipsilesional_side = "right", "left"
    else:
        contralesional_side = ipsilesional_side = "unknown"
    for index, (start, next_start) in enumerate(zip(left_onsets[:-1], left_onsets[1:], strict=True), start=1):
        end = int(next_start) - 1
        right_candidates = right_onsets[(right_onsets >= start) & (right_onsets < next_start)]
        right_start = int(right_candidates[0]) if len(right_candidates) else None
        left_stance_end = _stance_end(left_stance, int(start), end)
        right_stance_end = _stance_end(right_stance, right_start, end) if right_start is not None else None
        coverage = float(
            trajectories.loc[start:end, "required_tracking_valid"].astype(float).mean()
        )
        speed_values = trajectories.loc[start:end, "body_speed_cm_s"].to_numpy(dtype=float)
        finite_speed = speed_values[np.isfinite(speed_values)]
        mean_speed = float(np.nanmean(finite_speed)) if len(finite_speed) else np.nan
        speed_cv = (
            float(np.nanstd(finite_speed, ddof=1) / abs(mean_speed))
            if len(finite_speed) > 1 and mean_speed
            else np.nan
        )
        overlap_frames = _interval_overlap(
            int(start),
            left_stance_end,
            right_start,
            right_stance_end,
        )
        duration_frames = max(1, int(next_start) - int(start))
        row_valid = (
            right_start is not None
            and coverage >= 1.0
            and (not np.isfinite(speed_cv) or speed_cv <= 0.15)
        )
        rejection_reasons = []
        if right_start is None:
            rejection_reasons.append("missing_right_stance_onset")
        if coverage < 1.0:
            rejection_reasons.append("required_marker_gap")
        if np.isfinite(speed_cv) and speed_cv > 0.15:
            rejection_reasons.append("unstable_speed")
        rows.append(
            {
                **metadata_values,
                "session_id": session_id,
                "cycle_id": f"{session_id}:cycle-{index:04d}",
                "contralesional_side": contralesional_side,
                "ipsilesional_side": ipsilesional_side,
                "stride_start (frame)": int(start),
                "stride_end (frame)": end,
                "left_stance_start_frame": int(start),
                "left_stance_end_frame": left_stance_end,
                "right_stance_start_frame": right_start,
                "right_stance_end_frame": right_stance_end,
                "cycle_duration_frames": duration_frames,
                "left_right_hindlimb_phase_offset": (
                    100.0 * (right_start - int(start)) / duration_frames
                    if right_start is not None
                    else np.nan
                ),
                "hindlimb_stance_overlap_fraction": 100.0 * overlap_frames / duration_frames,
                "tracking_coverage": coverage,
                "mean_speed_cm_s": mean_speed,
                "speed_cv": speed_cv,
                "cycle_valid": bool(row_valid),
                "rejection_reason": ";".join(rejection_reasons),
            }
        )
    return pd.DataFrame(rows, columns=CANONICAL_CYCLE_COLUMNS)


def align_parameters_to_cycles(cycles, parameters, side: str, pd, np):
    """One-to-one overlap alignment of an ALMA table to canonical source frames."""

    output = []
    used_rows: set[int] = set()
    parameters = parameters.reset_index(drop=True)
    for _, cycle in cycles.iterrows():
        start = int(cycle["stride_start (frame)"])
        end = int(cycle["stride_end (frame)"])
        best_index = None
        best_iou = 0.0
        for row_index, row in parameters.iterrows():
            if row_index in used_rows:
                continue
            try:
                candidate_start = int(float(row["stride_start (frame)"]))
                candidate_end = int(float(row["stride_end (frame)"]))
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            intersection = max(0, min(end, candidate_end) - max(start, candidate_start) + 1)
            union = max(end, candidate_end) - min(start, candidate_start) + 1
            iou = intersection / union if union else 0.0
            if iou > best_iou:
                best_iou = iou
                best_index = int(row_index)
        if best_index is None or best_iou < 0.5:
            values = {f"{side}__{column}": np.nan for column in parameters.columns}
            values[f"{side}__cycle_match_iou"] = best_iou
            values[f"{side}__cycle_match_valid"] = False
        else:
            used_rows.add(best_index)
            values = {
                f"{side}__{column}": value
                for column, value in parameters.loc[best_index].items()
            }
            values[f"{side}__cycle_match_iou"] = best_iou
            values[f"{side}__cycle_match_valid"] = True
        output.append(values)
    return pd.DataFrame(output)


def calculate_stroke_features(cycles, trajectories, calibration, pd, np):
    """Calculate the six coordination/stability measures selected from the SOP."""

    x_scale = float(calibration["x_pixels_per_cm"])
    y_scale = float(calibration["y_pixels_per_cm"])
    rows = []
    for _, cycle in cycles.iterrows():
        left_start = int(cycle["left_stance_start_frame"])
        left_end = int(cycle["left_stance_end_frame"])
        right_start = cycle["right_stance_start_frame"]
        right_end = cycle["right_stance_end_frame"]
        overlap_start = max(left_start, int(right_start)) if pd.notna(right_start) else None
        overlap_end = min(left_end, int(right_end)) if pd.notna(right_end) else None
        if overlap_start is not None and overlap_end is not None and overlap_end >= overlap_start:
            overlap = trajectories.loc[overlap_start:overlap_end]
            separation = np.sqrt(
                ((overlap["left_x"] - overlap["right_x"]) / x_scale) ** 2
                + ((overlap["left_y"] - overlap["right_y"]) / y_scale) ** 2
            )
        else:
            separation = pd.Series(dtype=float)
        left_slice = trajectories.loc[left_start:left_end]
        right_slice = (
            trajectories.loc[int(right_start):int(right_end)]
            if pd.notna(right_start) and pd.notna(right_end)
            else pd.DataFrame()
        )
        left_midline = _distance_to_center(left_slice, "left", x_scale, y_scale, np)
        right_midline = _distance_to_center(right_slice, "right", x_scale, y_scale, np)
        rows.append(
            {
                "mean_hindlimb_base_support": _safe_mean(separation, np),
                "variance_hindlimb_base_support": _safe_variance(separation, np),
                "left_hindpaw_midline_distance": _safe_mean(left_midline, np),
                "right_hindpaw_midline_distance": _safe_mean(right_midline, np),
                "left_right_hindlimb_phase_offset": cycle["left_right_hindlimb_phase_offset"],
                "hindlimb_stance_overlap_fraction": cycle["hindlimb_stance_overlap_fraction"],
            }
        )
    return pd.DataFrame(rows, columns=CUSTOM_STROKE_PARAMETER_NAMES)


def add_asymmetry_features(dataframe, lesion_hemisphere: str, np):
    result = dataframe.copy()
    if lesion_hemisphere == "right":
        contralesional, ipsilesional = "left", "right"
    elif lesion_hemisphere == "left":
        contralesional, ipsilesional = "right", "left"
    else:
        contralesional = ipsilesional = None

    for output_name, base_name in _ALMA_ASYMMETRY_COLUMNS.items():
        if contralesional is None:
            result[output_name] = np.nan
            continue
        result[output_name] = _normalized_asymmetry(
            result.get(f"{contralesional}__{base_name}"),
            result.get(f"{ipsilesional}__{base_name}"),
            np,
        )

    left_excursion = _column_difference(
        result,
        "left__back__protraction",
        "left__back__retraction",
        np,
    )
    right_excursion = _column_difference(
        result,
        "right__back__protraction",
        "right__back__retraction",
        np,
    )
    if contralesional == "left":
        contra_excursion, ipsi_excursion = left_excursion, right_excursion
    elif contralesional == "right":
        contra_excursion, ipsi_excursion = right_excursion, left_excursion
    else:
        contra_excursion = ipsi_excursion = None
    result["protraction_retraction_excursion_asymmetry"] = _normalized_asymmetry(
        contra_excursion,
        ipsi_excursion,
        np,
    )
    return result


def summarize_session(stride_features, metadata, trajectory_qc, session_usable, pd, np):
    if "cycle_valid" in stride_features:
        valid_strides = stride_features.loc[stride_features["cycle_valid"].fillna(False).astype(bool)]
    else:
        valid_strides = stride_features
    numeric = valid_strides.select_dtypes(include="number")
    medians = numeric.median(axis=0, skipna=True)
    q1 = numeric.quantile(0.25)
    q3 = numeric.quantile(0.75)
    row = asdict(metadata)
    row["valid_cycle_count"] = int(len(valid_strides))
    row["session_usable"] = bool(session_usable)
    row["tracking_coverage"] = float(trajectory_qc["required_tracking_coverage"])
    row["session_speed_cm_s"] = float(valid_strides.get("mean_speed_cm_s", pd.Series(dtype=float)).median())
    row["session_speed_cv"] = float(valid_strides.get("speed_cv", pd.Series(dtype=float)).median())
    for column in numeric:
        row[column] = medians[column]
        row[f"{column}__iqr"] = q3[column] - q1[column]
    return pd.DataFrame([row])


def build_feature_dictionary(stride_features, pd):
    rows = []
    for column in stride_features.columns:
        if column in IDENTIFIER_COLUMNS or column.endswith(("valid", "usable")):
            continue
        family, source, unit, status = _feature_metadata(column)
        rows.append(
            {
                "feature": column,
                "family": family,
                "source": source,
                "unit": unit,
                "analysis_status": status,
                "required_markers": _required_markers(column),
                "formula": _formula(column),
            }
        )
    return pd.DataFrame(rows)


def _bottom_trajectories(merged, settings, calibration, kinematics, pd, np):
    columns = coordinate_columns(merged)
    marker_map = {
        "left": "d-back-left",
        "right": "d-back-right",
        "center": "d-center-back",
    }
    result = pd.DataFrame(index=range(len(merged)))
    coverage = {}
    interpolation_counts = {}
    for label, marker in marker_map.items():
        for coord in ("x", "y"):
            column = columns.get((marker, coord))
            if column is None:
                result[f"{label}_{coord}"] = np.nan
                coverage[f"{marker}_{coord}"] = 0.0
                interpolation_counts[f"{marker}_{coord}"] = 0
                continue
            values = pd.to_numeric(merged[column], errors="coerce").astype(float)
            likelihood_column = columns.get((marker, "likelihood"))
            if likelihood_column is not None:
                likelihood = pd.to_numeric(merged[likelihood_column], errors="coerce")
                values = values.mask(likelihood < settings.stroke_likelihood_threshold)
            original_valid = values.notna()
            interpolated = _interpolate_short_gaps(values, settings.max_interpolation_gap_frames, pd)
            interpolation_counts[f"{marker}_{coord}"] = int((~original_valid & interpolated.notna()).sum())
            coverage[f"{marker}_{coord}"] = float(original_valid.mean())
            result[f"{label}_{coord}"] = _filter_with_gaps(
                interpolated,
                settings.frame_rate,
                settings.filter_cutoff,
                kinematics,
                pd,
                np,
            )

    required = ["left_x", "left_y", "right_x", "right_y", "center_x", "center_y"]
    side_required = []
    for prefix in ("l", "r"):
        for bodypart in ("back-toe", "back-mtp", "back-ankle", "back-knee", "hip", "iliac-crest"):
            marker = f"{prefix}-{bodypart}"
            for coord in ("x", "y"):
                validity_name = f"required__{marker}__{coord}"
                side_required.append(validity_name)
                column = columns.get((marker, coord))
                if column is None:
                    result[validity_name] = False
                    coverage[f"{marker}_{coord}"] = 0.0
                    interpolation_counts[f"{marker}_{coord}"] = 0
                    continue
                values = pd.to_numeric(merged[column], errors="coerce").astype(float)
                likelihood_column = columns.get((marker, "likelihood"))
                if likelihood_column is not None:
                    likelihood = pd.to_numeric(merged[likelihood_column], errors="coerce")
                    values = values.mask(likelihood < settings.stroke_likelihood_threshold)
                original_valid = values.notna()
                interpolated = _interpolate_short_gaps(
                    values,
                    settings.max_interpolation_gap_frames,
                    pd,
                )
                result[validity_name] = interpolated.notna()
                coverage[f"{marker}_{coord}"] = float(original_valid.mean())
                interpolation_counts[f"{marker}_{coord}"] = int(
                    (~original_valid & interpolated.notna()).sum()
                )
    result["required_tracking_valid"] = (
        result[required].notna().all(axis=1)
        & result[side_required].all(axis=1)
    )
    x_scale = float(calibration["x_pixels_per_cm"])
    y_scale = float(calibration["y_pixels_per_cm"])
    for side in ("left", "right"):
        dx = result[f"{side}_x"].diff() / x_scale
        dy = result[f"{side}_y"].diff() / y_scale
        speed = np.sqrt(dx**2 + dy**2) * float(settings.frame_rate)
        result[f"{side}_speed_cm_s"] = speed
        result[f"{side}_stance"] = speed <= float(settings.swing_speed_threshold_cm_s)
    center_dx = result["center_x"].diff() / x_scale
    center_dy = result["center_y"].diff() / y_scale
    result["body_speed_cm_s"] = np.sqrt(center_dx**2 + center_dy**2) * float(settings.frame_rate)
    return result, {
        "marker_coordinate_coverage": coverage,
        "interpolated_samples": interpolation_counts,
        "required_tracking_coverage": float(result["required_tracking_valid"].mean()),
    }


def _resolved_metadata(view_set: AlmaViewCsvSet) -> tuple[StrokeStudyMetadata, tuple[str, ...]]:
    metadata = view_set.metadata or StrokeStudyMetadata()
    values = asdict(metadata)
    missing = [
        field
        for field in ("animal_id", "group", "sex", "timepoint", "trial", "session_id")
        if not str(values[field]).strip()
    ]
    if values["lesion_hemisphere"] not in {"left", "right"}:
        missing.append("lesion_hemisphere")
    if missing:
        raise ValueError(
            "Stroke analysis requires complete study metadata. Missing or unknown: "
            + ", ".join(missing)
            + ". Edit the CSV pairing metadata."
        )
    return StrokeStudyMetadata(**values), ()


def _metadata_frame(metadata, cycles, pd):
    values = asdict(metadata)
    values["animal_id"] = values["animal_id"] or "unknown"
    values["session_id"] = values["session_id"] or "unknown"
    frame = pd.DataFrame([values] * len(cycles))
    frame["cycle_id"] = cycles["cycle_id"].to_numpy() if len(cycles) else []
    return frame


def _view_calibration(settings: AlmaSettings, view: str) -> dict[str, object] | None:
    configured = (settings.view_calibration or {}).get(view)
    if isinstance(configured, (int, float)) and float(configured) > 0:
        value = float(configured)
        return {"x_pixels_per_cm": value, "y_pixels_per_cm": value, "source": f"{view} scalar"}
    if isinstance(configured, dict):
        scalar = configured.get("pixels_per_cm")
        x_value = configured.get("x_pixels_per_cm", scalar)
        y_value = configured.get("y_pixels_per_cm", scalar)
        if x_value and y_value and float(x_value) > 0 and float(y_value) > 0:
            return {
                "x_pixels_per_cm": float(x_value),
                "y_pixels_per_cm": float(y_value),
                "source": f"{view} axis-specific",
            }
    if settings.pixels_per_cm and float(settings.pixels_per_cm) > 0:
        value = float(settings.pixels_per_cm)
        return {"x_pixels_per_cm": value, "y_pixels_per_cm": value, "source": "manual scalar"}
    return None


def _side_calibration_source(settings: AlmaSettings, view: str) -> str:
    configured = (settings.view_calibration or {}).get(view)
    if configured:
        return f"{view} view-specific calibration: {configured}"
    if settings.calibration_method == "reference":
        return (
            f"ALMA anatomical reference: {settings.reference_segment}="
            f"{settings.reference_length_cm:g} cm"
        )
    if settings.pixels_per_cm:
        return f"manual scalar: {float(settings.pixels_per_cm):g} px/cm"
    return "unresolved"


def _interpolate_short_gaps(values, maximum_gap: int, pd):
    values = values.copy()
    missing = values.isna().to_numpy()
    candidate = values.interpolate(method="linear", limit_area="inside")
    for start, end in _true_runs(missing):
        if end - start > int(maximum_gap):
            candidate.iloc[start:end] = float("nan")
    return candidate


def _filter_with_gaps(values, frame_rate, cutoff, kinematics, pd, np):
    output = pd.Series(np.nan, index=values.index, dtype=float)
    valid = values.notna().to_numpy()
    for start, end in _true_runs(valid):
        segment = values.iloc[start:end].to_numpy(dtype=float)
        if len(segment) < 4:
            output.iloc[start:end] = segment
            continue
        try:
            output.iloc[start:end] = kinematics.butterworth_filter(segment, frame_rate, cutoff)
        except (ValueError, TypeError):
            output.iloc[start:end] = segment
    return output


def _debounce_boolean(values, minimum_run: int, np):
    values = np.asarray(values, dtype=bool).copy()
    for start, end in _true_runs(values):
        if end - start < minimum_run:
            values[start:end] = False
    inverse = ~values
    for start, end in _true_runs(inverse):
        if 0 < start and end < len(values) and end - start < minimum_run:
            values[start:end] = True
    return values


def _true_runs(values):
    start = None
    for index, value in enumerate(values):
        if bool(value) and start is None:
            start = index
        elif not bool(value) and start is not None:
            yield start, index
            start = None
    if start is not None:
        yield start, len(values)


def _onsets(stance, np):
    if len(stance) == 0:
        return np.asarray([], dtype=int)
    transitions = np.flatnonzero(stance & ~np.r_[False, stance[:-1]])
    return transitions.astype(int)


def _stance_end(stance, start, maximum):
    if start is None:
        return None
    end = int(start)
    while end < maximum and stance[end + 1]:
        end += 1
    return end


def _interval_overlap(left_start, left_end, right_start, right_end):
    if right_start is None or right_end is None:
        return 0
    return max(0, min(left_end, right_end) - max(left_start, right_start) + 1)


def _distance_to_center(frame, side, x_scale, y_scale, np):
    if frame.empty:
        return np.asarray([], dtype=float)
    return np.sqrt(
        ((frame[f"{side}_x"] - frame["center_x"]) / x_scale) ** 2
        + ((frame[f"{side}_y"] - frame["center_y"]) / y_scale) ** 2
    )


def _normalized_asymmetry(contralesional, ipsilesional, np):
    if contralesional is None or ipsilesional is None:
        return np.nan
    denominator = 0.5 * (contralesional.abs() + ipsilesional.abs())
    return (contralesional - ipsilesional) / denominator.replace(0, np.nan)


def _column_difference(dataframe, minuend: str, subtrahend: str, np):
    if minuend not in dataframe or subtrahend not in dataframe:
        return None
    return dataframe[minuend] - dataframe[subtrahend]


def _safe_mean(values, np):
    array = np.asarray(values, dtype=float)
    return float(np.nanmean(array)) if np.isfinite(array).any() else np.nan


def _safe_variance(values, np):
    array = np.asarray(values, dtype=float)
    return float(np.nanvar(array, ddof=1)) if np.count_nonzero(np.isfinite(array)) > 1 else np.nan


def _feature_metadata(column: str) -> tuple[str, str, str, str]:
    if column in PRIMARY_STROKE_PARAMETER_NAMES:
        return "stroke primary", "multi-view", _unit_for(column), "primary"
    if column in CUSTOM_STROKE_PARAMETER_NAMES or column in ASYMMETRY_PARAMETER_NAMES:
        return "coordination/asymmetry", "multi-view", _unit_for(column), "secondary"
    if column in RUSTLAB1_PARAMETER_NAMES:
        return "RustLab1", "side/bottom", _unit_for(column), "secondary"
    if column.startswith(("left__", "right__")):
        return "ALMA", column.split("__", 1)[0], _unit_for(column), "secondary"
    if "tracking" in column or "match" in column or "speed_cv" in column:
        return "quality control", "multi-view", _unit_for(column), "qc"
    return "cycle", "bottom", _unit_for(column), "exploratory"


def _unit_for(column: str) -> str:
    lowered = column.lower()
    if "asymmetry" in lowered:
        return "unitless"
    if "fraction" in lowered or "percentage" in lowered or "phase_offset" in lowered:
        return "%"
    if "variance_hindlimb" in lowered:
        return "cm^2"
    if "frame" in lowered:
        return "frames"
    if "(s)" in lowered or "duration" in lowered:
        return "s"
    if "speed" in lowered or "velocity" in lowered:
        return "cm/s"
    if "angle" in lowered or "(deg)" in lowered:
        return "deg"
    if "(mm)" in lowered or "average_height" in lowered or "__movement" in lowered:
        return "mm"
    if "support" in lowered or "distance" in lowered or "height" in lowered or "length" in lowered:
        return "cm"
    return ""


def _required_markers(column: str) -> str:
    if column in {
        "mean_hindlimb_base_support",
        "variance_hindlimb_base_support",
        "left_right_hindlimb_phase_offset",
        "hindlimb_stance_overlap_fraction",
    }:
        return "bottom left hindpaw; bottom right hindpaw"
    if "midline" in column:
        return "bottom hindpaw; bottom center back"
    if "asymmetry" in column:
        return "bilateral side-view counterparts"
    if column.startswith(("left__", "right__")):
        return "toe; MTP; ankle; knee; hip; iliac crest"
    if column in RUSTLAB1_PARAMETER_NAMES:
        return "feature-specific side/down-view RustLab1 markers"
    return ""


def _formula(column: str) -> str:
    formulas = {
        "mean_hindlimb_base_support": "mean Euclidean hindpaw separation during bilateral stance",
        "variance_hindlimb_base_support": "sample variance of hindpaw separation during bilateral stance",
        "left_hindpaw_midline_distance": "mean left hindpaw-to-center distance during left stance",
        "right_hindpaw_midline_distance": "mean right hindpaw-to-center distance during right stance",
        "left_right_hindlimb_phase_offset": "100 * (right stance onset - left onset) / left cycle frames",
        "hindlimb_stance_overlap_fraction": "100 * bilateral stance-overlap frames / left cycle frames",
    }
    if column in ASYMMETRY_PARAMETER_NAMES:
        return "(contralesional - ipsilesional) / mean(abs(contralesional), abs(ipsilesional))"
    if column in formulas:
        return formulas[column]
    if column.startswith(("left__", "right__")):
        return "ALMA KinematicsFunctions definition evaluated on the matched canonical cycle"
    if column in RUSTLAB1_PARAMETER_NAMES:
        return "RustLab1-derived definition evaluated on the canonical source-frame window"
    return "cycle metadata or quality-control value; see feature name"


__all__ = [
    "ASYMMETRY_PARAMETER_NAMES",
    "CANONICAL_CYCLE_COLUMNS",
    "CUSTOM_STROKE_PARAMETER_NAMES",
    "PRIMARY_STROKE_PARAMETER_NAMES",
    "StrokeOutputBundle",
    "add_asymmetry_features",
    "align_parameters_to_cycles",
    "build_feature_dictionary",
    "calculate_stroke_features",
    "detect_canonical_cycles",
    "generate_stroke_analysis_outputs",
    "summarize_session",
]
