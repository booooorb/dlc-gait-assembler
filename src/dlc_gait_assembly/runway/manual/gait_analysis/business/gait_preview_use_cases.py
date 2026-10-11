"""Prepare full-recording scientific previews and detector comparisons without running the export pipeline."""

from collections.abc import Sequence
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_engine import calculate_alma_recording
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_continuous_sequences import (
    prepare_full_recording_stickplot,
    preview_cycle_rows,
    stickplot_axis_limits,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.gait_stride_detection import (
    BOTTOM_METHODS,
    STRIDE_METHODS,
    bottom_detection,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_calibration import settings_for_view
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_timing import (
    raw_on_timeline,
    read_view_track,
)


@dataclass(frozen=True)
class StrideComparisonResults(Sequence):
    methods: tuple

    def __len__(self):
        return len(self.methods)

    def __getitem__(self, index):
        return self.methods[index]


class GaitPreviewUseCases:
    def __init__(self, coordinates, renderer):
        self.coordinates = coordinates
        self.renderer = renderer

    def _recordings(self, inputs, settings, progress_callback=None):
        settings = self.coordinates.resolve_calibration(settings)
        tracks = {
            label.lower(): read_view_track(
                self.coordinates.read_table(path, header=[1, 2]), path, label.lower(), settings
            )
            for label, path in inputs
        }
        bottom = tracks.get("bottom")
        recordings = []
        for index, (label, path) in enumerate(inputs, start=1):
            if label.lower() == "bottom":
                continue
            if progress_callback:
                progress_callback(index, max(1, len(inputs)), f"Preparing {path.name}")
            mapping = (settings.view_bodypart_mapping or {}).get(label.lower())
            current = replace(
                settings_for_view(settings, label.lower()),
                custom_bodypart_mapping=mapping or settings.custom_bodypart_mapping,
                view_bodypart_mapping=None,
            )
            track = tracks[label.lower()]
            current = replace(current, frame_rate=track.frame_rate)
            raw = track.frame
            detection, diagnostics = None, {}
            if settings.stride_detection_method in BOTTOM_METHODS:
                if bottom is None:
                    raise ValueError(f"{settings.stride_detection_method} requires a paired bottom CSV.")
                detection = bottom_detection(
                    raw_on_timeline(bottom, track.times),
                    label.lower(),
                    current,
                    settings.view_bodypart_mapping,
                    diagnostics,
                )
            recording = calculate_alma_recording(
                raw, current, cycle_detection=detection, detection_diagnostics=diagnostics
            )
            recording[1].attrs["view_label"] = label
            recordings.append((label, recording))
        return recordings

    @staticmethod
    def _count(recording):
        return len(preview_cycle_rows(recording[0], len(recording[1]), include_rejected=True))

    def _prepare_plots(self, recordings, settings):
        prepared, messages = [], []
        for label, recording in recordings:
            parameters, coords, stance, bodyparts, masks, starts, detail = recording
            plot = prepare_full_recording_stickplot(parameters, coords, bodyparts, stance)
            if plot is not None and plot.tracking_only:
                messages.append(f"{label}: no complete strides detected; full tracking remains visible.")
            if plot is not None:
                prepared.append((label, plot))
            if plot is not None:
                finite = np.isfinite(plot.x_coordinates.to_numpy(float)) & np.isfinite(
                    plot.y_coordinates.to_numpy(float)
                )
                drawable = np.any(finite[:-1] & finite[1:], axis=0)
                unavailable = len(coords) - int(drawable.sum())
                if unavailable:
                    messages.append(
                        f"{label}: {unavailable} frames have no drawable limb segments after tracking-confidence filtering; the full source timeline is retained."
                    )
            diagnostics = coords.attrs.get("detection_diagnostics", {})
            if "phase_confidence" in diagnostics:
                support = np.asarray(diagnostics["phase_confidence"], float)
                raw = np.asarray(diagnostics["raw_stance_probability"], float)
                raw_support = np.maximum(raw, 1 - raw)
                finite = np.isfinite(support) & np.isfinite(raw_support)
                if finite.any():
                    current = np.mean(support[finite] >= 0.70) * 100
                    previous = np.mean(raw_support[finite] >= 0.70) * 100
                    messages.append(
                        f"{label}: phase support ≥70% on {current:.1f}% of usable frames (Speed mixture alone: {previous:.1f}%). Neighbour context: {diagnostics['mixture_context_ms']:g} ms. Model support, not measured accuracy."
                    )
            accepted = int(pd.to_numeric(parameters["cycle duration (s)"], errors="coerce").notna().sum())
            messages.extend(detail)
            messages.append(
                f"{label}: {self._count(recording)} detected, {accepted} passed filters; showing all {len(coords)} frames. Calibration: {coords.attrs.get('pixels_per_cm')} px/cm."
            )
        return prepared, messages

    @staticmethod
    def _limits(data):
        return stickplot_axis_limits(data)

    def _render(self, prepared, limits=None):
        plots = []
        for label, data in prepared:
            data = replace(data, axis_limits=limits[label] if limits and label in limits else self._limits(data))
            svg = self.renderer.render_preview(data)
            if svg:
                plots.append((f"{label} · stick plot", svg))
        return tuple(plots)

    def prepare(self, inputs, settings, progress_callback=None):
        recordings = self._recordings(inputs, settings, progress_callback)
        prepared, messages = self._prepare_plots(recordings, settings)
        plots = self._render(prepared)
        if not plots:
            raise RuntimeError(
                "No previewable tracking coordinates were available. Check the selected CSVs and marker mapping."
            )
        source = ", ".join(path.name for label, path in inputs if label.lower() != "bottom")
        return plots, source, tuple(messages)

    def compare(self, inputs, settings, progress_callback=None):
        calculations = []
        for index, method in enumerate(STRIDE_METHODS, start=1):
            if progress_callback:
                progress_callback(index, len(STRIDE_METHODS) * 2, f"Detecting {method}")
            try:
                recordings = self._recordings(inputs, replace(settings, stride_detection_method=method))
                calculations.append((method, recordings, ""))
            except (ValueError, RuntimeError) as exc:
                calculations.append((method, [], str(exc)))
        prepared_methods, limits = [], {}
        for method, recordings, error in calculations:
            prepared, messages = self._prepare_plots(recordings, settings)
            prepared_methods.append((method, prepared, [error] if error else messages))
            for label, data in prepared:
                geometry_limits = self._limits(data)
                if label in limits and limits[label] != geometry_limits:
                    raise RuntimeError(f"{label}: detector changed the recording geometry; comparison stopped.")
                limits[label] = geometry_limits
        results = []
        for index, (method, prepared, messages) in enumerate(prepared_methods, start=1):
            if progress_callback:
                progress_callback(len(STRIDE_METHODS) + index, len(STRIDE_METHODS) * 2, f"Drawing {method} stick plots")
            note = "Full recording: identical skeleton frames and axes for every method in each view. Only phase colours and stride boundaries change; detected counts may differ."
            plots = self._render(prepared, limits)
            results.append((method, plots, "\n".join([note, *messages])))
        return StrideComparisonResults(tuple(results))

    def prepare_rustlab1(self, view_set, settings, *, calculation=None):
        """Draw side skeletons on the standalone reference paw's actual stride frames."""
        from dlc_gait_assembly.runway.manual.gait_analysis.business.alma import alma_signal_filter
        from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import ALMA_BODYPARTS
        from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_coordinate_normalization import (
            prepare_alma_coordinates,
        )
        from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_alignment import (
            view_mappings_for_set,
        )
        from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_stride_detection import (
            detect_rustlab1_strides,
            rustlab1_stance_mask,
        )

        if calculation is None:
            raw = self.coordinates.read_views(view_set, view_mappings_for_set(settings, view_set.name))
            prepared = prepare_alma_coordinates(raw, settings, alma_signal_filter)
            strides = detect_rustlab1_strides(prepared, settings, pd, np, allow_empty=True)
        else:
            raw, prepared, strides = calculation.raw, calculation.preprocessed, calculation.strides
        stance, _speed = rustlab1_stance_mask(prepared.series[settings.reference_paw]["x"], settings, np)
        marker_names = ("back-toe", "back-mtp", "back-ankle", "back-knee", "hip", "iliac-crest")
        plots = []
        for side, prefix in (("Left", "l"), ("Right", "r")):
            coords = pd.DataFrame(index=range(len(raw)))
            for bodypart, name in zip(ALMA_BODYPARTS, marker_names, strict=True):
                marker = f"{prefix}-{name}"
                confidence_column = prepared.columns.get((marker, "likelihood"))
                good = (
                    np.ones(len(raw), dtype=bool)
                    if confidence_column is None or settings.likelihood_threshold <= 0
                    else pd.to_numeric(raw[confidence_column], errors="coerce")
                    .ge(settings.likelihood_threshold)
                    .to_numpy()
                )
                for axis in ("x", "y"):
                    values = prepared.series.get(marker, {}).get(axis)
                    coords[f"{bodypart} {axis}"] = np.where(good, values, np.nan) if values is not None else np.nan
            if not np.isfinite(coords.to_numpy()).any():
                continue
            coords.attrs.update(
                view_label=side,
                stride_method="RustLab1 (standalone)",
                timing_source=f"Bottom reference paw: {settings.reference_paw}",
            )
            plot = prepare_full_recording_stickplot(strides, coords, ALMA_BODYPARTS, stance)
            plots.append((side, plot))
        if not plots:
            raise ValueError("No side-view skeleton coordinates are available. Check left/right label mapping.")
        messages = (
            f"RustLab1: {len(strides)} complete strides from {settings.reference_paw}; side stick plots use these exact frame boundaries.",
        )
        if len(strides) < settings.minimum_complete_strides:
            messages += (
                f"The recording has fewer than the required {settings.minimum_complete_strides} strides. Tracking is shown for review.",
            )
        return self._render(plots), view_set.name, messages
