from __future__ import annotations

from pathlib import Path

from dlc_gait_assembly.services.pipeline.rustlab1.extraction import (
    RUSTLAB1_FIGURE_FILENAMES,
    RUSTLAB1_PARAMETER_NAMES,
    RustLab1Extraction,
    coordinate_columns,
    filtered_series,
)


def generate_rustlab1_figures(
    raw_dataframe,
    alma_parameters,
    extraction: RustLab1Extraction,
    output_folder: Path,
    settings,
    kinematics,
    plt,
) -> tuple[Path, ...]:
    """Write the 18 RustLab1 runway figure categories for one recording.

    The upstream R notebook aggregates animals and experimental days. The gait
    assembler processes one paired recording at a time, so these figures retain
    the upstream categories and filenames while showing marker-, view-, limb-,
    and gait-cycle-level diagnostics for the current recording.
    """
    if extraction.dataframe is None:
        return ()

    import numpy as np
    import pandas as pd

    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    context = _rustlab1_figure_context(
        raw_dataframe,
        alma_parameters,
        extraction,
        settings,
        kinematics,
        np,
        pd,
    )
    plotters = (
        _plot_tracking_reliability,
        _plot_view_reliability,
        lambda ctx, pyplot: _plot_coordinate_scatter(ctx, pyplot, filtered=False),
        lambda ctx, pyplot: _plot_coordinate_scatter(ctx, pyplot, filtered=True),
        lambda ctx, pyplot: _plot_coordinate_distribution(ctx, pyplot, "x"),
        lambda ctx, pyplot: _plot_coordinate_distribution(ctx, pyplot, "y"),
        _plot_normalized_marker_overview,
        _plot_down_paw_speed,
        _plot_cycle_summary,
        _plot_vertical_summary,
        _plot_vertical_timecourse,
        _plot_hindpaw_position_qc,
        _plot_protraction_summary,
        _plot_protraction_timecourse,
        _plot_step_duration,
        _plot_distance_per_step,
        _plot_hindpaw_angle_timecourse,
        _plot_hindpaw_angle_summary,
    )

    output_paths: list[Path] = []
    for filename, plotter in zip(RUSTLAB1_FIGURE_FILENAMES, plotters, strict=True):
        figure = plotter(context, plt)
        output_path = output_folder / filename
        _save_rustlab1_figure(figure, output_path, plt)
        output_paths.append(output_path)
    return tuple(output_paths)


def _rustlab1_figure_context(raw_dataframe, alma_parameters, extraction, settings, kinematics, np, pd):
    columns = coordinate_columns(raw_dataframe)
    markers = sorted({marker for marker, _coord in columns})
    raw: dict[str, dict[str, object]] = {}
    filtered: dict[str, dict[str, object]] = {}
    for marker in markers:
        raw[marker] = {}
        filtered[marker] = {}
        for coord in ("x", "y", "likelihood"):
            column = columns.get((marker, coord))
            raw[marker][coord] = (
                None
                if column is None
                else pd.to_numeric(raw_dataframe[column], errors="coerce").to_numpy(dtype=float)
            )
        for coord in ("x", "y"):
            filtered[marker][coord] = filtered_series(
                raw_dataframe,
                columns,
                marker,
                coord,
                settings,
                kinematics,
            )
    return {
        "np": np,
        "pd": pd,
        "markers": markers,
        "raw": raw,
        "filtered": filtered,
        "parameters": alma_parameters.reset_index(drop=True),
        "rustlab": extraction.dataframe.reset_index(drop=True),
        "pixels_per_cm": extraction.pixels_per_cm,
        "frame_rate": float(settings.frame_rate),
    }


def _plot_tracking_reliability(context, plt):
    markers = context["markers"]
    values = [_marker_reliability(context, marker) for marker in markers]
    height = max(4.0, 0.28 * len(markers) + 1.7)
    figure, axis = plt.subplots(figsize=(8.5, height))
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


