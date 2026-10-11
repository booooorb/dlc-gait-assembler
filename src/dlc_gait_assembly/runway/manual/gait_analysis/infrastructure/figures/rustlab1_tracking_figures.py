"""Render RustLab1 tracking reliability, coordinate distributions, and quality-control figures."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_figure_data import (
    coordinate_mask as _coordinate_mask,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_figure_data import (
    marker_reliability as _marker_reliability,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_figure_data import (
    marker_view as _marker_view,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_figure_data import (
    sample_indices as _sample_indices,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_figure_style import no_data as _no_data
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_figure_style import (
    style_axes as _style_axes,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_figure_style import (
    view_color as _view_color,
)


def plot_tracking_reliability(context, plt):
    markers = context["markers"]
    values = [_marker_reliability(context, marker) for marker in markers]
    height = max(4.0, 0.28 * len(markers) + 1.7)
    (figure, axis) = plt.subplots(figsize=(8.5, height))
    positions = list(range(len(markers)))
    colors = [_view_color(_marker_view(marker)) for marker in markers]
    axis.barh(positions, values, color=colors, edgecolor="white")
    axis.set_yticks(positions)
    axis.set_yticklabels(markers, fontsize=8)
    axis.invert_yaxis()
    axis.set_xlim(0, 100)
    axis.set_xlabel("Confident tracked samples (%)")
    axis.set_title("RustLab1 tracking reliability by marker")
    for position, value in zip(positions, values, strict=True):
        axis.text(min(value + 1.0, 96.0), position, f"{value:.1f}%", va="center", fontsize=7)
    _style_axes(axis)
    return figure


def plot_view_reliability(context, plt):
    (figure, axes) = plt.subplots(1, 3, figsize=(9, 3.4))
    for axis, view in zip(axes, ("left", "down", "right"), strict=True):
        view_markers = [marker for marker in context["markers"] if _marker_view(marker) == view]
        values = [_marker_reliability(context, marker) for marker in view_markers]
        ratio = float(context["np"].nanmedian(values)) if values else 0.0
        axis.pie(
            [ratio, max(0.0, 100.0 - ratio)],
            startangle=90,
            colors=[_view_color(view), "#e5e7eb"],
            wedgeprops={"width": 0.3, "edgecolor": "white"},
        )
        axis.text(0, 0, f"{ratio:.1f}%", ha="center", va="center", fontsize=13, weight="bold")
        axis.set_title(f"{view.title()} view")
    figure.suptitle("RustLab1 tracking reliability by camera view", fontsize=13)
    return figure


def plot_coordinate_scatter(context, plt, *, filtered: bool):
    source = context["filtered"] if filtered else context["raw"]
    (figure, axes) = plt.subplots(1, 3, figsize=(12, 4), squeeze=False)
    for axis, view in zip(axes[0], ("left", "down", "right"), strict=True):
        plotted = False
        for marker in context["markers"]:
            if _marker_view(marker) != view:
                continue
            x = source[marker].get("x")
            y = source[marker].get("y")
            if x is None or y is None:
                continue
            mask = _coordinate_mask(context, marker, x, y, filtered=filtered)
            indices = _sample_indices(context["np"].flatnonzero(mask), 800, context["np"])
            if len(indices) == 0:
                continue
            axis.scatter(x[indices], y[indices], s=7, alpha=0.32, label=marker)
            plotted = True
        axis.set_title(view.title())
        axis.set_xlabel("x (pixels)")
        if axis is axes[0][0]:
            axis.set_ylabel("y (pixels)")
        axis.invert_yaxis()
        _style_axes(axis)
        if not plotted:
            _no_data(axis)
    label = "after likelihood filtering" if filtered else "before likelihood filtering"
    figure.suptitle(f"Coordinate quality control {label}", fontsize=13)
    figure.subplots_adjust(top=0.82)
    return figure


def plot_coordinate_distribution(context, plt, coord: str):
    (figure, axes) = plt.subplots(1, 3, figsize=(12, 3.8), squeeze=False)
    for axis, view in zip(axes[0], ("left", "down", "right"), strict=True):
        arrays = []
        for marker in context["markers"]:
            if _marker_view(marker) != view:
                continue
            values = context["filtered"][marker].get(coord)
            if values is not None:
                arrays.append(values[context["np"].isfinite(values)])
        values = context["np"].concatenate(arrays) if arrays else context["np"].array([])
        if len(values):
            axis.hist(values, bins=30, color=_view_color(view), alpha=0.85, edgecolor="white")
        else:
            _no_data(axis)
        axis.set_title(view.title())
        axis.set_xlabel(f"{coord} coordinate (pixels)")
        axis.set_ylabel("Count")
        _style_axes(axis)
    figure.suptitle(f"RustLab1 {coord.upper()}-coordinate distribution", fontsize=13)
    figure.subplots_adjust(top=0.82)
    return figure


def plot_normalized_marker_overview(context, plt):
    (figure, axes) = plt.subplots(1, 3, figsize=(13, 4.6), squeeze=False)
    references = {"left": "l-hip", "down": "d-back-left", "right": "r-hip"}
    for axis, view in zip(axes[0], ("left", "down", "right"), strict=True):
        reference_x = context["filtered"].get(references[view], {}).get("x")
        plotted = False
        if reference_x is not None:
            for marker in context["markers"]:
                if _marker_view(marker) != view:
                    continue
                x = context["filtered"][marker].get("x")
                y = context["filtered"][marker].get("y")
                if x is None or y is None:
                    continue
                n = min(len(x), len(y), len(reference_x))
                mask = (
                    context["np"].isfinite(x[:n])
                    & context["np"].isfinite(y[:n])
                    & context["np"].isfinite(reference_x[:n])
                )
                indices = _sample_indices(context["np"].flatnonzero(mask), 500, context["np"])
                if len(indices) == 0:
                    continue
                axis.scatter(x[indices] - reference_x[indices], y[indices], s=7, alpha=0.35, label=marker)
                plotted = True
        if not plotted:
            _no_data(axis)
        axis.set_title(f"{view.title()} - normalized to {references[view]}")
        axis.set_xlabel("Relative x (pixels)")
        axis.invert_yaxis()
        _style_axes(axis)
    (handles, labels) = axes[0][0].get_legend_handles_labels()
    if handles and len(labels) <= 12:
        axes[0][0].legend(fontsize=6, loc="best")
    axes[0][0].set_ylabel("y (pixels)")
    figure.suptitle("Normalized marker profile", fontsize=13)
    figure.subplots_adjust(top=0.82)
    return figure


def plot_down_paw_speed(context, plt):
    (figure, axis) = plt.subplots(figsize=(8.5, 4.5))
    pixels_per_cm = context["bottom_pixels_per_cm"] or 49.143
    plotted = False
    series = [("d-back-left", "#ef4444"), ("d-back-right", "#2563eb")]
    if context["include_forelimb"]:
        series.extend((("d-front-left", "#f59e0b"), ("d-front-right", "#22c55e")))
    for marker, color in series:
        x = context["filtered"].get(marker, {}).get("x")
        if x is None or len(x) < 2:
            continue
        speed_px = context["np"].abs(context["np"].diff(x))
        valid = context["np"].isfinite(speed_px)
        speed = speed_px[valid] * context["frame_rate"] / pixels_per_cm
        if len(speed) == 0:
            continue
        axis.hist(speed, bins=30, alpha=0.42, label=marker, color=color)
        plotted = True
    threshold_px = context["stance_speed_threshold_px_frame"]
    threshold = threshold_px * context["frame_rate"] / pixels_per_cm
    axis.axvline(
        threshold, color="#111827", linestyle="--", linewidth=1.2, label=f"{threshold_px:g} px/frame stance threshold"
    )
    tracking_limit_px = context["maximum_tracking_speed_px_frame"]
    tracking_limit = tracking_limit_px * context["frame_rate"] / pixels_per_cm
    axis.axvline(
        tracking_limit,
        color="#dc2626",
        linestyle=":",
        linewidth=1.2,
        label=f"{tracking_limit_px:g} px/frame tracking limit",
    )
    if plotted:
        axis.legend(fontsize=8)
    else:
        _no_data(axis)
    axis.set_xlabel("Paw x-speed (cm/s)")
    axis.set_ylabel("Frame transitions")
    axis.set_title("Down-view paw speed quality control")
    _style_axes(axis)
    return figure


def plot_hindpaw_position_qc(context, plt):
    (figure, axis) = plt.subplots(figsize=(8.5, 4.5))
    plotted = False
    series = [("Left hindpaw", "l-back-toe", "l-hip", "#f59e0b"), ("Right hindpaw", "r-back-toe", "r-hip", "#22c55e")]
    if context["include_forelimb"]:
        series.extend(
            (
                ("Left forepaw", "l-front-toe-tip", "l-shoulder", "#ef4444"),
                ("Right forepaw", "r-front-toe-tip", "r-shoulder", "#2563eb"),
            )
        )
    for label, toe_marker, reference_marker, color in series:
        toe_x = context["filtered"].get(toe_marker, {}).get("x")
        reference_x = context["filtered"].get(reference_marker, {}).get("x")
        if toe_x is None or reference_x is None:
            continue
        side = "left" if toe_marker.startswith("l-") else "right"
        pixels_per_cm = context["side_x_scales"][side]
        if not pixels_per_cm or pixels_per_cm <= 0:
            continue
        distance = (toe_x - reference_x) * 10.0 / pixels_per_cm
        distance = distance[context["np"].isfinite(distance)]
        if len(distance) == 0:
            continue
        axis.hist(distance, bins=30, alpha=0.45, label=label, color=color)
        plotted = True
    if plotted:
        axis.legend()
    else:
        _no_data(axis)
    axis.axvline(0, color="#111827", linewidth=0.9)
    axis.set_xlabel("Paw position relative to proximal reference (mm)")
    axis.set_ylabel("Frames")
    axis.set_title("Horizontal paw-position quality control")
    _style_axes(axis)
    return figure
