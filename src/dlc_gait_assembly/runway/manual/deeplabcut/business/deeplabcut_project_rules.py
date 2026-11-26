"""Identify DeepLabCut training datasets and interpret their shuffle metadata."""

import math


def training_dataset_identity(config):
    # DeepLabCut uses the original Task and date strings in model and dataset folder names.
    task, date = str(config.get("Task", "")), str(config.get("date", ""))
    try:
        iteration = int(config.get("iteration", 0))
        fractions = config.get("TrainingFraction")
        if not task.strip() or not date.strip() or not isinstance(fractions, list) or not fractions:
            return None
        fractions = tuple(float(fraction) for fraction in fractions)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(fraction) for fraction in fractions):
        return None
    return iteration, f"{task}{date}", fractions


def shuffle_metadata_entries(metadata):
    shuffles = metadata.get("shuffles") if isinstance(metadata, dict) else None
    if not isinstance(shuffles, dict):
        return set()
    engines = {"pytorch": "pytorch", "torch": "pytorch", "tensorflow": "tensorflow", "tf": "tensorflow"}
    entries = set()
    for shuffle in shuffles.values():
        if not isinstance(shuffle, dict):
            continue
        try:
            fraction = float(shuffle.get("train_fraction"))
            index = int(shuffle.get("index"))
        except (TypeError, ValueError):
            continue
        engine = engines.get(str(shuffle.get("engine", "")).strip().casefold())
        if engine is not None:
            entries.add((fraction, index, engine))
    return entries
