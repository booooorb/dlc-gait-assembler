"""Coordinate recording calculations, selected parameters, output tables, figures, and run reports through ports."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma import alma_signal_filter
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_engine import calculate_alma_recording
from dlc_gait_assembly.runway.manual.gait_analysis.business.custom_features.custom_sop_feature_calculations import (
    extract_custom_sop_parameters,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.custom_features.custom_sop_feature_definitions import (
    CUSTOM_SOP_PARAMETER_NAMES,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_contracts import AlmaRunResult
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_ports import GaitOutputPort
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaViewCsvSet
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_stride_export import (
    STRIDE_DETAIL_COLUMNS,
    validate_stride_rows,
    with_stride_details,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.alma_parameter_definitions import (
    ALMA_PARAMETER_NAMES,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.rustlab1_parameter_definitions import (
    rustlab1_parameter_names_for_scope,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_coordinate_normalization import (
    prepare_alma_coordinates,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_alignment import (
    view_mapping_for,
    view_mappings_for_set,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_feature_extraction import (
    extract_rustlab1_parameters,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_cycle_alignment import (
    align_parameters_to_cycles,
)

FRAME_COLUMNS = ("stride_start (frame)", "stride_end (frame)")


@dataclass
class RecordingFigures:
    """Keep the exact calculations used by the CSV available to the exporters."""

    sides: dict = field(default_factory=dict)
    rustlab: tuple | None = None
    rustlab_by_side: dict = field(default_factory=dict)


def alma_input_label(item):
    return item.name if isinstance(item, AlmaViewCsvSet) else Path(item).stem


def is_single_side_input_mode(input_mode):
    return input_mode in {"Single side view", "Single-side ALMA"}


def recording_in_report_units(result, pd):
    """Legacy ALMA returns fractions in columns labelled (%); reports use 0–100."""
    parameters = result[0].copy()
    for name in ("stance percentage (%)", "swing percentage (%)", "drag percentage (%)"):
        if name in parameters:
            parameters[name] = pd.to_numeric(parameters[name], errors="coerce") * 100.0
    return with_stride_details((parameters, *result[1:]))


def calculate_recording_table(
    item, settings, outputs, pd, kinematics=alma_signal_filter, calculate=calculate_alma_recording, *, figures=None
):
    """Legacy wide-table calculation for compatibility; not used by file exports.

    New exports use calculate_recording_tables with independent side windows.
    """
    import numpy as np

    # Old profiles may disable a family or select only a few columns. The export
    # contract is now the complete supported schema, independent of those flags.
    settings = outputs.resolve_calibration(replace(settings, enabled_parameter_names=None))
    multiview = isinstance(item, AlmaViewCsvSet) and not is_single_side_input_mode(settings.input_mode)
    if not multiview:
        source = item.alma_csv if isinstance(item, AlmaViewCsvSet) else Path(item)
        raw = outputs.read_table(source, header=[1, 2])
        result = recording_in_report_units(calculate(raw, settings), pd)
        parameters, _, _, _, _, _, messages = result
        if figures is not None:
            figures.sides["side"] = result
        identifiers = [name for name in ("limb (hind left / right)",) if name in parameters]
        table = parameters.reindex(
            columns=[*identifiers, *STRIDE_DETAIL_COLUMNS, *FRAME_COLUMNS, *ALMA_PARAMETER_NAMES]
        ).copy()
        side_parameters = {"side": parameters}
    else:
        mappings = view_mappings_for_set(settings, item.name)
        from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.gait_stride_detection import (
            BOTTOM_METHODS,
            bottom_detection,
        )
        from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_calibration import (
            settings_for_view,
        )

        bottom_raw = (
            outputs.read_table(item.bottom_csv, header=[1, 2])
            if settings.stride_detection_method in BOTTOM_METHODS
            else None
        )
        side_parameters, messages = {}, []
        for side in ("left", "right"):
            raw = outputs.read_table(getattr(item, f"{side}_csv"), header=[1, 2])
            current = settings_for_view(settings, side)
            if bottom_raw is not None:
                if len(bottom_raw) != len(raw):
                    raise ValueError(
                        "Bottom and side CSVs must have the same synchronized frame count for bottom-paw detection."
                    )
                diagnostics = {}
                detection = bottom_detection(bottom_raw, side, current, mappings, diagnostics)
                result = calculate(
                    raw,
                    current,
                    view_mapping_for(mappings, side),
                    cycle_detection=detection,
                    detection_diagnostics=diagnostics,
                )
            else:
                result = calculate(raw, current, view_mapping_for(mappings, side))
            result = recording_in_report_units(result, pd)
            side_parameters[side] = result[0]
            if figures is not None:
                figures.sides[side] = result
            if result[1] is not None and result[1].attrs.get("pixels_per_cm"):
                # Carry the exact scale used by ALMA into post-ALMA measurements.
                configured = (settings.view_calibration or {}).get(side, {})
                node = dict(configured) if isinstance(configured, dict) else {}
                node.setdefault("pixels_per_cm", result[1].attrs["pixels_per_cm"])
                settings = replace(settings, view_calibration={**(settings.view_calibration or {}), side: node})
            messages.extend(f"{side.title()}: {message}" for message in result[6])
            if result[1] is not None:
                messages.append(f"{side.title()} calibration: {result[1].attrs.get('pixels_per_cm')} pixels/cm.")
        reference = "left" if not side_parameters["left"].empty else "right"
        cycles = side_parameters[reference]
        opposite = "right" if reference == "left" else "left"
        aligned = align_parameters_to_cycles(cycles, side_parameters[opposite], opposite, pd, np)
        side_columns = [*STRIDE_DETAIL_COLUMNS, *FRAME_COLUMNS, *ALMA_PARAMETER_NAMES]
        tables = {}
        tables[reference] = cycles.reindex(columns=side_columns).reset_index(drop=True).add_prefix(f"{reference}__")
        tables[opposite] = aligned.reindex(columns=[f"{opposite}__{name}" for name in side_columns])
        raw = outputs.read_views(item, mappings)
        prepared = prepare_alma_coordinates(raw, settings, kinematics)
        rustlab = extract_rustlab1_parameters(raw, cycles, settings, kinematics, prepared)
        custom = extract_custom_sop_parameters(raw, cycles, settings, kinematics, prepared)
        rustlab_names = rustlab1_parameter_names_for_scope(settings.limb_scope)
        rustlab_table = rustlab.dataframe if rustlab.dataframe is not None else pd.DataFrame(index=range(len(cycles)))
        table = pd.concat(
            [
                tables["left"],
                tables["right"],
                rustlab_table.reindex(columns=rustlab_names).reset_index(drop=True),
                custom.dataframe.reindex(columns=CUSTOM_SOP_PARAMETER_NAMES).reset_index(drop=True),
            ],
            axis=1,
        )
        table.insert(0, "reference_view", reference)
        # Retain opposite-view cycles that have no overlapping reference cycle.
        # Pairing is useful for comparison, but must never drop observed strides.
        opposite_bounds = [f"{opposite}__{name}" for name in FRAME_COLUMNS]
        matched_bounds = set(map(tuple, aligned.reindex(columns=opposite_bounds).dropna().to_numpy()))
        other = side_parameters[opposite]
        extra_mask = [tuple(row) not in matched_bounds for row in other.reindex(columns=FRAME_COLUMNS).to_numpy()]
        extra = other.loc[extra_mask].reset_index(drop=True)
        if len(extra):
            extra_rustlab = extract_rustlab1_parameters(raw, extra, settings, kinematics, prepared)
            extra_custom = extract_custom_sop_parameters(raw, extra, settings, kinematics, prepared)
            extra_rustlab_table = (
                extra_rustlab.dataframe
                if extra_rustlab.dataframe is not None
                else pd.DataFrame(index=range(len(extra)))
            )
            extra_table = pd.concat(
                [
                    extra.reindex(columns=side_columns).add_prefix(f"{opposite}__"),
                    extra_rustlab_table.reindex(columns=rustlab_names).reset_index(drop=True),
                    extra_custom.dataframe.reindex(columns=CUSTOM_SOP_PARAMETER_NAMES).reset_index(drop=True),
                ],
                axis=1,
            )
            extra_table["reference_view"] = opposite
            table = pd.concat([table, extra_table.reindex(columns=table.columns)], ignore_index=True)
            messages.append(f"{len(extra)} unmatched {opposite}-view cycles retained as additional rows.")
            figure_rustlab = pd.concat([rustlab_table, extra_rustlab_table], ignore_index=True)
            figure_rustlab["gait_cycle"] = range(1, len(figure_rustlab) + 1)
            rustlab = replace(rustlab, dataframe=figure_rustlab)
        if figures is not None:
            # Cycle-distribution figures include every side's actual cycles,
            # including the paired side, with explicit camera labels. The legacy
            # extractor can leave its limb column blank for spontaneous walking.
            figure_cycles = pd.concat(
                [frame.assign(**{"limb (hind left / right)": side}) for side, frame in side_parameters.items()],
                ignore_index=True,
            )
            figures.rustlab = (raw, figure_cycles, rustlab, settings, kinematics, prepared)

        missing = [name for name in (*rustlab_names, *CUSTOM_SOP_PARAMETER_NAMES) if table[name].isna().all()]
        if missing and len(table):
            messages.append(f"{len(missing)} post-ALMA parameter columns have no valid values and remain blank.")
        unmatched = int((~aligned[f"{opposite}__cycle_match_valid"]).sum()) if len(aligned) else 0
        if unmatched:
            messages.append(
                f"{unmatched} {reference}-view cycles had no matching {opposite}-view cycle; those opposite-view values remain blank."
            )
    # ALMA's mixed limb/numeric array can arrive as strings; keep real NaNs and numbers.
    numeric_names = set(ALMA_PARAMETER_NAMES) | set(FRAME_COLUMNS)
    numeric_names |= {
        f"{side}__{name}" for side in ("left", "right") for name in (*ALMA_PARAMETER_NAMES, *FRAME_COLUMNS)
    }
    table = pd.DataFrame(
        {
            column: pd.to_numeric(table[column], errors="coerce") if column in numeric_names else table[column]
            for column in table.columns
        },
        index=table.index,
    )
    validate_stride_rows(table, side_parameters)
    table.insert(0, "gait_cycle", range(1, len(table) + 1))
    table.insert(0, "recording", alma_input_label(item))
    if isinstance(item, AlmaViewCsvSet) and item.metadata is not None:
        for field, value in asdict(item.metadata).items():
            table[field] = value
    if table.empty:
        messages = [*messages, "No gait cycles detected; parameter column headers are retained."]
    return table, tuple(messages)


class GaitAnalysisUseCases:
    """Independent side-stride and general parameter files for each recording."""

    def __init__(self, outputs: GaitOutputPort):
        self.outputs = outputs

    def run(self, csv_files, output_folder, settings, progress_callback=None):
        import re

        from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_recording_tables import (
            PARAMETER_FILENAMES,
            calculate_recording_tables,
        )

        if not csv_files:
            raise ValueError("Select at least one recording to analyze.")
        output_folder = Path(output_folder).expanduser().resolve()
        self.outputs.prepare(output_folder)
        report = output_folder / "export_report.txt"
        lines = [
            f"Gait analysis export: {len(csv_files)} separate recording(s).",
            f"Stride detector: {settings.stride_detection_method}",
            f"Likelihood cutoff: {settings.likelihood_threshold:g}.",
            "Each recording has independent left_stride_parameters.csv and right_stride_parameters.csv.",
            "General recording-level synchronization is in general_parameters/general_parameters.csv.",
            "Single-side inputs have side_stride_parameters.csv and a general metadata file.",
            "Each side uses all of its own detected strides; left and right strides are never paired into rows.",
            "Bottom stride features are recalculated over each side’s [stride_start (s), stride_stop (s)) video-time interval.",
            "CSV timestamps take precedence; otherwise filename clip start + source frame/FPS determines video time.",
            "Matched bottom source frames and time/tracking coverage are included in each stride row. Incomplete bottom windows remain blank.",
            "passed_stride_filters marks ALMA acceptance; rejected measurements remain blank with their stride bounds retained.",
            "Whole-recording synchronization uses only the common time interval and reports its usable tracking coverage.",
            "All supported parameters are retained in their applicable side/general tables. Standard deviations remain; ALMA multi-stride variability is excluded.",
            "Stick plots cover the full recording; their stride boundaries match the corresponding side table.",
            "Each RustLab1 figure subfolder states which side’s stride windows it uses.",
            "",
        ]
        pending = []
        for index, item in enumerate(csv_files, start=1):
            if progress_callback:
                progress_callback(index, len(csv_files), f"Processing {alma_input_label(item)}")
            figures = RecordingFigures()
            tables, messages = calculate_recording_tables(item, settings, self.outputs, figures=figures)
            name = re.sub(r"[^\w.-]+", "_", alma_input_label(item)).strip("._")[:100] or "recording"
            folder = output_folder / f"{index:03d}_{name}"
            self.outputs.prepare(folder)
            files = []
            for side, table in tables.items():
                path = folder / PARAMETER_FILENAMES[side]
                self.outputs.prepare(path.parent)
                self.outputs.write_table(table, path, index=False)
                self.outputs.validate_outputs((path,), expected_rows=len(table))
                files.append(path)
            files.extend(self._write_figures(figures, folder, settings))
            counts = ", ".join(f"{side}: {len(table)} rows" for side, table in tables.items())
            lines.extend([f"{alma_input_label(item)} — {counts}", *messages])
            lines.extend(f"  {path.relative_to(output_folder)}" for path in files)
            lines.append("")
            pending.append(
                (item, files, (*messages, f"Saved separate parameter tables and figures to {folder} ({counts})."))
            )
        self.outputs.write_text(report, "\n".join(lines))
        self.outputs.validate_outputs((report,))
        return [
            AlmaRunResult(item.alma_csv if isinstance(item, AlmaViewCsvSet) else Path(item), (*files, report), messages)
            for item, files, messages in pending
        ]

    def _write_figures(self, figures, folder, settings):
        from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_continuous_sequences import (
            prepare_full_recording_stickplot,
        )

        files = []
        self.outputs.prepare(folder)
        for side, result in figures.sides.items():
            parameters, coords, stance, bodyparts = result[:4]
            if settings.generate_stickplot:
                coords.attrs["view_label"] = side.title()
                prepared = prepare_full_recording_stickplot(parameters, coords, bodyparts, stance)
                if prepared is None:
                    raise ValueError(f"No tracking coordinates available for the {side} stick plot.")
                destination = folder / f"{side}_stickplot.svg"
                self.outputs.render_stickplot(prepared, destination)
                files.append(destination)
            if settings.generate_alma_representations:
                paths = self.outputs.render_alma(parameters, folder, side)
                if not paths:
                    raise RuntimeError(f"No {side} ALMA figures were exported.")
                files.extend(paths)
        if settings.generate_rustlab1_parameters and figures.rustlab is not None:
            raw, cycles, extracted, resolved, filtering, prepared = figures.rustlab
            paths = self.outputs.render_rustlab1(
                raw, cycles, extracted, folder / "rustlab1_figures", resolved, filtering, prepared
            )
            if not paths:
                raise RuntimeError("No RustLab1 figures were exported. Check the paired CSV labels.")
            files.extend(paths)
        if settings.generate_rustlab1_parameters:
            for side, context in figures.rustlab_by_side.items():
                raw, cycles, extracted, resolved, filtering, prepared = context
                paths = self.outputs.render_rustlab1(
                    raw,
                    cycles,
                    extracted,
                    folder / "rustlab1_figures" / f"{side}_strides",
                    resolved,
                    filtering,
                    prepared,
                )
                if not paths:
                    raise RuntimeError(f"No RustLab1 figures were exported for {side} strides.")
                files.extend(paths)
        self.outputs.validate_outputs(files)
        return tuple(files)
