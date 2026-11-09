"""Bottom-paw measurements on actual video-time intervals, for either side."""

from dataclasses import replace

import numpy as np
import pandas as pd

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.gait_stride_detection import trusted_samples
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.tracking_gap_policy import tracking_gap_frames
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.stroke_recovery_parameter_definitions import (
    BOTTOM_RECOVERY_NAMES,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_contact_states import (
    configured_axis_scale,
    stance_mask,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_coordinate_normalization import (
    coordinate_columns,
    prepare_alma_coordinates,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_spatial_scaling import (
    resolve_pixels_per_cm,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_alignment import (
    align_multiview_coordinates,
)

BOTTOM_STRIDE_NAMES = BOTTOM_RECOVERY_NAMES
BOTTOM_FORE_NAMES = ("left__front__seconds", "right__front__seconds", "FLBR_RATIO", "FRBL_RATIO")
BOTTOM_TIME_COLUMNS = (
    "bottom_start_frame",
    "bottom_end_frame",
    "bottom_alignment_coverage (%)",
    "bottom_tracking_coverage (%)",
)
GENERAL_PHASE_NAMES = ("FLBR_RATIO", "FRBL_RATIO")


class BottomWindows:
    def __init__(self, track, settings, mappings, filtering, scale_source):
        self.track = track
        self.settings = replace(settings, frame_rate=track.frame_rate)
        native = align_multiview_coordinates({"bottom": track.frame}, pd, mappings)
        prepared = prepare_alma_coordinates(native, self.settings, filtering)
        self.series = prepared.series
        fallback, _ = resolve_pixels_per_cm(scale_source, coordinate_columns(scale_source), settings)
        # The fallback comes from the aligned side/reference calibration, while
        # explicit bottom X/Y scales always take precedence.
        self.x_scale = configured_axis_scale(settings, "bottom", "x", fallback)
        self.y_scale = configured_axis_scale(settings, "bottom", "y", fallback)
        self.phase, self.trusted = {}, {}
        gap = tracking_gap_frames(settings.max_interpolation_gap_frames, track.frame_rate)
        for marker, axes in self.series.items():
            if axes.get("x") is None or axes.get("y") is None:
                continue
            conf_column = (marker, "likelihood")
            confidence = native[conf_column].to_numpy(float) if conf_column in native else np.ones(len(native))
            valid = track.present & np.isfinite(native[(marker, "x")]) & np.isfinite(native[(marker, "y")])
            observed = np.array(valid, dtype=bool, copy=True)
            if settings.likelihood_threshold > 0:
                observed &= np.isfinite(confidence) & (confidence >= settings.likelihood_threshold)
            _, trusted = trusted_samples(observed, 0.5, gap)
            trusted &= np.isfinite(axes["x"]) & np.isfinite(axes["y"])
            self.trusted[marker] = trusted
            self.phase[marker] = stance_mask(self.series, marker, self.x_scale, self.y_scale, self.settings, np)

    def _window(self, start, stop):
        weights = np.maximum(
            0.0, np.minimum(self.track.times + 1 / self.track.frame_rate, stop) - np.maximum(self.track.times, start)
        )
        weights[weights < 1e-9] = 0.0
        selected = weights > 0
        alignment = float(weights[self.track.present].sum() / (stop - start)) if stop > start else 0.0
        return weights, selected, min(1.0, alignment)

    def _valid(self, markers):
        if any(marker not in self.trusted or self.phase.get(marker) is None for marker in markers):
            return np.zeros(len(self.track.times), bool)
        return np.logical_and.reduce([self.trusted[marker] for marker in markers])

    def stride(self, start, stop, side, forelimbs=False):
        names = (*BOTTOM_STRIDE_NAMES, *(BOTTOM_FORE_NAMES if forelimbs else ()), *BOTTOM_TIME_COLUMNS)
        result = dict.fromkeys(names, np.nan)
        if not np.isfinite(start + stop) or stop <= start:
            return result
        weights, selected, alignment = self._window(start, stop)
        result["bottom_alignment_coverage (%)"] = alignment * 100
        available = selected & self.track.present
        if available.any():
            result["bottom_start_frame"], result["bottom_end_frame"] = self.track.frame_ids[available][[0, -1]]
        hind = ("d-back-left", "d-back-right")
        valid = self._valid(hind)
        coverage = float(weights[valid].sum() / (stop - start))
        result["bottom_tracking_coverage (%)"] = min(1.0, coverage) * 100
        if alignment >= 1 - 1e-6 and coverage >= 1 - 1e-6:
            left, right = (self.phase[m] for m in hind)
            own, other = (left, right) if side == "left" else (right, left)
            result[BOTTOM_RECOVERY_NAMES[0]] = 100.0 * weights[selected & own & ~other].sum() / (stop - start)
            result[BOTTOM_RECOVERY_NAMES[1]] = 100.0 * weights[selected & other & ~own].sum() / (stop - start)
            opposite = "d-back-right" if side == "left" else "d-back-left"
            phase = self.phase[opposite]
            onsets = phase & ~np.r_[phase[0], phase[:-1]] & valid & np.r_[False, valid[:-1]]
            times = self.track.times[onsets & (self.track.times >= start - 1e-9) & (self.track.times < stop - 1e-9)]
            if len(times):
                phase_offset = max(0.0, 100.0 * (times[0] - start) / (stop - start))
                result[BOTTOM_RECOVERY_NAMES[2]] = abs(phase_offset - 50.0)
        if forelimbs and alignment >= 1 - 1e-6:
            result.update(self._diagonal(weights, require_complete=True))
            for paw_side in ("left", "right"):
                marker = f"d-front-{paw_side}"
                phase = self.phase.get(marker)
                if phase is None or not self.trusted[marker][selected].all():
                    continue
                onsets = np.flatnonzero(
                    phase
                    & ~np.r_[phase[0], phase[:-1]]
                    & self.trusted[marker]
                    & np.r_[False, self.trusted[marker][:-1]]
                )
                times = self.track.times[onsets]
                intervals = np.diff(times)
                overlaps = (times[:-1] < stop) & (times[1:] > start)
                # Do not infer a forepaw cycle across an untrusted tracking gap,
                # even if both touchdowns and the requested window are observed.
                overlaps &= np.array(
                    [self.trusted[marker][a : b + 1].all() for a, b in zip(onsets[:-1], onsets[1:], strict=True)],
                    dtype=bool,
                )
                if overlaps.any():
                    result[f"{paw_side}__front__seconds"] = float(np.median(intervals[overlaps]))
        return result

    def _diagonal(self, weights, require_complete):
        result = {"FLBR_RATIO": np.nan, "FRBL_RATIO": np.nan}
        markers = ("d-front-left", "d-front-right", "d-back-left", "d-back-right")
        if any(self.phase.get(m) is None for m in markers):
            return result
        valid = self._valid(markers) & self.track.present
        if require_complete and not valid[weights > 0].all():
            return result
        fl, fr, bl, br = (self.phase[m] for m in markers)
        include = valid & ~(fl & fr & bl & br)
        denominator = weights[include].sum()
        if denominator > 0:
            result["FLBR_RATIO"] = float(weights[include & (fl != br)].sum() / denominator)
            result["FRBL_RATIO"] = float(weights[include & (fr != bl)].sum() / denominator)
        return result

    def general(self, start, stop):
        result = dict.fromkeys(GENERAL_PHASE_NAMES, np.nan)
        weights, _, _ = self._window(start, stop)
        valid = self._valid(("d-back-left", "d-back-right")) & self.track.present
        duration = weights[valid].sum()
        result["synchronization_usable_time (s)"] = float(duration)
        result["synchronization_coverage (%)"] = 100.0 * duration / (stop - start) if stop > start else 0.0
        result.update(self._diagonal(weights, require_complete=False))
        return result
