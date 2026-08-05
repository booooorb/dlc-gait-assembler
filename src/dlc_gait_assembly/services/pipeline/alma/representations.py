"""Tabular summaries and diagnostic figures derived from ALMA gait cycles."""

from __future__ import annotations

from pathlib import Path

ALMA_FIGURE_FILENAMES = (
    "1_ALMA_cycle_timing.svg",
    "2_ALMA_spatiotemporal_profile.svg",
    "3_ALMA_joint_kinematics.svg",
    "4_ALMA_cycle_trends.svg",
    "5_ALMA_parameter_heatmap.svg",
    "6_ALMA_parameter_correlation.svg",
    "7_ALMA_variability.svg",
    "8_ALMA_drag_profile.svg",
)

_IDENTIFIER_COLUMNS = {
    "limb (hind left / right)",
    "stride_start (frame)",
    "stride_end (frame)",
}


def generate_alma_representations(
    parameters,
    output_folder: Path,
    base_name: str,
    plt,
    pd,
) -> tuple[Path, ...]:
    """Write tidy/summary tables and eight robust ALMA diagnostic figures."""
    import numpy as np

    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    figures_folder = output_folder / f"{base_name}_alma_figures"
    figures_folder.mkdir(parents=True, exist_ok=True)

    normalized = parameters.reset_index(drop=True).copy()
    normalized.insert(0, "gait_cycle", np.arange(1, len(normalized) + 1))
    numeric = _numeric_parameter_frame(normalized, pd, np)

    long_path = output_folder / f"{base_name}_parameters_long.csv"
    summary_path = output_folder / f"{base_name}_parameter_summary.csv"
    _long_parameter_table(normalized, numeric, pd).to_csv(long_path, index=False)
    _parameter_summary(normalized, numeric, pd, np).to_csv(summary_path, index=False)

    context = {
        "parameters": normalized,
        "numeric": numeric,
        "np": np,
        "pd": pd,
    }
    plotters = (
        _plot_cycle_timing,
        _plot_spatiotemporal_profile,
        _plot_joint_kinematics,
        _plot_cycle_trends,
        _plot_parameter_heatmap,
        _plot_parameter_correlation,
        _plot_variability,
        _plot_drag_profile,
    )
    figure_paths: list[Path] = []
    for filename, plotter in zip(ALMA_FIGURE_FILENAMES, plotters, strict=True):
        figure = plotter(context, plt)
        path = figures_folder / filename
        figure.savefig(path, format="svg", bbox_inches="tight")
        plt.close(figure)
        figure_paths.append(path)
    return (long_path, summary_path, *figure_paths)


def _numeric_parameter_frame(parameters, pd, np):
    output = pd.DataFrame(index=parameters.index)
    for column in parameters.columns:
        if column == "gait_cycle" or column in _IDENTIFIER_COLUMNS:
            continue
        values = pd.to_numeric(parameters[column], errors="coerce")
        if np.isfinite(values.to_numpy(dtype=float)).any():
            output[column] = values
    return output


def _long_parameter_table(parameters, numeric, pd):
    identifier_columns = ["gait_cycle"]
    for column in _IDENTIFIER_COLUMNS:
        if column in parameters:
            identifier_columns.append(column)
    if numeric.empty:
        return pd.DataFrame(columns=[*identifier_columns, "parameter", "value", "unit"])
    tidy = pd.concat([parameters[identifier_columns], numeric], axis=1).melt(
        id_vars=identifier_columns,
        value_vars=list(numeric.columns),
        var_name="parameter",
        value_name="value",
    )
    tidy["unit"] = tidy["parameter"].map(_parameter_unit)
    return tidy


def _parameter_summary(parameters, numeric, pd, np):
    columns = (
        "limb",
        "parameter",
        "unit",
        "count",
        "mean",
        "standard_deviation",
        "median",
        "q1",
        "q3",
        "minimum",
        "maximum",
        "coefficient_of_variation",
    )
    if numeric.empty:
        return pd.DataFrame(columns=columns)
    limb_column = "limb (hind left / right)"
    groups = [("all", parameters.index)]
    if limb_column in parameters:
        groups = [
            (str(limb), group.index)
            for limb, group in parameters.groupby(limb_column, dropna=False, sort=True)
        ]
    rows = []
    for limb, indices in groups:
        for parameter in numeric.columns:
            values = numeric.loc[indices, parameter].to_numpy(dtype=float)
            values = values[np.isfinite(values)]
            count = int(len(values))
            mean = float(np.mean(values)) if count else np.nan
            standard_deviation = float(np.std(values, ddof=1)) if count > 1 else np.nan
            rows.append(
                {
                    "limb": limb,
                    "parameter": parameter,
                    "unit": _parameter_unit(parameter),
                    "count": count,
                    "mean": mean,
                    "standard_deviation": standard_deviation,
                    "median": float(np.median(values)) if count else np.nan,
                    "q1": float(np.percentile(values, 25)) if count else np.nan,
                    "q3": float(np.percentile(values, 75)) if count else np.nan,
                    "minimum": float(np.min(values)) if count else np.nan,
                    "maximum": float(np.max(values)) if count else np.nan,
                    "coefficient_of_variation": (
                        standard_deviation / abs(mean)
                        if count > 1 and np.isfinite(mean) and mean != 0
                        else np.nan
                    ),
                }
            )
    return pd.DataFrame(rows, columns=columns)


