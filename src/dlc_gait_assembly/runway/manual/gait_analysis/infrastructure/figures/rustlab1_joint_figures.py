"""Render RustLab1 angular summaries and joint-angle time courses."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.rustlab1_parameter_definitions import (
    RUSTLAB1_PARAMETER_NAMES,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_figure_data import (
    forelimb_joint_angles as _forelimb_joint_angles,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_figure_data import (
    gait_cycles as _gait_cycles,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_figure_style import no_data as _no_data
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_figure_style import (
    plot_parameter_lines as _plot_parameter_lines,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_figure_style import (
    style_axes as _style_axes,
)


def plot_hindpaw_angle_timecourse(context, plt):
    """Only side-view forelimb angles survive the four-paw input contract."""
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for axis, prefix, title in zip(axes, ("l", "r"), ("Left forelimb joints", "Right forelimb joints"), strict=True):
        angles = _forelimb_joint_angles(context, prefix)
        plotted = False
        for label, values in angles.items():
            if context["np"].isfinite(values).any():
                axis.plot(context["np"].arange(len(values)), values, linewidth=1, label=label)
                plotted = True
        if plotted:
            axis.legend(fontsize=8)
        else:
            _no_data(axis)
        axis.set(title=title, xlabel="Frame", ylabel="Angle (degrees)")
        _style_axes(axis)
    figure.subplots_adjust(wspace=0.3)
    return figure


def plot_hindpaw_angle_summary(context, plt):
    figure, axis = plt.subplots(figsize=(10, 4.8))
    columns = [name for name in RUSTLAB1_PARAMETER_NAMES if "__front__" in name and "Angle__" in name]
    if not _plot_parameter_lines(context, axis, _gait_cycles(context), columns):
        _no_data(axis)
    axis.set(xlabel="Gait cycle", ylabel="Angle (degrees)", title="Side-view forelimb joint angles")
    _style_axes(axis)
    return figure
