"""Render ALMA cycle timing, spatiotemporal summaries, and cycle trends."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.alma_parameter_definitions import (
    parameter_unit as _parameter_unit,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.alma_figure_style import (
    boxplot_by_limb as _boxplot_by_limb,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.alma_figure_style import (
    short_label as _short_label,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.alma_figure_style import (
    style_axes as _style_axes,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.alma_figure_style import (
    trend_by_limb as _trend_by_limb,
)


def plot_cycle_timing(context, plt):
    columns = ("cycle duration (s)", "stance duration (s)", "swing duration (s)", "stance percentage (%)")
    (figure, axes) = plt.subplots(2, 2, figsize=(9.5, 7.0))
    for axis, column in zip(axes.flat, columns, strict=True):
        _boxplot_by_limb(context, axis, column)
        axis.set_title(_short_label(column))
        axis.set_ylabel(_parameter_unit(column))
        _style_axes(axis)
    figure.suptitle("ALMA gait-cycle timing", fontsize=13)
    figure.subplots_adjust(top=0.9, hspace=0.38)
    return figure


def plot_spatiotemporal_profile(context, plt):
    columns = (
        "stride length (cm)",
        "step height (cm)",
        "max velocity during swing (cm/s)",
        "mean toe-to-crest distance (cm)",
    )
    (figure, axes) = plt.subplots(2, 2, figsize=(9.5, 7.0))
    for axis, column in zip(axes.flat, columns, strict=True):
        _boxplot_by_limb(context, axis, column)
        axis.set_title(_short_label(column))
        axis.set_ylabel(_parameter_unit(column))
        _style_axes(axis)
    figure.suptitle("ALMA spatiotemporal gait profile", fontsize=13)
    figure.subplots_adjust(top=0.9, hspace=0.38)
    return figure


def plot_cycle_trends(context, plt):
    columns = ("stride length (cm)", "step height (cm)", "stance percentage (%)", "knee joint amplitude (deg)")
    (figure, axes) = plt.subplots(2, 2, figsize=(10.5, 7.2))
    for axis, column in zip(axes.flat, columns, strict=True):
        _trend_by_limb(context, axis, column)
        axis.set_title(_short_label(column))
        axis.set_xlabel("Gait cycle")
        axis.set_ylabel(_parameter_unit(column))
        _style_axes(axis)
    figure.suptitle("ALMA parameters across gait cycles", fontsize=13)
    figure.subplots_adjust(top=0.9, hspace=0.42)
    return figure
