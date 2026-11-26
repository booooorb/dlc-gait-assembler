"""Provide the run coordinator with concrete manifest and output storage adapters."""

import shutil
from pathlib import Path
from uuid import uuid4

from dlc_gait_assembly.runway.automatic.business.automatic_stage_definitions import AutomatedStage
from dlc_gait_assembly.runway.automatic.review.infrastructure.automatic_label_artifacts import apply_label_edits
from dlc_gait_assembly.runway.automatic.runs.infrastructure.automatic_run_checkpoint_store import (
    persist_run_checkpoint,
    record_run_interruption,
    restore_run_checkpoint,
    snapshot_run_profile,
)
from dlc_gait_assembly.runway.automatic.runs.infrastructure.automatic_run_manifest_store import (
    persist_knee_replacements,
    persist_run_manifest,
    reset_knee_replacements,
)
from dlc_gait_assembly.runway.automatic.runs.infrastructure.automatic_run_output_layout import (
    allocate_run_output,
    attach_run_output,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_calibration import settings_for_view
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_calibration_loader import (
    resolve_calibration_settings,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_settings_manifest_store import (
    alma_settings_from_manifest,
)
from dlc_gait_assembly.runway.manual.knee_correction.infrastructure.knee_settings_manifest_store import (
    knee_settings_from_manifest,
)
from dlc_gait_assembly.runway.manual.video_processing.infrastructure.video_settings_manifest_store import (
    video_settings_from_manifest,
)
from dlc_gait_assembly.shared.infrastructure.windows_filesystem_paths import windows_filesystem_path


class AutomaticRunStorage:
    allocate = staticmethod(allocate_run_output)
    attach = staticmethod(attach_run_output)
    snapshot_profile = staticmethod(snapshot_run_profile)
    write_checkpoint = staticmethod(persist_run_checkpoint)
    restore_checkpoint = staticmethod(restore_run_checkpoint)
    record_interruption = staticmethod(record_run_interruption)
    video_settings = staticmethod(video_settings_from_manifest)
    knee_settings = staticmethod(knee_settings_from_manifest)

    def gait_settings(self, manifest, calibration):
        settings = resolve_calibration_settings(alma_settings_from_manifest(manifest, calibration))
        if settings.calibration_method == "per_view":
            for view in ("left", "right"):
                settings_for_view(settings, view)
        return settings

    apply_label_edits = staticmethod(apply_label_edits)
    persist_knee_replacements = staticmethod(persist_knee_replacements)
    write_manifest = staticmethod(persist_run_manifest)

    def is_file(self, path):
        return windows_filesystem_path(Path(path)).is_file()

    def resolve_video_paths(self, paths):
        return tuple(Path(path).expanduser().resolve() for path in paths)

    def reset_stage_outputs(self, run, stage):
        if stage is AutomatedStage.KNEE_CORRECTION:
            reset_knee_replacements(run.knee_correction_folder)
        folders = (
            run.processed_videos_folder,
            run.analyzed_videos_folder,
            run.knee_correction_folder,
            run.labeled_videos_folder,
            run.stickplots_folder,
            run.gait_analysis_folder,
        )
        run_folder = run.output_folder
        if stage in (
            AutomatedStage.DEEPLABCUT_ANALYSIS, AutomatedStage.LABELED_VIDEOS,
            AutomatedStage.STICKPLOT, AutomatedStage.GAIT_ANALYSIS,
        ):
            run_folder = windows_filesystem_path(run_folder)
        folder = run_folder / folders[stage].relative_to(run.output_folder)
        partial_paths = list(folder.iterdir())
        if stage is AutomatedStage.VIDEO_PROCESSING:
            saved = {path for paths in run.processed_by_region.values() for path in paths}
            partial_paths = [path for path in folder.rglob("*") if path.is_file() and path not in saved]
        if stage is AutomatedStage.LABELED_VIDEOS:
            # DLC renders beside its coordinate files before the bridge moves the videos.
            analyzed_folder = run_folder / run.analyzed_videos_folder.relative_to(run.output_folder)
            partial_paths.extend(
                path
                for path in analyzed_folder.rglob("*")
                if path.is_file()
                and path.suffix.casefold() in {".mp4", ".avi", ".mov", ".mkv"}
                and "label" in path.stem.casefold()
            )
        if partial_paths:
            archive = run_folder / ".partial" / f"{stage.name.lower()}_{uuid4().hex[:8]}"
            for path in partial_paths:
                destination = archive / path.relative_to(run_folder)
                destination.parent.mkdir(parents=True, exist_ok=True)
                path.replace(destination)

    def discard_knee_backups(self, run):
        shutil.rmtree(run.knee_correction_folder / "work", ignore_errors=True)
