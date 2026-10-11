"""Define shared gait figure styling, limits, and export conventions."""

from __future__ import annotations

from pathlib import Path

from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_figure_data import (
    numeric_column as _numeric_column,
)


def view_color(view: str) -> str:
    return {"left": "#22c55e", "down": "#f97316", "right": "#3b82f6"}.get(view, "#94a3b8")


def boxplot_parameter_by_limb(context, axis, column: str) -> None:
    parameters = context["parameters"]
    values = _numeric_column(context, parameters, column)
    if len(values) == 0:
        no_data(axis)
        return
    if "limb (hind left / right)" in parameters:
        limb_values = (
            parameters["limb (hind left / right)"]
            .fillna("All")
            .astype(str)
            .replace({"nan": "All", "": "All"})
            .to_numpy()
        )
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
        no_data(axis)
        return
    boxes = axis.boxplot(groups, patch_artist=True, widths=0.55)
    for patch, color in zip(boxes["boxes"], ("#f59e0b", "#3b82f6", "#94a3b8"), strict=False):
        patch.set_facecolor(color)
        patch.set_alpha(0.65)
    axis.set_xticks(range(1, len(valid_labels) + 1))
    axis.set_xticklabels(valid_labels)


def parameter_mean_bars(context, axis, columns) -> None:
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
        labels.append(short_parameter_label(column))
        colors.append("#f59e0b" if column.startswith(("l-", "left__")) else "#22c55e")
    if not means:
        no_data(axis)
        return
    positions = context["np"].arange(len(means))
    axis.bar(positions, means, yerr=errors, color=colors, alpha=0.78, capsize=3)
    axis.set_xticks(positions)
    axis.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)


def plot_parameter_lines(context, axis, x_values, columns) -> bool:
    plotted = False
    for column in columns:
        values = _numeric_column(context, context["rustlab"], column)
        n = min(len(x_values), len(values))
        if n == 0 or not context["np"].isfinite(values[:n]).any():
            continue
        axis.plot(
            x_values[:n], values[:n], marker="o", markersize=3, linewidth=1.1, label=short_parameter_label(column)
        )
        plotted = True
    if plotted:
        axis.legend(fontsize=6, ncol=2, loc="best")
    return plotted


def short_parameter_label(column: str) -> str:
    return (
        column.replace("l-back-", "L ")
        .replace("r-back-", "R ")
        .replace("l-front-", "L front ")
        .replace("r-front-", "R front ")
        .replace("l-", "L ")
        .replace("r-", "R ")
        .replace("left__back__", "L ")
        .replace("right__back__", "R ")
        .replace("left__front__", "L front ")
        .replace("right__front__", "R front ")
        .replace("__", " ")
        .replace("_", " ")
    )


def style_axes(axis) -> None:
    axis.grid(True, color="#e5e7eb", linewidth=0.7, alpha=0.8)
    axis.set_axisbelow(True)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)


def no_data(axis) -> None:
    axis.text(0.5, 0.5, "No compatible data", ha="center", va="center", transform=axis.transAxes, color="#64748b")


def save_rustlab1_figure(figure, output_path: Path, plt) -> None:
    try:
        with plt.rc_context({"svg.fonttype": "none"}):
            figure.savefig(output_path, format="svg", bbox_inches="tight", facecolor="white")
    finally:
        plt.close(figure)
