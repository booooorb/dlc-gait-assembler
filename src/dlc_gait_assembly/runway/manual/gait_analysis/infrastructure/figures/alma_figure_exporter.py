"""Coordinate ALMA figure families and preserve their established export names."""

from __future__ import annotations

from pathlib import Path

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_figure_data import (
    long_parameter_table as _long_parameter_table,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_figure_data import (
    numeric_parameter_frame as _numeric_parameter_frame,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_figure_data import (
    parameter_summary as _parameter_summary,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.alma_distribution_figures import (
    plot_parameter_correlation as _plot_parameter_correlation,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.alma_distribution_figures import (
    plot_parameter_heatmap as _plot_parameter_heatmap,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.alma_kinematics_figures import (
    plot_drag_profile as _plot_drag_profile,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.alma_kinematics_figures import (
    plot_joint_kinematics as _plot_joint_kinematics,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.alma_timing_figures import (
    plot_cycle_timing as _plot_cycle_timing,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.alma_timing_figures import (
    plot_cycle_trends as _plot_cycle_trends,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.alma_timing_figures import (
    plot_spatiotemporal_profile as _plot_spatiotemporal_profile,
)

ALMA_FIGURE_FILENAMES = (
    "1_ALMA_cycle_timing.svg",
    "2_ALMA_spatiotemporal_profile.svg",
    "3_ALMA_joint_kinematics.svg",
    "4_ALMA_cycle_trends.svg",
    "5_ALMA_parameter_heatmap.svg",
    "6_ALMA_parameter_correlation.svg",
    "8_ALMA_drag_profile.svg",
)


def generate_alma_representations(
    parameters, output_folder: Path, base_name: str, plt, pd, *, write_tables=True
) -> tuple[Path, ...]:
    """Seven diagnostic figures; multi-stride variability is deliberately excluded."""
    import numpy as np

    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    figures_folder = output_folder / f"{base_name}_alma_figures"
    figures_folder.mkdir(parents=True, exist_ok=True)
    normalized = parameters.reset_index(drop=True).copy()
    normalized = normalized.drop(columns=[name for name in normalized if name.startswith("Variability ")])
    normalized.insert(0, "gait_cycle", np.arange(1, len(normalized) + 1))
    numeric = _numeric_parameter_frame(normalized, pd, np)
    long_path = output_folder / f"{base_name}_parameters_long.csv"
    summary_path = output_folder / f"{base_name}_parameter_summary.csv"
    if write_tables:
        _long_parameter_table(normalized, numeric, pd).to_csv(long_path, index=False)
        _parameter_summary(normalized, numeric, pd, np).to_csv(summary_path, index=False)
    context = {"parameters": normalized, "numeric": numeric, "np": np, "pd": pd}
    plotters = (
        _plot_cycle_timing,
        _plot_spatiotemporal_profile,
        _plot_joint_kinematics,
        _plot_cycle_trends,
        _plot_parameter_heatmap,
        _plot_parameter_correlation,
        _plot_drag_profile,
    )
    figure_paths: list[Path] = []
    for filename, plotter in zip(ALMA_FIGURE_FILENAMES, plotters, strict=True):
        figure = plotter(context, plt)
        path = figures_folder / filename
        try:
            with plt.rc_context({"svg.fonttype": "none"}):
                figure.savefig(path, format="svg", bbox_inches="tight")
        finally:
            plt.close(figure)
        figure_paths.append(path)
    return (*((long_path, summary_path) if write_tables else ()), *figure_paths)
