"""Add reviewed labels to their native DLC project and fine-tune in an isolated iteration."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from ruamel.yaml import YAML


def write_config(path, config):
    temporary = path.with_suffix(".tmp")
    YAML().dump(config, temporary)
    temporary.replace(path)


def copy_media(source, destination):
    if not destination.is_file():
        temporary = destination.with_suffix(".tmp")
        temporary.unlink(missing_ok=True)
        try:
            try:
                os.link(source, temporary)
            except OSError:
                shutil.copy2(source, temporary)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)


def add_label_group(root, config, recording):
    video = Path(recording["video"])
    token = hashlib.sha256(str(video.resolve()).encode()).hexdigest()[:16]
    video_copy = root / "videos" / f"gait-refinement-{token}{video.suffix}"
    label_folder = root / "labeled-data" / video_copy.stem
    label_folder.mkdir(parents=True, exist_ok=True)
    video_copy.parent.mkdir(exist_ok=True)

    scorer = config["scorer"]
    columns = pd.MultiIndex.from_product(
        [[scorer], config["bodyparts"], ["x", "y"]], names=["scorer", "bodyparts", "coords"]
    )
    h5_path = label_folder / f"CollectedData_{scorer}.h5"
    csv_path = label_folder / f"CollectedData_{scorer}.csv"
    # Use the human labels already published for this recording when revisiting a frame.
    existing = pd.read_hdf(h5_path) if h5_path.is_file() else None
    by_frame = defaultdict(list)
    for edit in recording["edits"]:
        if len(edit["marker"]) == 1 and edit["marker"][0] in config["bodyparts"]:
            by_frame[edit["frame"]].append(edit)

    crop_offset = recording["offset"]
    rows = {}
    capture = cv2.VideoCapture(str(video))
    try:
        if not capture.isOpened():
            raise OSError(f"Could not open the processed video {video}.")
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        for frame, edits in sorted(by_frame.items()):
            name = f"img{frame:08d}.png"
            key = ("labeled-data", video_copy.stem, name)
            row = (
                existing.loc[key].reindex(columns).copy()
                if existing is not None and key in existing.index
                else (pd.Series(np.nan, index=columns))
            )
            for edit in edits:
                point = edit["point"]
                x, y = (np.nan, np.nan) if point is None else (point[0] + crop_offset[0], point[1] + crop_offset[1])
                if point is not None and not (0 <= x < width and 0 <= y < height):
                    raise ValueError(f"Frame {frame + 1} of {video.name} has a label outside the image.")
                marker = edit["marker"][0]
                row.loc[(scorer, marker, "x")] = x
                row.loc[(scorer, marker, "y")] = y
            if row.notna().any():
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame)
                success, image = capture.read()
                if not success or not cv2.imwrite(str(label_folder / name), image):
                    raise OSError(f"Could not save frame {frame + 1} from {video.name}.")
            rows[key] = row
    finally:
        capture.release()

    if not rows:
        return set()
    corrections = pd.DataFrame.from_dict(rows, orient="index", columns=columns)
    corrections.index = pd.MultiIndex.from_tuples(corrections.index)
    if existing is not None:
        corrections = pd.concat([existing.loc[~existing.index.isin(corrections.index)], corrections])
    corrections = corrections.dropna(how="all").sort_index()
    if not corrections.empty:
        copy_media(video, video_copy)
        config.setdefault("video_sets", {})[str(video_copy)] = {"crop": f"0, {width}, 0, {height}"}

    temp_h5 = h5_path.with_suffix(".tmp.h5")
    temp_csv = csv_path.with_suffix(".tmp.csv")
    corrections.to_hdf(temp_h5, key="df_with_missing", mode="w")
    corrections.to_csv(temp_csv)
    temp_h5.replace(h5_path)
    temp_csv.replace(csv_path)
    return set(rows) & set(corrections.index)


def snapshot_for_recording(loader, scorer):
    from deeplabcut.pose_estimation_pytorch.apis.utils import get_model_snapshots
    from deeplabcut.pose_estimation_pytorch.task import Task

    snapshots = get_model_snapshots("all", loader.model_folder, loader.pose_task)
    detectors = (
        get_model_snapshots("all", loader.model_folder, Task.DETECT) if loader.pose_task == Task.TOP_DOWN else [None]
    )
    for snapshot in snapshots:
        for detector in detectors:
            if loader.scorer(snapshot, detector) == scorer:
                return snapshot, detector
    raise ValueError(f"The checkpoint used for {scorer} is missing from the saved Batch Run model.")


def next_iteration(root, base):
    used = {base}
    for folder in ("training-datasets", "dlc-models", "dlc-models-pytorch"):
        for path in (root / folder).glob("iteration-*"):
            value = path.name.removeprefix("iteration-")
            if value.isdecimal():
                used.add(int(value))
    return max(used) + 1


def split_frames(annotations, reviewed, fraction, previous_test):
    tracked = [index for index, key in enumerate(annotations.index) if key in reviewed]
    if not tracked:
        raise ValueError("Add at least one visible model label to fine-tune this project.")
    test = [index for index, key in enumerate(annotations.index) if key in previous_test and key not in reviewed]
    if not test:
        # Keep newly reviewed frames in training, even when the source split is unavailable.
        pool = [index for index, key in enumerate(annotations.index) if key not in reviewed]
        count = min(len(pool), max(1, round(len(annotations) * (1 - fraction))))
        test = sorted(np.random.default_rng(0).choice(pool, count, replace=False).tolist())
    if not test:
        raise ValueError("The original DLC project needs at least one labeled frame for validation.")
    train = sorted(set(range(len(annotations))) - set(test))
    return train, test, round(len(train) / len(annotations), 2)


def refine(request):
    import deeplabcut
    import torch
    from deeplabcut.generate_training_dataset.metadata import get_shuffle_engine
    from deeplabcut.generate_training_dataset.trainingsetmanipulation import merge_annotateddatasets
    from deeplabcut.pose_estimation_pytorch.data.dlcloader import DLCLoader
    from deeplabcut.utils import auxiliaryfunctions

    used_config = Path(request["used_config"])
    root = Path(request["source_config"]).parent
    project_config = root / "config.yaml"
    base = auxiliaryfunctions.read_config(str(used_config))
    shuffle = request.get("shuffle", 1)
    trainingsetindex = request.get("trainingsetindex", 0)
    engine = get_shuffle_engine(base, trainingsetindex, shuffle)
    if engine != deeplabcut.Engine.PYTORCH or base.get("multianimalproject", False):
        raise ValueError("Fine-tuning requires a single-animal DeepLabCut 3 PyTorch project.")
    original = auxiliaryfunctions.read_config(str(project_config))
    for name in ("Task", "date", "scorer", "bodyparts"):
        if base[name] != original[name]:
            raise ValueError(f"The source DLC project's {name} differs from the Batch Run model.")
    if not (root / "labeled-data").is_dir():
        raise FileNotFoundError(f"The source DLC training labels are missing in {root}.")

    loader = DLCLoader(str(used_config), trainset_index=trainingsetindex, shuffle=shuffle)
    snapshot, detector = snapshot_for_recording(loader, request["scorer"])
    # The completion marker is written only after a new checkpoint can be selected for inference.
    tuned = root / f"config.gait-refinement-{request['id']}.yaml"
    completed = tuned.with_suffix(".complete.json")
    if completed.is_file():
        return tuned

    reviewed = set()
    for recording in request["recordings"]:
        reviewed.update(add_label_group(root, original, recording))
    if not reviewed:
        raise ValueError("Place a visible marker from the model on a frame before fine-tuning.")
    write_config(project_config, original)

    previous_test = set()
    old_cfg = {**base, "project_path": str(root)}
    old_folder = root / auxiliaryfunctions.get_training_set_folder(old_cfg)
    if (old_folder / f"CollectedData_{base['scorer']}.h5").is_file():
        try:
            previous_test.update(DLCLoader(old_cfg, trainset_index=trainingsetindex, shuffle=shuffle).df_test.index)
        except (KeyError, OSError, ValueError):
            pass

    settings = {
        **base,
        "project_path": str(root),
        "video_sets": original["video_sets"],
        "iteration": next_iteration(root, base["iteration"]),
        "snapshotindex": -1,
        "detector_snapshotindex": -1,
    }
    dataset_folder = root / auxiliaryfunctions.get_training_set_folder(settings)
    dataset_folder.mkdir(parents=True)
    annotations = merge_annotateddatasets(settings, str(dataset_folder))
    if annotations is None or annotations.empty:
        raise ValueError("DeepLabCut could not read the original training annotations.")
    train, test, fraction = split_frames(annotations, reviewed, loader.train_fraction, previous_test)
    settings["TrainingFraction"] = [fraction]
    write_config(tuned, settings)
    deeplabcut.create_training_dataset(
        str(tuned),
        Shuffles=[shuffle],
        userfeedback=False,
        trainIndices=[train],
        testIndices=[test],
        net_type=loader.model_cfg["net_type"],
        engine=deeplabcut.Engine.PYTORCH,
    )

    new_loader = DLCLoader(str(tuned), shuffle=shuffle)
    model_cfg = loader.model_cfg.copy()
    model_cfg["train_settings"] = {**model_cfg["train_settings"]}
    model_cfg["train_settings"].pop("weight_init", None)
    model_cfg.pop("resume_training_from", None)
    model_cfg.pop("logger", None)
    write_config(new_loader.model_config_path, model_cfg)
    if detector is not None:
        copy_media(detector.path, new_loader.model_folder / detector.path.name)
    epochs = request["epochs"]
    # A full DLC snapshot carries a starting epoch and can carry optimizer state.
    # Seed the new training run with weights only so the requested epochs are additional.
    weights = torch.load(snapshot.path, map_location="cpu", weights_only=True)
    seed = new_loader.model_folder / ".gait-refinement-seed.pth"
    torch.save({"model": weights["model"]}, seed)
    try:
        deeplabcut.train_network(
            str(tuned),
            shuffle=shuffle,
            engine=deeplabcut.Engine.PYTORCH,
            epochs=epochs,
            save_epochs=epochs,
            max_snapshots_to_keep=2,
            snapshot_path=seed,
            keepdeconvweights=True,
            detector_epochs=0,
        )
    finally:
        seed.unlink(missing_ok=True)

    from deeplabcut.pose_estimation_pytorch.apis.utils import get_model_snapshots

    trained = get_model_snapshots(-1, new_loader.model_folder, new_loader.pose_task)[0]
    completed.write_text(json.dumps({"snapshot": str(trained.path)}), encoding="utf-8")
    return tuned


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-request", type=Path, required=True)
    request = json.loads(parser.parse_args().run_request.read_text(encoding="utf-8"))
    tuned = refine(request)
    Path(request["result_path"]).write_text(json.dumps({"config": str(tuned)}), encoding="utf-8")


if __name__ == "__main__":
    main()
