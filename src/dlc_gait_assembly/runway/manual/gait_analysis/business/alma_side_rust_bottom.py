"""Export native ALMA side strides and optional RustLab underside session measures."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_continuous_sequences import (
    prepare_full_recording_stickplot,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.gait_stride_detection import BOTTOM_METHODS
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_contracts import AlmaRunResult
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaViewCsvSet
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_preview_use_cases import GaitPreviewUseCases
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.alma_parameter_definitions import (
    ALMA_REMOVED_VARIABILITY_NAMES,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_alignment import (
    view_mappings_for_set,
)


def run_native_gait_analysis(inputs, output_folder, settings, progress_callback, *, outputs):
    if not inputs:
        raise ValueError("Select at least one recording to analyze.")
    combined = settings.output_format == "alma_side_rust_bottom"
    if combined and (
        settings.input_mode in {"Single side view", "Single-side ALMA"}
        or any(not isinstance(item, AlmaViewCsvSet) for item in inputs)
    ):
        raise ValueError("ALMA side + rust bottom requires matched left, right and bottom CSVs.")
    settings = outputs.resolve_calibration(settings)
    output_folder = Path(output_folder).expanduser().resolve()
    outputs.prepare(output_folder)
    results = []
    for index, item in enumerate(inputs, start=1):
        multiview = isinstance(item, AlmaViewCsvSet) and settings.input_mode not in {
            "Single side view", "Single-side ALMA"
        }
        name = item.name if isinstance(item, AlmaViewCsvSet) else Path(item).stem
        if progress_callback:
            progress_callback(index, len(inputs), f"Processing {name}")
        basename = re.sub(r"[^\w.\-]+", "_", name).strip("._") or "recording"
        destination = output_folder / basename
        suffix = 2
        while outputs.exists(destination):
            destination = output_folder / f"{basename}_{suffix}"
            suffix += 1
        outputs.prepare(destination)
        current = replace(
            settings, view_bodypart_mapping=view_mappings_for_set(settings, name),
            generate_rustlab1_parameters=False, stroke_analysis_enabled=False,
        )
        sides = ("left", "right") if multiview else ("side",)
        paths, messages, side_csvs = [], [], {}
        sources = []
        for side in sides:
            source = getattr(item, f"{side}_csv") if multiview else (
                item.alma_csv if isinstance(item, AlmaViewCsvSet) else item
            )
            sources.append((side.title(), Path(source)))
        if multiview and settings.stride_detection_method in BOTTOM_METHODS:
            sources.append(("Bottom", Path(item.bottom_csv)))
        # Reuse the exact preview preparation, including source-frame gaps and
        # per-camera timing/calibration. Each side keeps all its own strides.
        recordings = GaitPreviewUseCases(outputs, None)._recordings(sources, current)
        for label, result in recordings:
            side = label.lower()
            parameters, coords, stance, bodyparts, _drag, _starts, notes = result
            # The upstream writer is exactly DataFrame.to_csv(path), including its
            # index and original fractional percentage values. Drop only variability.
            native = parameters.drop(columns=list(ALMA_REMOVED_VARIABILITY_NAMES), errors="ignore")
            path = destination / f"{side}_stride_parameters.csv"
            outputs.write_table(native, path)
            outputs.validate_outputs((path,), expected_rows=len(native))
            side_csvs[side] = path
            paths.append(path)
            messages.extend(f"{side.title()}: {message}" for message in notes)
            if coords is not None:
                coords.attrs["view_label"] = side.title()
                if settings.generate_stickplot:
                    prepared = prepare_full_recording_stickplot(parameters, coords, bodyparts, stance)
                    if prepared is not None:
                        stickplot = destination / f"Stickplot_{side}.svg"
                        outputs.render_stickplot(prepared, stickplot)
                        paths.append(stickplot)
            if settings.generate_alma_representations:
                import pandas as pd

                from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_use_cases import (
                    recording_in_report_units,
                )

                paths.extend(outputs.render_alma(
                    recording_in_report_units(result, pd)[0], destination / "alma_figures" / side, side
                ))
        if combined:
            exported, notes = outputs.write_rustlab_bottom(item, destination, settings, side_csvs)
            paths.extend(exported)
            messages.extend(notes)
        outputs.validate_outputs(paths)
        source = item.alma_csv if isinstance(item, AlmaViewCsvSet) else Path(item)
        results.append(AlmaRunResult(Path(source), tuple(paths), tuple(messages)))
    return results
