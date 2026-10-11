"""Read generated CSV/SVG artifacts and prepare parameter-figure pages for presentation."""

from __future__ import annotations

import csv
from pathlib import Path

from dlc_gait_assembly.shared.infrastructure.packaged_resource_reader import resource_path
from dlc_gait_assembly.shared.infrastructure.svg_preview_sanitizer import qt_safe_svg_bytes


def previewable_output_paths(output_files) -> tuple[Path, ...]:
    """Return existing SVG and CSV outputs once, preserving pipeline order."""
    paths: list[Path] = []
    seen: set[Path] = set()
    for output_file in output_files:
        path = Path(output_file)
        if path.suffix.lower() not in {".svg", ".csv"} or not path.is_file():
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        paths.append(resolved)
    return tuple(paths)


class GaitResultReader:
    previewable_paths = staticmethod(previewable_output_paths)

    @property
    def preview_root(self):
        return resource_path("analysis_previews")

    def exists(self, path):
        return Path(path).is_file()

    def svg_bytes(self, path):
        return qt_safe_svg_bytes(Path(path).read_bytes())

    def table_preview(self, path, limit):
        try:
            with Path(path).open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
                reader = csv.reader(handle)
                header = next(reader, [])
                rows = []
                for index, row in enumerate(reader):
                    if index >= limit:
                        break
                    rows.append(row)
            return header, rows
        except csv.Error as exc:
            raise ValueError(str(exc)) from exc

    def parameter_figures(self, selected_paths, progress_callback=None):
        import pandas as pd

        from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_parameter_figures import (
            parameter_figure_pages,
        )

        paths = selected_paths if isinstance(selected_paths, (tuple, list)) else (selected_paths,)
        plots = []
        for path in paths:
            path = Path(path)
            pages = parameter_figure_pages(pd.read_csv(path), progress_callback=progress_callback)
            recording = path.parent.parent.name if path.name == "general_parameters.csv" else path.parent.name
            plots.extend((f"{recording} · {path.stem} · {label}", svg) for label, svg in pages)
        if not plots:
            raise ValueError("No recognized gait parameter columns were found in this CSV.")
        return plots
