"""Export the RustLab underside tables with or without the optional R runtime."""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.alma_parameter_definitions import (
    ALMA_PARAMETER_NAMES,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_alignment import (
    align_multiview_coordinates,
    view_mappings_for_set,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_calibration import view_scale
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_timing import read_view_track
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab_bottom_measurements import (
    BOTTOM_MARKERS,
    BOTTOM_PAWS,
    calculate_bottom_tables,
)
from dlc_gait_assembly.shared.business.external_command_contracts import ExternalCommand
from dlc_gait_assembly.shared.infrastructure.coordinate_csv_codec import read_analysis_csv
from dlc_gait_assembly.shared.infrastructure.external_process_runner import ExternalProcessSession
from dlc_gait_assembly.shared.infrastructure.packaged_resource_reader import resource_path
from dlc_gait_assembly.shared.infrastructure.windows_filesystem_paths import windows_filesystem_path

R_DEPENDENCIES_UNAVAILABLE = 78  # Exit status reserved by the bundled underside script.


class RustLabBottomExecutor:
    def __init__(self, *, rscript=None, session_factory=ExternalProcessSession):
        self.rscript = rscript
        self.session_factory = session_factory

    def run(self, view_set, destination, settings, side_csvs):
        bottom_csv = Path(view_set.bottom_csv)
        track = read_view_track(read_analysis_csv(windows_filesystem_path(bottom_csv)), bottom_csv, "bottom", settings)
        frame = align_multiview_coordinates({"bottom": track.frame}, pd, view_mappings_for_set(settings, view_set.name))
        if frame.columns.duplicated().any():
            raise ValueError("Multiple bottom markers map to the same label. Check Label matching.")
        parts, missing = [], []
        for marker in BOTTOM_MARKERS:
            if not all((marker, axis) in frame for axis in ("x", "y", "likelihood")):
                missing.append(marker)
                continue
            parts.append(
                pd.DataFrame(
                    {
                        "source_frame": np.arange(len(frame)),
                        "parameter": marker,
                        # Original RustLab reflects the bottom x axis. Translation of
                        # either axis cancels from all twenty measures.
                        "x_corr": -pd.to_numeric(frame[(marker, "x")], errors="coerce").to_numpy(),
                        "y_corr": pd.to_numeric(frame[(marker, "y")], errors="coerce").to_numpy(),
                        "likelyhood": pd.to_numeric(frame[(marker, "likelihood")], errors="coerce").to_numpy(),
                    }
                )
            )
        if all(marker in missing for marker in BOTTOM_PAWS):
            raise ValueError("RustLab underside measurements require at least one mapped bottom paw.")
        destination = Path(destination)
        windows_filesystem_path(destination).mkdir(parents=True, exist_ok=True)
        metadata = view_set.metadata
        mouse_match = re.search(r"\bM\d+\b", view_set.name.replace("_", " "), re.I)
        day_match = re.search(r"DPI\s*(\d+)", view_set.name, re.I)
        full_id = metadata.session_id if metadata and metadata.session_id else view_set.name
        mouse = (metadata.animal_id if metadata else None) or (mouse_match.group() if mouse_match else "unknown")
        day = (metadata.timepoint if metadata else None) or (day_match.group(1) + "days" if day_match else "unknown")
        scale = view_scale(settings, "bottom")
        coordinates = pd.concat(parts, ignore_index=True)
        paths = tuple(destination / name for name in ("all_raw_data.csv", "all_summarized_data.csv"))
        log_path = destination / "Rust_bottom_R.log"
        requested = self.rscript or os.environ.get("DLC_GAIT_RSCRIPT") or "Rscript"
        executable = shutil.which(str(requested))
        if executable:
            result = self._run_r(executable, coordinates, side_csvs, paths, {
                "full_id": full_id,
                "day": day,
                "mouse": mouse,
                "frame_rate": track.frame_rate,
                "likelihood_threshold": settings.likelihood_threshold,
                "stance_speed_threshold_px_frame": settings.stance_speed_threshold_px_frame,
                "maximum_tracking_speed_px_frame": settings.maximum_tracking_speed_px_frame,
                "bottom_pixels_per_cm": scale,
            })
            output = result.output.rstrip()
            r_available = not (
                result.returncode == R_DEPENDENCIES_UNAVAILABLE and "RustLab R dependencies unavailable:" in output
            )
            if r_available and result.returncode:
                windows_filesystem_path(log_path).write_text(result.output, encoding="utf-8")
                raise RuntimeError(f"RustLab underside R analysis failed:\n{result.output}")
        else:
            output = "Rscript was not found."
            r_available = False

        if r_available:
            output = "Backend: R\n" + output
        else:
            side_tables = {side: pd.read_csv(windows_filesystem_path(Path(path))) for side, path in side_csvs.items()}
            raw, summary = calculate_bottom_tables(
                coordinates, side_tables, (full_id, day, mouse), settings, track.frame_rate, scale
            )
            for path, table in zip(paths, (raw, summary), strict=True):
                write_rustlab_csv(windows_filesystem_path(path), table)
            output = "Backend: Python (RustLab underside formulas)\n" + output

        notes = ["RustLab: 20 underside measures plus session ALMA mean and sample SD for each side parameter."]
        notes.append(
            f"Effective underside settings: {track.frame_rate:g} FPS; tracking confidence "
            f">= {settings.likelihood_threshold:g}."
        )
        if missing:
            notes.append("Missing underside markers (dependent measures remain NA): " + ", ".join(missing))
            raw_markers = tuple(dict.fromkeys(str(column[0]) for column in track.frame.columns))
            notes.append(
                "Available source marker labels: " + ", ".join(raw_markers) + ". "
                "Assign anatomical body references explicitly in Label matching; marker names alone do not "
                "establish that body_center or tail_base is the required front/back center."
            )
        if scale is None:
            notes.append("Bottom calibration is unset; underside stride-length measures remain NA.")
        raw_values = pd.read_csv(windows_filesystem_path(paths[0]))
        missing_values = pd.to_numeric(raw_values["Value"], errors="coerce").isna()
        notes.append(f"Unavailable session measures: {int(missing_values.sum())}/{len(raw_values)}.")
        notes.append(
            "all_summarized_data.csv summarizes one recording/session: its sd and sem columns "
            "are undefined for a singleton. Per-stride ALMA sample SDs are separate Measure rows "
            "ending in __sd; those require at least two available stride measurements."
        )
        windows_filesystem_path(log_path).write_text(output + "\n\n" + "\n".join(notes) + "\n", encoding="utf-8")
        return (*paths, log_path), tuple(notes)

    def _run_r(self, executable, coordinates, side_csvs, paths, settings):
        with TemporaryDirectory(prefix="rust-bottom-") as temporary:
            temporary = Path(temporary)
            bottom_path = temporary / "bottom_coordinates.csv"
            coordinates.to_csv(bottom_path, index=False, na_rep="NA")
            local_side_csvs = {}
            for side, path in side_csvs.items():
                local_side = temporary / f"{side}_strides.csv"
                shutil.copyfile(windows_filesystem_path(Path(path)), local_side)
                local_side_csvs[side] = str(local_side)
            config = {
                "bottom_coordinates": str(bottom_path),
                "alma_csvs": local_side_csvs,
                "alma_parameters": list(ALMA_PARAMETER_NAMES),
                "output_dir": str(temporary),
                **settings,
            }
            config_path = temporary / "config.json"
            config_path.write_text(json.dumps(config, allow_nan=False), encoding="utf-8")
            script = resource_path("analysis", "rustlab1", "Run_ALMA_Side_Rust_Bottom.R")
            result = self.session_factory().run(ExternalCommand((executable, str(script), f"--config={config_path}")))
            if result.returncode == 0:
                generated = [temporary / path.name for path in paths]
                if any(not path.is_file() or path.stat().st_size == 0 for path in generated):
                    raise RuntimeError("RustLab underside R analysis did not produce both CSV outputs.")
                for source, path in zip(generated, paths, strict=True):
                    shutil.copyfile(source, windows_filesystem_path(path))
            return result


def write_rustlab_csv(path, table):
    """Keep write.csv row names, quoted strings, and unquoted missing numbers."""

    def cell(value):
        if isinstance(value, str):
            return '"' + value.replace('"', '""') + '"'
        return "NA" if pd.isna(value) else str(value)

    with path.open("w", encoding="utf-8", newline="") as stream:
        stream.write(",".join(map(cell, ("", *table.columns))) + "\n")
        for index, row in enumerate(table.itertuples(index=False, name=None), start=1):
            stream.write(",".join(map(cell, (str(index), *row))) + "\n")