def _plot_cycle_timing(context, plt):
    columns = (
        "cycle duration (s)",
        "stance duration (s)",
        "swing duration (s)",
        "stance percentage (%)",
    )
    figure, axes = plt.subplots(2, 2, figsize=(9.5, 7.0))
    for axis, column in zip(axes.flat, columns, strict=True):
        _boxplot_by_limb(context, axis, column)
        axis.set_title(_short_label(column))
        axis.set_ylabel(_parameter_unit(column))
        _style_axes(axis)
    figure.suptitle("ALMA gait-cycle timing", fontsize=13)
    figure.subplots_adjust(top=0.90, hspace=0.38)
    return figure


def _plot_spatiotemporal_profile(context, plt):
    columns = (
        "stride length (cm)",
        "step height (cm)",
        "max velocity during swing (cm/s)",
        "mean toe-to-crest distance (cm)",
    )
    figure, axes = plt.subplots(2, 2, figsize=(9.5, 7.0))
    for axis, column in zip(axes.flat, columns, strict=True):
        _boxplot_by_limb(context, axis, column)
        axis.set_title(_short_label(column))
        axis.set_ylabel(_parameter_unit(column))
        _style_axes(axis)
    figure.suptitle("ALMA spatiotemporal gait profile", fontsize=13)
    figure.subplots_adjust(top=0.90, hspace=0.38)
    return figure


def _plot_joint_kinematics(context, plt):
    joints = ("mtp", "ankle", "knee", "hip")
    figure, axes = plt.subplots(2, 2, figsize=(10, 7.2))
    for axis, joint in zip(axes.flat, joints, strict=True):
        columns = [
            f"{joint} joint extension (deg)",
            f"{joint} joint flexion (deg)",
            f"{joint} joint amplitude (deg)",
        ]
        _mean_bars(context, axis, columns)
        axis.set_title(f"{joint.upper()} joint")
        axis.set_ylabel("degrees")
        _style_axes(axis)
    figure.suptitle("ALMA joint kinematics", fontsize=13)
    figure.subplots_adjust(top=0.90, hspace=0.42, wspace=0.28)
    return figure


def _plot_cycle_trends(context, plt):
    columns = (
        "stride length (cm)",
        "step height (cm)",
        "stance percentage (%)",
        "knee joint amplitude (deg)",
    )
    figure, axes = plt.subplots(2, 2, figsize=(10.5, 7.2))
    for axis, column in zip(axes.flat, columns, strict=True):
        _trend_by_limb(context, axis, column)
        axis.set_title(_short_label(column))
        axis.set_xlabel("Gait cycle")
        axis.set_ylabel(_parameter_unit(column))
        _style_axes(axis)
    figure.suptitle("ALMA parameters across gait cycles", fontsize=13)
    figure.subplots_adjust(top=0.90, hspace=0.42)
    return figure


def _plot_parameter_heatmap(context, plt):
    np = context["np"]
    numeric = context["numeric"]
    selected = _highest_variance_columns(numeric, 24, np)
    figure, axis = plt.subplots(figsize=(max(8.5, 0.35 * len(selected) + 2.5), 5.5))
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


def _plot_parameter_correlation(context, plt):
    np = context["np"]
    numeric = context["numeric"]
    selected = _highest_variance_columns(numeric, 16, np)
    figure, axis = plt.subplots(figsize=(8.5, 7.5))
    if len(selected) < 2:
        _no_data(axis)
        axis.set_title("ALMA parameter correlation")
        return figure
    correlation = numeric[selected].corr(method="spearman", min_periods=2).to_numpy(dtype=float)
    image = axis.imshow(correlation, cmap="coolwarm", vmin=-1, vmax=1)
    labels = [_short_label(name) for name in selected]
    axis.set_xticks(range(len(selected)))
    axis.set_yticks(range(len(selected)))
    axis.set_xticklabels(labels, rotation=70, ha="right", fontsize=7)
    axis.set_yticklabels(labels, fontsize=7)
    axis.set_title("ALMA parameter Spearman correlation")
    figure.colorbar(image, ax=axis, label="correlation", fraction=0.04, pad=0.02)
    return figure


