"""Persist run manifests and transactionally replace corrected coordinate pairs."""

from __future__ import annotations

import json
import shutil

from dlc_gait_assembly.runway.automatic.review.infrastructure.automatic_label_artifacts import preserve_raw_tracking
from dlc_gait_assembly.runway.automatic.runs.business.automatic_recording_pairing import safe_name
from dlc_gait_assembly.runway.automatic.runs.business.automatic_run_contracts import AutomatedPipelineResult
from dlc_gait_assembly.runway.automatic.runs.infrastructure.automatic_run_checkpoint_store import write_run_json


def reset_knee_replacements(knee_folder):
    """Restore original coordinates if correction was interrupted before its checkpoint."""
    work_folder = knee_folder / "work"
    journal = work_folder / "backups.json"
    if journal.is_file():
        for source, backup in json.loads(journal.read_text(encoding="utf-8")):
            shutil.copy2(backup, source)
    if work_folder.is_dir():
        shutil.rmtree(work_folder)


def persist_knee_replacements(run, pair_jobs, settings, corrected, progress_callback):
    total = max(1, len(pair_jobs))
    knee_output_folder = getattr(run, "knee_correction_folder", run.output_folder / "03_knee_correction")
    work_folder = knee_output_folder / "work"
    prepared = []
    replacement_records = []
    try:
        for index, (region, pair) in enumerate(pair_jobs, start=1):
            result = run.operations.knee.correct_pair(pair, work_folder / safe_name(region), settings)
            if pair.csv_path is None or pair.h5_path is None:
                raise RuntimeError(f"Knee correction lost the coordinate pair for {pair.stem}.")
            if not result.output_csv.is_file() or not result.output_h5.is_file():
                raise RuntimeError(f"Knee correction did not produce both outputs for {pair.stem}.")
            prepared.append((region, pair, result))
            if progress_callback is not None:
                progress_callback(index, total, f"Prepared correction for {pair.stem}")
        backups = []
        backup_folder = work_folder / "backups"
        backup_folder.mkdir(parents=True, exist_ok=True)
        for index, (_region, pair, _result) in enumerate(prepared, start=1):
            backup_csv = backup_folder / f"{index:04d}.csv"
            backup_h5 = backup_folder / f"{index:04d}.h5"
            shutil.copy2(pair.csv_path, backup_csv)
            shutil.copy2(pair.h5_path, backup_h5)
            preserve_raw_tracking(pair.h5_path)
            backups.extend(((pair.csv_path, backup_csv), (pair.h5_path, backup_h5)))
        write_run_json(work_folder / "backups.json", backups)
        for region, pair, result in prepared:
            result.output_csv.replace(pair.csv_path)
            result.output_h5.replace(pair.h5_path)
            corrected.setdefault(region, []).append(pair.csv_path)
            replacement_records.append(
                {
                    "region": region,
                    "video": str(pair.video_path) if pair.video_path is not None else "",
                    "csv": str(pair.csv_path),
                    "h5": str(pair.h5_path),
                }
            )
        write_run_json(knee_output_folder / "correction_manifest.json", {"replaced_coordinates": replacement_records})
    except Exception:
        reset_knee_replacements(knee_output_folder)
        raise
    return corrected


def persist_run_manifest(run, result: AutomatedPipelineResult) -> None:
    folders = {
        "processed_videos": run.processed_videos_folder,
        "analyzed_videos": run.analyzed_videos_folder,
        "labeled_videos": run.labeled_videos_folder,
        "knee_correction": run.knee_correction_folder,
        "stickplots": run.stickplots_folder,
        "gait_analysis": run.gait_analysis_folder,
    }
    artifacts = {
        "processed_videos": result.processed_videos,
        "coordinate_csvs": result.coordinate_csvs,
        "labeled_videos": result.labeled_videos,
        "stickplots": result.stickplots,
        "gait_analysis": result.analysis_outputs,
    }
    payload = {
        "profile": {"id": run.profile.id, "name": run.profile.name},
        "labeled_video_confidence": run.profile.labeled_video_confidence,
        "fine_tune_epochs": run.profile.fine_tune_epochs,
        "deeplabcut_models": run.profile.deeplabcut_models,
        "corrected_frame_count": len({edit.key[:3] for edit in run.label_edits}),
        "output_folder": str(run.output_folder),
        "folders": {name: str(path) for (name, path) in folders.items()},
        "artifacts": {name: [str(path) for path in paths] for (name, paths) in artifacts.items()},
    }
    write_run_json(result.output_manifest, payload)
