"""Calculate synchronized features against ALMA's canonical cycle boundaries."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from dlc_gait_assembly.runway.manual.gait_analysis.business.custom_features.custom_sop_feature_calculations import (
    extract_custom_sop_parameters,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.custom_features.custom_sop_feature_definitions import (
    CUSTOM_SOP_PARAMETER_NAMES,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.rustlab1_parameter_definitions import (
    rustlab1_parameter_names_for_scope,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.synchronized_parameter_definitions import (
    CANONICAL_CYCLE_COLUMNS,
    IDENTIFIER_COLUMNS,
    PRIMARY_STROKE_PARAMETER_NAMES,
    build_feature_dictionary,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.synchronized_parameter_definitions import (
    selected_alma_parameters as _selected_alma_parameters,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.synchronized_parameter_definitions import (
    selected_parameter_names as _selected_parameter_names,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_coordinate_normalization import (
    prepare_alma_coordinates,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_feature_extraction import (
    extract_rustlab1_parameters,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_asymmetry import (
    add_asymmetry_features,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_cycle_alignment import (
    align_feature_rows_to_cycles,
    align_parameters_to_cycles,
    canonical_cycles_from_alma,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_feature_calculations import (
    bottom_trajectories as _bottom_trajectories,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_session_summary import (
    metadata_frame as _metadata_frame,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_session_summary import (
    resolved_metadata as _resolved_metadata,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_session_summary import (
    summarize_session,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_signal_operations import (
    side_calibration_source as _side_calibration_source,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_signal_operations import (
    view_calibration as _view_calibration,
)


@dataclass(frozen=True)
class SynchronizedRecordingCalculation:
    tables: dict
    qc: dict
    messages: tuple[str, ...]


def calculate_synchronized_recording(merged, view_set, settings, left_parameters, right_parameters, kinematics, pd):
    import numpy as np

    preprocessed = prepare_alma_coordinates(merged, settings, kinematics)
    (metadata, metadata_warnings) = _resolved_metadata(view_set)
    calibration = _view_calibration(settings, "bottom")
    messages = list(metadata_warnings)
    if calibration is None:
        raise ValueError(
            "Stroke analysis requires a bottom-view pixel calibration. Set pixels_per_cm or view_calibration['bottom']; no scientific fallback is used."
        )
    (trajectories, trajectory_qc) = _bottom_trajectories(
        merged, settings, calibration, kinematics, pd, np, preprocessed
    )
    cycles = canonical_cycles_from_alma(left_parameters, trajectories, metadata, pd, np)
    cycles["frame_rate_hz"] = float(settings.frame_rate)
    cycles["bottom_x_pixels_per_cm"] = float(calibration["x_pixels_per_cm"])
    cycles["bottom_y_pixels_per_cm"] = float(calibration["y_pixels_per_cm"])
    cycles["calibration_source"] = calibration["source"]
    cycles["left_calibration_source"] = _side_calibration_source(settings, "left")
    cycles["right_calibration_source"] = _side_calibration_source(settings, "right")
    cycles["left_view_csv"] = str(Path(view_set.left_csv))
    cycles["right_view_csv"] = str(Path(view_set.right_csv))
    cycles["bottom_view_csv"] = str(Path(view_set.bottom_csv))
    cycles = cycles.reindex(columns=CANONICAL_CYCLE_COLUMNS)
    valid_count = int(cycles["cycle_valid"].sum()) if len(cycles) else 0
    session_usable = valid_count >= int(settings.minimum_synchronized_cycles)
    cycles["session_usable"] = session_usable
    left_aligned = align_parameters_to_cycles(
        cycles, _selected_alma_parameters(left_parameters, settings, side="left"), "left", pd, np
    )
    right_aligned = align_parameters_to_cycles(
        cycles, _selected_alma_parameters(right_parameters, settings, side="right"), "right", pd, np
    )
    rustlab = extract_rustlab1_parameters(merged, left_parameters, settings, kinematics, preprocessed)
    enabled_rustlab = _selected_parameter_names(settings, rustlab1_parameter_names_for_scope(settings.limb_scope))
    if rustlab.dataframe is None:
        rustlab_features = pd.DataFrame(np.nan, index=range(len(cycles)), columns=list(enabled_rustlab))
        messages.append("RustLab1 features unavailable: required side/down markers were not found.")
    else:
        rustlab_features = align_feature_rows_to_cycles(cycles, rustlab.dataframe, enabled_rustlab, pd, np)
        if rustlab.missing_markers:
            messages.append("Missing RustLab1 markers: " + ", ".join(rustlab.missing_markers))
    enabled_custom = _selected_parameter_names(settings, CUSTOM_SOP_PARAMETER_NAMES)
    custom_extraction = extract_custom_sop_parameters(merged, left_parameters, settings, kinematics, preprocessed)
    custom = align_feature_rows_to_cycles(cycles, custom_extraction.dataframe, enabled_custom, pd, np)
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
            "likelihood_threshold": settings.likelihood_threshold,
            "filter_cutoff_hz": settings.filter_cutoff,
            "coordinate_interpolation": "ALMA linear interpolation in both directions",
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
    qc_payload["warnings"] = list(messages)
    if not session_usable:
        messages.append(
            f"Stroke pilot QC: only {valid_count} valid synchronized cycles; {settings.minimum_synchronized_cycles} required."
        )
    else:
        messages.append(f"Stroke pilot QC: {valid_count} valid synchronized cycles.")
    return SynchronizedRecordingCalculation(
        {
            "canonical_cycles": cycles,
            "stride_features": stride_features,
            "session_summary": session_summary,
            "primary_stroke_panel": primary_panel,
            "feature_dictionary": dictionary,
        },
        qc_payload,
        tuple(messages),
    )