def _plot_view_reliability(context, plt):
    figure, axes = plt.subplots(1, 3, figsize=(9, 3.4))
    for axis, view in zip(axes, ("left", "down", "right"), strict=True):
        view_markers = [marker for marker in context["markers"] if _marker_view(marker) == view]
        values = [_marker_reliability(context, marker) for marker in view_markers]
        ratio = float(context["np"].nanmedian(values)) if values else 0.0
        axis.pie(
            [ratio, max(0.0, 100.0 - ratio)],
            startangle=90,
            colors=[_view_color(view), "#e5e7eb"],
            wedgeprops={"width": 0.30, "edgecolor": "white"},
        )
        axis.text(0, 0, f"{ratio:.1f}%", ha="center", va="center", fontsize=13, weight="bold")
        axis.set_title(f"{view.title()} view")
    figure.suptitle("RustLab1 tracking reliability by camera view", fontsize=13)
    return figure


def _plot_coordinate_scatter(context, plt, *, filtered: bool):
    source = context["filtered"] if filtered else context["raw"]
    figure, axes = plt.subplots(1, 3, figsize=(12, 4), squeeze=False)
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


def _plot_coordinate_distribution(context, plt, coord: str):
    figure, axes = plt.subplots(1, 3, figsize=(12, 3.8), squeeze=False)
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


def _plot_normalized_marker_overview(context, plt):
    figure, axes = plt.subplots(1, 3, figsize=(13, 4.6), squeeze=False)
    references = {"left": "l-hip", "down": "d-center-back", "right": "r-hip"}
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
    handles, labels = axes[0][0].get_legend_handles_labels()
    if handles and len(labels) <= 12:
        axes[0][0].legend(fontsize=6, loc="best")
    axes[0][0].set_ylabel("y (pixels)")
    figure.suptitle("Normalized marker profile", fontsize=13)
    figure.subplots_adjust(top=0.82)
    return figure


def _plot_down_paw_speed(context, plt):
    figure, axis = plt.subplots(figsize=(8.5, 4.5))
    pixels_per_cm = context["pixels_per_cm"] or 49.143
    plotted = False
    for marker, color in (("d-back-left", "#ef4444"), ("d-back-right", "#2563eb")):
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
    threshold = 7.0 * context["frame_rate"] / pixels_per_cm
    axis.axvline(threshold, color="#111827", linestyle="--", linewidth=1.2, label="7 px/frame phase threshold")
    if plotted:
        axis.legend(fontsize=8)
    else:
        _no_data(axis)
    axis.set_xlabel("Hindpaw x-speed (cm/s)")
    axis.set_ylabel("Frame transitions")
    axis.set_title("Down-view hindpaw speed quality control")
    _style_axes(axis)
    return figure


def _plot_cycle_summary(context, plt):
    metrics = (
        ("cycle duration (s)", "Cycle duration (s)"),
        ("stride length (cm)", "Stride length (cm)"),
        ("stance duration (s)", "Stance duration (s)"),
        ("swing duration (s)", "Swing duration (s)"),
    )
    figure, axes = plt.subplots(2, 2, figsize=(9, 7))
    for axis, (column, title) in zip(axes.flat, metrics, strict=True):
        _boxplot_parameter_by_limb(context, axis, column)
        axis.set_title(title)
        _style_axes(axis)
    figure.suptitle("ALMA gait-cycle summary on RustLab1 recording", fontsize=13)
    figure.subplots_adjust(top=0.90, hspace=0.35)
    return figure


def _plot_vertical_summary(context, plt):
    groups = (
        ("Average_Height", "Average height (mm)"),
        ("Movement", "Vertical excursion (mm)"),
    )
    figure, axes = plt.subplots(2, 1, figsize=(11, 7))
    for axis, (suffix, title) in zip(axes, groups, strict=True):
        columns = [name for name in RUSTLAB1_PARAMETER_NAMES if name.endswith(suffix) and name in context["rustlab"]]
        _parameter_mean_bars(context, axis, columns)
        axis.set_ylabel(title)
        _style_axes(axis)
    figure.suptitle("RustLab1 vertical parameter summary", fontsize=13)
    figure.subplots_adjust(top=0.92, hspace=0.55, bottom=0.17)
    return figure


