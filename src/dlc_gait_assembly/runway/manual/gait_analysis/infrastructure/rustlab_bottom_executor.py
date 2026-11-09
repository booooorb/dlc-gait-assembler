"""Run the underside-only R script and preserve its native CSV serialization."""

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
from dlc_gait_assembly.shared.business.external_command_contracts import ExternalCommand
from dlc_gait_assembly.shared.infrastructure.coordinate_csv_codec import read_analysis_csv
from dlc_gait_assembly.shared.infrastructure.external_process_runner import ExternalProcessSession
from dlc_gait_assembly.shared.infrastructure.packaged_resource_reader import resource_path

BOTTOM_MARKERS = (
    "d-back-left", "d-back-right", "d-front-left", "d-front-right", "d-center-back", "d-center-front"
)


class RustLabBottomExecutor:
    def __init__(self, *, rscript=None, session_factory=ExternalProcessSession):
        self.rscript = rscript
        self.session_factory = session_factory

    def run(self, view_set, destination, settings, side_csvs):
        requested = self.rscript or os.environ.get("DLC_GAIT_RSCRIPT") or "Rscript"
        executable = shutil.which(str(requested))
        if executable is None:
            raise RuntimeError("ALMA side + rust bottom requires Rscript and R packages dplyr, tidyr and jsonlite.")
        track = read_view_track(read_analysis_csv(view_set.bottom_csv), view_set.bottom_csv, "bottom", settings)
        frame = align_multiview_coordinates(
            {"bottom": track.frame}, pd, view_mappings_for_set(settings, view_set.name)
        )
        if frame.columns.duplicated().any():
            raise ValueError("Multiple bottom markers map to the same label. Check Label matching.")
        parts, missing = [], []
        for marker in BOTTOM_MARKERS:
            if not all((marker, axis) in frame for axis in ("x", "y", "likelihood")):
                missing.append(marker)
                continue
            parts.append(pd.DataFrame({
                "source_frame": np.arange(len(frame)),
                "parameter": marker,
                # Original RustLab reflects the bottom x axis. Translation of
                # either axis cancels from all twenty measures.
                "x_corr": -pd.to_numeric(frame[(marker, "x")], errors="coerce").to_numpy(),
                "y_corr": pd.to_numeric(frame[(marker, "y")], errors="coerce").to_numpy(),
                "likelyhood": pd.to_numeric(frame[(marker, "likelihood")], errors="coerce").to_numpy(),
            }))
        if not parts or not any(part.parameter.iloc[0] in BOTTOM_MARKERS[:4] for part in parts):
            raise ValueError("RustLab underside measurements require at least one mapped bottom paw.")
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        metadata = view_set.metadata
        mouse_match = re.search(r"\bM\d+\b", view_set.name.replace("_", " "), re.I)
        day_match = re.search(r"DPI\s*(\d+)", view_set.name, re.I)
        with TemporaryDirectory(prefix="rust-bottom-") as temporary:
            temporary = Path(temporary)
            bottom_path = temporary / "bottom_coordinates.csv"
            pd.concat(parts, ignore_index=True).to_csv(bottom_path, index=False, na_rep="NA")
            config = {
                "bottom_coordinates": str(bottom_path),
                "alma_csvs": {side: str(path) for side, path in side_csvs.items()},
                "alma_parameters": list(ALMA_PARAMETER_NAMES),
                "output_dir": str(destination),
                "full_id": metadata.session_id if metadata and metadata.session_id else view_set.name,
                "mouse": metadata.animal_id if metadata and metadata.animal_id else (
                    mouse_match.group() if mouse_match else "unknown"
                ),
                "day": metadata.timepoint if metadata and metadata.timepoint else (
                    day_match.group(1) + "days" if day_match else "unknown"
                ),
                "frame_rate": track.frame_rate,
                "likelihood_threshold": settings.likelihood_threshold,
                "stance_speed_threshold_px_frame": settings.stance_speed_threshold_px_frame,
                "maximum_tracking_speed_px_frame": settings.maximum_tracking_speed_px_frame,
                "bottom_pixels_per_cm": view_scale(settings, "bottom"),
            }
            config_path = temporary / "config.json"
            config_path.write_text(json.dumps(config, allow_nan=False), encoding="utf-8")
            script = resource_path("analysis", "rustlab1", "Run_ALMA_Side_Rust_Bottom.R")
            result = self.session_factory().run(ExternalCommand((executable, str(script), f"--config={config_path}")))
        log_path = destination / "Rust_bottom_R.log"
        log_path.write_text(result.output, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"RustLab underside R analysis failed:\n{result.output}")
        paths = tuple(destination / name for name in ("all_raw_data.csv", "all_summarized_data.csv"))
        if any(not path.is_file() or path.stat().st_size == 0 for path in paths):
            raise RuntimeError("RustLab underside R analysis did not produce both CSV outputs.")
        notes = ["RustLab: 20 underside measures plus session ALMA mean and sample SD for each side parameter."]
        if missing:
            notes.append("Missing underside markers (dependent measures remain NA): " + ", ".join(missing))
        if config["bottom_pixels_per_cm"] is None:
            notes.append("Bottom calibration is unset; underside stride-length measures remain NA.")
        return (*paths, log_path), tuple(notes)