def _plot_variability(context, plt):
    columns = [column for column in context["numeric"] if column.lower().startswith("variability ")]
    figure, axis = plt.subplots(figsize=(11, 5.5))
    _mean_bars(context, axis, columns)
    axis.set_ylabel("cm")
    axis.set_title("ALMA multi-stride variability")
    _style_axes(axis)
    figure.subplots_adjust(bottom=0.30)
    return figure


def _plot_drag_profile(context, plt):
    figure, axes = plt.subplots(1, 2, figsize=(9.5, 4.4))
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


def _boxplot_by_limb(context, axis, column: str) -> None:
    numeric = context["numeric"]
    parameters = context["parameters"]
    np = context["np"]
    if column not in numeric:
        _no_data(axis)
        return
    limb_column = "limb (hind left / right)"
    groups = []
    labels = []
    if limb_column in parameters:
        for limb, frame in parameters.groupby(limb_column, dropna=False, sort=True):
            values = numeric.loc[frame.index, column].to_numpy(dtype=float)
            values = values[np.isfinite(values)]
            if len(values):
                groups.append(values)
                labels.append(str(limb))
    else:
        values = numeric[column].to_numpy(dtype=float)
        values = values[np.isfinite(values)]
        if len(values):
            groups.append(values)
            labels.append("all cycles")
    if not groups:
        _no_data(axis)
        return
    axis.boxplot(groups, tick_labels=labels, patch_artist=True)
    for patch, color in zip(axis.patches, ("#2f80ed", "#f2994a", "#27ae60"), strict=False):
        patch.set_facecolor(color)
        patch.set_alpha(0.55)


def _mean_bars(context, axis, columns) -> None:
    np = context["np"]
    numeric = context["numeric"]
    columns = [column for column in columns if column in numeric]
    if not columns:
        _no_data(axis)
        return
    means = []
    errors = []
    for column in columns:
        values = numeric[column].to_numpy(dtype=float)
        values = values[np.isfinite(values)]
        means.append(float(np.mean(values)) if len(values) else np.nan)
        errors.append(float(np.std(values, ddof=1)) if len(values) > 1 else 0.0)
    positions = np.arange(len(columns))
    axis.bar(positions, means, yerr=errors, color="#2f80ed", alpha=0.76, capsize=3)
    axis.set_xticks(positions)
    axis.set_xticklabels([_short_label(column) for column in columns], rotation=55, ha="right", fontsize=7)


def _trend_by_limb(context, axis, column: str) -> None:
    numeric = context["numeric"]
    parameters = context["parameters"]
    np = context["np"]
    if column not in numeric:
        _no_data(axis)
        return
    limb_column = "limb (hind left / right)"
    if limb_column in parameters:
        colors = ("#2f80ed", "#f2994a", "#27ae60")
        plotted = False
        for (limb, frame), color in zip(
            parameters.groupby(limb_column, dropna=False, sort=True), colors, strict=False
        ):
            values = numeric.loc[frame.index, column].to_numpy(dtype=float)
            cycles = parameters.loc[frame.index, "gait_cycle"].to_numpy(dtype=float)
            valid = np.isfinite(values)
            if valid.any():
                axis.plot(cycles[valid], values[valid], marker="o", linewidth=1.2, label=str(limb), color=color)
                plotted = True
        if plotted:
            axis.legend(fontsize=8)
        else:
            _no_data(axis)
    else:
        values = numeric[column].to_numpy(dtype=float)
        cycles = parameters["gait_cycle"].to_numpy(dtype=float)
        valid = np.isfinite(values)
        if valid.any():
            axis.plot(cycles[valid], values[valid], marker="o", linewidth=1.2, color="#2f80ed")
        else:
            _no_data(axis)


def _highest_variance_columns(numeric, maximum: int, np) -> list[str]:
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
    return [column for _variance, column in ranked[:maximum]]


def _parameter_unit(parameter: str) -> str:
    lowered = parameter.lower()
    if "(cm/s)" in lowered:
        return "cm/s"
    if "(cm)" in lowered:
        return "cm"
    if "(deg)" in lowered:
        return "degrees"
    if "(s)" in lowered:
        return "seconds"
    if "(%)" in lowered:
        return "percent"
    if "frames" in lowered:
        return "frames"
    return "unitless"


def _short_label(parameter: str) -> str:
    label = parameter
    for suffix in (" (cm/s)", " (cm)", " (deg)", " (s)", " (%)", " (no. frames)"):
        label = label.replace(suffix, "")
    return label.replace("Variability ", "Var. ").replace(" plane ", " ")


def _style_axes(axis) -> None:
    axis.grid(axis="y", alpha=0.18)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)


def _no_data(axis) -> None:
    axis.text(0.5, 0.5, "No finite data", ha="center", va="center", transform=axis.transAxes)
    axis.set_xticks([])
    axis.set_yticks([])
