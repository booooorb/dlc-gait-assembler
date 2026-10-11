"""Persist automatic review previews independently of parameter export."""

from dataclasses import replace
from pathlib import Path

from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_contracts import AlmaRunResult
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaViewCsvSet
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_preview_use_cases import GaitPreviewUseCases
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_alignment import (
    view_mappings_for_set,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_stickplot_renderer import (
    GaitStickplotRenderer,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_result_writer import GaitResultWriter


def write_gait_stickplot_previews(inputs, output_folder, settings, progress_callback=None):
    preview = GaitPreviewUseCases(GaitResultWriter(), GaitStickplotRenderer())
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    results = []
    for index, item in enumerate(inputs, start=1):
        if isinstance(item, AlmaViewCsvSet):
            name, source = item.name, item.alma_csv
            views = [("Left", item.left_csv), ("Right", item.right_csv), ("Bottom", item.bottom_csv)]
            current = replace(settings, view_bodypart_mapping=view_mappings_for_set(settings, item.name))
        else:
            source = Path(item)
            name, views, current = source.stem, [("Side", source)], settings
        if progress_callback:
            progress_callback(index, len(inputs), f"Preparing {name}")
        plots, _, messages = preview.prepare(views, current)
        files = []
        for label, svg in plots:
            view_name = label.split(" · ", 1)[0].lower()
            destination = output_folder / f"{index:03d}_{Path(name).name}_{view_name}_stickplot.svg"
            destination.write_bytes(svg)
            files.append(destination)
        results.append(AlmaRunResult(source, tuple(files), messages))
    return results
