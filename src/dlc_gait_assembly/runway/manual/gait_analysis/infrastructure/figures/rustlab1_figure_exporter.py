"""Coordinate RustLab1 tracking, step, and joint figure families."""

from __future__ import annotations

from pathlib import Path

from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.rustlab1_parameter_definitions import (
    RUSTLAB1_FIGURE_FILENAMES,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_feature_extraction import (
    RustLab1Extraction,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_figure_data import (
    rustlab1_figure_context as _rustlab1_figure_context,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_figure_style import (
    save_rustlab1_figure as _save_rustlab1_figure,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.rustlab1_joint_figures import (
    plot_hindpaw_angle_summary as _plot_hindpaw_angle_summary,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.rustlab1_joint_figures import (
    plot_hindpaw_angle_timecourse as _plot_hindpaw_angle_timecourse,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.rustlab1_step_figures import (
    plot_cycle_summary as _plot_cycle_summary,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.rustlab1_step_figures import (
    plot_distance_per_step as _plot_distance_per_step,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.rustlab1_step_figures import (
    plot_protraction_summary as _plot_protraction_summary,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.rustlab1_step_figures import (
    plot_protraction_timecourse as _plot_protraction_timecourse,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.rustlab1_step_figures import (
    plot_step_duration as _plot_step_duration,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.rustlab1_step_figures import (
    plot_vertical_summary as _plot_vertical_summary,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.rustlab1_step_figures import (
    plot_vertical_timecourse as _plot_vertical_timecourse,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.rustlab1_tracking_figures import (
    plot_coordinate_distribution as _plot_coordinate_distribution,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.rustlab1_tracking_figures import (
    plot_coordinate_scatter as _plot_coordinate_scatter,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.rustlab1_tracking_figures import (
    plot_down_paw_speed as _plot_down_paw_speed,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.rustlab1_tracking_figures import (
    plot_hindpaw_position_qc as _plot_hindpaw_position_qc,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.rustlab1_tracking_figures import (
    plot_normalized_marker_overview as _plot_normalized_marker_overview,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.rustlab1_tracking_figures import (
    plot_tracking_reliability as _plot_tracking_reliability,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.rustlab1_tracking_figures import (
    plot_view_reliability as _plot_view_reliability,
)


def generate_rustlab1_figures(
    raw_dataframe,
    alma_parameters,
    extraction: RustLab1Extraction,
    output_folder: Path,
    settings,
    kinematics,
    plt,
    preprocessed=None,
) -> tuple[Path, ...]:
    """Write the supported RustLab1 runway figures for one recording.

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
        raw_dataframe, alma_parameters, extraction, settings, kinematics, np, pd, preprocessed
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
        if filename.startswith("10_") and not context["include_forelimb"]:
            # The two bottom-center angle plots have no four-paw equivalent.
            # Forelimb mode uses these categories for supported side-view joints.
            continue
        figure = plotter(context, plt)
        output_path = output_folder / filename
        _save_rustlab1_figure(figure, output_path, plt)
        output_paths.append(output_path)
    return tuple(output_paths)
