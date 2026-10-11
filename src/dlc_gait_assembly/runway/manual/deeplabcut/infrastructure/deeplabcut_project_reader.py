"""Inspect project configuration, training metadata, and required model files."""

from __future__ import annotations

from pathlib import Path

import yaml

from dlc_gait_assembly.runway.manual.deeplabcut.business.deeplabcut_project_rules import (
    shuffle_metadata_matches,
    training_dataset_identity,
    validate_project_components,
)

DLC_MODEL_FOLDER_NAMES = ("dlc-models-pytorch", "dlc-models")
DLC_TRAINING_DATASET_FOLDER_NAME = "training-datasets"


def resolve_deeplabcut_config(model_path: str | Path) -> Path:
    """Resolve a saved model file/folder to one unambiguous DLC config.yaml."""
    candidate = Path(model_path).expanduser().resolve()
    if candidate.is_file() and candidate.name.casefold() == "config.yaml":
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


def validate_deeplabcut_project(model_path: str | Path) -> Path:
    """Return the project config after checking that trained inference files exist."""
    config_path = resolve_deeplabcut_config(model_path)
    project_root = config_path.parent
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
        config_path, training_dataset_folder, allow_pytorch=has_pytorch_model, allow_tensorflow=has_tensorflow_model
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
