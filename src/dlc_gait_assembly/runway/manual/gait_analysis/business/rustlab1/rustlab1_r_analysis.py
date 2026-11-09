"""Run the adapted R measurements with independently detected side-toe GMM phases."""

from __future__ import annotations

from typing import Protocol

import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt, lfilter_zi

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.gait_stride_detection import detect_strides
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_calibration import view_scale


class RustLab1RExecutionPort(Protocol):
    def run_recording(self, view_set, output_folder, settings): ...


def validate_r_settings(settings):
    if not np.isfinite(settings.frame_rate) or settings.frame_rate <= 0:
        raise ValueError("RustLab1 frame rate must be finite and greater than zero.")
    if not np.isfinite(settings.filter_cutoff) or not 0 < settings.filter_cutoff < settings.frame_rate / 2:
        raise ValueError("RustLab1 filter cutoff must be positive and below half the frame rate.")
    if not np.isfinite(settings.likelihood_threshold) or not 0 <= settings.likelihood_threshold <= 1:
        raise ValueError("RustLab1 timing likelihood must be between zero and one.")
    if settings.minimum_complete_strides < 1:
        raise ValueError("RustLab1 needs at least one complete stride per side.")
    if settings.maximum_coordinate_gap_frames < 0:
        raise ValueError("RustLab1 coordinate-gap repair cannot be negative.")
    if settings.enabled_parameter_names is not None:
        raise ValueError(
            "Adapted RustLab1 R exports its complete 106-row catalog; parameter subsets are not supported."
        )


def r_filter_configuration(settings):
    b, a = butter(5, settings.filter_cutoff / (settings.frame_rate / 2), "low")
    return {"filter_b": b.tolist(), "filter_a": a.tolist(), "filter_zi": lfilter_zi(b, a).tolist()}


def r_calibration_configuration(merged, settings):
    """Use explicit camera scales; the original R fallback is marked arbitrary."""
    reference_scale = settings.calibration_method == "manual" and settings.pixels_per_cm is None
    if reference_scale:
        return {
            "pixels_per_cm": 31.3667,
            "stride_pixels_per_cm": 31.37,
            "side_scales": {"left": 31.3667, "right": 31.3667},
            "reference_scale": True,
        }
    scales = {side: view_scale(settings, side) for side in ("left", "right")}
    if settings.calibration_method == "reference":
        aliases = {"toe": "back-toe", "ankle": "back-ankle", "knee": "back-knee", "mtp": "back-mtp"}
        first, second = settings.reference_segment.split("_", 1)
        for side, prefix in (("left", "l"), ("right", "r")):
            markers = [f"{prefix}-{aliases.get(marker, marker)}" for marker in (first, second)]
            keys = [(marker, axis) for marker in markers for axis in ("x", "y")]
            if not all(key in merged for key in keys):
                raise ValueError(f"Set a calibration map or reference markers for the {side} camera.")
            x1, y1, x2, y2 = [pd.to_numeric(merged[key], errors="coerce").to_numpy(float) for key in keys]
            lengths = np.hypot(x1 - x2, y1 - y2)
            valid = lengths[np.isfinite(lengths) & (lengths > 0)]
            if not len(valid) or settings.reference_length_cm <= 0:
                raise ValueError(f"No usable calibration segment for the {side} camera.")
            scales[side] = float(np.median(valid) / settings.reference_length_cm)
    if settings.calibration_method == "treadmill":
        raise ValueError("Adapted RustLab1 R uses explicit camera calibration, not treadmill-speed calibration.")
    bottom = view_scale(settings, "bottom")
    return {
        "pixels_per_cm": settings.pixels_per_cm,
        "stride_pixels_per_cm": round(bottom, 2) if bottom is not None else None,
        "side_scales": scales,
        "reference_scale": False,
    }


def detect_r_gmm_phases(merged, settings):
    """Recompute the supplied R script's timing input; never read reference answers.

    Parameter coordinates are not confidence-filtered. Only this separate timing
    signal uses likelihood masking, interpolation, 5th-order Butterworth and GMM.
    Each side has its own accepted cycles; IDs are unique across both sides.
    """
    validate_r_settings(settings)
    frame_count = len(merged)
    if frame_count < 2:
        raise ValueError("RustLab1 needs at least two coordinate frames.")
    b, a = butter(5, settings.filter_cutoff / (settings.frame_rate / 2), "low")
    labels, next_id = [], 1
    for side, prefix in (("left", "l"), ("right", "r")):
        marker = f"{prefix}-back-toe"
        if not all((marker, axis) in merged for axis in ("x", "y")):
            raise ValueError(f"Speed GMM requires the {side} hind toe. Check label mapping.")
        x, y = [pd.to_numeric(merged[marker, axis], errors="coerce").to_numpy(float) for axis in ("x", "y")]
        confidence = (
            pd.to_numeric(merged[marker, "likelihood"], errors="coerce").to_numpy(float)
            if (marker, "likelihood") in merged
            else np.ones(frame_count)
        )
        coordinate_valid = np.isfinite(x) & np.isfinite(y)
        observed = coordinate_valid & (
            confidence >= settings.likelihood_threshold if settings.likelihood_threshold > 0 else True
        )
        signals = []
        for values in (x, y):
            filled = pd.Series(np.where(observed, values, np.nan)).interpolate(limit_direction="both").to_numpy()
            signals.append(filtfilt(b, a, filled) if frame_count > 3 * max(len(a), len(b)) else filled)
        diagnostics = {}
        stance, starts, ends, _ground = detect_strides(
            *signals,
            confidence,
            settings.frame_rate,
            method="Speed mixture (GMM)",
            cutoff=settings.likelihood_threshold,
            maximum_gap=-1,
            coordinate_valid=coordinate_valid,
            diagnostics=diagnostics,
        )
        trusted = np.asarray(diagnostics["trusted"], bool)
        cycles = np.full(frame_count, np.nan)
        for start, end in zip(starts, ends, strict=True):
            cycles[start : end + 1] = next_id
            next_id += 1
        labels.append(
            pd.DataFrame(
                {
                    "source_frame": np.arange(frame_count),
                    "parameter": f"d-back-{side}",
                    "phase_names": np.where(trusted, np.where(stance, "stance", "swing"), "unknown"),
                    "trusted": trusted,
                    "cycle_id": cycles,
                }
            )
        )
    return pd.concat(labels, ignore_index=True)


class RustLab1RUseCases:
    """The app's standalone path executes R; ALMA's optional figures stay separate."""

    def __init__(self, executor: RustLab1RExecutionPort):
        self.executor = executor

    def run(self, view_sets, output_folder, settings, progress_callback=None):
        if not view_sets:
            raise ValueError("Standalone RustLab1 requires at least one matched three-view CSV set.")
        validate_r_settings(settings)
        results = []
        for index, view_set in enumerate(view_sets, start=1):
            if progress_callback is not None:
                progress_callback(index, len(view_sets), f"RustLab1 R: processing {view_set.name}")
            results.append(self.executor.run_recording(view_set, output_folder, settings))
        return results
