"""Define ALMA figure layout, palette, and scientific plotting conventions."""

from __future__ import annotations


def boxplot_by_limb(context, axis, column: str) -> None:
    numeric = context["numeric"]
    parameters = context["parameters"]
    np = context["np"]
    if column not in numeric:
        no_data(axis)
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
        no_data(axis)
        return
    axis.boxplot(groups, tick_labels=labels, patch_artist=True)
    for patch, color in zip(axis.patches, ("#2f80ed", "#f2994a", "#27ae60"), strict=False):
        patch.set_facecolor(color)
        patch.set_alpha(0.55)


def mean_bars(context, axis, columns) -> None:
    np = context["np"]
    numeric = context["numeric"]
    columns = [column for column in columns if column in numeric]
    if not columns:
        no_data(axis)
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
    axis.set_xticklabels([short_label(column) for column in columns], rotation=55, ha="right", fontsize=7)


def trend_by_limb(context, axis, column: str) -> None:
    numeric = context["numeric"]
    parameters = context["parameters"]
    np = context["np"]
    if column not in numeric:
        no_data(axis)
        return
    limb_column = "limb (hind left / right)"
    if limb_column in parameters:
        colors = ("#2f80ed", "#f2994a", "#27ae60")
        plotted = False
        for (limb, frame), color in zip(parameters.groupby(limb_column, dropna=False, sort=True), colors, strict=False):
            values = numeric.loc[frame.index, column].to_numpy(dtype=float)
            cycles = parameters.loc[frame.index, "gait_cycle"].to_numpy(dtype=float)
            valid = np.isfinite(values)
            if valid.any():
                axis.plot(cycles[valid], values[valid], marker="o", linewidth=1.2, label=str(limb), color=color)
                plotted = True
        if plotted:
            axis.legend(fontsize=8)
        else:
            no_data(axis)
    else:
        values = numeric[column].to_numpy(dtype=float)
        cycles = parameters["gait_cycle"].to_numpy(dtype=float)
        valid = np.isfinite(values)
        if valid.any():
            axis.plot(cycles[valid], values[valid], marker="o", linewidth=1.2, color="#2f80ed")
        else:
            no_data(axis)


def short_label(parameter: str) -> str:
    label = parameter
    for suffix in (" (cm/s)", " (cm)", " (deg)", " (s)", " (%)", " (no. frames)"):
        label = label.replace(suffix, "")
    return label.replace("Variability ", "Var. ").replace(" plane ", " ")


def style_axes(axis) -> None:
    axis.grid(axis="y", alpha=0.18)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)


def no_data(axis, message="No finite data") -> None:
    axis.text(0.5, 0.5, message, ha="center", va="center", transform=axis.transAxes)
    axis.set_xticks([])
    axis.set_yticks([])