def _plot_vertical_timecourse(context, plt):
    figure, axes = plt.subplots(1, 2, figsize=(13, 4.5), squeeze=False)
    cycles = _gait_cycles(context)
    for axis, side in zip(axes[0], ("l-", "r-"), strict=True):
        columns = [
            name
            for name in RUSTLAB1_PARAMETER_NAMES
            if name.startswith(side) and (name.endswith("Average_Height") or name.endswith("Movement"))
        ]
        plotted = _plot_parameter_lines(context, axis, cycles, columns)
        if not plotted:
            _no_data(axis)
        axis.set_title("Left view" if side == "l-" else "Right view")
        axis.set_xlabel("Gait cycle")
        axis.set_ylabel("Millimeters")
        _style_axes(axis)
    figure.suptitle("RustLab1 vertical parameters across gait cycles", fontsize=13)
    figure.subplots_adjust(top=0.84)
    return figure


def _plot_hindpaw_position_qc(context, plt):
    figure, axis = plt.subplots(figsize=(8.5, 4.5))
    pixels_per_cm = context["pixels_per_cm"] or 49.143
    plotted = False
    for side, prefix, color in (("Left", "l", "#f59e0b"), ("Right", "r", "#22c55e")):
        toe_x = context["filtered"].get(f"{prefix}-back-toe", {}).get("x")
        hip_x = context["filtered"].get(f"{prefix}-hip", {}).get("x")
        if toe_x is None or hip_x is None:
            continue
        distance = (toe_x - hip_x) * 10.0 / pixels_per_cm
        distance = distance[context["np"].isfinite(distance)]
        if len(distance) == 0:
            continue
        axis.hist(distance, bins=30, alpha=0.45, label=side, color=color)
        plotted = True
    if plotted:
        axis.legend()
    else:
        _no_data(axis)
    axis.axvline(0, color="#111827", linewidth=0.9)
    axis.set_xlabel("Hindpaw position relative to hip (mm)")
    axis.set_ylabel("Frames")
    axis.set_title("Horizontal hindpaw-position quality control")
    _style_axes(axis)
    return figure


def _plot_protraction_summary(context, plt):
    columns = [
        name
        for name in RUSTLAB1_PARAMETER_NAMES
        if name.startswith(("left__back__", "right__back__")) and not name.endswith("movement_per_step")
    ]
    figure, axis = plt.subplots(figsize=(11, 5))
    _parameter_mean_bars(context, axis, columns)
    axis.axhline(0, color="#111827", linewidth=0.8)
    axis.set_ylabel("Hindpaw position relative to hip (mm)")
    axis.set_title("Protraction and retraction summary")
    _style_axes(axis)
    figure.subplots_adjust(bottom=0.24)
    return figure


def _plot_protraction_timecourse(context, plt):
    columns = [
        name
        for name in RUSTLAB1_PARAMETER_NAMES
        if name.startswith(("left__back__", "right__back__")) and not name.endswith("movement_per_step")
    ]
    figure, axis = plt.subplots(figsize=(10.5, 5))
    plotted = _plot_parameter_lines(context, axis, _gait_cycles(context), columns)
    if not plotted:
        _no_data(axis)
    axis.axhline(0, color="#111827", linewidth=0.8)
    axis.set_xlabel("Gait cycle")
    axis.set_ylabel("Hindpaw position relative to hip (mm)")
    axis.set_title("Protraction and retraction across gait cycles")
    _style_axes(axis)
    return figure


def _plot_step_duration(context, plt):
    figure, axis = plt.subplots(figsize=(7.5, 4.8))
    _boxplot_parameter_by_limb(context, axis, "cycle duration (s)")
    axis.set_ylabel("Seconds")
    axis.set_title("Step-cycle duration by hindlimb")
    _style_axes(axis)
    return figure


def _plot_distance_per_step(context, plt):
    figure, axes = plt.subplots(1, 2, figsize=(10, 4.6))
    _boxplot_parameter_by_limb(context, axes[0], "stride length (cm)")
    axes[0].set_ylabel("Centimeters")
    axes[0].set_title("ALMA stride length")
    _style_axes(axes[0])
    columns = ("left__back__movement_per_step", "right__back__movement_per_step")
    _parameter_mean_bars(context, axes[1], columns)
    axes[1].set_ylabel("Centimeters")
    axes[1].set_title("RustLab1 hip displacement per step")
    _style_axes(axes[1])
    figure.suptitle("Distance covered per gait cycle", fontsize=13)
    figure.subplots_adjust(top=0.84, bottom=0.22)
    return figure


