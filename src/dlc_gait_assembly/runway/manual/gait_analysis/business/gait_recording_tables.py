"""Independent left/right stride tables and one recording-level general table."""

from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma import alma_signal_filter
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_engine import calculate_alma_recording
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.gait_stride_detection import (
    BOTTOM_METHODS,
    bottom_detection,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.custom_features.custom_sop_feature_calculations import (
    extract_custom_sop_parameters,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.custom_features.custom_sop_feature_definitions import (
    CUSTOM_SOP_PARAMETER_NAMES,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_bottom_windows import (
    BOTTOM_FORE_NAMES,
    BOTTOM_STRIDE_NAMES,
    BOTTOM_TIME_COLUMNS,
    BottomWindows,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaViewCsvSet
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_stride_export import (
    FRAME_COLUMNS,
    STRIDE_DETAIL_COLUMNS,
    validate_stride_rows,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.alma_parameter_definitions import (
    ALMA_PARAMETER_NAMES,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.gait_parameter_registry import (
    rustlab1_definition,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.rustlab1_parameter_definitions import (
    rustlab1_parameter_names_for_scope,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_alignment import (
    view_mapping_for,
    view_mappings_for_set,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_calibration import settings_for_view
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_timing import (
    aligned_features,
    raw_on_timeline,
    read_view_track,
    stride_time_bounds,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_feature_extraction import (
    extract_rustlab1_parameters,
)

PARAMETER_FILENAMES = {
    "left": "left_stride_parameters.csv",
    "right": "right_stride_parameters.csv",
    "side": "side_stride_parameters.csv",
    "general": "general_parameters/general_parameters.csv",
}


def side_feature_names(side, scope):
    rustlab = tuple(
        name
        for name in rustlab1_parameter_names_for_scope(scope)
        if rustlab1_definition(name).views == f"{side.title()} side view"
    )
    custom = tuple(
        name
        for name in CUSTOM_SOP_PARAMETER_NAMES
        if name.startswith(f"{side}_") and name != "left_right_hindlimb_phase_offset"
    )
    return rustlab, custom


def metadata(table, item, side):
    table = table.copy()
    table.insert(0, "stride_side", side)
    table.insert(0, "recording", item.name if isinstance(item, AlmaViewCsvSet) else Path(item).stem)
    if isinstance(item, AlmaViewCsvSet) and item.metadata:
        for name, value in asdict(item.metadata).items():
            table[name] = value
    return table


def calculate_recording_tables(item, settings, outputs, *, figures, calculate=calculate_alma_recording):
    from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_use_cases import (
        is_single_side_input_mode,
        recording_in_report_units,
    )

    settings = outputs.resolve_calibration(replace(settings, enabled_parameter_names=None))
    paired = isinstance(item, AlmaViewCsvSet) and not is_single_side_input_mode(settings.input_mode)
    paths = (
        {side: getattr(item, f"{side}_csv") for side in ("left", "right", "bottom")}
        if paired
        else {"side": item.alma_csv if isinstance(item, AlmaViewCsvSet) else Path(item)}
    )
    tracks = {
        side: read_view_track(outputs.read_table(path, header=[1, 2]), path, side, settings)
        for side, path in paths.items()
    }
    mappings = view_mappings_for_set(settings, item.name) if paired else None
    messages, tables = [], {}
    for side, track in tracks.items():
        messages.append(
            f"{side.title()} timeline: {track.source}; {track.frame_rate:g} fps; {track.times[0]:.6f}–{track.stop_time:.6f} s."
        )
        if side == "bottom":
            continue
        current = replace(settings_for_view(settings, side), frame_rate=track.frame_rate)
        options = {}
        if settings.stride_detection_method in BOTTOM_METHODS:
            if not paired:
                raise ValueError("Bottom-paw detection requires paired left/right/bottom CSVs.")
            diagnostics = {}
            sampled = raw_on_timeline(tracks["bottom"], track.times)
            options = {
                "cycle_detection": bottom_detection(sampled, side, current, mappings, diagnostics),
                "detection_diagnostics": diagnostics,
            }
        result = recording_in_report_units(
            calculate(track.frame, current, view_mapping_for(mappings, side), **options), pd
        )
        figures.sides[side] = result
        messages.extend(f"{side.title()}: {message}" for message in result[6])
        scale = result[1].attrs.get("pixels_per_cm") if result[1] is not None else None
        if scale:
            configured = (settings.view_calibration or {}).get(side)
            node = dict(configured) if isinstance(configured, dict) else {}
            node["pixels_per_cm"] = scale
            settings = replace(settings, view_calibration={**(settings.view_calibration or {}), side: node})
            messages.append(f"{side.title()} calibration: {scale} pixels/cm.")
    bottom = None
    if paired:
        common_start = max(track.times[0] for track in tracks.values())
        common_stop = min(track.stop_time for track in tracks.values())
        if common_stop <= common_start:
            raise ValueError(
                "The left, right and bottom CSV timestamps do not overlap. Check pairing and Setup → View timing offsets."
            )
        first_raw, _ = aligned_features(tracks, "left", settings, mappings, alma_signal_filter)
        bottom = BottomWindows(tracks["bottom"], settings, mappings, alma_signal_filter, first_raw)
    for side, result in figures.sides.items():
        track = tracks[side]
        cycles = result[0].copy()
        # Real strides only; stationary ALMA summaries are not stride rows.
        for name in (*FRAME_COLUMNS, *ALMA_PARAMETER_NAMES):
            cycles[name] = pd.to_numeric(cycles[name], errors="coerce")
        cycles = cycles.loc[cycles[FRAME_COLUMNS[1]].gt(cycles[FRAME_COLUMNS[0]])].reset_index(drop=True)
        table = cycles.reindex(columns=[*STRIDE_DETAIL_COLUMNS, *FRAME_COLUMNS, *ALMA_PARAMETER_NAMES]).copy()
        bounds = stride_time_bounds(cycles, track)
        table["stride_start (s)"] = [a for a, _ in bounds]
        table["stride_stop (s)"] = [b for _, b in bounds]
        table["source_start_frame"] = [track.frame_ids[int(a)] for a in cycles[FRAME_COLUMNS[0]]]
        table["source_end_frame"] = [track.frame_ids[int(b)] for b in cycles[FRAME_COLUMNS[1]]]
        table.insert(0, "gait_cycle", range(1, len(table) + 1))
        if paired:
            raw, prepared = aligned_features(tracks, side, settings, mappings, alma_signal_filter)
            current = replace(settings, frame_rate=track.frame_rate)
            rustlab = extract_rustlab1_parameters(raw, cycles, current, alma_signal_filter, prepared)
            custom = extract_custom_sop_parameters(raw, cycles, current, alma_signal_filter, prepared)
            rust_names, custom_names = side_feature_names(side, settings.limb_scope)
            rust_frame = rustlab.dataframe if rustlab.dataframe is not None else pd.DataFrame(index=table.index)
            forelimbs = settings.limb_scope == "Hindlimb + Forelimb"
            bottom_names = (*BOTTOM_STRIDE_NAMES, *(BOTTOM_FORE_NAMES if forelimbs else ()), *BOTTOM_TIME_COLUMNS)
            bottom_frame = pd.DataFrame([bottom.stride(a, b, side, forelimbs) for a, b in bounds], columns=bottom_names)
            table = pd.concat(
                [
                    table,
                    rust_frame.reindex(columns=rust_names),
                    custom.dataframe.reindex(columns=custom_names),
                    bottom_frame,
                ],
                axis=1,
            )
            # Figures for this side use this side's own cycles and time alignment.
            # Keep cross-view geometry available, but do not summarize opposite-side
            # measurements over this side's strides as if they were its own strides.
            figure_frame = rust_frame.copy()
            own_or_bottom = {*rust_names, *BOTTOM_FORE_NAMES}
            for name in rustlab1_parameter_names_for_scope(settings.limb_scope):
                if name in figure_frame and name not in own_or_bottom:
                    figure_frame[name] = np.nan
            for name in BOTTOM_FORE_NAMES:
                if name in bottom_frame:
                    figure_frame[name] = bottom_frame[name]
            figures.rustlab_by_side[side] = (
                raw,
                cycles.assign(**{"limb (hind left / right)": side}),
                replace(rustlab, dataframe=figure_frame),
                current,
                alma_signal_filter,
                prepared,
            )
        validate_stride_rows(table, {"side": cycles})
        tables[side] = metadata(table, item, side)
        accepted = int(cycles["cycle duration (s)"].notna().sum())
        messages.append(
            f"{side.title()}: {len(cycles)} stride rows; {accepted} accepted for ALMA measurements. No opposite-side stride pairing is applied."
        )
    general = {"recording": item.name if isinstance(item, AlmaViewCsvSet) else Path(item).stem}
    for side, track in tracks.items():
        general.update(
            {
                f"{side}_source_csv": str(track.path),
                f"{side}_frame_rate": track.frame_rate,
                f"{side}_start (s)": track.times[0],
                f"{side}_stop (s)": track.stop_time,
                f"{side}_timing_source": track.source,
            }
        )
        if side in tables:
            general[f"{side}_stride_count"] = len(tables[side])
    if paired:
        general.update(
            {
                "synchronization_start (s)": common_start,
                "synchronization_stop (s)": common_stop,
                "bottom_x_pixels_per_cm": bottom.x_scale,
                "bottom_y_pixels_per_cm": bottom.y_scale,
                **bottom.general(common_start, common_stop),
            }
        )
    else:
        general["synchronization_status"] = "Unavailable: single side recording"
    if isinstance(item, AlmaViewCsvSet) and item.metadata:
        general.update(asdict(item.metadata))
    tables["general"] = pd.DataFrame([general])
    return tables, tuple(messages)
