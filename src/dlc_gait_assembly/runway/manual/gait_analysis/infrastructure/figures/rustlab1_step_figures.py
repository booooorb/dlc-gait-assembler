"""Render RustLab1 step timing, displacement, height, and protraction figures."""

from __future__ import annotations

from pathlib import Path

from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.rustlab1_parameter_definitions import (
    RUSTLAB1_PARAMETER_NAMES,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_figure_data import (
    gait_cycles as _gait_cycles,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_figure_style import (
    boxplot_parameter_by_limb as _boxplot_parameter_by_limb,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_figure_style import no_data as _no_data
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_figure_style import (
    parameter_mean_bars as _parameter_mean_bars,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_figure_style import (
    plot_parameter_lines as _plot_parameter_lines,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_figure_style import (
    style_axes as _style_axes,
)


def plot_cycle_summary(context, plt):
    metrics = (
        ("cycle duration (s)", "Cycle duration (s)"),
        ("stride length (cm)", "Stride length (cm)"),
        ("stance duration (s)", "Stance duration (s)"),
        ("swing duration (s)", "Swing duration (s)"),
    )
    if context["include_forelimb"]:
        (figure, axes) = plt.subplots(2, 3, figsize=(12, 7))
        sync_axis = axes.flat[0]
        _parameter_mean_bars(context, sync_axis, ("FLBR_RATIO", "FRBL_RATIO"))
        sync_axis.set_title("Diagonal asynchronous-phase fraction")
        sync_axis.set_ylabel("Fraction")
        _style_axes(sync_axis)
        metric_axes = list(axes.flat[1:5])
        axes.flat[5].axis("off")
    else:
        (figure, axes) = plt.subplots(2, 2, figsize=(9, 7))
        metric_axes = list(axes.flat)
    for axis, (column, title) in zip(metric_axes, metrics, strict=True):
        _boxplot_parameter_by_limb(context, axis, column)
        axis.set_title(title)
        _style_axes(axis)
    figure.suptitle("RustLab1 synchronization and gait-cycle summary", fontsize=13)
    figure.subplots_adjust(top=0.9, hspace=0.35)
    return figure


def plot_vertical_summary(context, plt):
    groups = (("Average_Height", "Average height (mm)"), ("Movement", "Vertical excursion (mm)"))
    (figure, axes) = plt.subplots(2, 1, figsize=(11, 7))
    for axis, (suffix, title) in zip(axes, groups, strict=True):
        columns = [name for name in RUSTLAB1_PARAMETER_NAMES if name.endswith(suffix) and name in context["rustlab"]]
        _parameter_mean_bars(context, axis, columns)
        axis.set_ylabel(title)
        _style_axes(axis)
    limb_text = "hindlimb and forelimb" if context["include_forelimb"] else "hindlimb"
    figure.suptitle(f"RustLab1 {limb_text} vertical parameter summary", fontsize=13)
    figure.subplots_adjust(top=0.92, hspace=0.55, bottom=0.17)
    return figure


def plot_vertical_timecourse(context, plt):
    (figure, axes) = plt.subplots(1, 2, figsize=(13, 4.5), squeeze=False)
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


def plot_protraction_summary(context, plt):
    prefixes = ["left__back__", "right__back__"]
    if context["include_forelimb"]:
        prefixes.extend(("left__front__", "right__front__"))
    columns = [
        name
        for name in RUSTLAB1_PARAMETER_NAMES
        if name.startswith(tuple(prefixes)) and (not name.endswith(("movement_per_step", "seconds")))
    ]
    (figure, axis) = plt.subplots(figsize=(11, 5))
    _parameter_mean_bars(context, axis, columns)
    axis.axhline(0, color="#111827", linewidth=0.8)
    axis.set_ylabel("Paw position relative to proximal reference (mm)")
    axis.set_title("Protraction and retraction summary")
    _style_axes(axis)
    figure.subplots_adjust(bottom=0.24)
    return figure


def plot_protraction_timecourse(context, plt):
    prefixes = ["left__back__", "right__back__"]
    if context["include_forelimb"]:
        prefixes.extend(("left__front__", "right__front__"))
    columns = [
        name
        for name in RUSTLAB1_PARAMETER_NAMES
        if name.startswith(tuple(prefixes)) and (not name.endswith(("movement_per_step", "seconds")))
    ]
    (figure, axis) = plt.subplots(figsize=(10.5, 5))
    plotted = _plot_parameter_lines(context, axis, _gait_cycles(context), columns)
    if not plotted:
        _no_data(axis)
    axis.axhline(0, color="#111827", linewidth=0.8)
    axis.set_xlabel("Gait cycle")
    axis.set_ylabel("Paw position relative to proximal reference (mm)")
    axis.set_title("Protraction and retraction across gait cycles")
    _style_axes(axis)
    return figure


def plot_step_duration(context, plt):
    if context["include_forelimb"]:
        (figure, axes) = plt.subplots(1, 2, figsize=(10, 4.8))
        _boxplot_parameter_by_limb(context, axes[0], "cycle duration (s)")
        axes[0].set_title("ALMA hindlimb gait cycle")
        _parameter_mean_bars(context, axes[1], ("left__front__seconds", "right__front__seconds"))
        axes[1].set_title("RustLab1 forelimb step duration")
        for axis in axes:
            axis.set_ylabel("Seconds")
            _style_axes(axis)
        figure.subplots_adjust(bottom=0.22)
    else:
        (figure, axis) = plt.subplots(figsize=(7.5, 4.8))
        _boxplot_parameter_by_limb(context, axis, "cycle duration (s)")
        axis.set_ylabel("Seconds")
        axis.set_title("Step-cycle duration by hindlimb")
        _style_axes(axis)
    return figure


def plot_distance_per_step(context, plt):
    (figure, axes) = plt.subplots(1, 2, figsize=(10, 4.6))
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


def generate_rustlab1_stride_preview(speed, strides, output_path: Path, settings, plt, np) -> Path:
    """Render the reference-paw speed trace and detected RustLab1 strides."""
    (figure, axis) = plt.subplots(figsize=(10, 3.8))
    frames = np.arange(len(speed))
    axis.plot(frames, speed, color="#315c8b", linewidth=1.25, label="Paw speed")
    axis.axhline(
        float(settings.stance_speed_threshold_px_frame),
        color="#d97706",
        linestyle="--",
        linewidth=1.2,
        label="Stance threshold",
    )
    for row_index, row in strides.iterrows():
        start = int(row["stride_start (frame)"])
        end = int(row["stride_end (frame)"])
        axis.axvspan(start, end, color="#22c55e", alpha=0.08 if row_index % 2 else 0.14)
        axis.axvline(start, color="#15803d", alpha=0.55, linewidth=0.8)
    axis.set_title(f"RustLab1 stride detection — {settings.reference_paw}")
    axis.set_xlabel("Frame")
    axis.set_ylabel("Absolute x speed (px/frame)")
    axis.set_xlim(0, max(1, len(speed) - 1))
    axis.legend(loc="upper right", frameon=False)
    axis.grid(axis="y", alpha=0.2)
    figure.tight_layout()
    if not hasattr(output_path, "write"):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, format="svg", bbox_inches="tight")
    plt.close(figure)
    return output_path