def _plot_hindpaw_angle_timecourse(context, plt):
    figure, axis = plt.subplots(figsize=(10, 4.8))
    angles = _down_hindpaw_angles(context)
    plotted = False
    series = (
        ("Left hindpaw", angles.get("LB"), "#ef4444"),
        ("Right hindpaw", angles.get("RB"), "#2563eb"),
    )
    for label, values, color in series:
        if values is None:
            continue
        frames = context["np"].arange(len(values))
        axis.plot(frames, values, color=color, linewidth=1.1, alpha=0.9, label=label)
        plotted = True
    if plotted:
        axis.legend()
    else:
        _no_data(axis)
    axis.set_xlabel("Frame")
    axis.set_ylabel("Angle (degrees)")
    axis.set_title("Down-view hindpaw angle timecourse")
    _style_axes(axis)
    return figure


def _plot_hindpaw_angle_summary(context, plt):
    columns = [name for name in RUSTLAB1_PARAMETER_NAMES if name.startswith(("LB__", "RB__"))]
    figure, axis = plt.subplots(figsize=(10, 4.8))
    plotted = _plot_parameter_lines(context, axis, _gait_cycles(context), columns)
    if not plotted:
        _no_data(axis)
    axis.set_xlabel("Gait cycle")
    axis.set_ylabel("Angle (degrees)")
    axis.set_title("Hindpaw angle summary across gait cycles")
    _style_axes(axis)
    return figure


def _marker_reliability(context, marker: str) -> float:
    np = context["np"]
    values = context["raw"][marker]
    likelihood = values.get("likelihood")
    if likelihood is not None and len(likelihood):
        finite = np.isfinite(likelihood)
        return float(np.mean(likelihood[finite] > 0.95) * 100.0) if finite.any() else 0.0
    available = [values.get(coord) for coord in ("x", "y") if values.get(coord) is not None]
    if not available:
        return 0.0
    n = min(len(array) for array in available)
    valid = np.ones(n, dtype=bool)
    for array in available:
        valid &= np.isfinite(array[:n])
    return float(np.mean(valid) * 100.0) if n else 0.0


def _marker_view(marker: str) -> str:
    if marker.startswith("l-"):
        return "left"
    if marker.startswith("r-"):
        return "right"
    if marker.startswith("d-"):
        return "down"
    return "other"


def _view_color(view: str) -> str:
    return {"left": "#22c55e", "down": "#f97316", "right": "#3b82f6"}.get(view, "#94a3b8")


def _coordinate_mask(context, marker, x, y, *, filtered: bool):
    np = context["np"]
    n = min(len(x), len(y))
    mask = np.isfinite(x[:n]) & np.isfinite(y[:n])
    if filtered:
        likelihood = context["raw"].get(marker, {}).get("likelihood")
        if likelihood is not None:
            n = min(n, len(likelihood))
            mask = mask[:n] & np.isfinite(likelihood[:n]) & (likelihood[:n] >= 0.95)
    return mask


def _sample_indices(indices, maximum: int, np):
    if len(indices) <= maximum:
        return indices
    positions = np.linspace(0, len(indices) - 1, maximum, dtype=int)
    return indices[positions]


def _numeric_column(context, dataframe, column: str):
    if column not in dataframe:
        return context["np"].array([], dtype=float)
    return context["pd"].to_numeric(dataframe[column], errors="coerce").to_numpy(dtype=float)


def _gait_cycles(context):
    values = _numeric_column(context, context["rustlab"], "gait_cycle")
    if len(values):
        return values
    return context["np"].arange(1, len(context["rustlab"]) + 1, dtype=float)


