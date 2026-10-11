"""Validate already-inspected DeepLabCut project metadata and model completeness."""


def training_dataset_identity(config):
    task, date = str(config.get("Task", "")).strip(), str(config.get("date", "")).strip()
    try:
        iteration = int(config.get("iteration", 0))
        fractions = config.get("TrainingFraction")
        if not task or not date or not isinstance(fractions, list) or not fractions:
            return None
        fraction = float(fractions[0])
    except (TypeError, ValueError):
        return None
    return iteration, f"UnaugmentedDataSet_{task}{date}", fraction


def shuffle_metadata_matches(config, metadata, tensorflow_documentation, *, allow_pytorch, allow_tensorflow):
    identity = training_dataset_identity(config)
    if identity is None:
        return False
    expected_fraction = identity[2]
    if metadata is None:
        return allow_tensorflow and tensorflow_documentation
    shuffles = metadata.get("shuffles")
    if not isinstance(shuffles, dict):
        return False
    for shuffle in shuffles.values():
        if not isinstance(shuffle, dict):
            continue
        try:
            fraction_matches = abs(float(shuffle.get("train_fraction")) - expected_fraction) <= 1e-9
            index_matches = int(shuffle.get("index")) == 1
        except (TypeError, ValueError):
            continue
        engine = str(shuffle.get("engine", "")).strip().casefold()
        engine_matches = (allow_pytorch and engine in {"pytorch", "torch"}) or (
            allow_tensorflow and engine in {"tensorflow", "tf"}
        )
        if fraction_matches and index_matches and engine_matches:
            return True
    return False


def validate_project_components(has_pytorch, has_tensorflow, has_shuffle):
    if not has_pytorch and not has_tensorflow:
        raise FileNotFoundError(
            "The selected DeepLabCut project has no complete trained model. Select its config.yaml or project folder with the trained model directory intact."
        )
    if not has_shuffle:
        raise ValueError(
            "The selected DeepLabCut project metadata does not define shuffle 1 for its first TrainingFraction with the trained model engine. Select the original complete project, including its training-datasets directory."
        )
