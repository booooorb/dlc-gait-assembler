"""Render ALMA joint-angle and dragging figures from prepared cycle measurements."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.alma_figure_style import (
    boxplot_by_limb as _boxplot_by_limb,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.alma_figure_style import (
    mean_bars as _mean_bars,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.alma_figure_style import (
    style_axes as _style_axes,
)


def plot_joint_kinematics(context, plt):
    joints = ("mtp", "ankle", "knee", "hip")
    (figure, axes) = plt.subplots(2, 2, figsize=(10, 7.2))
    for axis, joint in zip(axes.flat, joints, strict=True):
        columns = [f"{joint} joint extension (deg)", f"{joint} joint flexion (deg)", f"{joint} joint amplitude (deg)"]
        _mean_bars(context, axis, columns)
        axis.set_title(f"{joint.upper()} joint")
        axis.set_ylabel("degrees")
        _style_axes(axis)
    figure.suptitle("ALMA joint kinematics", fontsize=13)
    figure.subplots_adjust(top=0.9, hspace=0.42, wspace=0.28)
    return figure


def plot_drag_profile(context, plt):
    (figure, axes) = plt.subplots(1, 2, figsize=(9.5, 4.4))
    _boxplot_by_limb(context, axes[0], "drag duration (s)")
    axes[0].set_title("Drag duration")
    axes[0].set_ylabel("seconds")
    _boxplot_by_limb(context, axes[1], "drag percentage (%)")
    axes[1].set_title("Drag percentage")
    axes[1].set_ylabel("percent")
    for axis in axes:
        _style_axes(axis)
    figure.suptitle("ALMA toe-drag profile", fontsize=13)
    figure.subplots_adjust(top=0.84)
    return figure
