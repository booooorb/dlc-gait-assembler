"""Coordinate RustLab1-only detection and measurement results independently of ALMA execution."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma import alma_signal_filter
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_coordinate_normalization import (
    prepare_alma_coordinates,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_alignment import (
    view_mappings_for_set,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_analysis_settings import (
    validate_rustlab1_settings as _validate_rustlab1_settings,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_feature_extraction import (
    extract_rustlab1_parameters,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_recording_summary import (
    summarize_rustlab1 as _summarize_rustlab1,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_stride_detection import (
    detect_rustlab1_strides,
)


@dataclass(frozen=True)
class RustLab1RecordingCalculation:
    raw: object
    preprocessed: object
    strides: object
    extraction: object
    summary: object
    paw_speed: object
    messages: tuple[str, ...]


def calculate_rustlab1_recording(merged, settings):
    _validate_rustlab1_settings(settings)
    kinematics = alma_signal_filter
    preprocessed = prepare_alma_coordinates(merged, settings, kinematics)
    strides = detect_rustlab1_strides(preprocessed, settings, pd, np)
    extraction = extract_rustlab1_parameters(merged, strides, settings, kinematics, preprocessed)
    if extraction.dataframe is None:
        raise ValueError("RustLab1 markers were not found. Check label mapping.")
    summary = _summarize_rustlab1(extraction.dataframe, pd, np)
    x = np.asarray(preprocessed.series[settings.reference_paw]["x"], dtype=float)
    speed = np.abs(np.diff(x, prepend=x[0]))
    messages = [
        f"RustLab1: detected {len(strides)} stride(s) from {settings.reference_paw}.",
        f"RustLab1: calculated {len(extraction.available_parameters)} selected parameter(s).",
    ]
    rejected_tracking_jumps = int(strides.attrs.get("rejected_tracking_jump_strides", 0))
    if rejected_tracking_jumps:
        messages.append(
            f"RustLab1 stride QC: rejected {rejected_tracking_jumps} candidate stride(s) at or above {settings.maximum_tracking_speed_px_frame:g} px/frame."
        )
    if extraction.missing_markers:
        messages.append("RustLab1 missing markers: " + ", ".join(extraction.missing_markers))
    return RustLab1RecordingCalculation(merged, preprocessed, strides, extraction, summary, speed, tuple(messages))


def run_rustlab1_analysis(view_sets, output_folder, settings, progress_callback=None, *, outputs):
    if not view_sets:
        raise ValueError("Standalone RustLab1 analysis requires at least one three-view CSV set.")
    _validate_rustlab1_settings(settings)
    output_folder = outputs.prepare(output_folder)
    results = []
    for index, view_set in enumerate(view_sets, start=1):
        if progress_callback is not None:
            progress_callback(index, len(view_sets), f"RustLab1: processing {view_set.name}")
        mappings = view_mappings_for_set(settings, view_set.name)
        merged = outputs.read_views(view_set, mappings)
        calculation = calculate_rustlab1_recording(merged, settings)
        results.append(outputs.write_recording(calculation, view_set, output_folder, settings))
    return results


class RustLab1StandaloneUseCases:
    def __init__(self, outputs):
        self.outputs = outputs

    def run(self, view_sets, output_folder, settings, progress_callback=None):
        return run_rustlab1_analysis(view_sets, output_folder, settings, progress_callback, outputs=self.outputs)
