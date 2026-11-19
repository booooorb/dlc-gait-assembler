"""Store automatic run checkpoints and index them alongside historical outputs."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from dlc_gait_assembly.runway.automatic.business.automatic_stage_definitions import AutomatedStage
from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_contracts import AutomatedPipelineProfile
from dlc_gait_assembly.runway.automatic.profiles.infrastructure.automatic_profile_asset_store import (
    copy_profile_deeplabcut_project,
)
from dlc_gait_assembly.runway.automatic.runs.business.automatic_run_contracts import SavedAutomaticRun
from dlc_gait_assembly.runway.manual.deeplabcut.business.deeplabcut_job_contracts import DlcAnalysisResult
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_contracts import AlmaRunResult
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_settings_manifest_store import (
    write_analysis_manifest,
)

CHECKPOINT_NAME = "run_checkpoint.json"
PROFILE_MANIFESTS = ("processing_manifest", "calibration_map", "analysis_manifest", "knee_manifest")


def write_run_json(path, payload):
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def snapshot_run_profile(run, profile):
    assets = run.output_folder / "settings"
    assets.mkdir()
    manifests = {}
    for name in PROFILE_MANIFESTS:
        source = getattr(profile, name)
        if source is not None and Path(source).is_file():
            destination = assets / f"{name}{Path(source).suffix}"
            if name == "analysis_manifest" and run.gait_settings is not None:
                write_analysis_manifest(destination, run.gait_settings)
            else:
                shutil.copy2(source, destination)
            manifests[name] = destination
    models = {}
    for index, (region, source) in enumerate(profile.deeplabcut_models.items(), start=1):
        source = Path(source).expanduser().resolve()
        # Workflow-owned models can be replaced or removed as the user edits profiles.
        if source.is_dir() and (source.parent.parent / "profile.json").is_file():
            source = copy_profile_deeplabcut_project(source, assets / f"model_{index:02d}", reuse_owned_files=True)
        models[region] = source
    return replace(profile, workspace_state={}, deeplabcut_models=models, **manifests)


def persist_run_checkpoint(run):
    payload = {
        "version": 1,
        "profile": asdict(run.profile),
        "video_paths": run.video_paths,
        "enable_knee_correction": run.enable_knee_correction,
        "enable_gait_analysis": run.enable_gait_analysis,
        "status": run.status,
        "stage": run.current_stage,
        "message": "",
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "completed_stages": sorted(run.completed_stages),
        "approved_reviews": sorted(run.approved_reviews),
        "processed_sources": run.processed_sources,
        "dlc_results": [asdict(result) for result in run.dlc_results],
        "analysis_csvs_by_region": run.analysis_csvs_by_region,
        "stickplot_results": [asdict(result) for result in run.stickplot_results],
        "gait_results": [asdict(result) for result in run.gait_results],
    }
    write_run_json(run.output_folder / CHECKPOINT_NAME, payload)


def read_run_checkpoint(folder):
    data = json.loads((folder / CHECKPOINT_NAME).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("Unsupported automatic run checkpoint.")
    return data


def record_run_interruption(run, status, message):
    path = run.output_folder / CHECKPOINT_NAME
    data = read_run_checkpoint(run.output_folder)
    if data["status"] != "complete":
        data.update(
            status=status, message=message, updated_at=datetime.now().astimezone().isoformat(timespec="seconds")
        )
        write_run_json(path, data)


def restore_run_checkpoint(run):
    data = read_run_checkpoint(run.output_folder)
    profile = data["profile"]
    for name in PROFILE_MANIFESTS:
        profile[name] = Path(profile[name]) if profile[name] is not None else None
    profile["deeplabcut_models"] = {region: Path(model) for region, model in profile["deeplabcut_models"].items()}
    run.profile = AutomatedPipelineProfile(**profile)
    run.video_paths = tuple(map(Path, data["video_paths"]))
    run.enable_knee_correction = data["enable_knee_correction"]
    run.enable_gait_analysis = data["enable_gait_analysis"]
    run.status = data["status"]
    run.current_stage = data["stage"]
    run.completed_stages.update(AutomatedStage(stage) for stage in data["completed_stages"])
    run.approved_reviews.update(AutomatedStage(stage) for stage in data["approved_reviews"])
    run.processed_sources = {
        int(index): {region: list(map(Path, paths)) for region, paths in outputs.items()}
        for index, outputs in data["processed_sources"].items()
    }
    run.analysis_csvs_by_region = {
        region: list(map(Path, paths)) for region, paths in data["analysis_csvs_by_region"].items()
    }
    run.dlc_results = [
        DlcAnalysisResult(
            item["region"],
            tuple(map(Path, item["video_paths"])),
            tuple(map(Path, item["csv_paths"])),
            tuple(map(Path, item["h5_paths"])),
            tuple(map(Path, item["labeled_video_paths"])),
        )
        for item in data["dlc_results"]
    ]
    for name in ("stickplot_results", "gait_results"):
        setattr(
            run,
            name,
            [
                AlmaRunResult(Path(item["input_file"]), tuple(map(Path, item["output_files"])), tuple(item["messages"]))
                for item in data[name]
            ],
        )


def list_saved_automatic_runs(root):
    root = Path(root)
    runs = []
    for folder in root.iterdir() if root.is_dir() else ():
        if not folder.is_dir():
            continue
        checkpoint = folder / CHECKPOINT_NAME
        try:
            if checkpoint.is_file():
                data = read_run_checkpoint(folder)
                datetime.fromisoformat(data["updated_at"])
                runs.append(
                    SavedAutomaticRun(
                        folder,
                        data["profile"]["name"],
                        data["status"],
                        data["stage"],
                        data["updated_at"],
                        len(data["video_paths"]),
                        data["message"],
                    )
                )
            elif (manifest := folder / "run_manifest.json").is_file():
                data = json.loads(manifest.read_text(encoding="utf-8"))
                updated_at = datetime.fromtimestamp(manifest.stat().st_mtime).astimezone().isoformat(timespec="seconds")
                runs.append(SavedAutomaticRun(folder, data["profile"]["name"], "complete", -1, updated_at, 0))
            elif (folder / "01_processed_videos").is_dir():
                updated_at = datetime.fromtimestamp(folder.stat().st_mtime).astimezone().isoformat(timespec="seconds")
                runs.append(SavedAutomaticRun(folder, folder.name, "outputs_only", -1, updated_at, 0))
        except (OSError, ValueError, TypeError, KeyError):
            continue
    return sorted(runs, key=lambda run: datetime.fromisoformat(run.updated_at).timestamp(), reverse=True)
