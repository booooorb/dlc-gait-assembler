"""Validate a manifest's visible settings before applying them to the gait page."""

import math
from copy import deepcopy

from PySide6.QtCore import QSignalBlocker

from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_marker_requirements import reference_segment_label

SPINS = {
    "frame_rate": "frame_rate_spin",
    "filter_cutoff": "filter_cutoff_spin",
    "treadmill_speed_cm_s": "treadmill_speed_spin",
    "mixture_context_ms": "mixture_context_spin",
    "reference_length_cm": "reference_length_spin",
    "likelihood_threshold": "likelihood_threshold_spin",
    "drag_clearance_cm": "drag_clearance_spin",
    "drag_min_consecutive_frames": "drag_frames_spin",
    "step_height_min_cm": "step_height_min_spin",
    "step_height_max_cm": "step_height_max_spin",
    "stride_length_min_cm": "stride_length_min_spin",
    "stride_length_max_cm": "stride_length_max_spin",
    "max_interpolation_gap_frames": "detection_gap_spin",
    "swing_speed_threshold_cm_s": "stroke_swing_speed_spin",
    "minimum_synchronized_cycles": "stroke_min_cycles_spin",
}
CHECKS = {
    "no_outlier_filter": "no_outlier_checkbox",
    "dragging_filter": "dragging_filter_checkbox",
    "generate_stickplot": "stickplot_checkbox",
    "generate_alma_representations": "alma_representations_checkbox",
    "generate_rustlab1_parameters": "rustlab1_checkbox",
    "stroke_analysis_enabled": "stroke_analysis_checkbox",
}


