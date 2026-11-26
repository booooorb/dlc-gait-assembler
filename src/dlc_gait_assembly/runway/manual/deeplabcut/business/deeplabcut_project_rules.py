"""Identify DeepLabCut training datasets and interpret their shuffle metadata."""

def training_dataset_identity(config):
    # DeepLabCut uses the original Task and date strings in model and dataset folder names.
    task, date = str(config.get("Task", "")), str(config.get("date", ""))
    try:
        iteration = int(config.get("iteration", 0))
        fractions = config.get("TrainingFraction")
        if not task.strip() or not date.strip() or not isinstance(fractions, list) or not fractions:
            return None
        fractions = tuple(float(fraction) for fraction in fractions)
    except (OverflowError, TypeError, ValueError):
        return None
    if not all(0 < fraction <= 1 for fraction in fractions):
        return None
    return iteration, f"{task}{date}", fractions


def shuffle_metadata_entries(metadata):
    shuffles = metadata.get("shuffles") if isinstance(metadata, dict) else None
    if not isinstance(shuffles, dict):
        return {}
    engines = {"pytorch": "pytorch", "torch": "pytorch", "tensorflow": "tensorflow", "tf": "tensorflow"}
    entries = {}
    for shuffle in shuffles.values():
        if not isinstance(shuffle, dict):
            return {}
        fraction = shuffle.get("train_fraction")
        index = shuffle.get("index")
        engine = engines.get(str(shuffle.get("engine", "")).casefold())
        # DeepLabCut reads the whole metadata file and compares these values without coercion.
        if type(fraction) not in (int, float) or not 0 < fraction <= 1 or type(index) is not int or engine is None:
            return {}
        if (fraction, index) in entries:
            return {}
        entries[fraction, index] = engine
    return entries
