"""Inspect project configuration, training metadata, and required model files."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from dlc_gait_assembly.runway.manual.deeplabcut.business.deeplabcut_job_contracts import DlcTrainedModel
from dlc_gait_assembly.runway.manual.deeplabcut.business.deeplabcut_project_rules import (
    shuffle_metadata_entries,
    training_dataset_identity,
)
from dlc_gait_assembly.shared.infrastructure.windows_filesystem_paths import windows_filesystem_path

DLC_MODEL_FOLDER_NAMES = ("dlc-models-pytorch", "dlc-models")
DLC_TRAINING_DATASET_FOLDER_NAME = "training-datasets"
SOURCE_PROJECT_FILENAME = "source_project.json"
MODEL_LAYOUTS = (
    ("pytorch", DLC_MODEL_FOLDER_NAMES[0], "pytorch_config.yaml", ("*.pt", "*.pth")),
    ("tensorflow", DLC_MODEL_FOLDER_NAMES[1], "pose_cfg.yaml", ("*.index", "*.h5")),
)


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


def validate_deeplabcut_project(model_path: str | Path, shuffle: int | None = None) -> Path:
    return select_deeplabcut_model(model_path, shuffle).config_path


def select_deeplabcut_model(model_path: str | Path, shuffle: int | None = None) -> DlcTrainedModel:
    choices = deeplabcut_model_choices(model_path)
    for model in choices:
        if shuffle is None or model.shuffle == shuffle:
            return model
    raise ValueError(f'Shuffle {shuffle} is unavailable in "{choices[0].config_path}".')


def deeplabcut_model_choices(model_path: str | Path) -> tuple[DlcTrainedModel, ...]:
    """Return trained models in config fraction order, with shuffle 1 preferred at each fraction."""
    config_path = resolve_deeplabcut_config(model_path)
    config_file = windows_filesystem_path(config_path)
    project_root = config_file.parent
    if not any((project_root / folder).is_dir() for folder in DLC_MODEL_FOLDER_NAMES):
        raise FileNotFoundError(f'No complete trained model was found next to "{config_path}".')

    config = read_project_yaml(config_file)
    identity = training_dataset_identity(config) if isinstance(config, dict) else None
    if identity is None:
        raise ValueError(f'Check Task, date, iteration and TrainingFraction in "{config_path}".')
    iteration, project_name, fractions = identity
    iteration_folder = f"iteration-{iteration}"
    trained = sorted(
        trained_shuffles(project_root, iteration_folder, project_name),
        key=lambda item: (item[1] != 1, item[1]),
    )
    if not trained:
        raise FileNotFoundError(f'No complete trained model for {iteration_folder} was found next to "{config_path}".')

    dataset = project_root / DLC_TRAINING_DATASET_FOLDER_NAME / iteration_folder / f"UnaugmentedDataSet_{project_name}"
    metadata_path = dataset / "metadata.yaml"
    metadata = shuffle_metadata_entries(read_project_yaml(metadata_path)) if metadata_path.is_file() else None
    choices = {}
    for trainingsetindex, fraction in enumerate(fractions):
        for percent, shuffle, engine in trained:
            if percent != int(100 * fraction):
                continue
            if metadata is None:
                documentation = dataset / f"Documentation_data-{config['Task']}_{percent}shuffle{shuffle}.pickle"
                matches = engine == "tensorflow" and documentation.is_file()
            else:
                matches = (fraction, shuffle, engine) in metadata
            if matches:
                # A numbered override uses the first configured fraction that has that trained shuffle.
                choices.setdefault(shuffle, DlcTrainedModel(config_path, iteration, fraction, trainingsetindex, shuffle))

    if choices:
        return tuple(choices.values())
    raise ValueError(
        f'No trained shuffle in "{config_path}" matches the configured TrainingFraction and training metadata. '
        f'Select the original DeepLabCut project or restore "{dataset.relative_to(project_root)}".'
    )


def read_project_yaml(path):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f'Could not read DeepLabCut YAML in "{path}".') from exc


def trained_shuffles(root, iteration_folder, project_name):
    pattern = re.compile(rf"{re.escape(project_name)}-trainset(\d+)shuffle(\d+)")
    for engine, folder, model_config, weight_patterns in MODEL_LAYOUTS:
        for model in (root / folder / iteration_folder).glob("*"):
            match = pattern.fullmatch(model.name)
            train = model / "train"
            if match and (train / model_config).is_file() and any(
                weight.is_file() for glob in weight_patterns for weight in train.glob(glob)
            ):
                percent, shuffle = map(int, match.groups())
                yield percent, shuffle, engine


class DeepLabCutProjectReader:
    select_model = staticmethod(select_deeplabcut_model)