def _boxplot_parameter_by_limb(context, axis, column: str) -> None:
    parameters = context["parameters"]
    values = _numeric_column(context, parameters, column)
    if len(values) == 0:
        _no_data(axis)
        return
    if "limb (hind left / right)" in parameters:
        limb_values = parameters["limb (hind left / right)"].astype(str).to_numpy()
    else:
        limb_values = context["np"].array(["All"] * len(values), dtype=object)
    labels = [label for label in dict.fromkeys(limb_values) if label and label.lower() != "nan"] or ["All"]
    groups = []
    valid_labels = []
    for label in labels:
        group = values[(limb_values == label) & context["np"].isfinite(values)]
        if len(group):
            groups.append(group)
            valid_labels.append(label)
    if not groups:
        _no_data(axis)
        return
    boxes = axis.boxplot(groups, patch_artist=True, widths=0.55)
    for patch, color in zip(
        boxes["boxes"],
        ("#f59e0b", "#3b82f6", "#94a3b8"),
        strict=False,
    ):
        patch.set_facecolor(color)
        patch.set_alpha(0.65)
    axis.set_xticks(range(1, len(valid_labels) + 1))
    axis.set_xticklabels(valid_labels)


def _parameter_mean_bars(context, axis, columns) -> None:
    means = []
    errors = []
    labels = []
    colors = []
    for column in columns:
        values = _numeric_column(context, context["rustlab"], column)
        values = values[context["np"].isfinite(values)]
        if len(values) == 0:
            continue
        means.append(float(context["np"].mean(values)))
        errors.append(float(context["np"].std(values)))
        labels.append(_short_parameter_label(column))
        colors.append("#f59e0b" if column.startswith(("l-", "left__")) else "#22c55e")
    if not means:
        _no_data(axis)
        return
    positions = context["np"].arange(len(means))
    axis.bar(positions, means, yerr=errors, color=colors, alpha=0.78, capsize=3)
    axis.set_xticks(positions)
    axis.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)


def _plot_parameter_lines(context, axis, x_values, columns) -> bool:
    plotted = False
    for column in columns:
        values = _numeric_column(context, context["rustlab"], column)
        n = min(len(x_values), len(values))
        if n == 0 or not context["np"].isfinite(values[:n]).any():
            continue
        axis.plot(
            x_values[:n],
            values[:n],
            marker="o",
            markersize=3,
            linewidth=1.1,
            label=_short_parameter_label(column),
        )
        plotted = True
    if plotted:
        axis.legend(fontsize=6, ncol=2, loc="best")
    return plotted


def _short_parameter_label(column: str) -> str:
    return (
        column.replace("l-back-", "L ")
        .replace("r-back-", "R ")
        .replace("l-", "L ")
        .replace("r-", "R ")
        .replace("left__back__", "L ")
        .replace("right__back__", "R ")
        .replace("__", " ")
        .replace("_", " ")
    )


def _down_hindpaw_angles(context):
    np = context["np"]
    center_x = context["filtered"].get("d-center-back", {}).get("x")
    center_y = context["filtered"].get("d-center-back", {}).get("y")
    result = {}
    if center_x is None or center_y is None:
        return result
    for label, marker in (("LB", "d-back-left"), ("RB", "d-back-right")):
        paw_x = context["filtered"].get(marker, {}).get("x")
        paw_y = context["filtered"].get(marker, {}).get("y")
        if paw_x is None or paw_y is None:
            continue
        n = min(len(center_x), len(center_y), len(paw_x), len(paw_y))
        angle = np.abs(np.degrees(np.arctan2(paw_y[:n] - center_y[:n], paw_x[:n] - center_x[:n])))
        result[label] = np.where(angle > 90.0, angle - 90.0, angle)
    return result


def _style_axes(axis) -> None:
    axis.grid(True, color="#e5e7eb", linewidth=0.7, alpha=0.8)
    axis.set_axisbelow(True)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)


def _no_data(axis) -> None:
    axis.text(0.5, 0.5, "No compatible data", ha="center", va="center", transform=axis.transAxes, color="#64748b")


def _save_rustlab1_figure(figure, output_path: Path, plt) -> None:
    try:
        figure.savefig(output_path, format="svg", bbox_inches="tight", facecolor="white")
    finally:
        plt.close(figure)
