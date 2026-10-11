"""Select treadmill or spontaneous ALMA calculations and assemble one recording result."""

from __future__ import annotations

import numpy as np
import pandas as pd

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_bodypart_aliases import fix_column_names
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_signal_filter import butterworth_filter
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_spontaneous_parameters import (
    extract_spontaneous_parameters,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_treadmill_parameters import extract_parameters
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_confidence_masking import (
    filter_low_confidence_coordinates,
    hide_low_confidence_stickplot_frames,
)


def calculate_alma_recording(
    raw_dataframe, settings, side_mapping=None, cycle_detection=None, detection_diagnostics=None
):

    dataframe = raw_dataframe.copy()
    (dataframe, bodyparts, _bodyparts_raw) = fix_column_names(
        dataframe, side_mapping or settings.custom_bodypart_mapping
    )
    from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_calibration import (
        side_recording_scale,
    )

    pixels_per_cm = (
        side_recording_scale(settings, dataframe)
        if settings.analysis_type != "Treadmill" or settings.calibration_method == "manual"
        else None
    )
    original_dataframe = dataframe.copy()
    (dataframe, confidence_mask, confidence_messages) = filter_low_confidence_coordinates(
        dataframe, settings.likelihood_threshold, pd
    )
    from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.gait_stride_detection import (
        side_cycles_from_bottom,
        side_detector,
    )

    diagnostics = detection_diagnostics if detection_diagnostics is not None else {}
    detector = (
        side_cycles_from_bottom(cycle_detection, settings.likelihood_threshold)
        if cycle_detection is not None
        else side_detector(settings, dataframe, diagnostics, original_dataframe)
    )
    if (
        settings.analysis_type == "Treadmill"
        and getattr(settings, "stride_detection_method", "ALMA (legacy)") != "ALMA (legacy)"
    ):
        raise ValueError(
            "Alternative stride detectors are for spontaneous walking. Select Spontaneous walking or ALMA (legacy)."
        )
    if settings.analysis_type == "Treadmill":
        (parameters, coords, is_stance, bodyparts, drag_masks, starts) = extract_parameters(
            settings.frame_rate,
            dataframe,
            settings.filter_cutoff,
            "toe",
            cm_speed=settings.treadmill_speed_cm_s,
            right_to_left=settings.right_to_left,
            step_height_min_cm=settings.step_height_min_cm,
            step_height_max_cm=settings.step_height_max_cm,
            stride_length_min_cm=settings.stride_length_min_cm,
            stride_length_max_cm=settings.stride_length_max_cm,
            drag_clearance_cm=settings.drag_clearance_cm,
            drag_min_consecutive_frames=settings.drag_min_consecutive_frames,
            pixels_per_cm_override=pixels_per_cm,
        )
    else:
        (parameters, coords, is_stance, bodyparts, drag_masks, starts) = extract_spontaneous_parameters(
            settings.frame_rate,
            dataframe,
            settings.filter_cutoff,
            pixels_per_cm=pixels_per_cm,
            no_outlier_filter=settings.no_outlier_filter,
            dragging_filter=settings.dragging_filter,
            step_height_min_cm=settings.step_height_min_cm,
            step_height_max_cm=settings.step_height_max_cm,
            stride_length_min_cm=settings.stride_length_min_cm,
            stride_length_max_cm=settings.stride_length_max_cm,
            drag_clearance_cm=settings.drag_clearance_cm,
            drag_min_consecutive_frames=settings.drag_min_consecutive_frames,
            right_to_left=settings.right_to_left,
            stride_detector=detector,
        )
        # The legacy spontaneous extractor returns its input coordinates. Draw the
        # same filtered geometry used for its joint/stride calculations instead.
        coords = coords.copy()
        for marker in bodyparts:
            for axis in ("x", "y"):
                column = f"{marker} {axis}"
                if column in coords:
                    coords[column] = butterworth_filter(dataframe[column], settings.frame_rate, settings.filter_cutoff)
    if confidence_mask is not None and coords is not None:
        coords = hide_low_confidence_stickplot_frames(coords, confidence_mask)
    if "observed" in diagnostics:
        observed = np.asarray(diagnostics["observed"], bool)
        trusted = np.asarray(diagnostics["trusted"], bool)
        gap = diagnostics["maximum_gap_frames"]
        confidence_messages = (
            *confidence_messages,
            f"Stride timing: {int(observed.sum())}/{len(observed)} observed frames; "
            f"{int((trusted & ~observed).sum())} frames bridged in short internal gaps "
            f"(limit {gap} frames, {1000 * gap / settings.frame_rate:g} ms). Longer gaps remain excluded.",
        )
        if len(parameters) <= 1 and gap == 0 and not observed.all():
            confidence_messages = (
                *confidence_messages,
                "Strict tracking-gap setting (0 frames) excludes an entire cycle for any missing timing frame. "
                "Choose Auto under Stride detection → Bridge tracking gaps and compare the stick plot before exporting.",
            )
    if coords is not None:
        if pixels_per_cm is not None:
            coords.attrs["pixels_per_cm"] = pixels_per_cm
        coords.attrs["detection_diagnostics"] = {
            key: value.tolist() if isinstance(value, np.ndarray) else value for key, value in diagnostics.items()
        }
        coords.attrs["stride_method"] = (
            "ALMA (treadmill)" if settings.analysis_type == "Treadmill" else settings.stride_detection_method
        )
        coords.attrs["timing_source"] = diagnostics.get(
            "signal_label",
            "Bottom hind paw"
            if cycle_detection is not None
            else "Side toe relative to hip"
            if settings.stride_detection_method == "Paw excursion peaks"
            else "Side toe",
        )
    return (parameters, coords, is_stance, bodyparts, drag_masks, starts, confidence_messages)
