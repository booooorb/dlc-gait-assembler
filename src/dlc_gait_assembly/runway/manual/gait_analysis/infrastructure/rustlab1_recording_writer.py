"""Persist already-calculated RustLab1 tables and render their recording figures."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma import alma_signal_filter
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_standalone_contracts import RustLab1RunResult
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.rustlab1_figure_exporter import (
    generate_rustlab1_figures,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_coordinate_repository import (
    merge_multiview_rustlab1_dataframe,
)


class RustLab1RecordingWriter:
    def prepare(self, path):
        output = Path(path).expanduser().resolve()
        output.mkdir(parents=True, exist_ok=True)
        return output

    def read_views(self, view_set, mappings):
        return merge_multiview_rustlab1_dataframe(view_set, pd, mappings)

    def write_recording(self, calculation, view_set, output_folder, settings):
        from matplotlib import pyplot as plt

        from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_preview_use_cases import GaitPreviewUseCases
        from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_stickplot_renderer import (
            GaitStickplotRenderer,
        )
        from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_result_writer import GaitResultWriter

        stem = view_set.name
        stride_path = output_folder / f"{stem}_rustlab1_strides.csv"
        parameters_path = output_folder / f"{stem}_rustlab1_parameters.csv"
        summary_path = output_folder / f"{stem}_rustlab1_summary.csv"
        calculation.strides.to_csv(stride_path, index=False)
        calculation.extraction.dataframe.to_csv(parameters_path, index=False)
        calculation.summary.to_csv(summary_path, index=False)
        output_files = [stride_path, parameters_path, summary_path]
        preview = GaitPreviewUseCases(None, GaitStickplotRenderer())
        plots, _, _ = preview.prepare_rustlab1(view_set, settings, calculation=calculation)
        for label, svg in plots:
            side = label.split(" · ", 1)[0].lower()
            path = output_folder / f"{stem}_{side}_stickplot.svg"
            path.write_bytes(svg)
            output_files.append(path)
        if settings.generate_figures:
            output_files.extend(
                generate_rustlab1_figures(
                    calculation.raw,
                    calculation.strides,
                    calculation.extraction,
                    output_folder / f"{stem}_rustlab1_figures",
                    settings,
                    alma_signal_filter,
                    plt,
                    calculation.preprocessed,
                )
            )
        GaitResultWriter().validate_outputs(output_files)
        return RustLab1RunResult(
            input_file=Path(view_set.bottom_csv), output_files=tuple(output_files), messages=calculation.messages
        )
