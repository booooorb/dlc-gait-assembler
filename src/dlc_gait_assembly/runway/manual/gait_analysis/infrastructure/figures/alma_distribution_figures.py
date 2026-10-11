"""Render ALMA heatmaps, correlation plots, and variability distributions from prepared data."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.alma_figure_style import (
    mean_bars as _mean_bars,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.alma_figure_style import no_data as _no_data
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.alma_figure_style import (
    short_label as _short_label,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.alma_figure_style import (
    style_axes as _style_axes,
)


def plot_parameter_heatmap(context, plt):
    np = context["np"]
    numeric = context["numeric"]
    selected = list(numeric.columns)  # Include every available parameter, even constant ones.
    (figure, axis) = plt.subplots(figsize=(max(8.5, 0.35 * len(selected) + 2.5), 5.5))
    if not selected or numeric.empty:
        _no_data(axis)
        axis.set_title("Cycle-level standardized parameter heatmap")
        return figure
    matrix = numeric[selected].to_numpy(dtype=float)
    means = np.nanmean(matrix, axis=0)
    standard_deviations = np.nanstd(matrix, axis=0)
    standard_deviations[~np.isfinite(standard_deviations) | (standard_deviations == 0)] = 1.0
    standardized = (matrix - means) / standard_deviations
    image = axis.imshow(standardized, aspect="auto", cmap="coolwarm", vmin=-2.5, vmax=2.5)
    axis.set_xticks(range(len(selected)))
    axis.set_xticklabels([_short_label(name) for name in selected], rotation=70, ha="right", fontsize=7)
    axis.set_ylabel("Gait cycle")
    axis.set_yticks(range(len(matrix)))
    axis.set_yticklabels(range(1, len(matrix) + 1), fontsize=7)
    axis.set_title("Cycle-level standardized parameter heatmap")
    figure.colorbar(image, ax=axis, label="z-score", fraction=0.035, pad=0.02)
    return figure


def plot_parameter_correlation(context, plt):
    np = context["np"]
    numeric = context["numeric"]
    selected = highest_variance_columns(numeric, len(numeric.columns), np)
    (figure, axis) = plt.subplots(figsize=(8.5, 7.5))
    if len(selected) < 2 or len(numeric) < 3:
        _no_data(axis, "At least three usable cycles with varying parameters are required")
        axis.set_title("ALMA parameter correlation")
        return figure
    correlation = numeric[selected].corr(method="spearman", min_periods=3).to_numpy(dtype=float)
    if not np.isfinite(correlation).any():
        _no_data(axis, "At least three usable cycles per parameter are required")
        axis.set_title("ALMA parameter correlation")
        return figure
    image = axis.imshow(correlation, cmap="coolwarm", vmin=-1, vmax=1)
    labels = [_short_label(name) for name in selected]
    axis.set_xticks(range(len(selected)))
    axis.set_yticks(range(len(selected)))
    axis.set_xticklabels(labels, rotation=70, ha="right", fontsize=7)
    axis.set_yticklabels(labels, fontsize=7)
    axis.set_title("ALMA parameter Spearman correlation")
    figure.colorbar(image, ax=axis, label="correlation", fraction=0.04, pad=0.02)
    return figure


def plot_variability(context, plt):
    columns = [column for column in context["numeric"] if column.lower().startswith("variability ")]
    (figure, axis) = plt.subplots(figsize=(11, 5.5))
    _mean_bars(context, axis, columns)
    axis.set_ylabel("cm")
    axis.set_title("ALMA multi-stride variability")
    _style_axes(axis)
    figure.subplots_adjust(bottom=0.3)
    return figure


def highest_variance_columns(numeric, maximum: int, np) -> list[str]:
    ranked = []
    for column in numeric:
        values = numeric[column].to_numpy(dtype=float)
        finite = values[np.isfinite(values)]
        if len(finite) < 2:
            continue
        variance = float(np.var(finite))
        if variance > 0:
            ranked.append((variance, column))
    ranked.sort(reverse=True)
    return [column for (_variance, column) in ranked[:maximum]]
