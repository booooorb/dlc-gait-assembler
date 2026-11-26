"""Inspect project configuration, training metadata, and required model files."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from dlc_gait_assembly.runway.manual.deeplabcut.business.deeplabcut_project_rules import (
    shuffle_metadata_matches,
    training_dataset_identity,
    validate_project_components,
)
from dlc_gait_assembly.shared.infrastructure.windows_filesystem_paths import windows_filesystem_path

DLC_MODEL_FOLDER_NAMES = ("dlc-models-pytorch", "dlc-models")
DLC_TRAINING_DATASET_FOLDER_NAME = "training-datasets"
SOURCE_PROJECT_FILENAME = "source_project.json"


def resolve_deeplabcut_config(model_path: str | Path) -> Path:
    """Resolve a saved model file/folder to one unambiguous DLC config.yaml."""
    candidate = Path(model_path).expanduser().resolve()
    if candidate.is_file() and (candidate.name.casefold() == "config.yaml" or is_refined_config(candidate)):
        return candidate
    if candidate.is_file():
        for parent in candidate.parents:
            config = parent / "config.yaml"
            if config.is_file():
                return config
    search_root = candidate if candidate.is_dir() else candidate.parent
    direct = search_root / "config.yaml"
    if direct.is_file():
        return direct
    configs = sorted(search_root.rglob("config.yaml")) if search_root.exists() else []
    if len(configs) == 1:
        return configs[0]
    if not configs:
        raise FileNotFoundError(f'No DeepLabCut config.yaml was found in "{candidate.name}".')
    raise ValueError(f'"{candidate.name}" contains multiple DeepLabCut projects. Select one project folder.')


def is_refined_config(path):
    return path.name.startswith("config.gait-refinement-") and path.suffix == ".yaml"


def deeplabcut_source_reference(config_path):
    """Retain provenance when copying a trained model, even if its source drive is offline."""
    source_file = config_path.with_name(SOURCE_PROJECT_FILENAME)
    if source_file.is_file():
        return Path(json.loads(source_file.read_text(encoding="utf-8"))["config"])
    if (config_path.parent / "labeled-data").is_dir():
        return config_path
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    project_path = config.get("project_path")
    return Path(project_path) / "config.yaml" if project_path else config_path


def original_deeplabcut_config(config_path):
    origin = deeplabcut_source_reference(config_path)
    if not origin.is_file() or not (origin.parent / "labeled-data").is_dir():
        raise FileNotFoundError(
            f"The original DLC training project is unavailable at {origin.parent}. "
            "Restore the source project or save frame corrections only."
        )
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    candidate = yaml.safe_load(origin.read_text(encoding="utf-8"))
    if any(candidate.get(key) != config.get(key) for key in ("Task", "date", "scorer")):
        raise ValueError(f"The source DLC project at {origin.parent} differs from the Batch Run model.")
    return origin


def validate_deeplabcut_project(model_path: str | Path) -> Path:
    """Return the project config after checking that trained inference files exist."""
    config_path = resolve_deeplabcut_config(model_path)
    config_file = windows_filesystem_path(config_path)
    project_root = config_file.parent
    model_folders = [project_root / name for name in DLC_MODEL_FOLDER_NAMES if (project_root / name).is_dir()]
    has_pytorch_model = any(
        any(folder.rglob("pytorch_config.yaml")) and (any(folder.rglob("*.pt")) or any(folder.rglob("*.pth")))
        for folder in model_folders
    )
    has_tensorflow_model = any(
        any(folder.rglob("pose_cfg.yaml")) and (any(folder.rglob("*.index")) or any(folder.rglob("*.h5")))
        for folder in model_folders
    )
    training_dataset_folder = project_root / DLC_TRAINING_DATASET_FOLDER_NAME
    has_shuffle_metadata = has_deeplabcut_shuffle_metadata(
        config_file, training_dataset_folder, allow_pytorch=has_pytorch_model, allow_tensorflow=has_tensorflow_model
    )
    validate_project_components(has_pytorch_model, has_tensorflow_model, has_shuffle_metadata)
    return config_path


def has_deeplabcut_shuffle_metadata(config_path, training_dataset_folder, *, allow_pytorch, allow_tensorflow):
    if not training_dataset_folder.is_dir():
        return False
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(config, dict):
            return False
        identity = training_dataset_identity(config)
        if identity is None:
            return False
        iteration, name, _fraction = identity
        folder = training_dataset_folder / f"iteration-{iteration}" / name
        metadata_path = folder / "metadata.yaml"
        metadata = (
            (yaml.safe_load(metadata_path.read_text(encoding="utf-8")) or {}) if metadata_path.is_file() else None
        )
        if metadata is not None and not isinstance(metadata, dict):
            return False
        return shuffle_metadata_matches(
            config,
            metadata,
            any(folder.glob("Documentation_data-*.pickle")),
            allow_pytorch=allow_pytorch,
            allow_tensorflow=allow_tensorflow,
        )
    except (OSError, TypeError, yaml.YAMLError):
        return False


class DeepLabCutProjectReader:
    def validate_project(self, path):
        return validate_deeplabcut_project(path)
