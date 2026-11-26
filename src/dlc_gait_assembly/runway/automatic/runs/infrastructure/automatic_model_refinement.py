"""Dispatch fine-tuning through the existing external DLC runtime for each source project."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QLockFile

from dlc_gait_assembly.runway.automatic.review.business.automatic_label_correction import marker_columns
from dlc_gait_assembly.runway.automatic.review.infrastructure.automatic_label_artifacts import load_label_artifacts
from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure.deeplabcut_bridge_client import run_bridge_request
from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure.deeplabcut_project_reader import (
    original_deeplabcut_config,
    select_deeplabcut_model,
    validate_deeplabcut_project,
)
from dlc_gait_assembly.shared.business.execution_feedback_contracts import ExecutionProgress


def fine_tune_models(sources, edits, epochs, revision, progress):
    by_recording = defaultdict(list)
    for edit in edits:
        by_recording[edit.region, edit.video].append(edit)

    projects = {}
    region_sources = {source.region: source for source in sources}
    for source in sources:
        updates = by_recording.get((source.region, source.video))
        if not updates:
            continue
        model = select_deeplabcut_model(source.model, source.shuffle)
        _table, raw, offset = load_label_artifacts(source)
        labels = marker_columns(raw)
        updates = [edit for edit in updates if edit.marker in labels]
        if not updates:
            continue
        origin = original_deeplabcut_config(model.config_path)
        scorer = str(raw.columns.get_level_values(0)[0])
        # Different region entries may share one original project and snapshot.
        project = projects.setdefault(
            (origin.parent, model.training_identity, scorer),
            {"model": model, "origin": origin, "recordings": [], "regions": set()},
        )
        project["recordings"].append(
            {
                "video": str(source.video),
                "offset": offset,
                "edits": [{**asdict(edit), "video": str(edit.video)} for edit in updates],
            }
        )
        project["regions"].add(source.region)
    if not projects:
        raise ValueError("Place a visible marker from the model on a frame before fine-tuning.")

    models = {}
    for index, ((root, model_identity, scorer), project) in enumerate(projects.items()):
        lock = QLockFile(str(root / ".gait-refinement.lock"))
        lock.setStaleLockTime(0)
        if not lock.tryLock(0):
            raise RuntimeError(f"Another run is fine-tuning {root.name}, or the original project is read-only.")
        try:
            model = project["model"]

            def report(current, total, message, project_index=index, name=root.name):
                overall = (project_index + current / max(1, total)) / len(projects)
                progress(round(1000 * overall), 1000, f"{name} · {message}")

            result = run_bridge_request(
                {
                    "id": f"{revision}-{index + 1}",
                    "epochs": epochs,
                    "scorer": scorer,
                    "used_config": str(model.config_path),
                    "shuffle": model.shuffle,
                    "trainingsetindex": model.trainingsetindex,
                    "engine_override": model.engine_override,
                    "source_config": str(project["origin"]),
                    "recordings": project["recordings"],
                },
                1,
                "training",
                f"Preparing training frames for {root.name}",
                f"DeepLabCut fine-tuning for {root.name}",
                ExecutionProgress(report, progress.checkpoint) if progress is not None else None,
                script_name="deeplabcut_refinement_entry.py",
            )
            tuned = Path(result["config"])
            validate_deeplabcut_project(tuned)
            for source in region_sources.values():
                if source.region in models or source.region in project["regions"]:
                    continue
                try:
                    other_model = select_deeplabcut_model(source.model, source.shuffle)
                    if original_deeplabcut_config(other_model.config_path).parent != root:
                        continue
                    if model_identity != other_model.training_identity:
                        continue
                except (OSError, ValueError):
                    continue
                _table, raw, _offset = load_label_artifacts(source)
                if str(raw.columns.get_level_values(0)[0]) == scorer:
                    models[source.region] = tuned
            models.update(dict.fromkeys(project["regions"], tuned))
        finally:
            lock.unlock()
    return models