def apply_manifest_settings(view, settings):
    """Preflight all values, then update controls together without intermediate previews."""
    if settings.calibration_method not in {"reference", "manual"}:
        raise ValueError("Unsupported calibration method.")
    if settings.reference_segment not in {"ankle_toe", "hip_knee", "knee_ankle", "ankle_mtp"}:
        raise ValueError("Unsupported reference body segment.")
    for name in ("minimum_stance_frames", "minimum_swing_frames"):
        value = getattr(settings, name)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or int(value) != value:
            raise ValueError(f"{name} must be a whole number of frames.")
    if settings.calibration_method == "manual" and settings.pixels_per_cm is None:
        raise ValueError(
            "This manifest has no shared pixel-to-cm scale. Export it again after selecting its calibration map."
        )
    if settings.input_mode not in {"Multi side view", "Three-view", "Single side view", "Single-side ALMA"}:
        raise ValueError("Unsupported input mode.")
    if settings.right_to_left != "auto" and not isinstance(settings.right_to_left, bool):
        raise ValueError("Walking direction must be true, false, or auto.")
    combos = {
        view.workflow_combo: "ALMA + post-ALMA features",
        view.input_mode_combo: "Single side view"
        if settings.input_mode in {"Single side view", "Single-side ALMA"}
        else "Multi side view",
        view.analysis_type_combo: settings.analysis_type,
        view.limb_scope_combo: settings.limb_scope,
        view.stride_method_combo: settings.stride_detection_method,
        view.calibration_method_combo: "Reference body segment"
        if settings.calibration_method == "reference"
        else "Manual pixel-to-cm ratio",
        view.reference_segment_combo: reference_segment_label(settings.reference_segment),
        view.direction_combo: "Auto-detect"
        if settings.right_to_left == "auto"
        else "Right-to-Left"
        if settings.right_to_left
        else "Left-to-Right",
    }
    for combo, value in combos.items():
        if combo.findText(value) < 0:
            raise ValueError(f"Unsupported manifest setting: {value}")
    spins = {getattr(view, control): getattr(settings, field) for field, control in SPINS.items()}
    spins.update({spin: getattr(settings, name) for name, spin in view.comparison_rustlab_spins.items()})
    spins[view.pixels_per_cm_spin] = settings.pixels_per_cm if settings.pixels_per_cm is not None else 50.0
    spins[view.stroke_likelihood_spin] = settings.likelihood_threshold
    sources = {}
    for side in ("left", "right", "bottom"):
        timing = (settings.view_timing or {}).get(side, {})
        if not isinstance(timing, dict):
            raise ValueError(f"Invalid {side} timing settings.")
        spins[view.view_fps_spins[side]] = timing.get("frame_rate", 0.0)
        spins[view.view_offset_spins[side]] = timing.get("offset_s", 0.0)
        calibration = (settings.view_calibration or {}).get(side, {})
        if isinstance(calibration, (float, int)):
            calibration = {"pixels_per_cm": calibration}
        if not isinstance(calibration, dict):
            raise ValueError(f"Invalid {side} calibration settings.")
        sources[side] = {k: v for k, v in calibration.items() if k in {"map_path", "source", "view_index"}}
        if side == "bottom":
            for axis in ("x", "y"):
                spins[getattr(view, f"bottom_{axis}_pixels_per_cm_spin")] = calibration.get(
                    f"{axis}_pixels_per_cm", calibration.get("pixels_per_cm", 0.0)
                )
        else:
            spins[view.view_scale_spins[side]] = calibration.get("pixels_per_cm", 0.0)
    for spin, value in spins.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (float, int))
            or not math.isfinite(value)
            or not spin.minimum() <= value <= spin.maximum()
        ):
            raise ValueError(f"Invalid or out-of-range numeric setting: {value}")
        if isinstance(spin.value(), int) and int(value) != value:
            raise ValueError(f"A frame count must be an integer: {value}")
    checks = {getattr(view, control): getattr(settings, field) for field, control in CHECKS.items()}
    if any(not isinstance(value, bool) for value in checks.values()):
        raise ValueError("Manifest output/filter switches must be true or false.")
    custom = settings.custom_bodypart_mapping or {}
    mappings = settings.view_bodypart_mapping or {}
    if not isinstance(custom, dict) or not isinstance(mappings, dict):
        raise ValueError("Invalid body-part mappings.")

    def validate_mapping(node):
        if not isinstance(node, dict) or any(
            not isinstance(k, str) or not isinstance(v, (str, dict)) for k, v in node.items()
        ):
            raise ValueError("Invalid body-part mappings.")
        for value in node.values():
            if isinstance(value, dict):
                validate_mapping(value)

    validate_mapping(mappings)
    if any(not isinstance(raw, str) or standard not in view._bodypart_combos for raw, standard in custom.items()):
        raise ValueError("Unsupported custom body-part mapping.")
    blockers = [
        QSignalBlocker(control)
        for control in (*combos, *spins, *checks, view.use_custom_mapping_checkbox, *view._bodypart_combos.values())
    ]
    try:
        for combo, value in combos.items():
            combo.setCurrentText(value)
        for spin, value in spins.items():
            spin.setValue(value)
        for check, value in checks.items():
            check.setChecked(value)
        view.state.calibration_map_path = None
        view.state.calibration_map_source = ""
        view.calibration_map_label.setText("Calibration values loaded from analysis manifest.")
        view.view_calibration_sources = sources
        for side, label in view.view_map_labels.items():
            label.setText(str(sources[side].get("map_path") or "Calibration values loaded from manifest"))
        view.state.view_label_mappings = deepcopy(mappings)
        view.state.raw_bodyparts = list(dict.fromkeys([*view.state.raw_bodyparts, *custom]))
        for standard, combo in view._bodypart_combos.items():
            combo.clear()
            combo.addItems(["(none)", *view.state.raw_bodyparts])
            combo.setCurrentText(next((raw for raw, target in custom.items() if target == standard), "(none)"))
        view.use_custom_mapping_checkbox.setChecked(bool(custom))
    finally:
        for blocker in blockers:
            blocker.unblock()
    view.setup._update_workflow()
    view.refresh_stride_method_description()
    view.setup._update_input_mode()
    view.calibration._update_calibration_method()
    view.mapping._update_mapping_enabled()
    view.controller._invalidate_stickplot_preview("Settings imported. Generate a new stick-plot preview.")
