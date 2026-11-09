"""Execute the packaged adapted R analysis without depending on a source checkout."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import ALMA_BODYPARTS
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_continuous_sequences import (
    prepare_full_recording_stickplot,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_standalone_contracts import RustLab1RunResult
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_alignment import (
    align_multiview_coordinates,
    rustlab1_marker_for_view,
    view_mappings_for_set,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_r_analysis import (
    detect_r_gmm_phases,
    r_calibration_configuration,
    r_filter_configuration,
    validate_r_settings,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_stickplot_renderer import (
    render_prepared_stickplot,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_calibration_loader import (
    resolve_calibration_settings,
)
from dlc_gait_assembly.shared.business.external_command_contracts import ExternalCommand
from dlc_gait_assembly.shared.infrastructure.coordinate_csv_codec import read_dlc_csv
from dlc_gait_assembly.shared.infrastructure.external_process_runner import ExternalProcessSession
from dlc_gait_assembly.shared.infrastructure.packaged_resource_reader import resource_path
from dlc_gait_assembly.shared.infrastructure.session_directory_allocator import make_session_output_dir

_NATIVE_MARKERS = {
    "left": {
        "back-toe": "toe",
        "back-mtp": "MTP",
        "back-ankle": "ankle",
        "back-knee": "knee",
        "hip": "hip",
        "iliac-crest": "iliac_crest",
    },
    "right": {
        "back-toe": "back_toe",
        "back-mtp": "MTP",
        "back-ankle": "ankle",
        "back-knee": "knee",
        "hip": "hip",
        "iliac-crest": "iliac_crest",
    },
    "bottom": {"back-left": "LH_paw", "back-right": "RH_paw"},
}


class RustLab1RExecutor:
    def __init__(self, *, rscript=None, session_factory=ExternalProcessSession):
        self.rscript = rscript
        self.session_factory = session_factory

    def _executable(self):
        requested = self.rscript or os.environ.get("DLC_GAIT_RSCRIPT") or "Rscript"
        executable = shutil.which(str(requested))
        if executable is None:
            raise RuntimeError(
                "Standalone RustLab1 requires Rscript and the R packages dplyr, tidyr and jsonlite. "
                "Install R or set DLC_GAIT_RSCRIPT to its executable."
            )
        return executable

    def _execute(self, view_set, destination, settings, *, preview=False):
        validate_r_settings(settings)
        executable = self._executable()
        settings = resolve_calibration_settings(settings, allow_unscaled=True)
        paths = {
            side: Path(getattr(view_set, f"{side}_csv")).expanduser().resolve() for side in ("left", "right", "bottom")
        }
        frames = {}
        for side, path in paths.items():
            frame = read_dlc_csv(path)
            frame.columns = frame.columns.droplevel(0)
            frames[side] = frame
        source_index = frames["left"].index
        if not all(frame.index.equals(source_index) for frame in frames.values()):
            raise ValueError("RustLab1 R requires synchronized views with identical source-frame indices.")
        mappings = view_mappings_for_set(settings, view_set.name)
        merged = align_multiview_coordinates(frames, pd, mappings)
        phase = detect_r_gmm_phases(merged, settings)
        aliases = {}
        for side, frame in frames.items():
            aliases[side] = {}
            prefix = {"left": "l-", "right": "r-", "bottom": "d-"}[side]
            for marker, _axis in frame.columns:
                canonical = rustlab1_marker_for_view(marker, side, mappings)
                native = _NATIVE_MARKERS[side].get(canonical.removeprefix(prefix))
                if native is not None:
                    aliases[side][str(marker)] = native
            required = (
                {"LH_paw", "RH_paw"}
                if side == "bottom"
                else {"toe" if side == "left" else "back_toe", "ankle", "hip", "iliac_crest"}
            )
            missing = required - set(aliases[side].values())
            if missing:
                raise ValueError(f"RustLab1 R missing {side} markers: {', '.join(sorted(missing))}")
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        diagnostics = destination / "diagnostics"
        phase_path = destination / "Stride_detection.csv"
        phase.to_csv(phase_path, index=False, na_rep="NA")
        metadata = view_set.metadata
        mouse = metadata.animal_id if metadata and metadata.animal_id else None
        mouse_match = re.search(r"\bM\d+\b", view_set.name.replace("_", " "), re.I)
        day = metadata.timepoint if metadata and metadata.timepoint else None
        day_match = re.search(r"DPI\s*(\d+)", view_set.name, re.I)
        config = {
            "input_files": {side: str(path) for side, path in paths.items()},
            "marker_mapping": aliases,
            "frame_count": len(merged),
            "frame_rate": settings.frame_rate,
            "filter_cutoff": settings.filter_cutoff,
            "timing_likelihood_threshold": settings.likelihood_threshold,
            "maximum_coordinate_gap_frames": settings.maximum_coordinate_gap_frames,
            "minimum_complete_strides": settings.minimum_complete_strides,
            "full_id": metadata.session_id if metadata and metadata.session_id else view_set.name,
            "mouse": mouse or (mouse_match.group() if mouse_match else "unknown"),
            "day": day or (day_match.group(1) + "days" if day_match else "unknown"),
            **r_filter_configuration(settings),
            **r_calibration_configuration(merged, settings),
        }
        config_path = destination / "run_config.json"
        config_path.write_text(json.dumps(config, indent=2, allow_nan=False), encoding="utf-8")
        script = resource_path("analysis", "rustlab1", "Run_GMM_Adapted_RustLab1.R")
        arguments = (
            executable,
            str(script),
            f"--config={config_path}",
            f"--timing-file={phase_path}",
            f"--output-dir={destination}",
            f"--diagnostics-dir={diagnostics}",
            "--no-stickplots",
            *(("--preview-only",) if preview else ()),
        )
        result = self.session_factory().run(ExternalCommand(arguments))
        (destination / "R_analysis.log").write_text(result.output, encoding="utf-8")
        if result.returncode:
            raise RuntimeError("RustLab1 R analysis failed:\n" + result.output[-8000:])
        manifest = {
            "backend": "adapted RustLab1 R",
            "recording": view_set.name,
            "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
            "inputs": {
                side: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                for side, path in paths.items()
            },
            "configuration": config,
        }
        (destination / "analysis_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return self._prepared_plots(destination, settings), phase, result.output

    @staticmethod
    def _prepared_plots(destination, settings):
        canonical = pd.read_csv(destination / "diagnostics" / "canonical.csv")
        phases = pd.read_csv(destination / "Stride_detection.csv")
        prepared = []
        for side in ("left", "right"):
            raw = pd.read_csv(destination / "diagnostics" / f"native_{side}.csv")
            mapping = {
                "toe": "toe" if side == "left" else "back_toe",
                "mtp": "MTP",
                "ankle": "ankle",
                "knee": "knee",
                "hip": "hip",
                "iliac crest": "iliac_crest",
            }
            coords = pd.DataFrame(
                {
                    f"{target} {axis}": raw.get(f"{source} {axis}", np.nan)
                    for target, source in mapping.items()
                    for axis in ("x", "y")
                },
                index=raw.index,
            )
            own = phases[phases.parameter.eq("d-back-" + side)].sort_values("source_frame")
            coords.attrs.update(
                view_label=side.title(),
                stride_method=f"Speed GMM | adapted RustLab1 | ALMA Butterworth 5th order, {settings.filter_cutoff:g} Hz",
                timing_source="Independent side-toe Speed GMM cycles; all finite parameter coordinates",
                detection_diagnostics={"trusted": own.trusted.to_numpy(bool)},
            )
            accepted = canonical[canonical.parameter.eq("d-back-" + side)]
            parameters = pd.DataFrame(
                {
                    "stride_start (frame)": accepted.start_frame,
                    "stride_end (frame)": accepted.end_frame_inclusive,
                    "cycle duration (s)": accepted.cycle_duration_seconds,
                }
            )
            plot = prepare_full_recording_stickplot(parameters, coords, ALMA_BODYPARTS, own.phase_names.eq("stance"))
            if plot is None:
                raise RuntimeError(f"No drawable {side} skeleton coordinates from the R analysis.")
            prepared.append((side, plot))
        return prepared

    def run_recording(self, view_set, output_folder, settings):
        name = re.sub(r"[^\w. -]+", "_", view_set.name).strip(". ") or "recording"
        destination = make_session_output_dir(Path(output_folder) / name)
        prepared, phase, _log = self._execute(view_set, destination, settings)
        output_files = [
            destination / name
            for name in (
                "all_raw_data.csv",
                "all_summarized_data.csv",
                "Per_stride_parameters.csv",
                "Stride_detection.csv",
                "run_config.json",
                "analysis_manifest.json",
                "R_analysis.log",
            )
        ]
        for side, plot in prepared:
            svg = destination / f"Stickplot_{side}.svg"
            render_prepared_stickplot(plot, svg)
            output_files.append(svg)
            if settings.generate_figures:
                png = destination / f"Stickplot_{side}.png"
                render_prepared_stickplot(plot, png, output_format="png", dpi=180)
                output_files.append(png)
        if not all(path.is_file() and path.stat().st_size for path in output_files):
            raise RuntimeError("RustLab1 R did not produce all required output artifacts.")
        counts = phase.groupby("parameter").cycle_id.nunique()
        return RustLab1RunResult(
            input_file=view_set.bottom_csv,
            output_files=tuple(output_files),
            messages=(
                f"Adapted RustLab1 R: {counts.get('d-back-left', 0)} left and "
                f"{counts.get('d-back-right', 0)} right complete Speed GMM strides; full 106-row catalog.",
            ),
        )

    def preview(self, view_set, settings):
        with TemporaryDirectory(prefix="rustlab1-r-preview-") as directory:
            prepared, _phase, _log = self._execute(view_set, Path(directory), settings, preview=True)
            plots, messages = [], []
            for side, plot in prepared:
                buffer = BytesIO()
                render_prepared_stickplot(plot, buffer)
                plots.append((f"{side.title()} · stick plot", buffer.getvalue()))
                messages.append(
                    f"{side.title()}: {len(plot.parameters)} complete Speed GMM strides; R-smoothed coordinates."
                )
        return tuple(plots), view_set.name, tuple(messages)
